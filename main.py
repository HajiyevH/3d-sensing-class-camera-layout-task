"""Camera setup designer for the Tesla Model 3.

    python main.py                       # open the GUI with the Tesla preset
    python main.py --preset surround     # Tesla preset + 4 surround fisheyes
    python main.py configs/my_rig.json   # open the GUI with a saved setup
    python main.py configs/my_rig.json --report [--csv out.csv]   # no GUI
"""
import argparse

from camsim.presets import (demo_objects, tesla_vision_cameras,
                            tesla_vision_plus_surround)
from camsim.report import text_report, write_csv
from camsim.scene import Scene


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("config", nargs="?", help="setup JSON saved from the GUI")
    ap.add_argument("--preset", choices=("tesla", "surround"), default="tesla",
                    help="camera preset used when no config is given")
    ap.add_argument("--report", action="store_true", help="print a report, no GUI")
    ap.add_argument("--csv", help="write the per-camera visibility table to CSV")
    ap.add_argument("--height", type=float, default=0.5, help="coverage height (m)")
    ap.add_argument("--radius", type=float, default=5.0,
                    help="coverage statistics radius around the body (m)")
    args = ap.parse_args()

    scene = Scene()
    if args.config:
        scene.load(args.config)
    else:
        factory = tesla_vision_plus_surround if args.preset == "surround" else tesla_vision_cameras
        scene.cameras, scene.objects = factory(), demo_objects()

    if args.report or args.csv:
        if args.csv:
            write_csv(scene, args.csv)
            print(f"wrote {args.csv}")
        if args.report:
            print(text_report(scene, args.height, args.radius))
        return

    from camsim.gui import run
    run(scene)


if __name__ == "__main__":
    main()
