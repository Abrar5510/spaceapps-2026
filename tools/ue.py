"""Run Python inside the running Unreal Editor through the local job folder (see Marswalk/Content/Python/init_unreal.py).

    python3 tools/ue.py -c "import unreal; print(unreal.SystemLibrary.get_engine_version())"
    python3 tools/ue.py tools/unreal/build_scene.py
"""
import os
import sys
import time
import uuid

JOBS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".scratch", "ue_jobs")


def run(code, timeout=1800):
    os.makedirs(JOBS, exist_ok=True)
    base = os.path.join(JOBS, f"{time.strftime('%H%M%S')}_{uuid.uuid4().hex[:6]}")
    with open(base + ".tmp", "w") as f:
        f.write(code)
    os.rename(base + ".tmp", base + ".py")  # atomic: the editor never sees a half-written job
    t0 = time.time()
    while not os.path.exists(base + ".done"):
        if time.time() - t0 > timeout:
            sys.exit(f"timed out; is the editor running? job: {base}.py")
        time.sleep(0.2)
    print(open(base + ".out").read(), end="")
    if open(base + ".done").read() != "ok":
        sys.exit(1)


if __name__ == "__main__":
    if sys.argv[1] == "-c":
        run(sys.argv[2])
    else:
        path = os.path.abspath(sys.argv[1])
        d = os.path.dirname(path)
        run(f"import runpy, sys; sys.path.insert(0, {d!r}); sys.modules.pop('common', None); "
            f"sys.argv={[path] + sys.argv[2:]!r}; runpy.run_path({path!r}, run_name='__main__')")
