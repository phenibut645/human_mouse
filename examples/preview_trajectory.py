"""Generate trajectory preview images without moving the real cursor.

Run:
    python examples/preview_trajectory.py

Output:
    trajectory_preview.png
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import matplotlib.pyplot as plt
import numpy as np

from human_mouse import MouseController, MovementProfile

mouse = MouseController()
profile = MovementProfile(speed_factor=1.0, target_width=32, target_height=32, fps=90)

start = (100, 100)
target = (900, 520)
trajectory = mouse.generate_trajectory(*start, *target, profile=profile)
xy = np.array(trajectory)

plt.figure(figsize=(9, 5))
plt.plot(xy[:, 0], xy[:, 1], marker=".", markersize=3, linewidth=1)
plt.scatter([start[0]], [start[1]], label="start")
plt.scatter([target[0]], [target[1]], label="target")
plt.gca().invert_yaxis()
plt.title("Enhanced human_mouse trajectory preview")
plt.xlabel("x")
plt.ylabel("y")
plt.legend()
plt.tight_layout()
plt.savefig("trajectory_preview.png", dpi=150)
print("Saved trajectory_preview.png")
print(f"Generated points: {len(trajectory)}")
