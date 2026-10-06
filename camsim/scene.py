"""Scene = car + cameras + target objects, and every visibility computation."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass

import numpy as np

from .camera import Camera
from .car import CarSpec, build_car
from .geometry import ConvexPart, box_vertices, rot_z, segment_blocked


@dataclass
class TargetObject:
    name: str = "object"
    kind: str = "Pedestrian"
    x: float = 5.0
    y: float = 0.0
    z: float = 0.0            # height of the object's base above the ground
    yaw: float = 0.0
    length: float = 0.6
    width: float = 0.6
    height: float = 1.75
    color: str = "#e377c2"

    @property
    def center(self) -> np.ndarray:
        return np.array([self.x, self.y, self.z + self.height / 2])

    @property
    def size(self):
        return self.length, self.width, self.height

    def corners(self) -> np.ndarray:
        return box_vertices(self.center, self.size, self.yaw)

    def part(self) -> ConvexPart:
        return ConvexPart(self.corners(), self.name, self.color)

    def sample_points(self, n: int = 4) -> np.ndarray:
        """n x n x n lattice spanning the box (corners included)."""
        g = np.linspace(-0.5, 0.5, n)
        gx, gy, gz = np.meshgrid(g * self.length, g * self.width, g * self.height,
                                 indexing="ij")
        local = np.stack([gx.ravel(), gy.ravel(), gz.ravel()], axis=1)
        return local @ rot_z(np.radians(self.yaw)).T + self.center

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TargetObject":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class CameraHit:
    visible: bool          # at least one sample point seen
    fraction: float        # share of sample points seen (0..1)
    in_fov_fraction: float # share inside the frustum, ignoring occlusion
    distance: float        # camera -> object centre (m)
    px_width: float        # bounding box of the seen samples, real pixels
    px_height: float


class Scene:
    # Points this close inside a car part make the camera count as "inside"
    # it (e.g. behind the windshield) - that part is then treated as glass.
    INSIDE_MARGIN = 0.02

    def __init__(self, car_spec: CarSpec | None = None):
        self.car_spec, self.car_parts = build_car(car_spec)
        self.cameras: list[Camera] = []
        self.objects: list[TargetObject] = []
        self.objects_occlude = True

    # ------------------------------------------------------------ occluders
    def mounted_inside(self, cam: Camera) -> list[str]:
        """Car parts the camera sits inside, i.e. it looks through their glass."""
        return [p.name for p in self.car_parts
                if p.contains(cam.position, self.INSIDE_MARGIN)[0]]

    def occluders(self, cam: Camera, exclude: TargetObject | None = None,
                  use_objects: bool | None = None):
        inside = self.mounted_inside(cam)
        parts = [p for p in self.car_parts if p.occluder and p.name not in inside]
        if use_objects is None:
            use_objects = self.objects_occlude
        if use_objects:
            parts += [o.part() for o in self.objects if o is not exclude]
        return parts

    def visible_mask(self, cam: Camera, points: np.ndarray,
                     exclude: TargetObject | None = None,
                     use_objects: bool | None = None):
        """(seen, in_fov, u, v) for vehicle-frame points as seen by `cam`."""
        points = np.atleast_2d(points)
        u, v, _, in_fov = cam.project(points)
        seen = in_fov.copy()
        if seen.any():
            idx = np.flatnonzero(seen)
            blocked = np.zeros(idx.size, bool)
            for part in self.occluders(cam, exclude, use_objects):
                todo = ~blocked
                if not todo.any():
                    break
                blocked[todo] = segment_blocked(part, cam.position, points[idx[todo]])
            seen[idx[blocked]] = False
        return seen, in_fov, u, v

    # ------------------------------------------------------ object analysis
    def object_visibility(self, obj: TargetObject, samples: int = 4):
        pts = obj.sample_points(samples)
        result: dict[str, CameraHit] = {}
        for cam in self.cameras:
            if not cam.enabled:
                continue
            seen, in_fov, u, v = self.visible_mask(cam, pts, exclude=obj)
            if seen.any():
                pw = float(u[seen].max() - u[seen].min())
                ph = float(v[seen].max() - v[seen].min())
            else:
                pw = ph = 0.0
            result[cam.name] = CameraHit(
                visible=bool(seen.any()), fraction=float(seen.mean()),
                in_fov_fraction=float(in_fov.mean()),
                distance=float(np.linalg.norm(obj.center - cam.position)),
                px_width=pw, px_height=ph)
        return result

    # ------------------------------------------------------------- coverage
    def coverage_grid(self, extent: float = 20.0, resolution: float = 0.25,
                      height: float = 0.0, use_objects: bool = False):
        """Number of cameras seeing each point of a horizontal grid.

        Returns (xs, ys, count) with count[j, i] for point (xs[i], ys[j]);
        points under/inside the car are NaN. With `use_objects` the target
        objects cast shadows into the map.
        """
        xs = np.arange(-extent, extent + 1e-9, resolution)
        ys = np.arange(-extent, extent + 1e-9, resolution)
        gx, gy = np.meshgrid(xs, ys)
        pts = np.stack([gx.ravel(), gy.ravel(), np.full(gx.size, height)], 1)
        count = np.zeros(pts.shape[0])
        for cam in self.cameras:
            if cam.enabled:
                count += self.visible_mask(cam, pts, use_objects=use_objects)[0]
        s = self.car_spec
        under_car = (np.abs(pts[:, 0]) <= s.length / 2) & (np.abs(pts[:, 1]) <= s.width / 2)
        count[under_car] = np.nan
        return xs, ys, count.reshape(gx.shape)

    def coverage_stats(self, xs, ys, count, radius: float):
        gx, gy = np.meshgrid(xs, ys)
        s = self.car_spec
        dx = np.maximum(np.abs(gx) - s.length / 2, 0)
        dy = np.maximum(np.abs(gy) - s.width / 2, 0)
        dist_to_body = np.hypot(dx, dy)
        region = (dist_to_body <= radius) & ~np.isnan(count)
        if not region.any():
            return {}
        c = count[region]
        blind = region & (count == 0)
        return {
            "covered_1": float((c >= 1).mean() * 100),
            "covered_2": float((c >= 2).mean() * 100),
            "blind_area_m2": float(blind.sum() * (xs[1] - xs[0]) * (ys[1] - ys[0])),
            "max_blind_dist": float(dist_to_body[blind].max()) if blind.any() else 0.0,
        }

    # --------------------------------------------------------- camera image
    def render_camera(self, cam: Camera, width: int = 240):
        """Ray-cast a preview image of what `cam` sees. Returns RGB (h, w, 3)."""
        height = max(1, int(round(width * cam.height_px / cam.width_px)))
        su = (np.arange(width) + 0.5) * cam.width_px / width
        sv = (np.arange(height) + 0.5) * cam.height_px / height
        uu, vv = np.meshgrid(su, sv)
        rays = cam.pixel_rays(uu.ravel(), vv.ravel())
        valid = np.isfinite(rays).all(axis=1)
        if cam.projection == "fisheye":
            fx, fy = cam._focal()
            theta = np.hypot((uu.ravel() - cam.width_px / 2) / fx,
                             (vv.ravel() - cam.height_px / 2) / fy)
            valid &= theta < np.pi
        rays = np.where(valid[:, None], rays, [0, 0, 1])
        n = rays.shape[0]
        o = cam.position

        # Sky gradient.
        elev = np.clip(rays[:, 2], -1, 1)
        img = np.stack([0.62 + 0.2 * elev, 0.76 + 0.15 * elev, 0.93 + 0.05 * elev], 1)
        depth = np.full(n, np.inf)

        # Ground plane z = 0 with a 1 m grid; darker beyond the camera range.
        with np.errstate(divide="ignore", invalid="ignore"):
            tg = np.where(rays[:, 2] < -1e-9, -o[2] / rays[:, 2], np.inf)
        hit_g = np.isfinite(tg)
        gp = o + rays * np.where(hit_g, tg, 0)[:, None]
        fx_, fy_ = np.abs(gp[:, 0] - np.round(gp[:, 0])), np.abs(gp[:, 1] - np.round(gp[:, 1]))
        line = (np.minimum(fx_, fy_) < 0.03 + 0.004 * tg) & (tg < 35)
        ground = np.where(line[:, None], [0.42, 0.45, 0.43], [0.60, 0.63, 0.58])
        fade = np.exp(-np.where(hit_g, tg, 0) / 120.0)[:, None]
        ground = ground * fade + img * (1 - fade)
        out_of_range = hit_g & (tg > cam.max_range)
        ground[out_of_range] = ground[out_of_range] * [1.0, 0.75, 0.75]
        img[hit_g] = ground[hit_g]
        depth[hit_g] = tg[hit_g]

        light = np.array([0.4, 0.3, 0.86])
        light /= np.linalg.norm(light)
        for part in self.occluders(cam):
            t_in, t_out, idx = part.clip(o, rays)
            hit = (t_in <= t_out) & (t_in > 1e-3) & (t_in < depth)
            if not hit.any():
                continue
            nrm = part.normals[idx[hit]]
            shade = 0.45 + 0.55 * np.clip(nrm @ light, 0, 1)
            rgb = np.array(_hex_to_rgb(part.color))
            img[hit] = rgb * shade[:, None]
            depth[hit] = t_in[hit]
        img[~valid] = 0.05
        return np.clip(img.reshape(height, width, 3), 0, 1)

    # -------------------------------------------------------------- persist
    def to_dict(self) -> dict:
        return {"car": asdict(self.car_spec),
                "objects_occlude": self.objects_occlude,
                "cameras": [c.to_dict() for c in self.cameras],
                "objects": [o.to_dict() for o in self.objects]}

    def load_dict(self, d: dict):
        if "car" in d:
            spec = CarSpec(**{k: v for k, v in d["car"].items()
                              if k in CarSpec.__dataclass_fields__})
            self.car_spec, self.car_parts = build_car(spec)
        self.objects_occlude = d.get("objects_occlude", True)
        self.cameras = [Camera.from_dict(c) for c in d.get("cameras", [])]
        self.objects = [TargetObject.from_dict(o) for o in d.get("objects", [])]

    def save(self, path: str):
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    def load(self, path: str):
        with open(path) as f:
            self.load_dict(json.load(f))


def _hex_to_rgb(h: str):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
