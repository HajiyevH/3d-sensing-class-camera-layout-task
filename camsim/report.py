"""Tabular visibility report shared by the GUI export and the command line."""
from __future__ import annotations

import csv

from .scene import Scene

COLUMNS = ["object", "kind", "camera", "visible", "visible_pct", "in_fov_pct",
           "distance_m", "px_width", "px_height"]


def report_rows(scene: Scene) -> list[dict]:
    rows = []
    for obj in scene.objects:
        for cam_name, hit in scene.object_visibility(obj).items():
            rows.append({
                "object": obj.name, "kind": obj.kind, "camera": cam_name,
                "visible": hit.visible,
                "visible_pct": round(hit.fraction * 100, 1),
                "in_fov_pct": round(hit.in_fov_fraction * 100, 1),
                "distance_m": round(hit.distance, 2),
                "px_width": round(hit.px_width), "px_height": round(hit.px_height),
            })
    return rows


def write_csv(scene: Scene, path: str):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(report_rows(scene))


def text_report(scene: Scene, coverage_height: float = 0.5,
                coverage_radius: float = 5.0) -> str:
    lines = [f"Car: {scene.car_spec.name}  "
             f"({scene.car_spec.length:.3f} x {scene.car_spec.width:.3f} x "
             f"{scene.car_spec.height:.3f} m)", "", "Cameras:"]
    for c in scene.cameras:
        state = "" if c.enabled else "  [disabled]"
        lines.append(f"  {c.name:<16} pos=({c.x:+.2f},{c.y:+.2f},{c.z:.2f}) "
                     f"ypr=({c.yaw:+.0f},{c.pitch:+.0f},{c.roll:+.0f}) "
                     f"{c.projection} {c.hfov:.0f}x{c.vfov:.0f} deg, "
                     f"{c.max_range:.0f} m{state}")
    lines += ["", "Objects:"]
    for obj in scene.objects:
        hits = {k: v for k, v in scene.object_visibility(obj).items() if v.visible}
        seen = ", ".join(f"{k} ({v.fraction * 100:.0f}%, {v.px_height:.0f}px)"
                         for k, v in hits.items()) or "NOT SEEN"
        lines.append(f"  {obj.name:<22} @({obj.x:+.1f},{obj.y:+.1f}): {seen}")
    extent = coverage_radius + scene.car_spec.length / 2 + 1
    xs, ys, cnt = scene.coverage_grid(extent, 0.2, coverage_height)
    st = scene.coverage_stats(xs, ys, cnt, coverage_radius)
    lines += ["", f"Coverage within {coverage_radius:.1f} m of the body at "
                  f"h={coverage_height:.2f} m:",
              f"  >=1 camera: {st['covered_1']:.1f}%   >=2 cameras: "
              f"{st['covered_2']:.1f}%",
              f"  blind area: {st['blind_area_m2']:.1f} m^2   farthest blind point "
              f"from body: {st['max_blind_dist']:.2f} m"]
    return "\n".join(lines)
