"""Editor-only helper: run Python job files dropped into <repo>/.scratch/ue_jobs (local files, no network).

tools/ue.py writes <id>.py there; this runs it on the editor's main thread and writes <id>.out and <id>.done.
"""
import contextlib
import io
import os
import traceback

import unreal

JOBS = os.path.abspath(os.path.join(unreal.Paths.project_dir(), "..", ".scratch", "ue_jobs"))
os.makedirs(JOBS, exist_ok=True)
_acc = [0.0]


_busy = [False]


def _tick(dt):
    # Long jobs pump Slate (progress dialogs, saves), which calls this again: never start a job inside a job.
    if _busy[0]:
        return
    _acc[0] += dt
    if _acc[0] < 0.3:
        return
    _acc[0] = 0.0
    _busy[0] = True
    try:
        _run_pending()
    finally:
        _busy[0] = False


def _run_pending():
    for name in sorted(os.listdir(JOBS)):
        if not name.endswith(".py"):
            continue
        path = os.path.join(JOBS, name)
        base = path[:-3]
        if os.path.exists(base + ".done") or os.path.exists(base + ".started"):
            continue
        open(base + ".started", "w").close()  # a crash mid-job must not re-run it on the next launch
        buf = io.StringIO()
        ok = True
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try:
                code = open(path).read()
                exec(compile(code, path, "exec"), {"__name__": "__main__", "__file__": path})
            except Exception:
                ok = False
                traceback.print_exc()
        with open(base + ".out", "w") as f:
            f.write(buf.getvalue())
        with open(base + ".done", "w") as f:
            f.write("ok" if ok else "error")


unreal.register_slate_post_tick_callback(_tick)

import marswalk_hud  # noqa: E402  helmet HUD / plan view logic for PIE and -game

marswalk_hud.start()
unreal.log(f"Marswalk job runner watching {JOBS}")
