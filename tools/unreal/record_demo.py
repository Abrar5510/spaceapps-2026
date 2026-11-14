"""Scripted demo capture in the running game (-game, 1600x900): one 'Shot showui' per frame, 30 fps timeline.

    python3 tools/ue.py tools/unreal/record_demo.py      (frames -> Marswalk/Saved/Screenshots/Mac/)
Then tools/make_video.sh assembles them.
"""
import math

import unreal

import marswalk_hud as m

FPS = 30
SECONDS = 28
R = m.ROUTE
CUM = m.CUM


def at_dist(d):
    """Route position (x, y, z) at distance d (cm) along the route."""
    i = max(0, min(len(CUM) - 2, next((k for k, c in enumerate(CUM) if c > d), len(CUM) - 1) - 1))
    t = (d - CUM[i]) / max(CUM[i + 1] - CUM[i], 1e-6)
    a, b = R[i], R[i + 1]
    return [a[j] + (b[j] - a[j]) * t for j in range(3)]


def look(pc, frm, to, pitch=-6):
    pc.set_control_rotation(unreal.Rotator(roll=0, pitch=pitch, yaw=math.degrees(math.atan2(to[1] - frm[1], to[0] - frm[0]))))


def place(pawn, p):
    pawn.set_actor_location(unreal.Vector(p[0], p[1], p[2] + 110), False, True)


# (start second, action) — key presses fire once
EVENTS = {int(7.0 * FPS): "T", int(10.5 * FPS): "M", int(12.5 * FPS): "L", int(14.5 * FPS): "L",
          int(16.5 * FPS): "L", int(18.5 * FPS): "L", int(18.8 * FPS): "M", int(23.5 * FPS): "K"}
state = {"f": 0, "handle": None}


def frame(dt):
    f = state["f"]
    h = m._state["hud"]
    if h is None or h.widget is None:
        return
    w = h.world
    pawn = unreal.GameplayStatics.get_player_pawn(w, 0)
    pc = unreal.GameplayStatics.get_player_controller(w, 0)
    t = f / FPS
    if f in EVENTS:
        h.press(EVENTS[f])
    s1, s2 = CUM[m.STOP_IDX[1]], CUM[m.STOP_IDX[2]]
    if t < 7.0:        # time-lapse walk out of the habitat toward the ridge stop
        d = s1 - 15000 + 12500 * (t / 7.0)
        p, ahead = at_dist(d), at_dist(d + 3000)
        place(pawn, p); look(pc, p, ahead)
    elif t < 10.5:     # arrive at the ridge stop: rover photo card
        p = at_dist(s1 - 1200 + (t - 7.0) * 250)
        place(pawn, p); look(pc, p, R[m.STOP_IDX[1]], -10)
    elif t < 19.5:     # habitat plan view (camera on BP_Marswalk); layers cycle via EVENTS
        pass
    elif t < 23.5:     # Monte Grande hollow and the Nevado Sajama ridge drill sites
        p = at_dist(s2 - 1800 + (t - 19.5) * 300)
        place(pawn, p); look(pc, p, R[m.STOP_IDX[3]], -12)
    else:              # solar storm: turn-back warning
        p = at_dist(s2 + 900)
        place(pawn, p); look(pc, p, R[0], -2)
    unreal.SystemLibrary.execute_console_command(w, "Shot showui")
    state["f"] = f + 1
    if state["f"] >= FPS * SECONDS:
        unreal.unregister_slate_post_tick_callback(state["handle"])
        for k in ("K", "T"):
            h.press(k)
        unreal.log("demo capture done")


state["handle"] = unreal.register_slate_post_tick_callback(frame)
print("recording", FPS * SECONDS, "frames")
