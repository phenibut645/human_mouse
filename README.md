# Human Mouse

Human Mouse is a Python package for local UI automation, testing, and accessibility tooling. It generates cursor movement with a profile-aware trajectory model instead of a single dense spline.

The current movement model uses:

- minimum-jerk timing for acceleration and deceleration;
- target-size awareness for small vs large UI controls;
- correlated hand tremor instead of white-noise jitter;
- optional overshoot and corrective sub-movement;
- an optional profile learned from recorded human pointer traces.

> Use this for your own applications, local UI tests, demos, and accessibility tooling. Do not use it to violate service rules, bypass anti-abuse systems, or automate games/services where automation is prohibited.

## Installation

```bash
pip install -e .
```

For examples and plots:

```bash
pip install matplotlib pytest
```

## Basic usage

```python
from human_mouse import MouseController

mouse = MouseController()
mouse.move(500, 300)
mouse.perform_click(500, 300)
```

## Target-aware movement

```python
from human_mouse import MouseController

mouse = MouseController()
mouse.move_to_target(
    700,
    420,
    target_width=80,
    target_height=32,
    speed_factor=1.0,
    fps=120,
)
```

`speed_factor` follows the original convention:

- `0.5` is faster;
- `1.0` is normal;
- `2.0` is slower.

## Generate a trajectory without moving the cursor

Useful for tests and graphs:

```python
from human_mouse import MouseController

mouse = MouseController()
trajectory = mouse.generate_trajectory(
    start=(100, 100),
    target=(900, 520),
    target_size=(32, 32),
)

for point in trajectory:
    print(point.x, point.y, point.delay)
```

## Record your own movement profile

This repository includes a fullscreen recorder. It shows a target circle. Your task is to move the real cursor to the target and press `Space`. Each trial is saved to JSONL.

Run from the repository root:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .
python examples\record_mouse_profile.py
```

Controls:

- `Space` saves the current movement when the cursor is near the target;
- `R` resets the current trial;
- `Esc` exits.

The recorder writes:

```text
data/mouse_recordings.jsonl
```

Recommended amount:

- 30 movements: enough to test the pipeline;
- 100-200 movements: decent personal profile;
- 500+ movements: better statistical stability.

## Build a profile from recordings

```powershell
python examples\build_profile.py --input data\mouse_recordings.jsonl --output data\motion_profile.json
```

The profile stores compact statistics:

- duration model by Fitts-like difficulty index;
- residual timing noise;
- lateral drift scale;
- tremor estimate;
- overshoot probability.

## Use the learned profile

```python
from human_mouse import MouseController

mouse = MouseController(profile_path="data/motion_profile.json")
mouse.move_to_target(700, 420, target_width=80, target_height=32)
```

## Preview generated trajectories

```powershell
python examples\preview_profiled_trajectory.py --profile data\motion_profile.json --output data\trajectory_preview.png
```

This creates a PNG plot without moving your real cursor.

## Tests

```powershell
pytest -q
```

## API compatibility

The original public methods are still available:

```python
mouse.move(500, 300)
mouse.move_random()
mouse.perform_click(500, 300)
mouse.perform_double_click(500, 300)
mouse.perform_context_click(500, 300)
```

New additions:

```python
mouse.move_to_target(...)
mouse.generate_trajectory(...)
```

## Notes on the algorithm

The old implementation was based on smooth spline interpolation. That can look visually pleasant but overly synthetic because the path is too continuous and the per-point delay is too uniform.

The new generator treats movement as a short motor sequence:

1. sample duration from distance and target size;
2. generate progress with a minimum-jerk curve;
3. add a broad lateral arc;
4. add correlated tremor with endpoint damping;
5. optionally move beyond the target and perform a short correction.

A learned `MotionProfile` replaces some of the default random parameters with statistics estimated from your own recordings.
