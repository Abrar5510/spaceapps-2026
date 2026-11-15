"""Cut the demo videos from the frames tools/unreal/record_demo.py captured: captions, narration, suit sounds.

    python3 tools/make_video.py <first frame number>
      -> media/marswalk_full.mp4   every chapter (about 100 s)
      -> media/marswalk_demo.mp4   30 s cut for the submission form

The picture is the game frame scaled into the top of the 1600x900 canvas; the caption strip sits below it, so
it never covers the helmet display. Sounds are the game's own (data/audio, synthesised by tools/make_ui.py),
laid down from the per-frame log the recorder wrote. No voice-over.
"""
import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SCRATCH, MEDIA, AUDIO = ROOT / ".scratch", ROOT / "media", ROOT / "data" / "audio"
FRAMES = ROOT / "Marswalk" / "Saved" / "Screenshots" / "MacEditor"
SR, FPS = 44100, 30
W, H, STRIP = 1600, 900, 104
# 30 s cut: chapter, seconds into it, length
CUT = [("map", 1.0, 3.0), ("layers", 3.5, 4.5), ("route", 0.5, 3.0), ("walk1", 3.0, 3.0), ("stop1", 2.0, 3.0), ("core2", 4.0, 3.5),
       ("airlock", 0.5, 2.5), ("stop4", 1.0, 3.0), ("home", 1.5, 2.0), ("debrief", 1.5, 2.5)]


def wav(path):
    with wave.open(str(path)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768.0


def captions(chapters):
    bold = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 34)
    plain = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 23)
    small = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 17)
    out = []
    for i, c in enumerate(chapters):
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rectangle([0, H - STRIP, W, H], fill=(10, 12, 16, 255))
        d.rectangle([0, H - STRIP, W, H - STRIP + 3], fill=(255, 184, 90, 255))
        d.text((36, H - STRIP + 14), c["title"], font=bold, fill=(255, 255, 255, 255))
        d.text((36, H - STRIP + 60), c["detail"], font=plain, fill=(255, 205, 150, 255))
        d.text((W - 36, H - STRIP + 20), f"{i + 1} / {len(chapters)}", font=small, fill=(150, 160, 170, 255), anchor="ra")
        d.text((W - 36, H - STRIP + 64), "Marswalk  |  NASA Space Apps 2026", font=small, fill=(150, 160, 170, 255), anchor="ra")
        p = SCRATCH / f"cap_{i:02d}.png"
        im.save(p)
        out.append(p)
    return out


def sound(log):
    n = len(log) * SR // FPS
    mix = np.zeros(n + SR, np.float32)
    snd = {k: wav(AUDIO / f"{k}.wav") for k in ("breath", "hum", "step", "drill", "beep", "alarm", "tick")}
    per = SR // FPS

    def gate(flag):                                   # per-frame on/off -> smooth per-sample envelope
        e = np.repeat(np.array([1.0 if flag(x) else 0.0 for x in log], np.float32), per)
        k = np.ones(per * 4, np.float32) / (per * 4)
        return np.convolve(e, k, "same")

    def loop(name, env, vol):
        s = snd[name]
        mix[:n] += np.tile(s, n // len(s) + 1)[:n] * env[:n] * vol

    def hit(name, frame, vol):
        a = frame * per
        s = snd[name]
        mix[a:a + len(s)] += s[:max(0, len(mix) - a)] * vol

    out = lambda x: x["state"] == "eva" and not x["plan"]
    loop("hum", gate(lambda x: x["state"] != "debrief"), 0.20)
    loop("breath", gate(out), 0.30)
    loop("drill", gate(lambda x: x["drill"]), 0.45)
    loop("alarm", gate(lambda x: x["storm"] and out(x)), 0.16)
    walked, rng = 0.0, np.random.default_rng(1)
    for f, x in enumerate(log):
        if out(x) and 0 < x["moved"] < 200:           # a teleport between shots is not a step
            walked += x["moved"]
            if walked > 550:                          # marswalk_hud: one boot fall per 5.5 m on screen
                walked = 0.0
                hit("step", f, 0.5)
        if x["storm"] and out(x) and rng.random() < 14 / FPS:
            hit("tick", f, 0.3)
        if f and (x["cores"] != log[f - 1]["cores"] or x["photos"] != log[f - 1]["photos"] or x["state"] != log[f - 1]["state"]):
            hit("beep", f, 0.5)
    mix = np.clip(mix[:n], -1, 1)
    return (mix * 32767).astype("<i2")


def save_wav(path, data):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(data.tobytes())


def main(first):
    plan = json.load(open(SCRATCH / "demo_plan.json"))
    log = json.load(open(SCRATCH / "demo_log.json"))
    ch = plan["chapters"]
    assert len(log) == plan["frames"], (len(log), plan["frames"])
    caps = captions(ch)
    sfx = sound(log)
    save_wav(SCRATCH / "demo_full.wav", sfx)
    start = {c["name"]: c["start"] for c in ch}
    assert abs(sum(c[2] for c in CUT) - 30.0) < 1e-6
    parts = [sfx[int((start[name] + a) * SR):int((start[name] + a) * SR) + int(d * SR)] for name, a, d in CUT]   # same slices as the picture
    save_wav(SCRATCH / "demo_cut.wav", np.concatenate(parts))

    gh = H - STRIP
    gw = round(gh * W / H / 2) * 2
    chain = [f"[0:v]scale={gw}:{gh}:flags=lanczos,pad={W}:{H}:{(W - gw) // 2}:0:black[v0]"]
    for i, c in enumerate(ch):
        chain.append(f"[v{i}][{i + 1}:v]overlay=0:0:enable='between(t,{c['start']:.4f},{c['start'] + c['dur'] - 1e-3:.4f})'[v{i + 1}]")
    inputs = ["-framerate", str(FPS), "-start_number", str(first), "-i", str(FRAMES / "ScreenShot%05d.png")]
    for p in caps:
        inputs += ["-i", str(p)]
    enc = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "19", "-preset", "slow", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart"]
    run = lambda args: subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + args, check=True)
    MEDIA.mkdir(exist_ok=True)
    vout = f"[v{len(ch)}]"
    run(inputs + ["-i", str(SCRATCH / "demo_full.wav"), "-filter_complex", ";".join(chain), "-map", vout, "-map", f"{len(ch) + 1}:a",
                  "-frames:v", str(plan["frames"])] + enc + [str(MEDIA / "marswalk_full.mp4")])

    rng = "+".join(f"between(t,{start[n] + a:.4f},{start[n] + a + d - 1e-3:.4f})" for n, a, d in CUT)
    cut = chain + [f"{vout}select='{rng}',setpts=N/{FPS}/TB[vc]"]
    run(inputs + ["-i", str(SCRATCH / "demo_cut.wav"), "-filter_complex", ";".join(cut), "-map", "[vc]", "-map", f"{len(ch) + 1}:a", "-r", str(FPS), "-t", "30"]
        + enc + [str(MEDIA / "marswalk_demo.mp4")])
    for f in ("marswalk_full.mp4", "marswalk_demo.mp4"):
        d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(MEDIA / f)],
                                 capture_output=True, text=True).stdout)
        print(f"media/{f}: {d:.1f} s, {(MEDIA / f).stat().st_size / 1e6:.1f} MB")
        assert f != "marswalk_demo.mp4" or d <= 30.05, "the submission video must be 30 s or less"


if __name__ == "__main__":
    main(int(sys.argv[1]))
