"""Move cursor in a small square after a 3-second delay.

Run from repo root:
    python examples/move_demo.py

Safety:
    Move the mouse to a screen corner to trigger pyautogui failsafe.
"""

import time

import pyautogui

from human_mouse import MouseController

pyautogui.FAILSAFE = True
mouse = MouseController()

print("Starting in 3 seconds. Move mouse to a screen corner to abort.")
time.sleep(3)

x, y = pyautogui.position()
points = [
    (x + 260, y),
    (x + 260, y + 180),
    (x, y + 180),
    (x, y),
]

for px, py in points:
    mouse.move_to_target(px, py, target_width=40, target_height=40, speed_factor=1.0)
    time.sleep(0.25)

print("Done")
