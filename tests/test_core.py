import numpy as np
import pytest

from camsim.camera import Camera
from camsim.presets import make_object, tesla_vision_cameras
from camsim.scene import Scene


@pytest.mark.parametrize("projection,hfov,vfov", [("pinhole", 60, 45), ("fisheye", 190, 140)])
def test_pixel_ray_roundtrip(projection, hfov, vfov):
    cam = Camera("c", 1, 0.5, 1.2, 30, -10, 5, hfov, vfov, 100, projection=projection)
    u = np.array([10.0, 640, 1200, 300])
    v = np.array([20.0, 480, 900, 700])
    pts = cam.position + cam.pixel_rays(u, v) * 7.0
    pu, pv, d, ok = cam.project(pts)
    assert ok.all()
    np.testing.assert_allclose(pu, u, atol=1e-6)
    np.testing.assert_allclose(pv, v, atol=1e-6)
    np.testing.assert_allclose(d, 7.0)


def test_yaw_convention():
    cam = Camera(yaw=90, pitch=0)
    np.testing.assert_allclose(cam.forward, [0, 1, 0], atol=1e-12)
    assert Camera(pitch=30).forward[2] > 0


def test_range_and_fov_limits():
    cam = Camera("c", 0, 0, 1, 0, 0, 0, 60, 45, 20)
    pts = np.array([[10, 0, 1], [30, 0, 1], [10, 10, 1], [-5, 0, 1]])
    assert cam.project(pts)[3].tolist() == [True, False, False, False]


def test_car_body_occludes():
    s = Scene()
    # Camera on the front bumper looking backwards over the car cannot see
    # a point right behind the car at bumper height.
    cam = Camera("front", s.car_spec.front_x + 0.01, 0, 0.5, 180, 0, 0, 120, 90, 50)
    seen, in_fov, *_ = s.visible_mask(cam, np.array([[-4.0, 0, 0.5]]))
    assert in_fov[0] and not seen[0]


def test_windshield_camera_sees_through_glass():
    s = Scene()
    s.cameras = tesla_vision_cameras()
    main = s.cameras[0]
    assert "cabin" in s.mounted_inside(main)
    s.objects = [make_object("Pedestrian", 10, 0)]
    assert s.object_visibility(s.objects[0])["Main forward"].visible


def test_objects_occlude_each_other():
    s = Scene()
    s.cameras = [Camera("c", 2.4, 0, 0.5, 0, 0, 0, 60, 45, 50)]
    near = make_object("Truck", 8, 0)
    far = make_object("Child", 20, 0)
    s.objects = [near, far]
    assert not s.object_visibility(far)["c"].visible
    s.objects_occlude = False
    assert s.object_visibility(far)["c"].visible


def test_save_load_roundtrip(tmp_path):
    s = Scene()
    s.cameras = tesla_vision_cameras()
    s.objects = [make_object("Cyclist", 3, 4, 30)]
    p = tmp_path / "rig.json"
    s.save(p)
    t = Scene()
    t.load(p)
    assert [c.to_dict() for c in t.cameras] == [c.to_dict() for c in s.cameras]
    assert t.objects[0].to_dict() == s.objects[0].to_dict()


def test_surround_preset_closes_near_field_blind_zone():
    from camsim.presets import tesla_vision_plus_surround

    def blind(cams):
        s = Scene()
        s.cameras = cams
        xs, ys, c = s.coverage_grid(4.0, 0.1, 0.1)
        return s.coverage_stats(xs, ys, c, 1.0)["blind_area_m2"]

    s = Scene()
    for cam in tesla_vision_plus_surround():
        assert s.mounted_inside(cam) == [] or cam.name.endswith("forward")
    assert blind(tesla_vision_plus_surround()) < 0.3 * blind(tesla_vision_cameras())
