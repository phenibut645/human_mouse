from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt

from human_mouse import MouseController


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview generated trajectories without moving the real cursor.")
    parser.add_argument("--profile", default="data/motion_profile.json", help="Optional profile JSON path.")
    parser.add_argument("--output", default="data/trajectory_preview.png", help="Image output path.")
    args = parser.parse_args()

    profile_path = Path(args.profile)
    mouse = MouseController(profile_path=profile_path if profile_path.exists() else None)

    starts_targets = [
        ((120, 120), (900, 520), (32, 32)),
        ((900, 520), (260, 690), (18, 18)),
        ((260, 690), (1300, 220), (64, 28)),
        ((1300, 220), (760, 760), (14, 14)),
    ]

    fig, ax = plt.subplots(figsize=(12, 7))
    ax.set_title("Generated cursor trajectories")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.invert_yaxis()
    ax.grid(True, alpha=0.25)

    for start, target, size in starts_targets:
        trajectory = mouse.generate_trajectory(start=start, target=target, target_size=size)
        xs = [p.x for p in trajectory]
        ys = [p.y for p in trajectory]
        ax.plot(xs, ys, marker=".", markersize=2, linewidth=1)
        ax.scatter([start[0]], [start[1]], marker="o")
        ax.scatter([target[0]], [target[1]], marker="x")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=160, bbox_inches="tight")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
