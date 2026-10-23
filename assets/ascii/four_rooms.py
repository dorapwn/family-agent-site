#!/usr/bin/env python3
"""
four_rooms.py — ASCII video: "四個房間 / Four Rooms"

One household, four agents. Each room is rendered as a separate character grid
with its own palette, hue family and motion vocabulary; in the final scene the
four dissolve into a single shared grid — the moment four people become one
household brain.

The script lives in the published repo on purpose: the guide claims this page
was made by the agent, so the exact code that made the banner should be
readable by anyone who lands on the page.

Usage:
    python four_rooms.py -o four-rooms.mp4

Requires: numpy, pillow, scipy, ffmpeg on PATH.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# --------------------------------------------------------------------------
# Creative direction
#
# Mood      : a quiet house at night, four rooms lit, one brain waking up
# Story     : study -> home -> work -> fun -> resolve into one grid
# Colour    : four distinct hue families, deliberately non-overlapping, plus a
#             shared CRT bloom so they still feel like one film
# Textures  : every scene owns a custom character ramp; no two share one
# Arc       : dense and clinical at the edges -> warm and open at the centre
# --------------------------------------------------------------------------

W, H = 1280, 720
FPS = 24
DURATION = 20.0
QUALITY = 0.72  # bloom/grain strength multiplier

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
FONT_SIZE = 20

# Per-scene character ramps. Deliberately invented per scene, not reused.
RAMPS = {
    # study: scientific / exam glyphs, descending
    "study": "0123456789+-×÷=∑∏√∞±∫∂∆∴",
    # home: soft blocks and warmth
    "home": "·∙◦○●◍◎◆◇■▢▣░▒▓█▄▀",
    # work: clinical bars and scans
    "work": "█▉▊▋▌▍▎▏▁▂▃▄▅▆▇─━│┃",
    # fun: chaotic mixed signals
    "fun": "※◈◇◆✦✧✳⋆⋄∴≋∿≽∾",
    # resolve: the union, densest first
    "resolve": "█▓▒░▉▊▋▌▍▎▏◆◇●◍◎○◦·",
}

# Hue families (degrees). Kept far apart so a cut reads as a cut.
HUES = {
    "study": (188.0, 205.0),   # teal -> cyan
    "home": (26.0, 42.0),      # amber -> gold
    "work": (205.0, 218.0),    # cold steel blue
    "fun": (292.0, 340.0),     # violet -> magenta
    "resolve": (16.0, 330.0),  # full sweep
}

# --------------------------------------------------------------------------
# Font + grid
# --------------------------------------------------------------------------

_FONT = None
_CELL = (10, 20)


def font():
    global _FONT
    if _FONT is None:
        _FONT = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    return _FONT


def cell():
    f = font()
    adv = f.getlength("M")
    asc, desc = f.getmetrics()
    return max(1, int(round(adv))), max(1, int(asc + desc))


def grid_shape():
    cw, ch = cell()
    return H // ch, W // cw


# --------------------------------------------------------------------------
# Glyph cache — every ramp is rasterised once and validated for blanks
# --------------------------------------------------------------------------

_MASKS: dict[str, np.ndarray] = {}


def mask_for(ramp: str) -> np.ndarray:
    """Return (n_chars, ch, cw) float masks. Skips chars the font can't draw."""
    if ramp in _MASKS:
        return _MASKS[ramp]
    cw, ch = cell()
    f = font()
    out = []
    for c in ramp:
        img = Image.new("L", (cw, ch), 0)
        d = ImageDraw.Draw(img)
        # centre the glyph in the cell
        try:
            bbox = d.textbbox((0, 0), c, font=f)
            gx = (cw - (bbox[2] - bbox[0])) / 2 - bbox[0]
            gy = (ch - (bbox[3] - bbox[1])) / 2 - bbox[1]
        except Exception:
            gx = gy = 0
        d.text((gx, gy), c, fill=255, font=f)
        a = np.asarray(img, dtype=np.float32) / 255.0
        if a.max() < 0.05:      # font lacks this glyph
            continue
        out.append(a)
    if not out:                # absolute fallback: never render an empty grid
        out = [np.ones((ch, cw), dtype=np.float32)]
    _MASKS[ramp] = np.stack(out).astype(np.float32)
    return _MASKS[ramp]


# --------------------------------------------------------------------------
# Value fields — each scene generates its own motion vocabulary
# --------------------------------------------------------------------------


def f_study(t: float):
    """Descending exam glyph columns. Dense, clinical, slightly anxious."""
    rows, cols = grid_shape()
    yy = np.linspace(0, 1, rows, dtype=np.float32)[:, None]
    xx = np.linspace(0, 1, cols, dtype=np.float32)[None, :]
    speed = 0.55 + 0.45 * np.sin(t * 0.9)
    head = (t * speed * 1.4 + xx * 3.1) % 1.0
    d = np.abs(yy - head)
    # column-wise intensity: only glyphs near the head are lit
    v = np.exp(-(d ** 2) / 0.004) * (0.55 + 0.45 * np.sin(xx * 26.0 + t * 2.0))
    v += 0.06 * np.sin(yy * 18.0 - t * 1.6) * np.sin(xx * 9.0)
    # horizontal scan sweep
    sweep = np.exp(-(((xx - (t * 0.31) % 1.4 - 0.2)) ** 2) / 0.006)
    v += sweep * 0.35
    return np.clip(v, 0, 1)


def f_home(t: float):
    """Warm concentric ripples from a domestic centre. Open, breathing."""
    rows, cols = grid_shape()
    yy = np.linspace(-1, 1, rows, dtype=np.float32)[:, None]
    xx = np.linspace(-1.6, 1.6, cols, dtype=np.float32)[None, :]
    r = np.sqrt(xx ** 2 + (yy * 1.15) ** 2)
    v = 0.5 + 0.5 * np.sin(r * 9.0 - t * 2.1)
    v *= np.exp(-r / 1.25)
    # slow convection so the warm air moves
    v += 0.14 * np.sin(xx * 3.0 + t * 0.7) * np.cos(yy * 4.0 - t * 0.5)
    v *= 0.75 + 0.25 * np.sin(t * 0.6)
    return np.clip(v, 0, 1)


def f_work(t: float):
    """Horizontal scanlines plus a slow column sweep. A report being read."""
    rows, cols = grid_shape()
    yy = np.linspace(0, 1, rows, dtype=np.float32)[:, None]
    xx = np.linspace(0, 1, cols, dtype=np.float32)[None, :]
    v = 0.5 + 0.5 * np.sin(yy * 34.0 + t * 1.2)
    sweep = (xx + t * 0.22) % 1.0
    v = v * 0.55 + (np.exp(-((sweep - 0.5) ** 2) / 0.02)) * 0.45
    # a slow horizontal line drawing itself across, like a form being filled
    line = np.exp(-((yy - (0.5 + 0.34 * np.sin(t * 0.8))) ** 2) / 0.0009)
    v += line * 0.5
    return np.clip(v, 0, 1)


def f_fun(t: float):
    """Curl-flow particles in a torus knot. Generative, no rules, just motion."""
    rows, cols = grid_shape()
    yy = np.linspace(-1, 1, rows, dtype=np.float32)[:, None]
    xx = np.linspace(-1.78, 1.78, cols, dtype=np.float32)[None, :]
    r = np.sqrt(xx ** 2 + yy ** 2) + 1e-5
    ang = np.arctan2(yy, xx)
    # torus knot polar path, three lobes, spinning
    lobes = 3.0
    path_r = 0.42 + 0.26 * np.sin(lobes * (ang * 2 + t * 1.3))
    band = np.exp(-((r - path_r) ** 2) / 0.010)
    swirl = 0.5 + 0.5 * np.sin(r * 26.0 - ang * 4.0 + t * 3.4)
    v = band * (0.45 + 0.55 * swirl)
    v += 0.20 * np.sin(xx * 7.0 + t * 2.2) * np.cos(yy * 8.0 - t * 1.7)
    return np.clip(v, 0, 1)


def f_resolve(t: float):
    """All four fields layered, then crossfaded into one shared grid."""
    a, b = f_study(t * 0.9), f_home(t * 0.9)
    c, d = f_work(t * 0.9), f_fun(t * 0.9)
    k = 0.5 + 0.5 * np.sin(t * 1.1)
    top = a * (1 - k) + c * k
    bot = b * (1 - k) + d * k
    return np.clip(top * 0.72 + bot * 0.72, 0, 1)


# --------------------------------------------------------------------------
# Colour
# --------------------------------------------------------------------------

from colorsys import hsv_to_rgb


def hsv_rgb(h_deg, s, v):
    r, g, b = hsv_to_rgb((h_deg % 360.0) / 360.0, float(np.clip(s, 0, 1)), float(np.clip(v, 0, 1)))
    return r, g, b


def colorize(field: np.ndarray, scene: str, t: float, rows: int, cols: int):
    lo, hi = HUES[scene]
    # hue sweeps across x within the scene's family, plus a slow global drift
    hx = lo + (hi - lo) * np.linspace(0.0, 1.0, cols, dtype=np.float32)[None, :]
    h = hx + (t * 11.0) % 12.0
    # s and v are derived from `field`, so they are already (rows, cols).
    # Only `h` is a single row and needs tiling — repeating an already-2D
    # array would produce (rows*rows, cols).
    s3 = 0.62 + 0.30 * (1.0 - field)
    v3 = 0.18 + 0.95 * field
    h3 = np.repeat(h, rows, axis=0)

    hh = (h3 / 60.0) % 6.0
    Cc = v3 * s3
    X = Cc * (1 - np.abs((hh % 2.0) - 1.0))
    m = v3 - Cc
    out = np.zeros((rows, cols, 3), dtype=np.float32)
    seg = np.clip((hh // 1.0).astype(np.int32), 0, 5)
    fills = [
        (Cc, X, np.zeros_like(Cc)),
        (X, Cc, np.zeros_like(Cc)),
        (np.zeros_like(Cc), Cc, X),
        (np.zeros_like(Cc), X, Cc),
        (X, np.zeros_like(Cc), Cc),
        (Cc, np.zeros_like(Cc), X),
    ]
    for i in range(6):
        sel = seg == i
        if not sel.any():
            continue
        r, g, b = fills[i]
        out[..., 0][sel] = r[sel] + m[sel]
        out[..., 1][sel] = g[sel] + m[sel]
        out[..., 2][sel] = b[sel] + m[sel]
    return np.clip(out, 0, 1)


# --------------------------------------------------------------------------
# Tonemap + shaders
# --------------------------------------------------------------------------


def tonemap(canvas, gamma=0.75):
    """Adaptive brightness normalisation. Never a linear multiplier."""
    f = canvas.astype(np.float32)
    lo, hi = np.percentile(f[::4, ::4], [1, 99.5])
    if hi - lo < 10:
        hi = lo + 10
    f = np.clip((f - lo) / (hi - lo), 0.0, 1.0) ** gamma
    return (f * 255.0).astype(np.float32)


def _box_blur(a: np.ndarray, r: int) -> np.ndarray:
    if r < 1:
        return a
    k = 2 * r + 1
    pad = np.pad(a, ((r, r), (r, r), (0, 0)), mode="edge")
    cs = np.cumsum(pad, axis=0)
    cs = np.vstack([np.zeros((1, cs.shape[1], cs.shape[2]), dtype=cs.dtype), cs])
    a1 = (cs[k:, :, :] - cs[:-k, :, :]) / k
    cs = np.cumsum(a1, axis=1)
    cs = np.hstack([np.zeros((cs.shape[0], 1, cs.shape[2]), dtype=cs.dtype), cs])
    a2 = (cs[:, k:, :] - cs[:, :-k, :]) / k
    return a2


def shade(canvas: np.ndarray, t: float, scene: str, rng_seed: int) -> np.ndarray:
    """bloom -> scanlines -> grain -> vignette -> edge chroma."""
    x = canvas
    # bright must be a single-channel mask (H, W, 1) so it scales all three
    # colour channels equally. Taking the mean of the already-3D array, not a
    # trailing axis on it, which would make the mask 4-D.
    bright = np.clip((x - 120.0) / 135.0, 0, 1).mean(axis=-1, keepdims=True)
    bloom = _box_blur(x, 7) * (0.85 * QUALITY)
    x = x + bloom * bright * 1.15

    # Row/column masks are 2-D (H, 1) or (1, W); they must carry a trailing
    # channel axis to scale an (H, W, 3) canvas. Every mask in this function
    # goes through one helper so the axis rule lives in exactly one place.
    def m2(a):
        return a[..., None]

    # scanlines + a faint rolling bar, the CRT tell
    yy = np.arange(H, dtype=np.float32)[:, None]
    x *= (1.0 - 0.11 * QUALITY * (0.5 + 0.5 * np.sin(yy * 1.6)))[..., None]
    roll = np.exp(-((((yy - ((t * 90.0) % (H + 240)) - 120.0) / 90.0) ** 2)))
    x += m2(roll) * 6.0 * QUALITY

    # grain
    rs = np.random.default_rng(rng_seed)
    x += rs.standard_normal((H, W, 1)).astype(np.float32) * (5.5 * QUALITY)

    # vignette
    yy2 = (np.arange(H, dtype=np.float32)[:, None] / H - 0.5) * 2.0
    xx2 = (np.arange(W, dtype=np.float32)[None, :] / W - 0.5) * 2.0
    vig = 1.0 - 0.42 * QUALITY * (yy2 ** 2 + xx2 ** 2)
    x *= np.clip(vig, 0, 1)[..., None]

    # edge chromatic aberration
    edge = (yy2 ** 2 + xx2 ** 2) > 0.55
    if edge.any():
        x[edge, 0] *= 1.05
        x[edge, 2] *= 0.94
    return x


# --------------------------------------------------------------------------
# Frame render
# --------------------------------------------------------------------------

SCENES = [
    ("study",   0.0,  4.6,  f_study,   0.72),
    ("home",    4.6,  9.2,  f_home,    0.80),
    ("work",    9.2, 13.8,  f_work,    0.68),
    ("fun",    13.8, 18.2,  f_fun,     0.86),
    ("resolve", 18.2, 20.0, f_resolve, 0.74),
]


def scene_at(t: float):
    for name, t0, t1, fn, gamma in SCENES:
        if t0 <= t < t1:
            return name, fn, gamma, (t - t0) / (t1 - t0)
    name, t0, t1, fn, gamma = SCENES[-1]
    return name, fn, gamma, 1.0


def render_frame(t: float, idx: int) -> np.ndarray:
    name, fn, gamma, _k = scene_at(t)
    rows, cols = grid_shape()
    field = np.clip(fn(t), 0, 1)

    masks = mask_for(RAMPS[name])
    n = masks.shape[0]
    idxs = np.clip((field * (n - 1)).astype(np.int32), 0, n - 1)

    # Take the FULL glyph mask for each cell and upsample it to canvas
    # resolution. Averaging the mask over the cell (mean over axes 2,3)
    # collapses every character to one number and renders solid colour
    # blocks — the letterforms only survive if the per-pixel mask is kept.
    tile = masks[idxs]                      # (rows, cols, ch, cw)
    cw, ch = cell()
    rows_full, cols_full = rows * ch, cols * cw
    # (rows, cols, ch, cw) -> (rows, ch, cols, cw) -> (rows*ch, cols*cw)
    alpha = tile.transpose(0, 2, 1, 3).reshape(rows_full, cols_full)

    rgb = colorize(field, name, t, rows, cols)      # (rows, cols, 3)
    gc = np.repeat(np.repeat(rgb, ch, axis=0), cw, axis=1)
    # The grid (cols*cell_w x rows*cell_h) rarely lands exactly on (W, H):
    # 106*12 = 1272 vs W = 1280, and any other resolution has the same problem.
    # Pad to full res rather than slicing, or the canvas and the glyph layer
    # broadcast against different widths.
    if rows_full < H or cols_full < W:
        alpha = np.pad(alpha, ((0, max(0, H - rows_full)), (0, max(0, W - cols_full))))
        gc = np.pad(gc, ((0, max(0, H - rows_full)), (0, max(0, W - cols_full)), (0, 0)))
    gy = alpha[:H, :W]
    gc = gc[:H, :W]

    base = np.full((H, W, 3), 7.0, dtype=np.float32)      # never pure black
    canvas = base + gc * gy[..., None] * 235.0

    # scene-cut glow so the transitions read as cuts
    for nm, t0, t1, _f, _g in SCENES[:-1]:
        if abs(t - t1) < 0.14:
            canvas += 26.0 * (1.0 - abs(t - t1) / 0.14)

    canvas = tonemap(canvas, gamma=gamma)
    canvas = shade(canvas, t, name, rng_seed=idx * 7919 + 13)
    return np.clip(canvas, 0, 255).astype(np.uint8)


def _worker(args):
    t, idx = args
    return t, idx, render_frame(t, idx)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default="four-rooms.mp4")
    ap.add_argument("--fps", type=int, default=FPS)
    ap.add_argument("--duration", type=float, default=DURATION)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--preview", default="", help="also write N still frames here")
    ap.add_argument("--preview-at", default="2.0,6.8,11.5,16.0,19.2")
    args = ap.parse_args()

    # warm the font + glyph caches before forking
    font()
    for k in RAMPS.values():
        mask_for(k)
    rows, cols = grid_shape()
    print(f"grid {cols}x{rows} (cell {cell()[0]}x{cell()[1]})", flush=True)

    if args.preview:
        os.makedirs(os.path.dirname(args.preview) or ".", exist_ok=True)
        for ts in [float(x) for x in args.preview_at.split(",")]:
            fr = render_frame(ts, int(ts * 100))
            Image.fromarray(fr).save(f"{args.preview}{ts:04.1f}.png")
            print(f"preview {ts:4.1f}s  mean={fr.mean():6.2f}  {scene_at(ts)[0]}", flush=True)

    total = int(round(args.duration * args.fps))
    jobs = [(i / args.fps, i) for i in range(total)]

    tmpdir = tempfile.mkdtemp(prefix="fourrooms-")
    prog = subprocess.Popen(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{W}x{H}", "-r", str(args.fps), "-i", "pipe:0",
            "-an",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            args.out,
        ],
        stdin=subprocess.PIPE,
        # stderr MUST NOT be PIPE: long-running ffmpeg fills the 64KB buffer
        # and deadlocks. Send it to a file.
        stderr=open(os.path.join(tmpdir, "ffmpeg.log"), "wb"),
    )

    t0 = time.time()
    done = 0
    try:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            for _t, idx, frame in ex.map(_worker, jobs, chunksize=4):
                prog.stdin.write(frame.tobytes())
                done += 1
                if done % 24 == 0 or done == total:
                    el = time.time() - t0
                    rate = done / el if el else 0
                    eta = (total - done) / rate if rate else 0
                    print(f"  {done}/{total}  {el:5.1f}s  {rate:4.1f} fps  eta {eta:4.1f}s",
                          flush=True)
        prog.stdin.close()
    except BrokenPipeError:
        print("ffmpeg died early; log:", flush=True)
        print(open(os.path.join(tmpdir, "ffmpeg.log")).read()[-2000:], flush=True)
        return 3
    rc = prog.wait()

    size = os.path.getsize(args.out) if os.path.exists(args.out) else 0
    print(f"wrote {args.out}  rc={rc}  {size/1024:.0f} KiB  "
          f"in {time.time()-t0:.1f}s", flush=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())