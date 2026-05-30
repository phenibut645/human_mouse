from __future__ import annotations

import json
import math
import random
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List, Sequence


@dataclass
class MotionSample:
    distance: float
    duration: float
    point_count: int
    straightness: float
    mean_speed: float
    peak_speed: float
    noise: float
    lateral_scale: float
    overshoot: bool
    target_radius: float


@dataclass
class MotionProfile:
    """Compact statistical profile learned from recorded pointer movements."""

    duration_a: float = 0.085
    duration_b: float = 0.052
    duration_noise: float = 0.035
    noise_median: float = 0.7
    noise_sigma: float = 0.25
    lateral_median: float = 18.0
    lateral_sigma: float = 0.45
    overshoot_probability: float = 0.18
    samples: int = 0

    @classmethod
    def from_jsonl(cls, path: str | Path) -> "MotionProfile":
        records = _read_records(path)
        samples = [sample_from_record(record) for record in records]
        return cls.from_samples(samples)

    @classmethod
    def from_samples(cls, samples: Sequence[MotionSample]) -> "MotionProfile":
        clean = [s for s in samples if s.distance > 2 and s.duration > 0.025]
        if not clean:
            return cls(samples=0)

        xs = [math.log2(s.distance / max(s.target_radius, 1.0) + 1.0) for s in clean]
        ys = [s.duration for s in clean]
        duration_a, duration_b = _linear_regression(xs, ys, default_a=0.085, default_b=0.052)
        residuals = [abs((duration_a + duration_b * x) - y) for x, y in zip(xs, ys)]

        noises = [max(0.01, s.noise) for s in clean]
        laterals = [max(0.01, s.lateral_scale) for s in clean]
        overshoot_probability = sum(1 for s in clean if s.overshoot) / len(clean)

        return cls(
            duration_a=max(0.025, duration_a),
            duration_b=max(0.001, duration_b),
            duration_noise=max(0.006, _median_or(residuals, 0.035)),
            noise_median=_median_or(noises, 0.7),
            noise_sigma=max(0.02, _robust_sigma(noises)),
            lateral_median=_median_or(laterals, 18.0),
            lateral_sigma=max(0.02, _robust_sigma(laterals)),
            overshoot_probability=max(0.0, min(0.6, overshoot_probability)),
            samples=len(clean),
        )

    def sample_parameters(self, distance: float, target_radius: float, rng: random.Random | None = None) -> dict:
        rng = rng or random.Random()
        difficulty = math.log2(distance / max(target_radius, 1.0) + 1.0)
        duration = self.duration_a + self.duration_b * difficulty
        duration += rng.gauss(0.0, self.duration_noise)

        noise = max(0.0, rng.gauss(self.noise_median, self.noise_sigma))
        lateral_scale = max(0.0, rng.gauss(self.lateral_median, self.lateral_sigma))
        # Scale lateral drift down for very short movements and up mildly for long ones.
        lateral_scale *= max(0.25, min(1.6, distance / 650.0))

        return {
            "duration": max(0.055, duration),
            "noise": noise,
            "lateral_scale": lateral_scale,
            "overshoot_probability": self.overshoot_probability,
        }

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "MotionProfile":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(**data)


def build_profile(input_jsonl: str | Path, output_json: str | Path) -> MotionProfile:
    profile = MotionProfile.from_jsonl(input_jsonl)
    profile.save(output_json)
    return profile


def sample_from_record(record: dict) -> MotionSample:
    points = record.get("points", [])
    if len(points) < 2:
        return MotionSample(0, 0, len(points), 1, 0, 0, 0, 0, False, 12)

    xs = [float(p["x"]) for p in points]
    ys = [float(p["y"]) for p in points]
    ts = [float(p["t"]) for p in points]
    duration = max(1e-9, ts[-1] - ts[0])
    distance = math.dist((xs[0], ys[0]), (xs[-1], ys[-1]))
    path_length = sum(math.dist((xs[i - 1], ys[i - 1]), (xs[i], ys[i])) for i in range(1, len(xs)))
    straightness = distance / max(path_length, 1e-9)

    speeds = []
    for i in range(1, len(xs)):
        dt = max(1e-9, ts[i] - ts[i - 1])
        speeds.append(math.dist((xs[i - 1], ys[i - 1]), (xs[i], ys[i])) / dt)

    target = record.get("target", {})
    tx = float(target.get("x", xs[-1]))
    ty = float(target.get("y", ys[-1]))
    radius = float(target.get("radius", 12.0))

    ux, uy = _unit((xs[0], ys[0]), (tx, ty))
    lx, ly = -uy, ux
    lateral_offsets = []
    endpoint_projection_max = 0.0
    for x, y in zip(xs, ys):
        vx, vy = x - xs[0], y - ys[0]
        lateral_offsets.append(vx * lx + vy * ly)
        endpoint_projection_max = max(endpoint_projection_max, (x - tx) * ux + (y - ty) * uy)

    lateral_scale = max(abs(v) for v in lateral_offsets) if lateral_offsets else 0.0
    # Residual wiggle estimate after subtracting a centered 5-point moving average.
    noise = _residual_noise(xs, ys)
    overshoot = endpoint_projection_max > max(2.0, radius * 0.55)

    return MotionSample(
        distance=distance,
        duration=duration,
        point_count=len(points),
        straightness=straightness,
        mean_speed=path_length / duration,
        peak_speed=max(speeds) if speeds else 0.0,
        noise=noise,
        lateral_scale=lateral_scale,
        overshoot=overshoot,
        target_radius=radius,
    )


def _read_records(path: str | Path) -> List[dict]:
    records = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def _unit(start: tuple[float, float], target: tuple[float, float]) -> tuple[float, float]:
    dx, dy = target[0] - start[0], target[1] - start[1]
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return 1.0, 0.0
    return dx / length, dy / length


def _residual_noise(xs: Sequence[float], ys: Sequence[float]) -> float:
    if len(xs) < 7:
        return 0.0
    residuals = []
    for i in range(2, len(xs) - 2):
        mx = sum(xs[i - 2 : i + 3]) / 5.0
        my = sum(ys[i - 2 : i + 3]) / 5.0
        residuals.append(math.dist((xs[i], ys[i]), (mx, my)))
    return _median_or(residuals, 0.0)


def _linear_regression(xs: Sequence[float], ys: Sequence[float], default_a: float, default_b: float) -> tuple[float, float]:
    if len(xs) < 2:
        return default_a, default_b
    mean_x = statistics.fmean(xs)
    mean_y = statistics.fmean(ys)
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom <= 1e-9:
        return mean_y, default_b
    b = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom
    a = mean_y - b * mean_x
    return a, b


def _median_or(values: Iterable[float], default: float) -> float:
    values = [v for v in values if math.isfinite(v)]
    return statistics.median(values) if values else default


def _robust_sigma(values: Sequence[float]) -> float:
    values = [v for v in values if math.isfinite(v)]
    if len(values) < 3:
        return 0.1
    med = statistics.median(values)
    mad = statistics.median(abs(v - med) for v in values)
    return 1.4826 * mad
