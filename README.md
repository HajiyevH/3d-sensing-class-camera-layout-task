# Camera Setup Designer – Tesla Model 3

Interactive Python tool for placing cameras on a Tesla Model 3, inspecting their
fields of view and checking whether objects around the car are seen.

## Run

```bash
pip install -r requirements.txt        # numpy, scipy, matplotlib (tkinter ships with Python)
python main.py                         # GUI, starts with the Tesla Vision 8-camera preset
python main.py --preset surround       # GUI, Tesla preset + 4 surround fisheyes
python main.py configs/tesla_model3_vision.json            # GUI with a saved setup
python main.py configs/tesla_model3_vision.json --report   # text report, no GUI
python main.py my_rig.json --csv visibility.csv            # per-camera table as CSV
python -m pytest tests                                     # unit tests
```

## The car

Built from the official dimensions: length 4.720 m, width 1.850 m (2.089 m with
mirrors), height 1.440 m, wheelbase 2.875 m, ground clearance 0.138 m. The body is a
low-poly set of convex solids (front, middle and rear body, glass cabin, mirrors and
wheels), which are also used for self-occlusion. Edit `camsim/car.py` to refine it.

**Coordinate frame:** x forward, y left, z up, with the origin on the ground under the
car centre. The front bumper is at x = +2.36 m and the rear bumper at x = −2.36 m.
Yaw 0 looks forward, +90 looks left and 180 looks backward. Positive pitch looks up.

## GUI

| Area | What you can do |
|---|---|
| **Cameras** tab | add, duplicate, mirror L↔R or delete cameras; set position, yaw, pitch, roll, H/V-FOV, range, resolution and pinhole/fisheye model with sliders or typed values |
| **Objects** tab | add pedestrians, children, cyclists, cars, trucks, cones, dogs or posts; move, rotate and resize them; the table shows **which cameras see each object**, the visible share and its height in pixels |
| **View / Analysis** | coverage heat-map (number of cameras that see each point at a chosen height), coverage statistics, blind area, object shadows, 3D frustum length |
| **Top view** | FOV wedges and the coverage map. Drag cameras or objects to move them. Scroll to change the selected camera's yaw (Shift+scroll changes pitch); scroll over an object to rotate it. Right-click to add an object or camera at that point, or to aim the selected camera there. |
| **3D view** | car mesh, camera frustums and objects. Drag to rotate. |
| **Side view** | vertical FOV of the forward and rear cameras, and the nearest ground each one can see past the bumper (the hood and trunk occlusion is taken into account) |
| **Camera view** | ray-traced picture of what the selected camera sees, including its own car body, with boxes and pixel heights for the objects it sees |
| **All cameras** | all camera images side by side |

From the File menu you can save and load setups as JSON, export the current view as a PNG,
and export the visibility table as a CSV.

## How visibility is decided

A point counts as visible to a camera when all of these are true:

1. It projects inside the image (pinhole or equidistant-fisheye model).
2. It is within the camera's maximum range.
3. The straight line from the camera to the point does not pass through any part of the
   car body or, optionally, another object.

A camera mounted more than 2 cm inside a car part, such as behind the windshield, looks
through that part as if it were glass.

An object is **seen** by a camera when at least one of its 4×4×4 sample points is
visible. The table reports the visible share and the pixel height of the seen part.

## Presets

Choose a preset from the File menu, or use `--preset tesla` or `--preset surround` on the command line.

### Tesla Vision (8 cameras)

`camsim/presets.py` holds the preset. The ranges and FOVs follow Tesla's published
specifications: narrow 35°/250 m, main 50°/150 m, wide 120°/60 m, B-pillar 90°/80 m,
repeaters 100 m and rear 50 m. **The mounting positions and angles are estimates.**
Replace them with your own measurements.

### Tesla Vision + 4 surround fisheyes (12 cameras)

This preset adds four low-mounted 190° × 140° fisheye cameras with a 15 m range. They
cover the near field that ultrasonic sensors would otherwise handle:

| Camera | Position (x, y, z) | Yaw / pitch |
|---|---|---|
| Surround front | front bumper (2.37, 0, 0.55) | 0° / −30° |
| Surround rear | above the rear bumper (−2.37, 0, 0.75) | 180° / −35° |
| Surround left / right | under the side mirrors (0.90, ±1.04, 0.94) | ±90° / −60° |

Within 1 m of the body at 10 cm height, these cameras reduce the blind area from about
7.7 m² to 0 m². The share of that area seen by two or more cameras rises from 7% to 63%.
