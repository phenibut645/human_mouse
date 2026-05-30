from pathlib import Path

from human_mouse import MouseController
from human_mouse.profile import MotionProfile


def test_generate_trajectory_has_endpoint():
    controller = MouseController()
    trajectory = controller.generate_trajectory(
        start=(100, 100),
        target=(500, 360),
        target_size=(32, 32),
        fps=90,
        overshoot=False,
    )
    assert len(trajectory) >= 5
    assert abs(trajectory[0].x - 100) < 1
    assert abs(trajectory[0].y - 100) < 1
    assert abs(trajectory[-1].x - 500) < 1
    assert abs(trajectory[-1].y - 360) < 1
    assert sum(p.delay for p in trajectory) > 0


def test_profile_save_load_roundtrip(tmp_path: Path):
    profile = MotionProfile(samples=12, duration_a=0.1, duration_b=0.05)
    path = tmp_path / "profile.json"
    profile.save(path)
    loaded = MotionProfile.load(path)
    assert loaded.samples == 12
    assert loaded.duration_a == 0.1
    assert loaded.duration_b == 0.05


def test_controller_accepts_profile_instance():
    profile = MotionProfile(samples=10)
    controller = MouseController(profile=profile)
    trajectory = controller.generate_trajectory(start=(0, 0), target=(300, 200), target_size=(24, 24))
    assert trajectory[-1].x == 300
    assert trajectory[-1].y == 200
