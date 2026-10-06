"""Regenerate diagrams/camera_setup_11cam.drawio. Run from the project root:
    python3 diagrams/make_drawio.py
"""
import math
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, ".")
from camsim.car import CarSpec  # noqa: E402
from camsim.presets import tesla_vision_plus_surround  # noqa: E402

S = 90.0                      # px per metre (car outline and camera positions)
CX, CY = 640, 540             # car centre on the page
spec = CarSpec()


def P(x, y):
    """Vehicle frame (x forward, y left) -> page coordinates."""
    return CX + x * S, CY - y * S


# name -> (number, colour, wedge radius px, legend label). Radii are schematic.
GROUP = {
    "Main forward": (1, "#1F77B4", 340, "Main forward"),
    "Narrow forward": (2, "#17BECF", 430, "Narrow forward"),
    "B-pillar left": (3, "#2CA02C", 280, "B-pillar left"),
    "B-pillar right": (4, "#2CA02C", 280, "B-pillar right"),
    "Repeater left": (5, "#FF7F0E", 300, "Repeater left"),
    "Repeater right": (6, "#FF7F0E", 300, "Repeater right"),
    "Rear": (7, "#8C564B", 270, "Rear"),
    "Surround front": (8, "#9467BD", 175, "Surround front"),
    "Surround rear": (9, "#9467BD", 175, "Surround rear"),
    "Surround left": (10, "#9467BD", 175, "Surround left"),
    "Surround right": (11, "#9467BD", 175, "Surround right"),
}
BADGE_TURN = {"Surround front": 50, "Surround rear": -50}
cams = [c for c in tesla_vision_plus_surround() if c.name != "Wide forward"]

root = ET.Element("mxfile", host="drawio")
diag = ET.SubElement(root, "diagram", id="cams", name="11-camera setup")
model = ET.SubElement(diag, "mxGraphModel", grid="1", gridSize="10", page="1",
                      pageWidth="1700", pageHeight="1080", background="#FFFFFF")
cells = ET.SubElement(model, "root")
ET.SubElement(cells, "mxCell", id="0")
ET.SubElement(cells, "mxCell", id="1", parent="0")
_id = [1]


def _new(**kw):
    _id[0] += 1
    return ET.SubElement(cells, "mxCell", id=f"c{_id[0]}", parent="1", **kw)


def box(x, y, w, h, style, value=""):
    c = _new(value=value, style=style, vertex="1")
    ET.SubElement(c, "mxGeometry", x=f"{x:.1f}", y=f"{y:.1f}", width=f"{w:.1f}",
                  height=f"{h:.1f}", **{"as": "geometry"})


def line(x1, y1, x2, y2, style, value=""):
    c = _new(value=value, style=style, edge="1")
    g = ET.SubElement(c, "mxGeometry", relative="1", **{"as": "geometry"})
    ET.SubElement(g, "mxPoint", x=f"{x1:.1f}", y=f"{y1:.1f}", **{"as": "sourcePoint"})
    ET.SubElement(g, "mxPoint", x=f"{x2:.1f}", y=f"{y2:.1f}", **{"as": "targetPoint"})


def wedge(cam, r, col, opacity, stroke_w):
    """FOV wedge with draw.io's pie shape (angles: fraction of a turn,
    clockwise from 12 o'clock)."""
    centre = (90.0 - cam.yaw) % 360          # page heading of the optical axis
    half = min(cam.hfov, 359) / 2
    start = ((centre - half) % 360) / 360
    end = ((centre + half) % 360) / 360
    ax, ay = P(cam.x, cam.y)
    box(ax - r, ay - r, 2 * r, 2 * r,
        f"shape=mxgraph.basic.pie;startAngle={start:.4f};endAngle={end:.4f};"
        f"fillColor={col};opacity={opacity};strokeColor={col};strokeWidth={stroke_w};")


DIM = ("endArrow=block;startArrow=block;endFill=1;startFill=1;html=1;strokeWidth=1.5;"
       "strokeColor=#222222;fontSize=13;fontStyle=1;labelBackgroundColor=#FFFFFF;")
EXT = "endArrow=none;html=1;dashed=1;strokeColor=#777777;strokeWidth=1;"

# --- title -----------------------------------------------------------------
box(40, 25, 1100, 34, "text;html=1;fontSize=24;fontStyle=1;align=left;verticalAlign=middle;",
    "Tesla Model 3 – 11-camera vision-only layout (top view)")
box(40, 62, 1100, 24, "text;html=1;fontSize=14;fontColor=#666666;align=left;",
    "Car and camera positions to scale (1 m = 90 px). Wedges show the horizontal FOV; "
    "wedge length is schematic – longer = longer range.")
box(40, 100, 150, 44, "shape=singleArrow;arrowWidth=0.5;arrowSize=0.35;fillColor=#444444;"
    "strokeColor=none;fontColor=#FFFFFF;fontSize=14;fontStyle=1;align=center;", "FRONT")
box(195, 100, 200, 44, "text;fontSize=13;fontColor=#444444;align=left;verticalAlign=middle;",
    "driving direction")

# --- wedges: long-range first, surround views last (on top) ------------------
for c in sorted(cams, key=lambda c: -GROUP[c.name][2]):
    num, col, r, _ = GROUP[c.name]
    surround = c.name.startswith("Surround")
    wedge(c, r, col, 30 if surround else 18, 2.5 if surround else 1.5)

# --- car --------------------------------------------------------------------
L, W = spec.length * S, spec.width * S
wr, ww = spec.wheel_radius * S, 0.24 * S
for ax_x in (spec.front_axle_x, spec.rear_axle_x):
    for side in (1, -1):
        x, y = P(ax_x, side * (W / 2 / S + 0.05))
        box(x - wr, y - ww / 2, 2 * wr, ww, "rounded=1;arcSize=35;fillColor=#222222;strokeColor=none;")
mw = spec.width_mirrors / 2
for side in (1, -1):
    x, y = P(0.98, side * mw if side > 0 else -spec.width / 2 + 0.02)
    box(x, y, 0.18 * S, (mw - spec.width / 2 + 0.02) * S,
        "rounded=1;arcSize=40;fillColor=#3C4248;strokeColor=none;")
bx, by = P(-spec.length / 2, spec.width / 2)
box(bx, by, L, W, "rounded=1;arcSize=24;fillColor=#E6EAEF;strokeColor=#333333;strokeWidth=2.5;")
gx, gy = P(-1.95, 0.80)
box(gx, gy, 3.0 * S, 1.6 * S, "rounded=1;arcSize=30;fillColor=#5B7488;strokeColor=#3D5366;strokeWidth=1.5;")
rx, ry = P(-1.10, 0.62)
box(rx, ry, 1.55 * S, 1.24 * S, "rounded=1;arcSize=25;fillColor=#8DA2B3;strokeColor=none;")
hx, hy = P(1.15, 0.3)
box(hx, hy, 1.1 * S, 0.6 * S, "text;fontSize=14;fontStyle=1;fontColor=#555555;align=center;"
    "verticalAlign=middle;", "FRONT →")

# --- dimension arrows -----------------------------------------------------
front_px, rear_px = P(spec.length / 2, 0)[0], P(-spec.length / 2, 0)[0]
top_px, bot_px = P(0, spec.width / 2)[1], P(0, -spec.width / 2)[1]
yl = bot_px + 120                                     # overall length
line(rear_px, bot_px + 10, rear_px, yl + 12, EXT)
line(front_px, bot_px + 10, front_px, yl + 12, EXT)
line(rear_px, yl, front_px, yl, DIM, f"Length {spec.length * 1000:.0f} mm")
yw = top_px - 120                                     # wheelbase
fa, ra = P(spec.front_axle_x, 0)[0], P(spec.rear_axle_x, 0)[0]
line(ra, top_px - 10, ra, yw - 12, EXT)
line(fa, top_px - 10, fa, yw - 12, EXT)
line(ra, yw, fa, yw, DIM, f"Wheelbase {spec.wheelbase * 1000:.0f} mm")
xw = rear_px - 70                                     # body width
line(rear_px + 30, top_px, xw - 12, top_px, EXT)
line(rear_px + 30, bot_px, xw - 12, bot_px, EXT)
line(xw, top_px, xw, bot_px, DIM + "horizontal=0;", f"Width {spec.width * 1000:.0f} mm")
mx = P(0.9, 0)[0]                                     # width with mirrors
mtop, mbot = P(0, mw)[1], P(0, -mw)[1]
line(mx, mtop, mx, mbot, DIM + "horizontal=0;strokeColor=#555555;fontSize=11;",
     f"{spec.width_mirrors * 1000:.0f} mm with mirrors")

# --- camera dots and number badges -------------------------------------------
placed = []
for c in cams:
    num, col, r, _ = GROUP[c.name]
    ax, ay = P(c.x, c.y)
    box(ax - 8, ay - 8, 16, 16, f"ellipse;fillColor={col};strokeColor=#FFFFFF;strokeWidth=2.5;")
    # Surround front/rear badges sit off-axis so they don't collide with 1/2/7.
    yaw = math.radians(c.yaw + BADGE_TURN.get(c.name, 0))
    d = r + 20
    while True:
        bx_, by_ = ax + d * math.cos(yaw), ay - d * math.sin(yaw)
        if all(math.hypot(bx_ - px, by_ - py) > 36 for px, py in placed):
            break
        d += 8
    placed.append((bx_, by_))
    box(bx_ - 16, by_ - 16, 32, 32, f"ellipse;fillColor={col};strokeColor=#FFFFFF;strokeWidth=2;"
        "fontColor=#FFFFFF;fontStyle=1;fontSize=15;", str(num))

# --- legend -------------------------------------------------------------------
LX, LY = 1200, 110
box(LX, LY, 460, 30, "text;fontSize=17;fontStyle=1;align=left;verticalAlign=middle;", "Cameras")
for i, c in enumerate(cams):
    num, col, _, label = GROUP[c.name]
    y = LY + 42 + i * 52
    box(LX, y, 30, 30, f"ellipse;fillColor={col};strokeColor=none;fontColor=#FFFFFF;"
        "fontStyle=1;fontSize=14;", str(num))
    lens = " fisheye" if c.projection == "fisheye" else ""
    box(LX + 42, y - 8, 420, 46, "text;html=1;fontSize=13;align=left;verticalAlign=middle;",
        f"<b>{label}</b> – {c.hfov:.0f}°{lens}, {c.max_range:.0f} m<br>"
        f"<font color='#666666'>x {c.x:+.2f} m, y {c.y:+.2f} m, height {c.z:.2f} m, "
        f"yaw {c.yaw:+.0f}°</font>")
ny = LY + 42 + len(cams) * 52 + 10
box(LX, ny, 460, 92, "rounded=1;whiteSpace=wrap;html=1;fillColor=#F5F5F5;strokeColor=#DDDDDD;"
    "fontSize=13;align=left;spacingLeft=12;fontColor=#333333;",
    f"<b>Car:</b> {spec.length * 1000:.0f} × {spec.width * 1000:.0f} mm "
    f"({spec.width_mirrors * 1000:.0f} mm with mirrors), height {spec.height * 1000:.0f} mm<br>"
    "<b>Long range:</b> 1–2 forward &nbsp; <b>Sides:</b> 3–6 &nbsp; <b>Rear:</b> 7<br>"
    "<b>Surround / parking (purple):</b> 8–11<br>"
    "<font color='#666666'>x forward, y left, origin = car centre on the ground</font>")

ET.indent(root)
out = "diagrams/camera_setup_11cam.drawio"
ET.ElementTree(root).write(out, encoding="utf-8")
print("wrote", out)
