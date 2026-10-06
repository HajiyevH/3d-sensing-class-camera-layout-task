"""Tkinter + matplotlib GUI for interactive camera placement on the car."""
from __future__ import annotations

import math
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk

import matplotlib

matplotlib.use("TkAgg")
import numpy as np  # noqa: E402
from matplotlib.backends.backend_tkagg import (  # noqa: E402
    FigureCanvasTkAgg, NavigationToolbar2Tk)
from matplotlib.colors import ListedColormap  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.patches import Patch, Polygon  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Line3DCollection, Poly3DCollection  # noqa: E402

from .camera import PROJECTIONS, Camera  # noqa: E402
from .car import car_footprint, car_side_profile  # noqa: E402
from .presets import (CAMERA_PRESETS, OBJECT_TEMPLATES,  # noqa: E402
                      demo_objects, make_object, tesla_vision_cameras)
from .report import text_report, write_csv  # noqa: E402
from .scene import Scene  # noqa: E402

# (attribute, label, min, max, step)
CAM_FIELDS = [
    ("x", "X forward (m)", -4.0, 4.0, 0.01),
    ("y", "Y left (m)", -2.0, 2.0, 0.01),
    ("z", "Z up (m)", 0.0, 3.0, 0.01),
    ("yaw", "Yaw (deg)", -180, 180, 1),
    ("pitch", "Pitch (deg)", -90, 90, 1),
    ("roll", "Roll (deg)", -180, 180, 1),
    ("hfov", "H-FOV (deg)", 1, 220, 1),
    ("vfov", "V-FOV (deg)", 1, 180, 1),
    ("max_range", "Range (m)", 1, 300, 1),
]
OBJ_FIELDS = [
    ("x", "X (m)", -60.0, 60.0, 0.1),
    ("y", "Y (m)", -30.0, 30.0, 0.1),
    ("z", "Base height (m)", 0.0, 5.0, 0.05),
    ("yaw", "Yaw (deg)", -180, 180, 1),
    ("length", "Length (m)", 0.1, 20.0, 0.05),
    ("width", "Width (m)", 0.1, 5.0, 0.05),
    ("height", "Height (m)", 0.1, 6.0, 0.05),
]
SEEN_C, UNSEEN_C = "#2ca02c", "#d62728"
TABS = ("Top view", "3D view", "Side view", "Camera view", "All cameras")


class SliderField:
    """Label + slider + entry bound to one numeric value."""

    def __init__(self, parent, row, label, lo, hi, step, on_change):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w")
        self.var = tk.DoubleVar(value=lo)
        self.scale = ttk.Scale(parent, from_=lo, to=hi, orient="horizontal",
                               variable=self.var, command=self._on_scale)
        self.scale.grid(row=row, column=1, sticky="ew", padx=4, pady=1)
        self.text = tk.StringVar()
        self.entry = ttk.Entry(parent, textvariable=self.text, width=7)
        self.entry.grid(row=row, column=2, sticky="e")
        self.entry.bind("<Return>", self._on_entry)
        self.entry.bind("<FocusOut>", self._on_entry)
        self.step, self.on_change = step, on_change
        self.decimals = max(0, -int(math.floor(math.log10(step))))
        self._silent = False
        self._value = lo

    def _on_scale(self, _):
        if self._silent:
            return
        v = round(round(self.var.get() / self.step) * self.step, self.decimals)
        if v == self._value:
            return
        self._value = v
        self.text.set(f"{v:.{self.decimals}f}")
        self.on_change(v)

    def _on_entry(self, _):
        try:
            v = float(self.text.get())
        except ValueError:
            self.text.set(f"{self._value:.{self.decimals}f}")
            return
        if abs(v - self._value) < 1e-12:
            return
        self.set(v)
        self.on_change(v)

    def set(self, v):
        self._silent = True
        self._value = v
        self.var.set(v)
        self.text.set(f"{v:.{self.decimals}f}")
        self._silent = False

    def set_state(self, enabled: bool):
        st = ["!disabled"] if enabled else ["disabled"]
        self.scale.state(st)
        self.entry.state(st)


class CameraSetupApp:
    def __init__(self, root: tk.Tk, scene: Scene | None = None):
        self.root = root
        root.title("Camera Setup Designer - Tesla Model 3")
        root.geometry("1500x930")
        self.scene = scene or self._default_scene()
        self.cam_idx: int | None = 0 if self.scene.cameras else None
        self.obj_idx: int | None = 0 if self.scene.objects else None
        self._redraw_job = None
        self._dirty_tabs = set(TABS)
        self._coverage = None
        self._cov_dirty = True
        self._results = {}
        self._drag = None
        self._top_limits = None
        self._loading = False

        # View settings.
        self.v_show_cov = tk.BooleanVar(value=True)
        self.v_cov_h = tk.DoubleVar(value=0.5)
        self.v_extent = tk.DoubleVar(value=20.0)
        self.v_cov_res = tk.DoubleVar(value=0.25)
        self.v_radius = tk.DoubleVar(value=5.0)
        self.v_obj_shadow = tk.BooleanVar(value=False)
        self.v_obj_occlude = tk.BooleanVar(value=self.scene.objects_occlude)
        self.v_frustum = tk.DoubleVar(value=6.0)
        self.v_lock_aspect = tk.BooleanVar(value=False)
        self.v_new_kind = tk.StringVar(value="Pedestrian")
        self.v_status = tk.StringVar()

        self._build_menu()
        self._build_layout()
        self._refresh_lists()
        self._load_camera_editor()
        self._load_object_editor()
        self.request_redraw(10)

    @staticmethod
    def _default_scene() -> Scene:
        s = Scene()
        s.cameras = tesla_vision_cameras()
        s.objects = demo_objects()
        return s

    # ================================================================ layout
    def _build_menu(self):
        m = tk.Menu(self.root)
        f = tk.Menu(m, tearoff=False)
        f.add_command(label="New (empty rig)", command=self.new_scene)
        for name, factory in CAMERA_PRESETS.items():
            f.add_command(label=f"Load preset: {name}",
                          command=lambda fn=factory: self.load_preset(fn))
        f.add_separator()
        f.add_command(label="Open setup (JSON)...", command=self.open_json,
                      accelerator="Cmd/Ctrl+O")
        f.add_command(label="Save setup (JSON)...", command=self.save_json,
                      accelerator="Cmd/Ctrl+S")
        f.add_separator()
        f.add_command(label="Export current view (PNG)...", command=self.export_png)
        f.add_command(label="Export visibility report (CSV)...", command=self.export_csv)
        f.add_command(label="Show text report", command=self.show_report)
        f.add_separator()
        f.add_command(label="Quit", command=self.root.destroy)
        m.add_cascade(label="File", menu=f)
        self.root.config(menu=m)
        for mod in ("Command", "Control"):
            self.root.bind_all(f"<{mod}-o>", lambda e: self.open_json())
            self.root.bind_all(f"<{mod}-s>", lambda e: self.save_json())

    def _build_layout(self):
        paned = ttk.PanedWindow(self.root, orient="horizontal")
        paned.pack(fill="both", expand=True)
        left = ttk.Frame(paned, width=410)
        right = ttk.Frame(paned)
        paned.add(left, weight=0)
        paned.add(right, weight=1)

        ctrl = ttk.Notebook(left)
        ctrl.pack(fill="both", expand=True, padx=4, pady=4)
        self._build_camera_tab(ctrl)
        self._build_object_tab(ctrl)
        self._build_settings_tab(ctrl)

        self.views = ttk.Notebook(right)
        self.views.pack(fill="both", expand=True)
        self.figs, self.canvases, self.axes = {}, {}, {}
        for name in TABS:
            frame = ttk.Frame(self.views)
            self.views.add(frame, text=name)
            fig = Figure(figsize=(9, 7), dpi=100, layout="constrained")
            canvas = FigureCanvasTkAgg(fig, master=frame)
            NavigationToolbar2Tk(canvas, frame).update()
            canvas.get_tk_widget().pack(fill="both", expand=True)
            self.figs[name], self.canvases[name] = fig, canvas
            if name == "3D view":
                self.axes[name] = fig.add_subplot(111, projection="3d")
            elif name != "All cameras":
                self.axes[name] = fig.add_subplot(111)
        self.views.bind("<<NotebookTabChanged>>", lambda e: self._draw_current())

        top = self.canvases["Top view"]
        top.mpl_connect("button_press_event", self._on_press)
        top.mpl_connect("motion_notify_event", self._on_motion)
        top.mpl_connect("button_release_event", self._on_release)
        top.mpl_connect("scroll_event", self._on_scroll)

        ttk.Label(self.root, textvariable=self.v_status, anchor="w",
                  relief="sunken", padding=(6, 2)).pack(fill="x", side="bottom")

    def _build_camera_tab(self, nb):
        tab = ttk.Frame(nb, padding=6)
        nb.add(tab, text="Cameras")
        self.cam_list = tk.Listbox(tab, height=9, exportselection=False,
                                   font=("TkDefaultFont", 12))
        self.cam_list.pack(fill="x")
        self.cam_list.bind("<<ListboxSelect>>", self._on_cam_select)
        bar = ttk.Frame(tab)
        bar.pack(fill="x", pady=4)
        for txt, cmd in (("Add", self.add_camera), ("Duplicate", self.dup_camera),
                         ("Mirror L/R", self.mirror_camera), ("Delete", self.del_camera)):
            ttk.Button(bar, text=txt, command=cmd).pack(side="left", expand=True, fill="x")

        ed = ttk.LabelFrame(tab, text="Selected camera", padding=6)
        ed.pack(fill="both", expand=True)
        ed.columnconfigure(1, weight=1)
        ttk.Label(ed, text="Name").grid(row=0, column=0, sticky="w")
        self.cam_name = tk.StringVar()
        e = ttk.Entry(ed, textvariable=self.cam_name)
        e.grid(row=0, column=1, columnspan=2, sticky="ew")
        e.bind("<Return>", self._on_cam_name)
        e.bind("<FocusOut>", self._on_cam_name)

        self.cam_enabled = tk.BooleanVar()
        ttk.Checkbutton(ed, text="Enabled", variable=self.cam_enabled,
                        command=lambda: self._set_cam("enabled", self.cam_enabled.get())
                        ).grid(row=1, column=0, sticky="w")
        self.cam_proj = tk.StringVar()
        cb = ttk.Combobox(ed, textvariable=self.cam_proj, values=PROJECTIONS,
                          state="readonly", width=9)
        cb.grid(row=1, column=1, sticky="w")
        cb.bind("<<ComboboxSelected>>", lambda e: self._set_cam("projection", self.cam_proj.get()))
        self.color_btn = tk.Button(ed, text="Color", width=6, command=self._pick_cam_color)
        self.color_btn.grid(row=1, column=2, sticky="e")

        self.cam_fields = {}
        for i, (attr, label, lo, hi, step) in enumerate(CAM_FIELDS, start=2):
            self.cam_fields[attr] = SliderField(
                ed, i, label, lo, hi, step, lambda v, a=attr: self._set_cam(a, v))
        r = len(CAM_FIELDS) + 2
        ttk.Label(ed, text="Resolution (px)").grid(row=r, column=0, sticky="w")
        res = ttk.Frame(ed)
        res.grid(row=r, column=1, columnspan=2, sticky="ew")
        self.cam_w, self.cam_h = tk.StringVar(), tk.StringVar()
        for var, attr in ((self.cam_w, "width_px"), (self.cam_h, "height_px")):
            en = ttk.Entry(res, textvariable=var, width=7)
            en.pack(side="left", padx=2)
            en.bind("<Return>", lambda e, a=attr, v=var: self._set_cam_int(a, v))
            en.bind("<FocusOut>", lambda e, a=attr, v=var: self._set_cam_int(a, v))
        ttk.Checkbutton(ed, text="Lock V-FOV to sensor aspect ratio",
                        variable=self.v_lock_aspect, command=self._apply_aspect
                        ).grid(row=r + 1, column=0, columnspan=3, sticky="w")
        self.cam_info = ttk.Label(ed, text="", foreground="#555", wraplength=370)
        self.cam_info.grid(row=r + 2, column=0, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Label(tab, text="Top view: drag a camera to move it, scroll to change "
                            "yaw (Shift+scroll: pitch). Right-click to add here.",
                  foreground="#666", wraplength=380).pack(fill="x", pady=4)

    def _build_object_tab(self, nb):
        tab = ttk.Frame(nb, padding=6)
        nb.add(tab, text="Objects")
        self.obj_list = tk.Listbox(tab, height=6, exportselection=False,
                                   font=("TkDefaultFont", 12))
        self.obj_list.pack(fill="x")
        self.obj_list.bind("<<ListboxSelect>>", self._on_obj_select)
        bar = ttk.Frame(tab)
        bar.pack(fill="x", pady=4)
        ttk.Combobox(bar, textvariable=self.v_new_kind, values=list(OBJECT_TEMPLATES),
                     state="readonly", width=13).pack(side="left")
        ttk.Button(bar, text="Add", command=self.add_object).pack(side="left", fill="x", expand=True)
        ttk.Button(bar, text="Delete", command=self.del_object).pack(side="left", fill="x", expand=True)

        ed = ttk.LabelFrame(tab, text="Selected object", padding=6)
        ed.pack(fill="x")
        ed.columnconfigure(1, weight=1)
        ttk.Label(ed, text="Name").grid(row=0, column=0, sticky="w")
        self.obj_name = tk.StringVar()
        e = ttk.Entry(ed, textvariable=self.obj_name)
        e.grid(row=0, column=1, columnspan=2, sticky="ew")
        e.bind("<Return>", self._on_obj_name)
        e.bind("<FocusOut>", self._on_obj_name)
        self.obj_fields = {}
        for i, (attr, label, lo, hi, step) in enumerate(OBJ_FIELDS, start=1):
            self.obj_fields[attr] = SliderField(
                ed, i, label, lo, hi, step, lambda v, a=attr: self._set_obj(a, v))

        res = ttk.LabelFrame(tab, text="Is it seen?  (all objects)", padding=4)
        res.pack(fill="both", expand=True, pady=(6, 0))
        self.res_tree = ttk.Treeview(res, columns=("n", "cams", "px"), height=6)
        self.res_tree.heading("#0", text="Object")
        self.res_tree.heading("n", text="#cams")
        self.res_tree.heading("cams", text="Seen by")
        self.res_tree.heading("px", text="max px")
        self.res_tree.column("#0", width=120)
        self.res_tree.column("n", width=45, anchor="center")
        self.res_tree.column("cams", width=160)
        self.res_tree.column("px", width=50, anchor="e")
        self.res_tree.tag_configure("seen", background="#e2f4e2")
        self.res_tree.tag_configure("unseen", background="#fbe1e1")
        self.res_tree.pack(fill="both", expand=True)
        self.res_tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        det = ttk.LabelFrame(tab, text="Selected object per camera", padding=4)
        det.pack(fill="both", expand=True, pady=(6, 0))
        cols = ("vis", "fov", "dist", "px")
        self.det_tree = ttk.Treeview(det, columns=cols, height=8)
        for c, t, w in zip(("#0",) + cols, ("Camera", "visible %", "in FOV %", "dist m", "px h"),
                           (130, 65, 65, 55, 50)):
            self.det_tree.heading(c, text=t)
            self.det_tree.column(c, width=w, anchor="w" if c == "#0" else "e")
        self.det_tree.tag_configure("seen", background="#e2f4e2")
        self.det_tree.tag_configure("unseen", background="#fbe1e1")
        self.det_tree.pack(fill="both", expand=True)

    def _build_settings_tab(self, nb):
        tab = ttk.Frame(nb, padding=8)
        nb.add(tab, text="View / Analysis")
        tab.columnconfigure(1, weight=1)
        r = 0

        def row_scale(label, var, lo, hi, step, cov=True):
            nonlocal r
            f = SliderField(tab, r, label, lo, hi, step,
                            lambda v: (var.set(v), self._settings_changed(cov)))
            f.set(var.get())
            r += 1
            return f

        ttk.Checkbutton(tab, text="Show coverage heat-map (number of cameras)",
                        variable=self.v_show_cov,
                        command=lambda: self._settings_changed(True)
                        ).grid(row=r, column=0, columnspan=3, sticky="w")
        r += 1
        row_scale("Map height (m)", self.v_cov_h, 0.0, 3.0, 0.05)
        row_scale("Map extent (m)", self.v_extent, 5, 150, 1)
        row_scale("Map cell (m)", self.v_cov_res, 0.05, 2.0, 0.05)
        row_scale("Stats radius (m)", self.v_radius, 0.5, 50, 0.5)
        ttk.Checkbutton(tab, text="Objects cast shadows in the coverage map",
                        variable=self.v_obj_shadow,
                        command=lambda: self._settings_changed(True)
                        ).grid(row=r, column=0, columnspan=3, sticky="w")
        r += 1
        ttk.Checkbutton(tab, text="Objects occlude each other (visibility check)",
                        variable=self.v_obj_occlude, command=self._toggle_occlude
                        ).grid(row=r, column=0, columnspan=3, sticky="w")
        r += 1
        row_scale("3D frustum length (m)", self.v_frustum, 0.5, 60, 0.5, cov=False)
        self.stats_lbl = ttk.Label(tab, text="", justify="left", wraplength=380,
                                   font=("TkFixedFont", 11))
        self.stats_lbl.grid(row=r, column=0, columnspan=3, sticky="w", pady=10)
        r += 1
        help_txt = (
            "Frame: x forward, y left, z up; origin on the ground under the car "
            "centre. Yaw 0 = forward, +90 = left, 180 = backward; pitch > 0 = up.\n\n"
            "A camera sitting >2 cm inside a car part (e.g. behind the windshield) "
            "looks through that part as glass; every other part of the car body "
            "blocks the view.\n\n"
            "An object counts as seen when at least one of its 4x4x4 sample points "
            "is inside the image, within range and not occluded.")
        ttk.Label(tab, text=help_txt, foreground="#555", wraplength=380,
                  justify="left").grid(row=r, column=0, columnspan=3, sticky="w")

    # ========================================================== list / edit
    @property
    def cam(self) -> Camera | None:
        if self.cam_idx is None or self.cam_idx >= len(self.scene.cameras):
            return None
        return self.scene.cameras[self.cam_idx]

    @property
    def obj(self):
        if self.obj_idx is None or self.obj_idx >= len(self.scene.objects):
            return None
        return self.scene.objects[self.obj_idx]

    def _refresh_lists(self):
        self.cam_list.delete(0, "end")
        for i, c in enumerate(self.scene.cameras):
            self.cam_list.insert("end", f"{'●' if c.enabled else '○'}  {c.name}")
            self.cam_list.itemconfig(i, foreground=c.color)
        if self.cam is not None:
            self.cam_list.selection_set(self.cam_idx)
        self.obj_list.delete(0, "end")
        for o in self.scene.objects:
            self.obj_list.insert("end", f"{o.name}  [{o.kind}]")
        if self.obj is not None:
            self.obj_list.selection_set(self.obj_idx)

    def _load_camera_editor(self):
        c = self.cam
        for f in self.cam_fields.values():
            f.set_state(c is not None)
        if c is None:
            self.cam_name.set("")
            self.cam_info.config(text="No camera selected.")
            return
        self.cam_name.set(c.name)
        self.cam_enabled.set(c.enabled)
        self.cam_proj.set(c.projection)
        self.color_btn.config(bg=c.color, highlightbackground=c.color)
        for attr, f in self.cam_fields.items():
            f.set(getattr(c, attr))
        self.cam_w.set(str(c.width_px))
        self.cam_h.set(str(c.height_px))
        self._update_cam_info()

    def _update_cam_info(self):
        c = self.cam
        if c is None:
            return
        inside = self.scene.mounted_inside(c)
        fx, _ = c._focal()
        ppd = fx * (math.radians(1) if c.projection == "fisheye"
                    else math.tan(math.radians(1)))
        txt = (f"~{ppd:.1f} px/deg at image centre.  "
               + (f"Mounted inside: {', '.join(inside)} (sees through it)."
                  if inside else "Mounted outside the body."))
        self.cam_info.config(text=txt)

    def _load_object_editor(self):
        o = self.obj
        for f in self.obj_fields.values():
            f.set_state(o is not None)
        if o is None:
            self.obj_name.set("")
            return
        self.obj_name.set(o.name)
        for attr, f in self.obj_fields.items():
            f.set(getattr(o, attr))
        self._update_detail_tree()

    def _on_cam_select(self, _):
        sel = self.cam_list.curselection()
        if sel:
            self.cam_idx = sel[0]
            self._load_camera_editor()
            self._dirty_tabs = set(TABS)
            self._draw_current()

    def _on_obj_select(self, _):
        sel = self.obj_list.curselection()
        if sel:
            self.obj_idx = sel[0]
            self._load_object_editor()
            self._dirty_tabs = set(TABS)
            self._draw_current()

    def _on_tree_select(self, _):
        sel = self.res_tree.selection()
        if sel:
            idx = self.res_tree.index(sel[0])
            if idx != self.obj_idx:
                self.obj_idx = idx
                self.obj_list.selection_clear(0, "end")
                self.obj_list.selection_set(idx)
                self._load_object_editor()
                self._dirty_tabs = set(TABS)
                self._draw_current()

    def _set_cam(self, attr, value):
        c = self.cam
        if c is None:
            return
        setattr(c, attr, value)
        if attr in ("hfov", "projection") and self.v_lock_aspect.get():
            self._apply_aspect()
        if attr in ("enabled",):
            self._refresh_lists()
        self._update_cam_info()
        self.request_redraw()

    def _set_cam_int(self, attr, var):
        c = self.cam
        try:
            v = int(float(var.get()))
        except ValueError:
            return
        if c is None or v <= 0 or getattr(c, attr) == v:
            return
        self._set_cam(attr, v)
        if self.v_lock_aspect.get():
            self._apply_aspect()

    def _apply_aspect(self):
        c = self.cam
        if c is None or not self.v_lock_aspect.get():
            return
        ratio = c.height_px / c.width_px
        if c.projection == "fisheye":
            v = c.hfov * ratio
        else:
            v = math.degrees(2 * math.atan(math.tan(math.radians(min(c.hfov, 179)) / 2) * ratio))
        c.vfov = round(v, 1)
        self.cam_fields["vfov"].set(c.vfov)
        self.request_redraw()

    def _on_cam_name(self, _):
        c = self.cam
        if c and self.cam_name.get().strip() and self.cam_name.get() != c.name:
            c.name = self.cam_name.get().strip()
            self._refresh_lists()
            self.request_redraw()

    def _pick_cam_color(self):
        c = self.cam
        if c is None:
            return
        col = colorchooser.askcolor(c.color, title="Camera colour")[1]
        if col:
            c.color = col
            self.color_btn.config(bg=col, highlightbackground=col)
            self._refresh_lists()
            self.request_redraw(coverage=False)

    def _set_obj(self, attr, value):
        o = self.obj
        if o is None:
            return
        setattr(o, attr, value)
        self.request_redraw(coverage=self.v_obj_shadow.get())

    def _on_obj_name(self, _):
        o = self.obj
        if o and self.obj_name.get().strip() and self.obj_name.get() != o.name:
            o.name = self.obj_name.get().strip()
            self._refresh_lists()
            self.request_redraw(coverage=False)

    # ---------------------------------------------------------- add / delete
    def add_camera(self, x=0.0, y=0.0, z=1.45, yaw=0.0):
        n = len(self.scene.cameras) + 1
        palette = matplotlib.colormaps["tab10"].colors
        col = matplotlib.colors.to_hex(palette[n % len(palette)])
        self.scene.cameras.append(Camera(f"Camera {n}", x, y, z, yaw, 0, 0, 90, 70, 50,
                                         color=col))
        self.cam_idx = len(self.scene.cameras) - 1
        self._after_structure_change()

    def dup_camera(self):
        c = self.cam
        if c is None:
            return
        d = Camera.from_dict(c.to_dict())
        d.name = c.name + " copy"
        self.scene.cameras.append(d)
        self.cam_idx = len(self.scene.cameras) - 1
        self._after_structure_change()

    def mirror_camera(self):
        """Duplicate the camera mirrored to the other side of the car."""
        c = self.cam
        if c is None:
            return
        d = Camera.from_dict(c.to_dict())
        d.y, d.yaw, d.roll = -c.y, -c.yaw, -c.roll
        for a, b in (("left", "right"), ("Left", "Right"), ("L", "R")):
            if a in c.name:
                d.name = c.name.replace(a, b)
                break
            if b in c.name:
                d.name = c.name.replace(b, a)
                break
        else:
            d.name = c.name + " (mirror)"
        self.scene.cameras.append(d)
        self.cam_idx = len(self.scene.cameras) - 1
        self._after_structure_change()

    def del_camera(self):
        if self.cam is None:
            return
        del self.scene.cameras[self.cam_idx]
        self.cam_idx = min(self.cam_idx, len(self.scene.cameras) - 1) if self.scene.cameras else None
        self._after_structure_change()

    def add_object(self, x=6.0, y=0.0):
        kind = self.v_new_kind.get()
        n = sum(o.kind == kind for o in self.scene.objects) + 1
        self.scene.objects.append(make_object(kind, x, y, name=f"{kind} {n}"))
        self.obj_idx = len(self.scene.objects) - 1
        self._after_structure_change()

    def del_object(self):
        if self.obj is None:
            return
        del self.scene.objects[self.obj_idx]
        self.obj_idx = min(self.obj_idx, len(self.scene.objects) - 1) if self.scene.objects else None
        self._after_structure_change()

    def _after_structure_change(self):
        self._refresh_lists()
        self._load_camera_editor()
        self._load_object_editor()
        self.request_redraw()

    def _toggle_occlude(self):
        self.scene.objects_occlude = self.v_obj_occlude.get()
        self.request_redraw(coverage=False)

    def _settings_changed(self, coverage):
        if coverage:
            self._top_limits = None
        self.request_redraw(coverage=coverage)

    # ================================================================ files
    def new_scene(self):
        self.scene.cameras, self.scene.objects = [], []
        self.cam_idx = self.obj_idx = None
        self._after_structure_change()

    def load_preset(self, factory):
        self.scene.cameras = factory()
        if not self.scene.objects:
            self.scene.objects = demo_objects()
        self.cam_idx, self.obj_idx = 0, 0 if self.scene.objects else None
        self._after_structure_change()

    def open_json(self):
        path = filedialog.askopenfilename(filetypes=[("Camera setup", "*.json")])
        if not path:
            return
        try:
            self.scene.load(path)
        except Exception as exc:  # show any parse error to the user
            messagebox.showerror("Open failed", str(exc))
            return
        self.v_obj_occlude.set(self.scene.objects_occlude)
        self.cam_idx = 0 if self.scene.cameras else None
        self.obj_idx = 0 if self.scene.objects else None
        self._after_structure_change()

    def save_json(self):
        path = filedialog.asksaveasfilename(defaultextension=".json",
                                            filetypes=[("Camera setup", "*.json")])
        if path:
            self.scene.save(path)
            self.v_status.set(f"Saved {path}")

    def export_png(self):
        name = self.views.tab(self.views.select(), "text")
        path = filedialog.asksaveasfilename(defaultextension=".png",
                                            initialfile=name.replace(" ", "_").lower())
        if path:
            self.figs[name].savefig(path, dpi=200)

    def export_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv",
                                            initialfile="visibility_report.csv")
        if path:
            write_csv(self.scene, path)

    def show_report(self):
        win = tk.Toplevel(self.root)
        win.title("Visibility report")
        txt = tk.Text(win, width=120, height=40, font=("TkFixedFont", 11))
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", text_report(self.scene, self.v_cov_h.get(), self.v_radius.get()))

    # ============================================================== redraw
    def request_redraw(self, delay=60, coverage=True):
        self._cov_dirty |= coverage
        if self._redraw_job is not None:
            self.root.after_cancel(self._redraw_job)
        self._redraw_job = self.root.after(delay, self._redraw)

    def _redraw(self):
        self._redraw_job = None
        self._results = {id(o): self.scene.object_visibility(o) for o in self.scene.objects}
        self._update_result_trees()
        if self._cov_dirty and self._drag is None:
            self._compute_coverage()
        self._dirty_tabs = set(TABS)
        self._draw_current()

    def _compute_coverage(self):
        self._cov_dirty = False
        if not self.v_show_cov.get():
            self._coverage = None
            self.stats_lbl.config(text="")
            self.v_status.set(f"{sum(c.enabled for c in self.scene.cameras)} active cameras")
            return
        extent = self.v_extent.get()
        res = max(self.v_cov_res.get(), extent / 200)   # keep it interactive
        h = self.v_cov_h.get()
        xs, ys, cnt = self.scene.coverage_grid(extent, res, h, self.v_obj_shadow.get())
        self._coverage = (xs, ys, cnt)
        st = self.scene.coverage_stats(xs, ys, cnt, self.v_radius.get())
        if not st:
            return
        txt = (f"Coverage @ h={h:.2f} m, within {self.v_radius.get():.1f} m of body\n"
               f"  >= 1 camera : {st['covered_1']:6.1f} %\n"
               f"  >= 2 cameras: {st['covered_2']:6.1f} %\n"
               f"  blind area  : {st['blind_area_m2']:6.1f} m²\n"
               f"  farthest blind point from body: {st['max_blind_dist']:.2f} m")
        self.stats_lbl.config(text=txt)
        n_seen = sum(any(h.visible for h in r.values()) for r in self._results.values())
        self.v_status.set(
            f"{sum(c.enabled for c in self.scene.cameras)} active cameras  |  "
            f"objects seen: {n_seen}/{len(self.scene.objects)}  |  "
            f"coverage (h={h:.2f} m, ≤{self.v_radius.get():.1f} m from body): "
            f"≥1 cam {st['covered_1']:.1f}%, ≥2 cams {st['covered_2']:.1f}%, "
            f"blind {st['blind_area_m2']:.1f} m²")

    def _update_result_trees(self):
        self.res_tree.delete(*self.res_tree.get_children())
        for i, o in enumerate(self.scene.objects):
            hits = {k: v for k, v in self._results[id(o)].items() if v.visible}
            px = max((v.px_height for v in hits.values()), default=0)
            iid = self.res_tree.insert("", "end", text=o.name, values=(
                len(hits), ", ".join(hits) or "— not seen —", f"{px:.0f}"),
                tags=("seen" if hits else "unseen",))
            if i == self.obj_idx:
                self.res_tree.selection_set(iid)
        self._update_detail_tree()

    def _update_detail_tree(self):
        self.det_tree.delete(*self.det_tree.get_children())
        o = self.obj
        if o is None or id(o) not in self._results:
            return
        for name, h in self._results[id(o)].items():
            self.det_tree.insert("", "end", text=name, values=(
                f"{h.fraction * 100:.0f}", f"{h.in_fov_fraction * 100:.0f}",
                f"{h.distance:.1f}", f"{h.px_height:.0f}"),
                tags=("seen" if h.visible else "unseen",))

    def _draw_current(self):
        name = self.views.tab(self.views.select(), "text")
        if name not in self._dirty_tabs:
            return
        self._dirty_tabs.discard(name)
        {"Top view": self._draw_top, "3D view": self._draw_3d,
         "Side view": self._draw_side, "Camera view": self._draw_camera,
         "All cameras": self._draw_all_cameras}[name]()
        self.canvases[name].draw_idle()

    def _obj_seen(self, o) -> bool:
        return any(h.visible for h in self._results.get(id(o), {}).values())

    # ------------------------------------------------------------ top view
    def _draw_top(self):
        ax = self.axes["Top view"]
        prev = (ax.get_xlim(), ax.get_ylim()) if ax.has_data() else None
        ax.cla()
        ext = self.v_extent.get()
        handles = []
        if self.v_show_cov.get() and self._coverage is not None:
            xs, ys, cnt = self._coverage
            nmax = max(3, int(np.nanmax(cnt)) if np.isfinite(cnt).any() else 3)
            colors = ["#f4a6a6", "#fde9a9"] + list(
                matplotlib.colormaps["Greens"](np.linspace(0.35, 0.9, nmax - 1)))
            cmap = ListedColormap(colors[:nmax + 1])
            d = (xs[1] - xs[0]) / 2
            ax.imshow(cnt, origin="lower", cmap=cmap, vmin=-0.5, vmax=nmax + 0.5,
                      extent=[xs[0] - d, xs[-1] + d, ys[0] - d, ys[-1] + d],
                      interpolation="nearest", alpha=0.85, zorder=0)
            handles = [Patch(color=colors[0], label="blind (0 cams)"),
                       Patch(color=colors[1], label="1 cam"),
                       Patch(color=colors[2], label="2 cams"),
                       Patch(color=colors[min(3, nmax)], label="3+ cams")]

        spec = self.scene.car_spec
        ax.add_patch(Polygon(car_footprint(spec), closed=True, fc="#c8ced6",
                             ec="#333", lw=1.2, zorder=3))
        ax.plot([1.05, 1.05], [-0.8, 0.8], color="#5b7488", lw=2, zorder=3)
        ax.plot([-1.95, -1.95], [-0.8, 0.8], color="#5b7488", lw=2, zorder=3)
        ax.annotate("", xy=(spec.front_x - 0.2, 0), xytext=(spec.front_x - 1.0, 0),
                    arrowprops=dict(arrowstyle="->", color="#333"), zorder=4)

        wedge_r_cap = ext * 1.5
        for i, c in enumerate(self.scene.cameras):
            if not c.enabled:
                continue
            sel = i == self.cam_idx
            az = np.unwrap(np.radians(c.horizontal_extent()))
            r = min(c.max_range, wedge_r_cap)
            pts = np.vstack([[c.x, c.y], np.stack(
                [c.x + r * np.cos(az), c.y + r * np.sin(az)], 1), [c.x, c.y]])
            ax.fill(pts[:, 0], pts[:, 1], color=c.color, alpha=0.10 if not sel else 0.22,
                    zorder=1)
            ax.plot(pts[:, 0], pts[:, 1], color=c.color, lw=2.4 if sel else 1.0,
                    alpha=0.9, zorder=2)
            fwd = c.forward
            ax.plot(c.x, c.y, "o", ms=9 if sel else 6, mfc=c.color, mec="k",
                    mew=1.5 if sel else 0.6, zorder=6)
            ax.plot([c.x, c.x + 0.6 * fwd[0]], [c.y, c.y + 0.6 * fwd[1]],
                    color=c.color, lw=2, zorder=5)
            if sel:
                ax.annotate(c.name, (c.x, c.y), xytext=(6, 6), textcoords="offset points",
                            fontsize=9, weight="bold", zorder=7)

        for i, o in enumerate(self.scene.objects):
            seen = self._obj_seen(o)
            corners = o.corners()[[0, 2, 6, 4], :2]
            ax.add_patch(Polygon(corners, closed=True, fc=o.color,
                                 ec=SEEN_C if seen else UNSEEN_C,
                                 lw=3 if i == self.obj_idx else 1.8, zorder=5))
            ax.annotate(("✓ " if seen else "✗ ") + o.name, (o.x, o.y),
                        xytext=(0, 8 + o.width * 4), textcoords="offset points",
                        ha="center", fontsize=8, color=SEEN_C if seen else UNSEEN_C,
                        zorder=7)

        ax.set_aspect("equal")
        ax.set_xlabel("x  forward (m)")
        ax.set_ylabel("y  left (m)")
        ax.grid(alpha=0.25)
        if self._top_limits is not None and prev is not None:
            ax.set_xlim(*prev[0])
            ax.set_ylim(*prev[1])
        else:
            ax.set_xlim(-ext, ext)
            ax.set_ylim(-ext * 0.75, ext * 0.75)
            self._top_limits = True
        title = "Top view - horizontal FOV wedges"
        if self.v_show_cov.get():
            title += f" + coverage at h = {self.v_cov_h.get():.2f} m"
        ax.set_title(title)
        if handles:
            ax.legend(handles=handles, loc="upper right", fontsize=8, framealpha=0.85)

    # Mouse interaction on the top view ----------------------------------
    def _toolbar_busy(self):
        return bool(self.canvases["Top view"].toolbar.mode)

    def _pick(self, x, y):
        ax = self.axes["Top view"]
        tol = 0.025 * (ax.get_xlim()[1] - ax.get_xlim()[0])
        best = None
        for i, c in enumerate(self.scene.cameras):
            d = math.hypot(c.x - x, c.y - y)
            if d < tol and (best is None or d < best[2]):
                best = ("cam", i, d)
        if best:
            return best
        for i, o in enumerate(self.scene.objects):
            local = np.array([x - o.x, y - o.y])
            a = math.radians(-o.yaw)
            lx = local[0] * math.cos(a) - local[1] * math.sin(a)
            ly = local[0] * math.sin(a) + local[1] * math.cos(a)
            if abs(lx) <= o.length / 2 + tol / 2 and abs(ly) <= o.width / 2 + tol / 2:
                return ("obj", i, 0)
        return None

    def _on_press(self, ev):
        if ev.inaxes is None or self._toolbar_busy() or ev.xdata is None:
            return
        right = ev.button == 3 or (ev.button == 1 and ev.key == "control")
        if right:
            self._context_menu(ev)
            return
        if ev.button != 1:
            return
        hit = self._pick(ev.xdata, ev.ydata)
        if hit is None:
            return
        kind, idx, _ = hit
        if kind == "cam":
            self.cam_idx = idx
            self.cam_list.selection_clear(0, "end")
            self.cam_list.selection_set(idx)
            self._load_camera_editor()
            target = self.cam
        else:
            self.obj_idx = idx
            self.obj_list.selection_clear(0, "end")
            self.obj_list.selection_set(idx)
            self._load_object_editor()
            target = self.obj
        self._drag = (kind, target, ev.xdata - target.x, ev.ydata - target.y)
        self.request_redraw(10, coverage=False)

    def _on_motion(self, ev):
        if self._drag is None or ev.xdata is None:
            return
        kind, target, ox, oy = self._drag
        step = 0.01 if kind == "cam" else 0.1
        target.x = round((ev.xdata - ox) / step) * step
        target.y = round((ev.ydata - oy) / step) * step
        fields = self.cam_fields if kind == "cam" else self.obj_fields
        fields["x"].set(target.x)
        fields["y"].set(target.y)
        if kind == "cam":
            self._update_cam_info()
        self.request_redraw(30, coverage=kind == "cam" or self.v_obj_shadow.get())

    def _on_release(self, _):
        if self._drag is not None:
            self._drag = None
            self.request_redraw(10, coverage=self._cov_dirty)

    def _on_scroll(self, ev):
        if ev.inaxes is None:
            return
        delta = 3 if ev.button == "up" else -3
        hit = self._pick(ev.xdata, ev.ydata) if ev.xdata is not None else None
        if hit and hit[0] == "obj":
            o = self.scene.objects[hit[1]]
            o.yaw = (o.yaw + delta + 180) % 360 - 180
            self.obj_idx = hit[1]
            self._load_object_editor()
            self.request_redraw(30, coverage=self.v_obj_shadow.get())
            return
        c = self.cam
        if c is None:
            return
        if ev.key == "shift":
            c.pitch = float(np.clip(c.pitch + delta, -90, 90))
            self.cam_fields["pitch"].set(c.pitch)
        else:
            c.yaw = (c.yaw + delta + 180) % 360 - 180
            self.cam_fields["yaw"].set(c.yaw)
        self.request_redraw(40)

    def _context_menu(self, ev):
        x, y = ev.xdata, ev.ydata
        menu = tk.Menu(self.root, tearoff=False)
        menu.add_command(label=f"Add {self.v_new_kind.get()} here ({x:.1f}, {y:.1f})",
                         command=lambda: self.add_object(round(x, 1), round(y, 1)))
        for kind in OBJECT_TEMPLATES:
            if kind != self.v_new_kind.get():
                menu.add_command(label=f"   ... or {kind}",
                                 command=lambda k=kind: (self.v_new_kind.set(k),
                                                         self.add_object(round(x, 1), round(y, 1))))
        menu.add_separator()
        menu.add_command(label="Add camera here (aimed outwards)",
                         command=lambda: self.add_camera(
                             round(x, 2), round(y, 2), 1.2,
                             round(math.degrees(math.atan2(y, x)))))
        if self.cam is not None:
            menu.add_command(label=f"Aim '{self.cam.name}' at this point",
                             command=lambda: self._aim_camera(x, y))
        g = ev.guiEvent
        menu.tk_popup(g.x_root, g.y_root)

    def _aim_camera(self, x, y):
        c = self.cam
        c.yaw = round(math.degrees(math.atan2(y - c.y, x - c.x)), 1)
        self.cam_fields["yaw"].set(c.yaw)
        self.request_redraw()

    # -------------------------------------------------------------- 3D view
    def _draw_3d(self):
        ax = self.axes["3D view"]
        elev, azim = (ax.elev, ax.azim) if ax.has_data() else (25, -135)
        ax.cla()
        light = np.array([0.4, 0.3, 0.86]) / np.linalg.norm([0.4, 0.3, 0.86])
        for part in self.scene.car_parts:
            tris = part.triangles
            n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
            n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
            shade = 0.5 + 0.5 * np.clip(n @ light, 0, 1)
            base = np.array(matplotlib.colors.to_rgb(part.color))
            fc = np.clip(base * shade[:, None], 0, 1)
            ax.add_collection3d(Poly3DCollection(
                tris, facecolors=fc, edgecolors=fc, linewidths=0.2,
                alpha=0.75 if part.name == "cabin" else 1.0))

        L = self.v_frustum.get()
        for i, c in enumerate(self.scene.cameras):
            if not c.enabled:
                continue
            length = min(L, c.max_range)
            border, corners = c.frustum_outline(length, 10)
            apex = c.position
            faces = [[apex, border[j], border[(j + 1) % len(border)]]
                     for j in range(len(border))]
            sel = i == self.cam_idx
            ax.add_collection3d(Poly3DCollection(
                faces, facecolors=c.color, edgecolors="none",
                alpha=0.16 if sel else 0.07))
            lines = [[apex, k] for k in corners] + [
                [border[j], border[(j + 1) % len(border)]] for j in range(len(border))]
            ax.add_collection3d(Line3DCollection(
                lines, colors=c.color, linewidths=2.0 if sel else 0.8))
            ax.scatter(*apex, color=c.color, s=40 if sel else 15, edgecolors="k")

        for o in self.scene.objects:
            v = o.corners()
            quads = [v[[0, 1, 3, 2]], v[[4, 5, 7, 6]], v[[0, 1, 5, 4]],
                     v[[2, 3, 7, 6]], v[[0, 2, 6, 4]], v[[1, 3, 7, 5]]]
            ax.add_collection3d(Poly3DCollection(
                quads, facecolors=o.color, alpha=0.85,
                edgecolors=SEEN_C if self._obj_seen(o) else UNSEEN_C, linewidths=1.5))

        span = max(4.0, L * 1.05)
        g = np.arange(-math.ceil(span), math.ceil(span) + 1, max(1, round(span / 10)))
        grid = [[[a, g[0], 0], [a, g[-1], 0]] for a in g] + \
               [[[g[0], a, 0], [g[-1], a, 0]] for a in g]
        ax.add_collection3d(Line3DCollection(grid, colors="#bbbbbb", linewidths=0.4))
        zmax = max(2.0, min(span, 1.5 + L * 0.6))
        ax.set_xlim(-span, span)
        ax.set_ylim(-span, span)
        ax.set_zlim(0, zmax)
        ax.set_box_aspect((1, 1, zmax / (2 * span)))
        ax.set_xlabel("x fwd (m)")
        ax.set_ylabel("y left (m)")
        ax.set_zlabel("z (m)")
        ax.view_init(elev, azim)
        ax.set_title(f"3D view - frusta drawn to {L:.1f} m (drag to rotate)")

    # ------------------------------------------------------------ side view
    def _draw_side(self):
        ax = self.axes["Side view"]
        ax.cla()
        spec = self.scene.car_spec
        ax.add_patch(Polygon(car_side_profile(spec), closed=True, fc="#c8ced6",
                             ec="#333", lw=1.2, zorder=3))
        for ax_x in (spec.front_axle_x, spec.rear_axle_x):
            ax.add_patch(matplotlib.patches.Circle((ax_x, spec.wheel_radius),
                                                   spec.wheel_radius, fc="#2b2b2b", zorder=4))
        ax.axhline(0, color="#555", lw=1)
        Ls = 10.0
        notes = []
        for i, c in enumerate(self.scene.cameras):
            sel = i == self.cam_idx
            if not c.enabled or (abs(c.forward[1]) > 0.5 and not sel):
                continue
            rays = c.pixel_rays(np.array([c.width_px / 2] * 2), np.array([0, c.height_px]))
            for k, d in enumerate(rays):
                t = min(Ls * 2, c.max_range)
                if d[2] < -1e-9:
                    t = min(t, -c.z / d[2])
                end = c.position + d * t
                ax.plot([c.x, end[0]], [c.z, end[2]], color=c.color,
                        lw=2.2 if sel else 1.0, zorder=5)
            g = self._nearest_ground(c)
            if g is not None:
                front = g[0] > 0
                gap = abs(g[0] - (spec.front_x if front else spec.rear_x))
                notes.append(f"{c.name}: ground visible from {gap:.2f} m past the "
                             f"{'front' if front else 'rear'} bumper")
                ax.plot(g[0], 0, "v", color=c.color, ms=8, mec="k", zorder=6)
            ax.plot(c.x, c.z, "o", mfc=c.color, mec="k", ms=8 if sel else 5, zorder=6)
        if notes:
            ax.text(0.01, 0.98, "\n".join(notes), transform=ax.transAxes, va="top",
                    fontsize=8, bbox=dict(fc="w", alpha=0.85, lw=0.5))
        for o in self.scene.objects:
            xs = o.corners()[:, 0]
            ax.add_patch(matplotlib.patches.Rectangle(
                (xs.min(), o.z), xs.max() - xs.min(), o.height, fc=o.color, alpha=0.6,
                ec=SEEN_C if self._obj_seen(o) else UNSEEN_C, lw=1.5, zorder=4))
        ax.set_xlim(-Ls, Ls)
        ax.set_ylim(-0.5, 5.0)
        ax.set_aspect("equal")
        ax.grid(alpha=0.3)
        ax.set_xlabel("x forward (m)")
        ax.set_ylabel("z up (m)")
        ax.set_title("Side view - vertical FOV (centre column) of forward/backward "
                     "cameras and the selected one; ▼ = nearest visible ground")

    def _nearest_ground(self, c: Camera):
        """Closest ground point on the image centre column not hidden by the car."""
        v = np.linspace(0, c.height_px, 300)
        rays = c.pixel_rays(np.full_like(v, c.width_px / 2), v)
        down = rays[:, 2] < -1e-9
        if not down.any():
            return None
        pts = c.position + rays[down] * (-c.z / rays[down, 2])[:, None]
        seen = self.scene.visible_mask(c, pts, use_objects=False)[0]
        if not seen.any():
            return None
        pts = pts[seen]
        return pts[np.argmin(np.hypot(pts[:, 0] - c.x, pts[:, 1] - c.y))]

    # ---------------------------------------------------------- camera view
    def _overlay_objects(self, ax, c):
        for o in self.scene.objects:
            seen, _, u, v = self.scene.visible_mask(c, o.sample_points(5), exclude=o)
            if not seen.any():
                continue
            u0, u1, v0, v1 = u[seen].min(), u[seen].max(), v[seen].min(), v[seen].max()
            ax.add_patch(matplotlib.patches.Rectangle(
                (u0, v0), u1 - u0, v1 - v0, fill=False, ec="#00e000", lw=1.5))
            dist = np.linalg.norm(o.center - c.position)
            ax.text(u0, max(v0 - 8, 12), f"{o.name}\n{v1 - v0:.0f}px  {dist:.1f}m",
                    color="w", fontsize=7, va="bottom",
                    bbox=dict(fc="k", alpha=0.5, pad=1, lw=0))

    def _draw_camera(self):
        ax = self.axes["Camera view"]
        ax.cla()
        c = self.cam
        if c is None:
            ax.text(0.5, 0.5, "Select a camera", ha="center", transform=ax.transAxes)
            return
        img = self.scene.render_camera(c, 360)
        ax.imshow(img, extent=[0, c.width_px, c.height_px, 0], interpolation="bilinear")
        self._overlay_objects(ax, c)
        ax.axhline(c.height_px / 2, color="w", lw=0.4, alpha=0.5)
        ax.axvline(c.width_px / 2, color="w", lw=0.4, alpha=0.5)
        ax.set_xlim(0, c.width_px)
        ax.set_ylim(c.height_px, 0)
        ax.set_title(f"{c.name} - {c.projection} {c.hfov:.0f}°×{c.vfov:.0f}°, "
                     f"{c.width_px}×{c.height_px}px, range {c.max_range:.0f} m"
                     f"{'' if c.enabled else '  (disabled)'}")
        ax.set_xlabel("u (px)   - reddish ground = beyond camera range")

    def _draw_all_cameras(self):
        fig = self.figs["All cameras"]
        fig.clf()
        cams = [c for c in self.scene.cameras if c.enabled]
        if not cams:
            return
        cols = 3 if len(cams) > 4 else 2
        rows = math.ceil(len(cams) / cols)
        for k, c in enumerate(cams):
            ax = fig.add_subplot(rows, cols, k + 1)
            ax.imshow(self.scene.render_camera(c, 200),
                      extent=[0, c.width_px, c.height_px, 0], interpolation="bilinear")
            self._overlay_objects(ax, c)
            ax.set_xlim(0, c.width_px)
            ax.set_ylim(c.height_px, 0)
            ax.set_title(c.name, fontsize=9, color=c.color, weight="bold")
            ax.set_xticks([])
            ax.set_yticks([])


def run(scene: Scene | None = None):
    root = tk.Tk()
    try:
        ttk.Style(root).theme_use("clam" if root.tk.call("tk", "windowingsystem") != "aqua"
                                  else "aqua")
    except tk.TclError:
        pass
    CameraSetupApp(root, scene)
    root.mainloop()
