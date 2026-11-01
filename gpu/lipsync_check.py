"""Crude lip-sync check: mouth-region signals vs audio RMS per video frame (25 fps).

usage: python gpu/lipsync_check.py video.mp4 x y w h [start_s dur_s]
  (x,y,w,h) = mouth box in video pixels.
openness = mean darkness in the box (open mouth -> dark gap); motion = mean |frame diff| in the box.
Prints Pearson r at lag 0 and best lag in [-3,3] frames (positive lag = mouth after audio).
"motion_clean" drops frames whose whole-frame change is > 3x the median (chunk cuts, big head moves).
This is a rough proxy, not a perceptual lip-sync score; listen to the clip to confirm.
"""
import subprocess
import sys

import numpy as np

v = sys.argv[1]
x, y, w, h = map(int, sys.argv[2:6])
ss = sys.argv[6] if len(sys.argv) > 6 else "0"
dur = sys.argv[7] if len(sys.argv) > 7 else "999"
raw = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-ss", ss, "-t", dur, "-i", v, "-vf",
                      f"crop={w}:{h}:{x}:{y},format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
fr = np.frombuffer(raw, np.uint8).reshape(-1, h, w).astype(np.float32)
pcm = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-ss", ss, "-t", dur, "-i", v, "-vn", "-ac", "1",
                      "-ar", "16000", "-f", "f32le", "-"], capture_output=True).stdout
a = np.frombuffer(pcm, np.float32)
hop = 640
n = min(len(fr), len(a) // hop)
fr = fr[:n]
rms = np.sqrt((a[: n * hop].reshape(n, hop) ** 2).mean(1))
openness = (255 - fr).mean((1, 2))
full = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-ss", ss, "-t", dur, "-i", v, "-vf",
                       "scale=128:128,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
g = np.frombuffer(full, np.uint8).reshape(-1, 128, 128).astype(np.float32)[:n]
gd = np.r_[0, np.abs(np.diff(g, axis=0)).mean((1, 2))]
keep = gd <= 3 * np.median(gd[1:])
motion = np.r_[0, np.abs(np.diff(fr, axis=0)).mean((1, 2))]


def r(s, lag, mask=None):
    m = np.ones(n, bool) if mask is None else mask
    if lag > 0:
        p, q, k = s[lag:], rms[:-lag], m[lag:]
    elif lag < 0:
        p, q, k = s[:lag], rms[-lag:], m[:lag]
    else:
        p, q, k = s, rms, m
    return float(np.corrcoef(p[k], q[k])[0, 1])


for name, s, mask in (("openness", openness, None), ("motion", motion, None), ("motion_clean", motion, keep)):
    rs = {lag: r(s, lag, mask) for lag in range(-3, 4)}
    best = max(rs, key=rs.get)
    print(f"{name}: r0={rs[0]:+.3f} best_lag={best:+d} r={rs[best]:+.3f}  (n={n if mask is None else int(mask.sum())})")
