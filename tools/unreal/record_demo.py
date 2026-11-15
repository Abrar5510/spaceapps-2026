"""Scripted demo capture in the running game (-game, 1600x900): one 'Shot showui' per frame, 30 fps timeline.

    python3 tools/demo_script.py                                        (chapters, narration, lengths)
    start the game with -UseFixedTimeStep -FPS=30 so every frame is exactly 1/30 s of game time
    python3 tools/ue.py tools/unreal/record_demo.py                     (frames -> Marswalk/Saved/Screenshots/)
Then python3 tools/make_video.py <first frame number> adds captions and sound and cuts both videos.

One whole EVA: the habitat map and its data layers, the brief, walk, core, storm, run home, airlock refill, two more cores in
the late light, Curiosity, home before sunset, debrief. Walking legs are shortened; where the film jumps ahead
the mission clock, oxygen and dose are advanced as the plan would have them (skip()).
"""
import json
import math
import os

import unreal

import marswalk_hud as m

FPS = 30
R, CUM = m.ROUTE, m.CUM
PACE = m.PACE_M_S * 100 * m.TIME_SCALE      # on-screen cm/s
S = [CUM[i] for i in m.STOP_IDX]
ST4 = R[m.STOP_IDX[4]]
ROVER = (ST4[0] + 500, ST4[1] + 350)        # tools/unreal/build_props.py
A4 = (ST4[0] - 900, ST4[1] - 500)           # where the Curiosity approach starts
PLAN = json.load(open(os.path.join(unreal.Paths.project_dir(), "..", ".scratch", "demo_plan.json")))   # tools/demo_script.py
START = {c["name"]: int(round(c["start"] * FPS)) for c in PLAN["chapters"]}   # in frames: no rounding slips
DUR = {c["name"]: c["dur"] for c in PLAN["chapters"]}
ORDER = [c["name"] for c in PLAN["chapters"]]
FRAMES = PLAN["frames"]
LOG = []
state = {"f": 0, "handle": None}


def at_dist(d):
    i = max(0, min(len(CUM) - 2, next((k for k, c in enumerate(CUM) if c > d), len(CUM) - 1) - 1))
    t = (d - CUM[i]) / max(CUM[i + 1] - CUM[i], 1e-6)
    return [R[i][j] + (R[i + 1][j] - R[i][j]) * t for j in range(3)]


def ground(w, x, y, pawn):
    h = unreal.SystemLibrary.line_trace_single(w, unreal.Vector(x, y, 30000), unreal.Vector(x, y, -30000),
                                               unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, [pawn], unreal.DrawDebugTrace.NONE, True)
    return h.to_tuple()[4].z if h else 0.0


def skip(h, hour):
    """Jump the mission clock; oxygen and dose move as a steady walk would have moved them."""
    dt = (hour - m.START_HOUR) * 3600 - h.t
    if dt > 0:
        h.t += dt
        h.dose += dt * m.QUIET_UGY_S
        h.o2 = max(h.o2 - dt / (m.O2_HOURS * 3600) * 1.2, 0.3)


def frame(dt):
    h = m._state["hud"]
    if h is None or h.widget is None:
        return
    f = state["f"]
    t = f / FPS
    w = h.world
    pawn = unreal.GameplayStatics.get_player_pawn(w, 0)
    pc = unreal.GameplayStatics.get_player_controller(w, 0)
    seg = [n for n in ORDER if START[n] <= f][-1]
    u = (f - START[seg]) / FPS                       # seconds into this chapter
    D = DUR[seg]
    once = lambda sec: f == START[seg] + int(round(sec * FPS))

    def put(p):
        pawn.set_actor_location(unreal.Vector(p[0], p[1], p[2] + 110), False, True)

    def look(frm, to, pitch=-6.0):
        roll = pc.get_control_rotation().roll        # keep the slope lean the HUD code applies
        pc.set_control_rotation(unreal.Rotator(roll=roll, pitch=pitch, yaw=math.degrees(math.atan2(to[1] - frm[1], to[0] - frm[0]))))

    def along(d, ahead=2500.0, pitch=-6.0):
        p = at_dist(d); put(p); look(p, at_dist(d + ahead), pitch)

    def core(k, start):                              # walk the last metres to the stake, photograph, drill
        if u < start:
            p = at_dist(S[k] - 250 - (start - u) * PACE); put(p); look(p, R[m.STOP_IDX[k]], -10)
        else:
            if once(start):
                h.press("F")
            if k not in h.samples:
                h.force = {"E"}

    h.force = set()
    if once(0.0):
        h.last = None
    if seg == "map":                                 # habitat plan view first: this is a map
        if once(0.0):
            h.press("M")
        along(3000)
    elif seg == "layers":                            # image -> slope -> thermal inertia -> hazards
        for frac in (0.22, 0.45, 0.72):
            if once(D * frac):
                h.press("L")
        along(3000)
    elif seg == "route":                             # hazards with the route on top, then back to the image
        if once(D * 0.6):
            h.press("L")
        along(3000)
    elif seg == "brief":
        if once(0.0):
            h.press("M")
        along(3000)
    elif seg == "walk1":
        if once(0.0):
            h.press("Enter")
        along(3000 + u * PACE)
    elif seg == "stop1":
        core(1, 1.5)
    elif seg == "core2":                             # second core: the storm arrives
        core(2, 1.5)
    elif seg == "run":                               # turn back, running
        h.force = {"LeftShift"}
        along(S[2] - 300 - u * PACE * m.PUSH, -2500.0, -4)
    elif seg == "airlock":                           # refill, wait out the storm, go again
        if once(0.0):                                # the rest of the run home, not filmed: storm dose and running oxygen
            left_s = (S[2] - 300 - DUR["run"] * PACE * m.PUSH) / 100 / (m.PACE_M_S * m.PUSH)
            h.t += left_s
            h.dose += left_s * m.STORM_UGY_S
            h.o2 -= left_s / (m.O2_HOURS * 3600) * 1.8
            put((R[0][0] + 300, R[0][1] + 300, R[0][2])); look(R[0], (R[0][0] + 1900, R[0][1] - 1300), 0)
        if once(D - 1.6):
            h.press("Enter")
    elif seg == "stop3":
        if once(0.0):
            skip(h, 16.2)
        core(3, 1.2)
    elif seg == "stop4":                             # Curiosity, where it stood on sol 4855; then the last core
        if once(0.0):
            skip(h, 16.7)
        if u < 4.0:
            k = u * PACE / math.hypot(ROVER[0] - A4[0], ROVER[1] - A4[1])
            x, y = A4[0] + (ROVER[0] - A4[0]) * k, A4[1] + (ROVER[1] - A4[1]) * k
            put((x, y, ground(w, x, y, pawn))); look((x, y), ROVER, -3)
        else:
            if once(4.0):
                p = at_dist(S[4] - 250); put(p); look(p, R[m.STOP_IDX[4]], -10); h.last = None
            core(4, 4.0)
    elif seg == "home":                              # last leg, low Sun
        if once(0.0):
            skip(h, 17.0)
        along(CUM[-1] - 9000 + u * PACE, 2500.0, -3)
    else:                                            # debrief
        if once(0.0):
            put((R[0][0] + 300, R[0][1] + 300, R[0][2])); look(R[0], (R[0][0] + 1900, R[0][1] - 1300), 0)
    loc = pawn.get_actor_location()
    prev = state.get("loc", loc)
    state["loc"] = loc
    LOG.append({"state": h.state, "plan": h.plan, "storm": h.storm, "drill": h.drill > 0 and "E" in h.force,
                "moved": round(math.hypot(loc.x - prev.x, loc.y - prev.y)), "cores": len(h.samples), "photos": len(h.photos)})
    unreal.SystemLibrary.execute_console_command(w, "Shot showui")
    state["f"] = f + 1
    if state["f"] >= FRAMES:
        unreal.unregister_slate_post_tick_callback(state["handle"])
        h.force = set()
        json.dump(LOG, open(os.path.join(unreal.Paths.project_dir(), "..", ".scratch", "demo_log.json"), "w"))
        unreal.log("demo capture done")


state["handle"] = unreal.register_slate_post_tick_callback(frame)
print("recording", FRAMES, "frames")
