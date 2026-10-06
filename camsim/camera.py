"""Camera model: mounting pose, intrinsics (pinhole or fisheye) and projection.

Camera optical frame: z forward, x right, y down (OpenCV convention).
Pose is given in the vehicle frame as position + yaw/pitch/roll in degrees,
where yaw=0 looks forward (+x), yaw=90 looks left, yaw=180 looks backwards.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from .geometry import body_rotation

PROJECTIONS = ("pinhole", "fisheye")


@dataclass
class Camera:
    name: str = "camera"
    x: float = 0.0
    y: float = 0.0
    z: float = 1.4
    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    hfov: float = 60.0
    vfov: float = 45.0
    max_range: float = 50.0
    width_px: int = 1280
    height_px: int = 960
    projection: str = "pinhole"
    color: str = "#1f77b4"
    enabled: bool = True

    # ------------------------------------------------------------------ pose
    @property
    def position(self) -> np.ndarray:
        return np.array([self.x, self.y, self.z], float)

    @property
    def R_body(self) -> np.ndarray:
        return body_rotation(self.yaw, self.pitch, self.roll)

    @property
    def R_cam_to_vehicle(self) -> np.ndarray:
        """Columns = camera x (right), y (down), z (forward) in vehicle frame."""
        rb = self.R_body
        return np.stack([-rb[:, 1], -rb[:, 2], rb[:, 0]], axis=1)

    @property
    def forward(self) -> np.ndarray:
        return self.R_body[:, 0]

    # ------------------------------------------------------------ intrinsics
    def _focal(self):
        hh, hv = np.radians(self.hfov) / 2, np.radians(self.vfov) / 2
        if self.projection == "fisheye":           # equidistant: r = f * theta
            return self.width_px / 2 / hh, self.height_px / 2 / hv
        hh, hv = min(hh, np.radians(89.5)), min(hv, np.radians(89.5))
        return self.width_px / 2 / np.tan(hh), self.height_px / 2 / np.tan(hv)

    def to_camera(self, points: np.ndarray) -> np.ndarray:
        return (np.atleast_2d(points) - self.position) @ self.R_cam_to_vehicle

    def project(self, points: np.ndarray):
        """Project vehicle-frame points -> (u, v, depth, in_image).

        depth is the Euclidean distance to the camera. `in_image` is True when
        the point falls inside the sensor and inside the camera's max range.
        """
        pc = self.to_camera(points)
        fx, fy = self._focal()
        cx, cy = self.width_px / 2, self.height_px / 2
        dist = np.linalg.norm(pc, axis=1)
        if self.projection == "fisheye":
            theta = np.arccos(np.clip(pc[:, 2] / np.maximum(dist, 1e-12), -1, 1))
            rxy = np.hypot(pc[:, 0], pc[:, 1])
            safe = np.maximum(rxy, 1e-12)
            u = cx + fx * theta * pc[:, 0] / safe
            v = cy + fy * theta * pc[:, 1] / safe
            front = theta < np.pi * 0.999
        else:
            zc = np.where(pc[:, 2] > 1e-6, pc[:, 2], np.nan)
            u = cx + fx * pc[:, 0] / zc
            v = cy + fy * pc[:, 1] / zc
            front = pc[:, 2] > 1e-6
        with np.errstate(invalid="ignore"):
            in_img = (front & (u >= 0) & (u <= self.width_px)
                      & (v >= 0) & (v <= self.height_px)
                      & (dist <= self.max_range) & (dist > 1e-6))
        return u, v, dist, np.nan_to_num(in_img, nan=False).astype(bool)

    def pixel_rays(self, u: np.ndarray, v: np.ndarray) -> np.ndarray:
        """Unit ray directions (vehicle frame) through pixel coordinates."""
        fx, fy = self._focal()
        xn = (np.asarray(u, float) - self.width_px / 2) / fx
        yn = (np.asarray(v, float) - self.height_px / 2) / fy
        if self.projection == "fisheye":
            theta = np.hypot(xn, yn)
            safe = np.maximum(theta, 1e-12)
            s = np.sin(theta) / safe
            d = np.stack([xn * s, yn * s, np.cos(theta)], axis=-1)
        else:
            d = np.stack([xn, yn, np.ones_like(xn)], axis=-1)
            d /= np.linalg.norm(d, axis=-1, keepdims=True)
        return d @ self.R_cam_to_vehicle.T

    def frustum_outline(self, length: float, samples: int = 12):
        """Points on the image border back-projected to `length` metres.

        Returns (border_points (M,3), corner_points (4,3)).
        """
        w, h = self.width_px, self.height_px
        t = np.linspace(0, 1, samples, endpoint=False)
        u = np.concatenate([t * w, np.full_like(t, w), (1 - t) * w, np.zeros_like(t)])
        v = np.concatenate([np.zeros_like(t), t * h, np.full_like(t, h), (1 - t) * h])
        border = self.position + self.pixel_rays(u, v) * length
        corners = self.position + self.pixel_rays(
            np.array([0, w, w, 0]), np.array([0, 0, h, h])) * length
        return border, corners

    def horizontal_extent(self):
        """Azimuth interval (deg, vehicle frame) covered by the image middle row."""
        u = np.linspace(0, self.width_px, 41)
        rays = self.pixel_rays(u, np.full_like(u, self.height_px / 2))
        return np.degrees(np.arctan2(rays[:, 1], rays[:, 0]))

    # ------------------------------------------------------------- serialise
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Camera":
        allowed = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in allowed})
