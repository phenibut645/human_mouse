from __future__ import annotations

import json
import math
import random
import time
import tkinter as tk
from pathlib import Path

OUTPUT = Path("data/mouse_recordings.jsonl")
TARGET_RADIUS = 18
MIN_SAMPLES = 8


class RecorderApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Human Mouse Recorder")
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#111111")

        self.canvas = tk.Canvas(root, bg="#111111", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.width = root.winfo_screenwidth()
        self.height = root.winfo_screenheight()
        self.target = self._new_target(first=True)
        self.points: list[dict] = []
        self.trial = 0
        self.last_mouse = None
        self.recording = False

        self.info = self.canvas.create_text(
            24,
            24,
            anchor="nw",
            fill="#eeeeee",
            font=("Segoe UI", 14),
            text="Move to the highlighted target and press SPACE. Esc exits. R resets current trial.",
        )
        self.target_shape = None
        self.path_shape = None
        self._draw_target()

        root.bind("<Motion>", self._on_motion)
        root.bind("<space>", self._finish_trial)
        root.bind("r", self._reset_trial)
        root.bind("R", self._reset_trial)
        root.bind("<Escape>", lambda _event: self.root.destroy())

    def _new_target(self, first: bool = False) -> dict:
        margin = 90
        if first:
            return {"x": self.width // 2, "y": self.height // 2, "radius": TARGET_RADIUS}
        return {
            "x": random.randint(margin, self.width - margin),
            "y": random.randint(margin, self.height - margin),
            "radius": random.choice([12, 16, 18, 24, 32]),
        }

    def _draw_target(self) -> None:
        if self.target_shape is not None:
            self.canvas.delete(self.target_shape)
        x, y, r = self.target["x"], self.target["y"], self.target["radius"]
        self.target_shape = self.canvas.create_oval(
            x - r,
            y - r,
            x + r,
            y + r,
            outline="#66ff99",
            width=3,
            fill="#1f6f3a",
        )
        self.canvas.tag_raise(self.info)

    def _on_motion(self, event: tk.Event) -> None:
        now = time.perf_counter()
        point = {"t": now, "x": int(event.x_root), "y": int(event.y_root)}
        if not self.recording:
            self.recording = True
            self.points = [point]
        else:
            self.points.append(point)
        self.last_mouse = (int(event.x_root), int(event.y_root))
        self._draw_path_lightweight()

    def _draw_path_lightweight(self) -> None:
        if len(self.points) < 2:
            return
        if self.path_shape is not None:
            self.canvas.delete(self.path_shape)
        sampled = self.points[-90:]
        coords = []
        for p in sampled:
            coords.extend([p["x"], p["y"]])
        self.path_shape = self.canvas.create_line(*coords, fill="#5599ff", width=2, smooth=False)
        self.canvas.tag_raise(self.target_shape)
        self.canvas.tag_raise(self.info)

    def _finish_trial(self, _event: tk.Event) -> None:
        if len(self.points) < MIN_SAMPLES:
            self._set_info("Too few points. Move normally to the target, then press SPACE.")
            return

        last = self.points[-1]
        dist_to_target = math.dist((last["x"], last["y"]), (self.target["x"], self.target["y"]))
        if dist_to_target > self.target["radius"] * 1.8:
            self._set_info("Cursor is not close enough to target. Finish inside/near the circle, then press SPACE.")
            return

        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "created_at": time.time(),
            "screen": {"width": self.width, "height": self.height},
            "target": self.target,
            "points": self._normalize_times(self.points),
        }
        with OUTPUT.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        self.trial += 1
        self.points = []
        self.recording = False
        if self.path_shape is not None:
            self.canvas.delete(self.path_shape)
            self.path_shape = None
        self.target = self._new_target()
        self._draw_target()
        self._set_info(f"Saved trial #{self.trial} to {OUTPUT}. Continue, or Esc exits.")

    def _reset_trial(self, _event: tk.Event | None = None) -> None:
        self.points = []
        self.recording = False
        if self.path_shape is not None:
            self.canvas.delete(self.path_shape)
            self.path_shape = None
        self._set_info("Current trial reset. Move to the target and press SPACE.")

    def _normalize_times(self, points: list[dict]) -> list[dict]:
        t0 = points[0]["t"]
        return [{"t": round(p["t"] - t0, 6), "x": p["x"], "y": p["y"]} for p in points]

    def _set_info(self, text: str) -> None:
        self.canvas.itemconfigure(self.info, text=text)


def main() -> None:
    root = tk.Tk()
    RecorderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
