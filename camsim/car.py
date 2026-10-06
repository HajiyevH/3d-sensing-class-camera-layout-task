"""Low-poly Tesla Model 3 built from convex solids.

Official dimensions (metres):
    length 4.720, width 1.850 (2.089 with mirrors), height 1.440,
    wheelbase 2.875, ground clearance 0.138.
The front overhang (~0.84 m) and the body profile are approximations
good enough for field-of-view and self-occlusion studies.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .geometry import ConvexPart, cylinder_y_vertices


@dataclass
class CarSpec:
    name: str = "Tesla Model 3"
    length: float = 4.720
    width: float = 1.850
    width_mirrors: float = 2.089
    height: float = 1.440
    wheelbase: float = 2.875
    ground_clearance: float = 0.138
    front_overhang: float = 0.840
    wheel_radius: float = 0.334        # 235/45 R18
    wheel_width: float = 0.235
    track: float = 1.580

    @property
    def front_x(self) -> float:
        return self.length / 2

    @property
    def rear_x(self) -> float:
        return -self.length / 2

    @property
    def front_axle_x(self) -> float:
        return self.front_x - self.front_overhang

    @property
    def rear_axle_x(self) -> float:
        return self.front_axle_x - self.wheelbase


def _mirror_y(points):
    pts = np.asarray(points, float)
    return np.vstack([pts, pts * [1, -1, 1]])


def build_car(spec: CarSpec | None = None) -> tuple[CarSpec, list[ConvexPart]]:
    s = spec or CarSpec()
    L2, W2, H = s.length / 2, s.width / 2, s.height
    gc = s.ground_clearance
    body_c, glass_c, wheel_c, dark_c = "#c8ced6", "#5b7488", "#2b2b2b", "#3c4248"

    parts: list[ConvexPart] = []

    # Front nose + bumper (rounded front end, low hood).
    parts.append(ConvexPart(_mirror_y([
        [L2, 0.80, 0.30], [L2, 0.80, 0.62],
        [L2 - 0.12, W2 - 0.03, 0.22], [L2 - 0.12, W2 - 0.03, 0.74],
        [L2 - 0.35, W2, gc + 0.04], [L2 - 0.35, W2, 0.80],
        [s.front_axle_x, W2, gc + 0.04], [s.front_axle_x, W2, 0.86],
    ]), "front body", body_c))

    # Middle body (doors, sills) up to the belt line, rising towards the rear.
    parts.append(ConvexPart(_mirror_y([
        [s.front_axle_x, W2, gc + 0.04], [s.front_axle_x, W2, 0.86],
        [1.05, W2, 0.98],
        [s.rear_axle_x, W2, gc + 0.04], [s.rear_axle_x, W2, 1.00],
    ]), "mid body", body_c))

    # Rear body: trunk lid + rear bumper.
    parts.append(ConvexPart(_mirror_y([
        [s.rear_axle_x, W2, gc + 0.04], [s.rear_axle_x, W2, 1.00],
        [-L2 + 0.25, W2 - 0.02, 0.22], [-L2 + 0.20, W2 - 0.03, 1.02],
        [-L2, 0.82, 0.38], [-L2, 0.82, 0.98],
    ]), "rear body", body_c))

    # Greenhouse (windshield, roof glass, side windows, rear window).
    parts.append(ConvexPart(_mirror_y([
        [1.05, 0.80, 0.97], [-1.95, 0.80, 1.00],      # glass base
        [0.25, 0.64, H - 0.02], [-0.65, 0.64, H],     # roof
        [0.45, 0.62, H - 0.07], [-1.10, 0.62, H - 0.08],
    ]), "cabin", glass_c))

    # Side mirrors.
    mw = s.width_mirrors / 2
    for side in (1, -1):
        parts.append(ConvexPart([
            [0.98, side * (W2 - 0.10), 0.96], [0.98, side * (W2 - 0.10), 1.08],
            [0.82, side * (W2 - 0.10), 0.96], [0.82, side * (W2 - 0.10), 1.08],
            [0.94, side * mw, 0.97], [0.94, side * mw, 1.07],
            [0.84, side * mw, 0.98], [0.84, side * mw, 1.06],
        ], "mirror " + ("L" if side > 0 else "R"), dark_c))

    # Wheels.
    for ax_x, tag in ((s.front_axle_x, "F"), (s.rear_axle_x, "R")):
        for side in (1, -1):
            c = [ax_x, side * (s.track / 2), s.wheel_radius]
            parts.append(ConvexPart(
                cylinder_y_vertices(c, s.wheel_radius, s.wheel_width, 16),
                f"wheel {tag}{'L' if side > 0 else 'R'}", wheel_c))
    return s, parts


def car_footprint(spec: CarSpec) -> np.ndarray:
    """Top-view outline polygon (x, y), used for 2D plots."""
    L2, W2 = spec.length / 2, spec.width / 2
    return np.array([
        [L2, 0.80], [L2 - 0.12, W2 - 0.03], [L2 - 0.35, W2],
        [-L2 + 0.20, W2 - 0.02], [-L2, 0.82], [-L2, -0.82],
        [-L2 + 0.20, -W2 + 0.02], [L2 - 0.35, -W2], [L2 - 0.12, -W2 + 0.03],
        [L2, -0.80], [L2, 0.80]])


def car_side_profile(spec: CarSpec) -> np.ndarray:
    """Side-view outline polygon (x, z)."""
    L2, H, gc = spec.length / 2, spec.height, spec.ground_clearance
    return np.array([
        [L2, 0.30], [L2, 0.62], [L2 - 0.12, 0.74], [L2 - 0.35, 0.80],
        [spec.front_axle_x, 0.86], [1.05, 0.98], [0.45, H - 0.07],
        [0.25, H - 0.02], [-0.65, H], [-1.10, H - 0.08], [-1.95, 1.00],
        [-L2 + 0.20, 1.02], [-L2, 0.98], [-L2, 0.38], [-L2 + 0.25, 0.22],
        [-L2 + 0.35, gc + 0.04], [L2 - 0.35, gc + 0.04], [L2 - 0.12, 0.22],
        [L2, 0.30]])

