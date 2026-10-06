"""Ready-made camera rigs and object templates."""
from __future__ import annotations

from .camera import Camera
from .scene import TargetObject

# Approximation of Tesla's 8-camera "Tesla Vision" layout (HW3, 1280x960).
# Ranges are Tesla's published maximum distances; mounting positions and
# angles are estimates from photos - adjust them to your own measurements.
def tesla_vision_cameras() -> list[Camera]:
    return [
        Camera("Main forward", 0.42, 0.00, 1.30, 0, -1, 0, 50, 38, 150,
               color="#1f77b4"),
        Camera("Narrow forward", 0.42, 0.07, 1.30, 0, -1, 0, 35, 27, 250,
               color="#17becf"),
        Camera("Wide forward", 0.42, -0.07, 1.30, 0, -3, 0, 120, 90, 60,
               projection="fisheye", color="#9467bd"),
        Camera("B-pillar left", -0.15, 0.77, 1.10, 60, -10, 0, 90, 74, 80,
               color="#2ca02c"),
        Camera("B-pillar right", -0.15, -0.77, 1.10, -60, -10, 0, 90, 74, 80,
               color="#bcbd22"),
        Camera("Repeater left", 1.20, 0.94, 0.85, 145, -8, 0, 75, 58, 100,
               color="#ff7f0e"),
        Camera("Repeater right", 1.20, -0.94, 0.85, -145, -8, 0, 75, 58, 100,
               color="#d62728"),
        Camera("Rear", -2.37, 0.00, 0.95, 180, -25, 0, 130, 100, 50,
               projection="fisheye", color="#8c564b"),
    ]


# Low-mounted 190 deg fisheyes for near-field / parking coverage, like the
# surround-view systems of many production cars. They replace ultrasound.
def surround_fisheye_cameras() -> list[Camera]:
    return [
        Camera("Surround front", 2.37, 0.00, 0.55, 0, -30, 0, 190, 140, 15,
               projection="fisheye", color="#e6550d"),
        Camera("Surround rear", -2.37, 0.00, 0.75, 180, -35, 0, 190, 140, 15,
               projection="fisheye", color="#843c39"),
        Camera("Surround left", 0.90, 1.04, 0.94, 90, -60, 0, 190, 140, 15,
               projection="fisheye", color="#31a354"),
        Camera("Surround right", 0.90, -1.04, 0.94, -90, -60, 0, 190, 140, 15,
               projection="fisheye", color="#756bb1"),
    ]


def tesla_vision_plus_surround() -> list[Camera]:
    return tesla_vision_cameras() + surround_fisheye_cameras()


# Name shown in the GUI -> camera factory.
CAMERA_PRESETS = {
    "Tesla Vision (8 cameras)": tesla_vision_cameras,
    "Tesla Vision + 4 surround fisheyes (12 cameras)": tesla_vision_plus_surround,
}

# name: (length, width, height, colour)
OBJECT_TEMPLATES = {
    "Pedestrian": (0.6, 0.6, 1.75, "#e377c2"),
    "Child": (0.4, 0.4, 1.10, "#ff9896"),
    "Cyclist": (1.8, 0.6, 1.70, "#98df8a"),
    "Car": (4.5, 1.8, 1.50, "#aec7e8"),
    "Truck": (8.0, 2.5, 3.50, "#c5b0d5"),
    "Traffic cone": (0.35, 0.35, 0.70, "#ff7f0e"),
    "Dog": (0.8, 0.3, 0.55, "#c49c94"),
    "Post / bollard": (0.2, 0.2, 1.00, "#7f7f7f"),
}


def make_object(kind: str, x: float, y: float, yaw: float = 0.0,
                name: str | None = None) -> TargetObject:
    l, w, h, c = OBJECT_TEMPLATES[kind]
    return TargetObject(name or kind, kind, x, y, 0.0, yaw, l, w, h, c)


def demo_objects() -> list[TargetObject]:
    return [
        make_object("Pedestrian", 9.0, 3.0, name="Pedestrian crossing"),
        make_object("Car", 28.0, -3.5, name="Lead car"),
        make_object("Child", -3.0, 0.0, name="Child behind car"),
        make_object("Traffic cone", 0.3, 1.5, name="Cone by door"),
        make_object("Cyclist", -7.0, 2.6, name="Cyclist overtaking"),
        make_object("Child", 2.9, 0.0, name="Child at bumper"),
    ]
