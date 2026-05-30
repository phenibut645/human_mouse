from __future__ import annotations

import argparse
from pathlib import Path

from human_mouse.profile import MotionProfile, build_profile, sample_from_record


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a motion profile from recorder JSONL data.")
    parser.add_argument("--input", default="data/mouse_recordings.jsonl", help="Path to recorder JSONL file.")
    parser.add_argument("--output", default="data/motion_profile.json", help="Path to write profile JSON.")
    args = parser.parse_args()

    profile = build_profile(Path(args.input), Path(args.output))
    print(f"Wrote profile to {args.output}")
    print(f"Samples: {profile.samples}")
    print(f"Duration model: duration = {profile.duration_a:.4f} + {profile.duration_b:.4f} * ID")
    print(f"Duration noise: {profile.duration_noise:.4f}s")
    print(f"Noise median: {profile.noise_median:.3f}")
    print(f"Lateral median: {profile.lateral_median:.3f}")
    print(f"Overshoot probability: {profile.overshoot_probability:.3f}")


if __name__ == "__main__":
    main()
