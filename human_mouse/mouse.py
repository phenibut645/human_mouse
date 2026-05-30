from __future__ import annotations

import math
import platform
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np
from numpy.typing import NDArray
import pyautogui

try:
    from .profile import MotionProfile
except Exception:  # pragma: no cover - keeps the core importable if profile.py is absent
    MotionProfile = None  # type: ignore


@dataclass(frozen=True)
class TrajectoryPoint:
    """One generated cursor sample.

    delay is the sleep time before moving to this point, in seconds.
    """

    x: float
    y: float
    delay: float


class MouseController:
    """Mouse controller with profile-aware, non-spline cursor motion.

    The old implementation generated a very dense spline and used one constant
    sleep interval. That looks smooth, but it also looks synthetic. This version
    models a UI movement as a short sequence of phases:

    1. ballistic movement toward the target area,
    2. minimum-jerk timing profile,
    3. correlated hand tremor/lateral drift,
    4. optional overshoot and corrective sub-movement.

    The public API remains compatible with the original project: move(),
    move_random(), perform_click(), perform_double_click(), perform_context_click().
    """

    def __init__(
        self,
        is_virtual: bool = False,
        always_zigzag: bool = False,
        profile: Optional[object] = None,
        profile_path: Optional[str | Path] = None,
        rng: Optional[random.Random] = None,
    ):
        self.is_virtual = is_virtual
        self.always_zigzag = always_zigzag
        self.rng = rng or random.Random()
        self.profile = profile

        if profile is None and profile_path is not None and MotionProfile is not None:
            self.profile = MotionProfile.load(profile_path)

        if self.is_virtual:
            self._enable_virtual_display()

    def _enable_virtual_display(self) -> None:
        """Enable virtual display support for Linux systems."""
        if platform.system() != "Linux":
            return

        try:
            import os
            import Xlib.display

            pyautogui._pyautogui_x11._display = Xlib.display.Display(os.environ.get("DISPLAY", ":0"))
        except ImportError:
            print("Warning: Virtual display support requires python-xlib package")
        except Exception as e:
            print(f"Warning: Failed to initialize virtual display: {e}")

    def move(self, target_x: int, target_y: int, speed_factor: float = 1.0) -> None:
        """Move to a coordinate using a generated UI motion trajectory."""
        self.move_to_target(target_x, target_y, speed_factor=speed_factor)

    def move_to_target(
        self,
        target_x: int,
        target_y: int,
        target_width: float = 24.0,
        target_height: float = 24.0,
        speed_factor: float = 1.0,
        fps: int = 120,
        noise: Optional[float] = None,
        overshoot: Optional[bool] = None,
    ) -> None:
        """Move to a target area, not just a mathematical point.

        target_width/target_height are used to adapt duration and correction size.
        Small targets get slower terminal movement; large targets allow a looser
        endpoint. speed_factor > 1 is slower, speed_factor < 1 is faster.
        """
        start_x, start_y = pyautogui.position()
        trajectory = self.generate_trajectory(
            start=(float(start_x), float(start_y)),
            target=(float(target_x), float(target_y)),
            target_size=(float(target_width), float(target_height)),
            speed_factor=speed_factor,
            fps=fps,
            noise=noise,
            overshoot=overshoot,
        )
        self._perform_timed_movement(trajectory)

    def move_random(self, speed_factor: float = 1.0) -> None:
        """Navigate cursor to random screen coordinates."""
        width, height = pyautogui.size()
        self.move(self.rng.randint(0, width), self.rng.randint(0, height), speed_factor)

    def generate_trajectory(
        self,
        start: Tuple[float, float],
        target: Tuple[float, float],
        target_size: Tuple[float, float] = (24.0, 24.0),
        speed_factor: float = 1.0,
        fps: int = 120,
        noise: Optional[float] = None,
        overshoot: Optional[bool] = None,
    ) -> List[TrajectoryPoint]:
        """Generate a timed cursor trajectory without moving the actual cursor.

        This is useful for tests, plots, and comparing generated trajectories to
        recorded human traces.
        """
        sx, sy = start
        tx, ty = target
        distance = math.dist(start, target)
        if distance < 1:
            return [TrajectoryPoint(tx, ty, 0.0)]

        target_w, target_h = target_size
        target_radius = max(4.0, min(target_w, target_h) / 2.0)
        params = self._sample_motion_params(distance, target_radius, speed_factor)

        if noise is not None:
            params["noise"] = float(noise)
        if overshoot is not None:
            params["overshoot"] = bool(overshoot)

        aim_x, aim_y = tx, ty
        if params["overshoot"]:
            ux, uy = self._unit_vector(start, target)
            overshoot_distance = min(
                max(2.0, distance * self.rng.uniform(0.015, 0.055)),
                target_radius * self.rng.uniform(0.8, 2.2),
            )
            lateral_x, lateral_y = -uy, ux
            lateral = self.rng.uniform(-0.65, 0.65) * target_radius
            aim_x = tx + ux * overshoot_distance + lateral_x * lateral
            aim_y = ty + uy * overshoot_distance + lateral_y * lateral

        main = self._generate_segment(
            start=(sx, sy),
            target=(aim_x, aim_y),
            duration=params["duration"] * (0.78 if params["overshoot"] else 1.0),
            fps=fps,
            lateral_scale=params["lateral_scale"],
            noise_scale=params["noise"],
            endpoint_softness=target_radius,
        )

        if not params["overshoot"]:
            return main

        # Correction phase: short, slower, and less noisy.
        pause = self.rng.uniform(0.018, 0.075)
        correction_duration = max(0.055, params["duration"] * self.rng.uniform(0.10, 0.24))
        correction = self._generate_segment(
            start=(aim_x, aim_y),
            target=(tx, ty),
            duration=correction_duration,
            fps=fps,
            lateral_scale=params["lateral_scale"] * 0.18,
            noise_scale=params["noise"] * 0.28,
            endpoint_softness=max(1.0, target_radius * 0.25),
        )
        if correction:
            correction[0] = TrajectoryPoint(correction[0].x, correction[0].y, correction[0].delay + pause)
        return main + correction

    def _sample_motion_params(self, distance: float, target_radius: float, speed_factor: float) -> dict:
        # A compact Fitts-like duration model. It is not meant to be a perfect
        # motor-control model; it simply prevents tiny targets from being crossed
        # with the same terminal speed as large targets.
        index_of_difficulty = math.log2(distance / max(target_radius, 1.0) + 1.0)
        base_duration = 0.085 + 0.052 * index_of_difficulty + self.rng.uniform(-0.025, 0.045)

        if self.profile is not None:
            sampler = getattr(self.profile, "sample_parameters", None)
            if callable(sampler):
                sampled = sampler(distance=distance, target_radius=target_radius, rng=self.rng)
                base_duration = sampled.get("duration", base_duration)
                noise = sampled.get("noise", self.rng.uniform(0.25, 1.15))
                lateral_scale = sampled.get("lateral_scale", min(80.0, distance * self.rng.uniform(0.015, 0.065)))
                overshoot_p = sampled.get("overshoot_probability", 0.22)
                return {
                    "duration": max(0.075, base_duration * max(0.15, speed_factor)),
                    "noise": max(0.0, noise),
                    "lateral_scale": max(0.0, lateral_scale),
                    "overshoot": self.rng.random() < overshoot_p,
                }

        distance_factor = min(1.0, distance / 900.0)
        target_factor = max(0.35, min(1.35, 18.0 / max(target_radius, 4.0)))
        duration = max(0.075, base_duration * target_factor * max(0.15, speed_factor))
        lateral_scale = min(70.0, distance * self.rng.uniform(0.012, 0.055))
        noise = self.rng.uniform(0.18, 0.85) * (0.55 + distance_factor)
        overshoot_probability = min(0.38, 0.08 + 0.22 * distance_factor + 0.06 * target_factor)

        return {
            "duration": duration,
            "noise": noise,
            "lateral_scale": lateral_scale,
            "overshoot": self.always_zigzag or self.rng.random() < overshoot_probability,
        }

    def _generate_segment(
        self,
        start: Tuple[float, float],
        target: Tuple[float, float],
        duration: float,
        fps: int,
        lateral_scale: float,
        noise_scale: float,
        endpoint_softness: float,
    ) -> List[TrajectoryPoint]:
        sx, sy = start
        tx, ty = target
        distance = math.dist(start, target)
        samples = max(5, min(180, int(duration * max(30, fps))))
        raw_t = np.linspace(0.0, 1.0, samples)

        # Minimum-jerk timing: zero velocity at the start/end, peak near middle.
        progress = 10 * raw_t**3 - 15 * raw_t**4 + 6 * raw_t**5

        ux, uy = self._unit_vector(start, target)
        lx, ly = -uy, ux

        # One broad lateral arc + correlated tremor. The envelope fades at both
        # ends so the cursor does not vibrate on the exact endpoint.
        arc_direction = self.rng.choice([-1.0, 1.0])
        arc = arc_direction * lateral_scale * np.sin(math.pi * raw_t) ** self.rng.uniform(0.85, 1.6)
        tremor_x = self._correlated_noise(samples, noise_scale)
        tremor_y = self._correlated_noise(samples, noise_scale)
        endpoint_envelope = np.sin(math.pi * raw_t) ** 0.7
        terminal_damping = np.clip((1.0 - raw_t) / 0.22, 0.0, 1.0)
        noise_envelope = endpoint_envelope * (0.45 + 0.55 * terminal_damping)

        xs = sx + (tx - sx) * progress + lx * arc + tremor_x * noise_envelope
        ys = sy + (ty - sy) * progress + ly * arc + tremor_y * noise_envelope

        # Pin endpoints. The last few samples are gently pulled into the target,
        # which avoids a noisy final pixel crawl.
        xs[0], ys[0] = sx, sy
        xs[-1], ys[-1] = tx, ty
        for i in range(max(1, samples - 5), samples):
            blend = (i - (samples - 5)) / 5.0 if samples >= 5 else 1.0
            blend = max(0.0, min(1.0, blend))
            xs[i] = xs[i] * (1 - blend) + tx * blend
            ys[i] = ys[i] * (1 - blend) + ty * blend

        dt = duration / max(1, samples - 1)
        # Small timing variability while keeping the total duration close.
        jitter = np.random.default_rng().normal(1.0, 0.10, samples)
        jitter = np.clip(jitter, 0.72, 1.32)
        delays = dt * jitter
        delays *= duration / max(float(delays.sum()), 1e-9)
        delays[0] = 0.0

        return [TrajectoryPoint(float(x), float(y), float(d)) for x, y, d in zip(xs, ys, delays)]

    def _correlated_noise(self, samples: int, scale: float) -> NDArray[np.float64]:
        if samples <= 0 or scale <= 0:
            return np.zeros(samples)
        rng = np.random.default_rng()
        raw = rng.normal(0.0, scale, samples)
        kernel_size = max(3, min(17, samples // 6 * 2 + 1))
        kernel_x = np.linspace(-2.0, 2.0, kernel_size)
        kernel = np.exp(-0.5 * kernel_x**2)
        kernel /= kernel.sum()
        return np.convolve(raw, kernel, mode="same")

    @staticmethod
    def _unit_vector(start: Tuple[float, float], target: Tuple[float, float]) -> Tuple[float, float]:
        sx, sy = start
        tx, ty = target
        dx, dy = tx - sx, ty - sy
        length = math.hypot(dx, dy)
        if length < 1e-9:
            return 1.0, 0.0
        return dx / length, dy / length

    def _perform_timed_movement(self, trajectory: Sequence[TrajectoryPoint]) -> None:
        for point in trajectory:
            if point.delay > 0:
                time.sleep(point.delay)
            pyautogui.platformModule._moveTo(int(round(point.x)), int(round(point.y)))

    # Compatibility helpers retained from the original API.
    def perform_click(self, x: Optional[int] = None, y: Optional[int] = None) -> None:
        """Execute a single click at specified or current position."""
        self._prepare_click_position(x, y)
        pyautogui.click()

    def perform_double_click(self, x: Optional[int] = None, y: Optional[int] = None) -> None:
        """Execute a double click with randomized interval."""
        self._prepare_click_position(x, y)
        delay = self.rng.uniform(0.045, 0.24)
        pyautogui.click(clicks=2, interval=delay)

    def perform_context_click(self, x: Optional[int] = None, y: Optional[int] = None) -> None:
        """Execute right-click at specified or current position."""
        self._prepare_click_position(x, y)
        pyautogui.click(button="right")

    def _prepare_click_position(self, x: Optional[int], y: Optional[int]) -> None:
        current_x, current_y = pyautogui.position()
        if x is None and y is None:
            return
        if x is None:
            self.move(current_x, y)
        elif y is None:
            self.move(x, current_y)
        else:
            self.move(x, y)
