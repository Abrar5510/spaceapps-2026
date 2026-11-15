"""Generate the helmet HUD images and the suit sounds (all synthesised here; no recordings, no downloads).

    python3 tools/make_ui.py        -> data/ui/*.png, data/audio/*.wav
"""
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1] / "data"
SR = 44100
rng = np.random.default_rng(3)


def visor():
    """Helmet opening: clear in the middle, dark padded rim at the edges, a thin seal highlight."""
    w, h = 1920, 1080
    y, x = np.mgrid[0:h, 0:w]
    x, y = (x / (w - 1)) * 2 - 1, (y / (h - 1)) * 2 - 1
    r = (np.abs(x / 1.07) ** 2.6 + np.abs(y / 1.10) ** 2.6) ** (1 / 2.6)
    s = np.clip((r - 0.93) / (1.05 - 0.93), 0, 1)
    rim = s * s * (3 - 2 * s)
    seal = np.exp(-((r - 0.955) / 0.006) ** 2) * 0.22
    shade = np.clip((-y - 0.72) / 0.28, 0, 1) * 0.16          # sun shade along the top of the visor
    rgba = np.zeros((h, w, 4), np.float32)
    rgba[..., :3] = 0.03 + seal[..., None] * np.array([0.5, 0.52, 0.55])
    rgba[..., 3] = np.clip(rim * 0.97 + seal * (1 - rim) + shade * (1 - rim), 0, 1)
    Image.fromarray((rgba * 255).astype(np.uint8)).save(ROOT / "ui" / "visor.png")


def arrow():
    im = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.polygon([(128, 18), (226, 214), (128, 166), (30, 214)], fill=(140, 235, 255, 255))
    im = im.filter(ImageFilter.GaussianBlur(1.5))
    im.resize((128, 128), Image.LANCZOS).save(ROOT / "ui" / "arrow.png")


def band(n, lo, hi):
    """White noise band-passed to lo..hi Hz (FFT brick wall with soft edges)."""
    f = np.fft.rfft(rng.normal(size=n))
    hz = np.fft.rfftfreq(n, 1 / SR)
    f *= np.clip((hz - lo) / (lo * 0.3 + 1), 0, 1) * np.clip((hi - hz) / (hi * 0.3), 0, 1)
    s = np.fft.irfft(f, n)
    return s / (np.abs(s).max() + 1e-9)


def save(name, s, peak=0.8):
    s = s / (np.abs(s).max() + 1e-9) * peak
    with wave.open(str(ROOT / "audio" / f"{name}.wav"), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((s * 32767).astype(np.int16).tobytes())


def sounds():
    t = lambda sec: np.arange(int(sec * SR)) / SR
    # Breathing inside a helmet: inhale (brighter), pause, exhale (lower, longer), pause. Loops.
    n = int(4.2 * SR)
    tt = np.arange(n) / SR
    inh = np.clip(np.sin(np.pi * np.clip(tt / 1.5, 0, 1)), 0, 1) ** 1.5
    exh = np.clip(np.sin(np.pi * np.clip((tt - 1.8) / 1.9, 0, 1)), 0, 1) ** 1.2
    save("breath", band(n, 700, 2600) * inh * 0.8 + band(n, 350, 1500) * exh, 0.5)
    # Suit fan and pump hum: whole cycles so it loops cleanly.
    tt = t(3.0)
    save("hum", np.sin(2 * np.pi * 55 * tt) + 0.5 * np.sin(2 * np.pi * 110 * tt) + 0.25 * np.sin(2 * np.pi * 165 * tt)
         + 0.6 * band(len(tt), 150, 900), 0.35)
    # Boot on regolith: a short low crunch.
    tt = t(0.24)
    save("step", band(len(tt), 90, 1400) * np.exp(-tt * 22) + 0.4 * band(len(tt), 1500, 5000) * np.exp(-tt * 45), 0.7)
    # Core drill: motor buzz with a rattle.
    tt = t(2.0)
    saw = sum(np.sin(2 * np.pi * 140 * k * tt) / k for k in range(1, 9))
    save("drill", saw * (0.75 + 0.25 * np.sin(2 * np.pi * 23 * tt)) + 0.5 * band(len(tt), 800, 5000), 0.6)
    tt = t(0.28)
    save("beep", np.where(tt < 0.12, np.sin(2 * np.pi * 880 * tt), np.sin(2 * np.pi * 1320 * tt)) * np.minimum(1, (0.28 - tt) * 40), 0.5)
    tt = t(1.2)
    save("alarm", np.sin(2 * np.pi * np.where((tt % 0.6) < 0.3, 620, 780) * tt) * (0.6 + 0.4 * np.sin(2 * np.pi * 3.33 * tt) ** 2), 0.55)
    tt = t(0.02)
    save("tick", band(len(tt), 1500, 9000) * np.exp(-tt * 400), 0.6)


if __name__ == "__main__":
    for d in ("ui", "audio"):
        (ROOT / d).mkdir(exist_ok=True)
    visor(); arrow(); sounds()
    print("ui + audio written to", ROOT)
