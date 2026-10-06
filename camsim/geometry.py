"""Low-level geometry: rotations, convex solids and ray/segment intersection.

Vehicle frame (ISO 8855 / ROS style):
    x -> forward, y -> left, z -> up, origin on the ground below the car centre.
All lengths are in metres, all user-facing angles in degrees.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial import ConvexHull


def rot_x(a: float) -> np.ndarray:
    c, s = np.cos(a), np.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rot_y(a: float) -> np.ndarray:
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def rot_z(a: float) -> np.ndarray:
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def body_rotation(yaw_deg: float, pitch_deg: float, roll_deg: float) -> np.ndarray:
    """Rotation of a body whose +x axis is its 'forward' direction.

    yaw   > 0 turns left (counter-clockwise seen from above)
    pitch > 0 tilts the nose up
    roll  > 0 rotates clockwise around the forward axis (right side down)
    """
    return (rot_z(np.radians(yaw_deg))
            @ rot_y(-np.radians(pitch_deg))
            @ rot_x(np.radians(roll_deg)))


class ConvexPart:
    """A closed convex solid stored as half-spaces  n . p + d <= 0  (inside)."""

    def __init__(self, vertices, name: str = "part", color: str = "#9aa4ad",
                 occluder: bool = True):
        self.vertices = np.asarray(vertices, dtype=float)
        self.name = name
        self.color = color
        self.occluder = occluder
        hull = ConvexHull(self.vertices)
        eq = hull.equations                      # (P, 4): normal (unit), offset
        # Merge coplanar facets (Qhull triangulates faces) to keep tests cheap.
        eq_rounded = np.round(eq, 6)
        _, keep = np.unique(eq_rounded, axis=0, return_index=True)
        self.planes = eq[np.sort(keep)]
        self.normals = self.planes[:, :3]
        self.offsets = self.planes[:, 3]
        self.triangles = self.vertices[hull.simplices]          # (T, 3, 3)
        # Make triangle winding consistent with the outward normal.
        centre = self.vertices.mean(axis=0)
        tri_n = np.cross(self.triangles[:, 1] - self.triangles[:, 0],
                         self.triangles[:, 2] - self.triangles[:, 0])
        flip = np.einsum("ij,ij->i", tri_n, self.triangles.mean(axis=1) - centre) < 0
        self.triangles[flip] = self.triangles[flip][:, ::-1]
        self.bbox_min = self.vertices.min(axis=0)
        self.bbox_max = self.vertices.max(axis=0)

    def signed_distance(self, points: np.ndarray) -> np.ndarray:
        """Max plane distance: < 0 inside, > 0 outside (exact on faces)."""
        points = np.atleast_2d(points)
        return (points @ self.normals.T + self.offsets).max(axis=1)

    def contains(self, points: np.ndarray, margin: float = 0.0) -> np.ndarray:
        return self.signed_distance(points) < -margin

    def clip(self, origin: np.ndarray, dirs: np.ndarray):
        """Cyrus-Beck clipping of rays origin + t*dirs against this solid.

        Returns (t_enter, t_exit, enter_plane_idx). No hit <=> t_enter > t_exit.
        `origin` is a single point (3,) or one per ray (N, 3).
        """
        dirs = np.atleast_2d(dirs)
        n = dirs.shape[0]
        origin = np.broadcast_to(origin, (n, 3))
        den = dirs @ self.normals.T                                  # (N, P)
        num = -(origin @ self.normals.T + self.offsets)              # (N, P)
        with np.errstate(divide="ignore", invalid="ignore"):
            t = num / den
        entering = den < -1e-12
        exiting = den > 1e-12
        parallel_out = (~entering) & (~exiting) & (num < 0)

        t_in_all = np.where(entering, t, -np.inf)
        t_enter = t_in_all.max(axis=1)
        enter_idx = t_in_all.argmax(axis=1)
        t_exit = np.where(exiting, t, np.inf).min(axis=1)
        t_exit = np.where(parallel_out.any(axis=1), -np.inf, t_exit)
        return t_enter, t_exit, enter_idx


def segment_blocked(part: ConvexPart, origin: np.ndarray, targets: np.ndarray,
                    min_overlap: float = 0.01) -> np.ndarray:
    """True for each segment origin->target that passes through `part`.

    A segment only counts as blocked if it travels at least `min_overlap`
    metres inside the solid, so sensors mounted *on* a surface and targets
    lying *on* a surface are not reported as self-occluded.
    """
    dirs = targets - origin
    length = np.linalg.norm(dirs, axis=1)
    t_enter, t_exit, _ = part.clip(origin, dirs)
    lo = np.maximum(t_enter, 0.0)
    hi = np.minimum(t_exit, 1.0)
    return (hi - lo) * length > min_overlap


def box_vertices(center, size, yaw_deg: float = 0.0) -> np.ndarray:
    """8 corners of an oriented box. `center` is the geometric centre."""
    l, w, h = size
    sx, sy, sz = np.meshgrid([-l / 2, l / 2], [-w / 2, w / 2], [-h / 2, h / 2],
                             indexing="ij")
    local = np.stack([sx.ravel(), sy.ravel(), sz.ravel()], axis=1)
    return local @ rot_z(np.radians(yaw_deg)).T + np.asarray(center, float)


def cylinder_y_vertices(center, radius: float, width: float, segments: int = 16):
    """Vertices of a cylinder whose axis is parallel to y (a wheel)."""
    a = np.linspace(0, 2 * np.pi, segments, endpoint=False)
    ring = np.stack([radius * np.cos(a), np.zeros_like(a), radius * np.sin(a)], 1)
    left = ring + [0, width / 2, 0]
    right = ring - [0, width / 2, 0]
    return np.vstack([left, right]) + np.asarray(center, float)
