"""Marswalk mission: helmet HUD, suit, sampling, the solar-storm call and the debrief (runs in PIE and in -game).

One EVA, start to finish:
  brief  -> ENTER opens the airlock
  eva    -> follow the visor line, hold E at each stake to drill a sample (30 mission minutes), F to photograph
            the outcrop; oxygen drains with effort; after the second sample a solar storm arrives and the walker
            decides: turn back now, or stay for more science and take the dose
  debrief-> back at the habitat (or out of oxygen): samples, time, dose against the limit, oxygen left, score

Keys: WASD walk | Shift push pace | E sample | F photo | M habitat plan | L data layer | K storm drill | R restart.
Every number comes from data/site (built by tools/*.py from NASA data); the suit rules below are assumptions.
"""
import csv
import json
import math
import os
import random

import unreal

SITE = os.path.abspath(os.path.join(unreal.Paths.project_dir(), "..", "data", "site"))
G = "/Game/Marswalk"

# --- suit and mission rules (planning assumptions, not measurements) ---
TIME_SCALE = 10.0           # mission seconds per real second: 7 m/s on screen is the planner's 0.7 m/s suit pace
GRAVITY_SCALE = 12.0        # time-lapse falls fast too; at Mars gravity and this speed the walker sails off every crest
PACE_M_S = 0.7              # tools/plan_route.py
PUSH = 1.5                  # Shift (run): half again as fast, at 1.8x the oxygen
START_HOUR = 13.75          # airlock opens 13:45 LMST: the 3.1 h plan ends about half an hour before sunset
O2_HOURS = 4.0              # oxygen for the plan plus about 30% reserve at a steady walk
DOSE_LIMIT_UGY = 250.0      # dose rule for one EVA
SAMPLE_HOLD_S = 3.0         # hold E this long (real seconds); the mission clock runs the full 30 minutes
SAMPLE_RADIUS_M = 7.0
CARD_RADIUS_M = 25.0
HOME_RADIUS_M = 14.0
STORM_AFTER_SAMPLES = 2
STORM_WAIT_H = 1.0          # sheltering in the habitat until the dose rate falls back (assumption; no dose counted inside)
REFILL_MIN = 10.0           # topping up the suit oxygen at the airlock
SLOPE_LIMIT = 20.0
OFF_ROUTE_M = 15.0
LAYERS = ["HiRISE 25 cm image", "Slope (green flat, red >20°)", None, "Hazards: no-go in red (slope >20° or rock >0.5 m)"]


def _csv(name):
    with open(os.path.join(SITE, name)) as f:
        return list(csv.DictReader(f))


ROUTE = [(float(r["X"]), float(r["Y"]), float(r["Z"]), int(r["Stop"])) for r in _csv("route.csv")]
STOPS = _csv("stops.csv")
PHOTOS = _csv("photos/photos.csv")
STATS = json.load(open(os.path.join(SITE, "route_stats.json")))
COND = json.load(open(os.path.join(SITE, "conditions.json")))
STOP_IDX = {}
for _i, _r in enumerate(ROUTE):
    if _r[3] >= 0 and _r[3] not in STOP_IDX:
        STOP_IDX[_r[3]] = _i
STOP_IDX = [STOP_IDX[k] for k in range(len(STOPS))]
CUM = [0.0]
for _a, _b in zip(ROUTE, ROUTE[1:]):
    CUM.append(CUM[-1] + math.dist(_a[:3], _b[:3]))
_ti = json.load(open(os.path.join(SITE, "site.json")))["thermal_inertia_range"]
LAYERS[2] = f"THEMIS thermal inertia {_ti[0]:.0f}-{_ti[1]:.0f} SI (yellow loose, purple firm)"
_hm = lambda t: int(t[:2]) + int(t[3:]) / 60
SUNSET = _hm(COND["sunset_lmst"])
DEC = math.asin(math.sin(math.radians(25.19)) * math.sin(math.radians(COND["ls_deg"])))
LAT = math.radians(-4.808)
SAMPLE_S = STATS["assumptions"]["stop_minutes"] * 60.0
QUIET_UGY_S = STATS["dose_rates"]["quiet_mGy_day"] * 1000 / 86400
STORM_UGY_S = STATS["dose_rates"]["storm_mGy_day"] * 1000 / 86400
N_STOPS = len(STOPS) - 1
COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def sun_angles(hour_lmst):
    """Sun elevation and azimuth (deg, azimuth clockwise from north) at the site."""
    h = math.radians((hour_lmst + COND["lmst_to_ltst_h"] - 12) * 15)
    el = math.asin(math.sin(LAT) * math.sin(DEC) + math.cos(LAT) * math.cos(DEC) * math.cos(h))
    az = math.atan2(-math.sin(h) * math.cos(DEC), math.cos(LAT) * math.sin(DEC) - math.sin(LAT) * math.cos(DEC) * math.cos(h))
    return math.degrees(el), math.degrees(az) % 360


def bearing(dx, dy):
    """Compass bearing of an Unreal XY offset (X east, Y south)."""
    return math.degrees(math.atan2(dx, -dy)) % 360


def nearest(x, y):
    best, bi = 1e30, 0
    for i, r in enumerate(ROUTE):
        d = (r[0] - x) ** 2 + (r[1] - y) ** 2
        if d < best:
            best, bi = d, i
    return bi, math.sqrt(best) / 100


def hm(hours):
    return f"{int(hours)} h {int(round((hours - int(hours)) * 60)):02d}"


def clock(hour):
    return f"{int(hour) % 24:02d}:{int((hour - int(hour)) * 60):02d}"


def o2_factor(speed_m_s, climb_m_s, pushing, drilling):
    """Oxygen use relative to a steady walk on the flat: resting 0.6, climbing costs extra, pushing 1.8x."""
    if drilling:
        return 0.8
    if speed_m_s < 0.1:
        return 0.6
    grade = max(climb_m_s, 0.0) / max(speed_m_s, 0.1)
    return (1.0 + 6.0 * grade) * (1.8 if pushing else 1.0)


def score(samples, photos, dose, o2, back_hour, failed):
    """0-100: science first, then coming home inside the rules."""
    if failed:
        return 0
    s = 15.0 * samples + 2.5 * photos
    s += 15.0 if dose <= DOSE_LIMIT_UGY else max(0.0, 15.0 - (dose - DOSE_LIMIT_UGY) / 10.0)
    s += 10.0 * min(o2 / 0.15, 1.0)
    s += 5.0 if back_hour <= SUNSET else 0.0
    return int(round(s))


def brief_text():
    s, c = STATS, COND
    return (f"Science goal: sample a boxwork ridge and the hollow beside it to learn how long groundwater flowed here.\n\n"
            f"Route  {s['distance_m'] / 1000:.1f} km loop, {N_STOPS} stops, {s['climb_m']:.0f} m of climb, planned {s['eva_time_h']:.1f} h.\n"
            f"The line avoids slopes over {SLOPE_LIMIT:.0f}° and rock over 0.5 m (HiRISE 1 m elevation).\n\n"
            f"Suit  {O2_HOURS:.0f} h of oxygen at a steady walk. Climbing and pushing the pace use more.\n"
            f"Radiation  quiet Sun today: {s['dose_quiet_mGy'] * 1000:.0f} µGy for the plan (Curiosity RAD). Limit for this EVA: {DOSE_LIMIT_UGY:.0f} µGy.\n"
            f"Daylight  airlock opens {clock(START_HOUR)} LMST, sunset {c['sunset_lmst']}. Air {c['air_min_c']} to {c['air_max_c']} °C, {c['pressure_pa']} Pa (REMS sol {c['sol']}).\n\n"
            f"The walk is shown as a {TIME_SCALE:.0f}x time-lapse: the suit pace is {PACE_M_S} m/s, the clock, oxygen and dose run at mission time.\n"
            f"Controls  [W A S D] walk, [Mouse] look, hold [Shift] to run (uses more oxygen).\n"
            f"At each stake: hold [E] to drill a core, press [F] to photograph the outcrop next to Curiosity's own frame.")


def plan_text():
    s, c = STATS, COND
    legs = "\n".join(f"  {i}  {st['Title']}  ({float(st['DistM']):.0f} m)" for i, st in enumerate(STOPS) if i)
    return (f"HABITAT PLAN: Boxwork ridges, Mount Sharp\nScience goal: sample ridges and hollows to date the groundwater\n\n"
            f"Route  {s['distance_m'] / 1000:.2f} km loop | climb {s['climb_m']:.0f} m | steepest {s['steepest_slope_deg']:.0f}°\n"
            f"Walk {s['walk_time_min']:.0f} min + {s['stop_time_min']} min at stops = EVA {s['eva_time_h']:.1f} h\n"
            f"Dose (RAD, quiet Sun): {s['dose_quiet_mGy'] * 1000:.0f} µGy  |  whole EVA in a storm: {s['dose_storm_mGy'] * 1000:.0f} µGy\n"
            f"Stops:\n{legs}\n\n"
            f"Conditions sol {c['sol']} (REMS): air {c['air_min_c']} to {c['air_max_c']} °C, ground {c['ground_min_c']} to "
            f"{c['ground_max_c']} °C, {c['pressure_pa']} Pa, UV {c['uv_index']}\nSunrise {c['sunrise_lmst']}, sunset {c['sunset_lmst']} LMST\n\n"
            f"No-go: slope >{SLOPE_LIMIT:.0f}° or rock/ledge >0.5 m ({s['nogo_fraction'] * 100:.0f}% of the site)")


def _key(name):
    k = unreal.Key()
    k.import_text(name)  # works in -game too (set_editor_property is editor-only for this struct)
    return k


KEYS = {n: _key(n) for n in ("M", "L", "K", "E", "F", "R", "Enter", "LeftShift", "Tab", "X")}
HIT, GONE = unreal.SlateVisibility.SELF_HIT_TEST_INVISIBLE, unreal.SlateVisibility.COLLAPSED   # children (buttons) stay clickable
BUTTONS = {"BtnMap": "M", "BtnBack": "M", "BtnHudMap": "M", "BtnLayer": "L", "BtnHudLayer": "L", "BtnPhoto": "F", "BtnRestart": "R", "BtnStart": "Start", "BtnEnd": "X"}


class Mission:
    def __init__(self, world):
        self.world = world
        self.state = "brief"
        self.layer, self.storm, self.plan = 0, False, False
        self.t = 0.0                          # mission seconds since the airlock opened
        self.dose, self.o2, self.walked = 0.0, 1.0, 0.0
        self.samples, self.photos = set(), set()
        self.drill = 0.0                      # 0..1 progress of the current core
        self.left_home, self.failed, self.note, self.note_until = False, "", "", 0.0
        self.last, self.stride, self.effort = None, 0.0, 0.6
        self.widget, self.loops = None, {}
        self.force = set()                    # keys held by a script (demo recording, tests)
        self.once, self.held = set(), set()   # one-frame presses from HUD buttons; buttons down last frame
        self.free, self.cursor = False, None  # Tab frees the mouse cursor during the walk
        self.grade, self.phase, self.sway, self.lean = 0.0, 0.0, 0.0, (0.0, 0.0)
        self.mpc = unreal.load_asset(f"{G}/MPC_Marswalk")
        self.snd = {n: unreal.load_asset(f"{G}/Audio/S_{n}") for n in ("breath", "hum", "step", "drill", "beep", "alarm", "tick")}
        self.sun = unreal.GameplayStatics.get_actor_of_class(world, unreal.DirectionalLight)
        self.manager = unreal.GameplayStatics.get_actor_of_class(world, unreal.load_class(None, f"{G}/BP_Marswalk.BP_Marswalk_C"))
        self.plan_only = unreal.GameplayStatics.get_all_actors_with_tag(world, "PlanOnly")
        self.labels = unreal.GameplayStatics.get_all_actors_with_tag(world, "BeaconLabel")
        unreal.MaterialLibrary.set_scalar_parameter_value(world, self.mpc, "Layer", 0.0)
        for a in self.plan_only:
            a.set_actor_hidden_in_game(True)

    # --- widget helpers ---
    def w(self, name):
        return self.widget.get_editor_property(name)

    def text(self, name, s):
        self.w(name).set_text(unreal.Text(s))

    def show(self, name, on):
        self.w(name).set_visibility(HIT if on else GONE)

    def bar(self, name, frac, color=None):
        b = self.w(name)
        b.set_percent(max(0.0, min(1.0, frac)))
        if color:
            b.set_fill_color_and_opacity(unreal.LinearColor(*color))

    def play(self, name, volume=1.0, pitch=1.0):
        if self.snd[name]:
            unreal.GameplayStatics.play_sound2d(self.world, self.snd[name], volume, pitch)

    def loop(self, name, on, volume=1.0, pitch=1.0):
        c = self.loops.get(name)
        if on and c is None and self.snd[name]:
            c = self.loops[name] = unreal.GameplayStatics.spawn_sound2d(self.world, self.snd[name], volume, pitch)
        if c is not None:
            if on:
                c.set_volume_multiplier(volume)
                c.set_pitch_multiplier(pitch)
            else:
                c.stop()
                self.loops[name] = None

    def say(self, s, seconds=5.0):
        self.note, self.note_until = s, self.t + seconds * TIME_SCALE

    # --- commands (also reachable from the browser: py import marswalk_hud; marswalk_hud.press('M')) ---
    def press(self, k):
        world = self.world
        if k == "L":
            self.layer = (self.layer + 1) % 4
            unreal.MaterialLibrary.set_scalar_parameter_value(world, self.mpc, "Layer", float(self.layer))
            self.say(f"Layer: {LAYERS[self.layer]}", 4)
        elif k == "K":
            self.set_storm(not self.storm)
        elif k == "M":
            self.plan = not self.plan
            pc = unreal.GameplayStatics.get_player_controller(world, 0)
            target = self.manager if self.plan else unreal.GameplayStatics.get_player_pawn(world, 0)
            pc.set_view_target_with_blend(target, 1.5, unreal.ViewTargetBlendFunction.VT_BLEND_EASE_IN_OUT, 2.0, False)
            for a in self.plan_only:
                a.set_actor_hidden_in_game(not self.plan)
        elif k == "Enter" and self.state == "brief":
            self.state = "eva"
            self.play("beep")
            self.say("Airlock open. Follow the line to stop 1.", 6)
        elif k == "Enter" and self.state == "base":      # refill, sit out the storm if there is one, go back out
            wait = REFILL_MIN * 60 + (STORM_WAIT_H * 3600 if self.storm else 0)
            self.t += wait
            self.o2, self.left_home, self.state = 1.0, False, "eva"
            self.set_storm(False)
            self.play("beep")
            self.say(f"Oxygen full. {wait / 60:.0f} min in the habitat. Back out for the remaining cores.", 6)
        elif k == "X" and self.state == "base":
            self.finish()
        elif k == "Start":
            self.press("R" if self.state == "debrief" else "Enter")
        elif k == "Tab":
            self.free = not self.free
        elif k == "F":
            self.once.add("F")
        elif k == "R":
            unreal.SystemLibrary.execute_console_command(world, "RestartLevel")

    def set_storm(self, on):
        self.storm = on
        self.loop("alarm", on, 0.5)

    def finish(self, failed=""):
        self.state, self.failed = "debrief", failed
        for n in list(self.loops):
            self.loop(n, False)
        self.play("beep")

    # --- per frame ---
    def tick(self):
        world = self.world
        pc = unreal.GameplayStatics.get_player_controller(world, 0)
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        if not pc or not pawn:
            return
        if self.widget is None:
            found = [x for x in unreal.WidgetLibrary.get_all_widgets_of_class(world, unreal.load_class(None, f"{G}/WBP_HUD.WBP_HUD_C"), False)
                     if x.is_in_viewport()]
            if not found:
                raise RuntimeError("WBP_HUD not on screen yet (BP_Marswalk creates it on BeginPlay)")
            self.widget = found[0]
            self.text("TxtStats", plan_text())
            self.widget.set_cursor(unreal.MouseCursor.NONE)          # ImgCursor is the pointer
            self.w("ImgCursor").set_render_transform_angle(-30.0)
            self.text("TxtKeys", "[W A S D] walk     [Mouse] look     [Shift] run     hold [E] drill     [Tab] mouse cursor on/off")
            ps = unreal.GameplayStatics.get_actor_of_class(world, unreal.PlayerStart)
            if ps and (pawn.get_actor_location() - ps.get_actor_location()).length() > 500:
                pawn.set_actor_location(ps.get_actor_location(), False, True)   # PIE can spawn at the editor camera
                pc.set_control_rotation(ps.get_actor_rotation())
        if not self.widget.is_in_viewport():
            raise RuntimeError("level restarted")              # _tick starts a fresh Mission with the new widget
        dt = unreal.GameplayStatics.get_world_delta_seconds(world)
        for k in ("M", "L", "K", "Enter", "R", "Tab", "X"):
            if pc.was_input_key_just_pressed(KEYS[k]):
                self.press(k)
        down = {b for b in BUTTONS if self.w(b).is_pressed()}
        for b in down - self.held:
            self.press(BUTTONS[b])
        self.held = down
        cursor = self.state != "eva" or self.plan or self.free
        if cursor != self.cursor:
            self.cursor = cursor
            pc.set_editor_property("show_mouse_cursor", cursor)
            if cursor:
                unreal.WidgetLibrary.set_input_mode_ui_only_ex(pc, None, unreal.MouseLockMode.DO_NOT_LOCK, False)   # lets go of the mouse
                unreal.WidgetLibrary.set_input_mode_game_and_ui_ex(pc, None, unreal.MouseLockMode.DO_NOT_LOCK, False, False)
            else:
                unreal.WidgetLibrary.set_input_mode_game_only(pc, False)

        move = pawn.get_component_by_class(unreal.CharacterMovementComponent)
        if move and move.get_editor_property("gravity_scale") != GRAVITY_SCALE:
            move.set_editor_property("gravity_scale", GRAVITY_SCALE)
        eva = self.state == "eva"
        pushing = eva and (pc.is_input_key_down(KEYS["LeftShift"]) or "LeftShift" in self.force)
        loc = pawn.get_actor_location()
        hit = unreal.SystemLibrary.line_trace_single(world, loc, loc - unreal.Vector(0, 0, 600), unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,
                                                     True, [pawn], unreal.DrawDebugTrace.NONE, True)
        n = hit.to_tuple()[7] if hit else unreal.Vector(0, 0, 1)
        slope = math.degrees(math.acos(max(-1.0, min(1.0, n.z))))
        if eva_now := self.state == "eva":
            # The body stands square to the ground: the view pitches with the slope ahead and rolls with the cross slope.
            rot = pc.get_control_rotation()
            y = math.radians(rot.yaw)
            nz = max(n.z, 0.3)
            want_p = 0.7 * math.degrees(math.atan(-(n.x * math.cos(y) + n.y * math.sin(y)) / nz))
            want_r = 0.8 * math.degrees(math.atan((-n.x * math.sin(y) + n.y * math.cos(y)) / nz))
            k = min(1.0, unreal.GameplayStatics.get_world_delta_seconds(world) * 4.0)
            # ponytail: head sway rides on the view angles; moving the template camera component itself throws it 30 m up
            new_p = self.lean[0] + (want_p - self.sway * abs(math.sin(self.phase)) - self.lean[0]) * k
            new_r = self.lean[1] + (want_r + 0.6 * self.sway * math.sin(self.phase) - self.lean[1]) * k
            pitch = (rot.pitch + 180) % 360 - 180 + new_p - self.lean[0]
            pc.set_control_rotation(unreal.Rotator(roll=new_r, pitch=max(-85.0, min(85.0, pitch)), yaw=rot.yaw))
            self.lean = (new_p, new_r)
            if slope > SLOPE_LIMIT:                       # too steep to stand on: boots slide downhill
                pawn.add_movement_input(unreal.Vector(n.x, n.y, 0).normal(), min((slope - SLOPE_LIMIT) / 10.0, 1.0), True)
        i, off_m = nearest(loc.x, loc.y)
        home_m = math.hypot(ROUTE[0][0] - loc.x, ROUTE[0][1] - loc.y) / 100
        near = min(range(1, len(STOPS)), key=lambda k: math.hypot(ROUTE[STOP_IDX[k]][0] - loc.x, ROUTE[STOP_IDX[k]][1] - loc.y))
        near_m = math.hypot(ROUTE[STOP_IDX[near]][0] - loc.x, ROUTE[STOP_IDX[near]][1] - loc.y) / 100
        can_drill = eva and near_m < SAMPLE_RADIUS_M and near not in self.samples
        drilling = can_drill and (pc.is_input_key_down(KEYS["E"]) or "E" in self.force)
        if move:
            hill = min(max(1.0 - 3.5 * self.grade, 0.3), 1.35)   # the suit slows on a climb, lengthens its stride downhill
            move.set_editor_property("max_walk_speed", 0.0 if (not eva or drilling) else PACE_M_S * 100 * TIME_SCALE * (PUSH if pushing else 1.0) * hill)

        # motion since last frame (on-screen metres; mission pace is this / TIME_SCALE)
        if self.last is None:
            self.last = loc
        step = math.hypot(loc.x - self.last.x, loc.y - self.last.y) / 100
        climb = (loc.z - self.last.z) / 100
        self.last = loc
        speed = step / max(dt, 1e-4) / TIME_SCALE
        if step > 0.02:
            self.grade += (max(-0.5, min(0.5, climb / step)) - self.grade) * min(1.0, dt * 3.0)
        self.phase += step / (0.55 * TIME_SCALE) * math.pi     # stride phase, drives the head sway below
        self.sway = (3.0 + 30.0 * max(self.grade, 0.0)) / 10.0 * min(speed / PACE_M_S, 1.0)   # degrees: heavier steps on a climb
        hour = START_HOUR + self.t / 3600.0

        if eva:
            mdt = dt * TIME_SCALE
            if drilling:
                self.drill += dt / SAMPLE_HOLD_S
                mdt = dt / SAMPLE_HOLD_S * SAMPLE_S            # the core takes 30 mission minutes
                if self.drill >= 1.0:
                    self.drill = 0.0
                    self.samples.add(near)
                    self.play("beep")
                    self.say(f"Core {len(self.samples)} of {N_STOPS} sealed: {STOPS[near]['Title']}.", 5)
                    if len(self.samples) == STORM_AFTER_SAMPLES and not self.storm:
                        self.set_storm(True)
            else:
                self.drill = max(0.0, self.drill - dt)
            factor = o2_factor(speed, climb / max(dt, 1e-4) / TIME_SCALE, pushing, drilling)
            self.effort += (factor - self.effort) * min(1.0, dt * 0.8)
            self.t += mdt
            self.o2 -= mdt / (O2_HOURS * 3600.0) * factor
            self.dose += mdt * (STORM_UGY_S if self.storm else QUIET_UGY_S)
            self.walked += step
            self.stride += step
            if self.stride > 0.55 * TIME_SCALE:                # one boot fall every ~0.8 s on screen
                self.stride = 0.0
                self.play("step", 0.5, random.uniform(0.85, 1.15))
            if random.random() < dt * (14.0 if self.storm else 0.5):
                self.play("tick", 0.35, random.uniform(0.9, 1.1))   # dose-rate ticks: sparse on a quiet day, a hail in a storm
            if (pc.was_input_key_just_pressed(KEYS["F"]) or "F" in self.force or "F" in self.once) and near_m < CARD_RADIUS_M and near not in self.photos:
                self.photos.add(near)
                self.play("beep", 0.7, 1.4)
                self.say(f"Outcrop photographed. Compare with Curiosity's frame, sol {PHOTOS[near]['Sol']}.", 5)
            edge = 3000.0, (len(ROUTE) and 201600.0) - 3000.0          # the 1 m elevation model ends at the site box
            if not (edge[0] < loc.x < edge[1] and edge[0] < loc.y < edge[1]):
                pawn.set_actor_location(unreal.Vector(min(max(loc.x, edge[0]), edge[1]), min(max(loc.y, edge[0]), edge[1]), loc.z), False, True)
                self.say("Edge of the surveyed map: no 1 m elevation data beyond here.", 4)
            if home_m > 40:
                self.left_home = True
            if self.o2 <= 0:
                self.o2 = 0.0
                self.finish("OUT OF OXYGEN")
            elif self.left_home and home_m < HOME_RADIUS_M:
                if len(self.samples) < N_STOPS:
                    self.state = "base"                        # at the airlock: refill and go again, or call it a day
                    self.loop("alarm", False)
                    self.play("beep")
                else:
                    self.finish()
        self.loop("hum", self.state != "debrief", 0.25)
        self.loop("breath", eva, 0.25 + 0.2 * min(self.effort, 2.5), 0.85 + 0.2 * min(self.effort, 2.5))
        self.loop("drill", drilling, 0.6)

        # Sun follows the mission clock
        el, az = sun_angles(hour)
        a = math.radians(az)
        if self.sun:
            self.sun.set_actor_rotation(unreal.Rotator(roll=0, pitch=-el, yaw=math.degrees(math.atan2(math.cos(a), -math.sin(a)))), False)
        for lab in self.labels:  # stop numbers face the walker (text renders are one-sided)
            l = lab.get_actor_location()
            lab.set_actor_rotation(unreal.Rotator(roll=0, pitch=0, yaw=math.degrees(math.atan2(loc.y - l.y, loc.x - l.x))), False)

        # --- navigation ---
        todo = [k for k in range(1, len(STOPS)) if k not in self.samples]
        go_home = self.storm or not todo
        nxt = 0 if go_home else todo[0]
        tgt = ROUTE[0] if nxt == 0 else ROUTE[STOP_IDX[nxt]]
        dx, dy = tgt[0] - loc.x, tgt[1] - loc.y
        heading = (pc.get_control_rotation().yaw + 90) % 360
        brg = bearing(dx, dy)
        back_min = min(CUM[i], CUM[-1] - CUM[i]) / 100 / PACE_M_S / 60
        self.w("ImgArrow").set_render_transform_angle((brg - heading + 180) % 360 - 180)
        self.text("TxtDist", f"{math.hypot(dx, dy) / 100:.0f} m")
        name = "HABITAT" if nxt == 0 else f"STOP {nxt}  {STOPS[nxt]['Title'].upper()}"
        deg = math.degrees(math.atan(self.grade))
        hill_txt = f"UPHILL {deg:.0f}°: slower, more oxygen" if deg > 3 else f"DOWNHILL {-deg:.0f}°" if deg < -3 else "level ground"
        self.text("TxtNav", f"{name}   |   heading {heading:03.0f}° {COMPASS[int((heading + 22.5) // 45) % 8]}   |   {hill_txt}")

        # --- checklist and clocks ---
        lines = []
        for k in range(1, len(STOPS)):
            mark = "[x]" if k in self.samples else "[  ]"
            cam = "  +photo" if k in self.photos else ""
            lines.append(f"{mark}  {k}  {STOPS[k]['Title']}{cam}")
        lines.append(("[>]" if go_home else "[  ]") + "  Return to the habitat")
        self.text("TxtObj", "\n".join(lines))
        ev = int(self.t)
        self.text("TxtClock", f"EVA {ev // 3600}:{ev % 3600 // 60:02d}   |   {clock(hour)} LMST   |   walk home {back_min:.0f} min")

        # --- suit ---
        o2_h = self.o2 * O2_HOURS / max(self.effort, 0.6)
        self.text("TxtO2", f"OXYGEN  {self.o2 * 100:.0f}%   about {hm(o2_h)} at this effort")
        self.bar("BarO2", self.o2, (1.0, 0.25, 0.2, 1) if self.o2 < 0.15 else (0.35, 0.85, 1.0, 1))
        rate_h = (STORM_UGY_S if self.storm else QUIET_UGY_S) * 3600
        self.text("TxtDose", f"DOSE  {self.dose:.0f} of {DOSE_LIMIT_UGY:.0f} µGy   {rate_h:.0f} µGy/h")
        f = self.dose / DOSE_LIMIT_UGY
        self.bar("BarDose", f, (1.0, 0.25, 0.2, 1) if f > 1 or self.storm else (0.55, 1.0, 0.55, 1))
        left = SUNSET - hour
        self.text("TxtDay", f"DAYLIGHT  {hm(max(left, 0))} to sunset")
        self.bar("BarDay", left / (SUNSET - START_HOUR), (1.0, 0.25, 0.2, 1) if left < 0.5 else (1.0, 0.8, 0.35, 1))
        self.text("TxtStatus", f"Slope {slope:.0f}°   pace {speed:.1f} m/s{'  PUSHING' if pushing else ''}   effort x{self.effort:.1f}\n"
                               f"Outside {COND['air_min_c']} to {COND['air_max_c']} °C, {COND['pressure_pa']} Pa   {self.walked / 1000:.2f} km walked")

        # --- prompt and warnings: storm > oxygen > off route > slope > daylight ---
        want_photo = eva and near_m < CARD_RADIUS_M and near not in self.photos
        if drilling:                                  # always say what to do next, with the key
            prompt = f"Keep holding [E]: drilling core, {self.drill * SAMPLE_S / 60:.0f} of {SAMPLE_S / 60:.0f} min"
        elif can_drill:
            prompt = f"HOLD [E] to drill a core at stop {near}" + ("      press [F] to photograph the outcrop" if want_photo else "")
        elif want_photo:
            prompt = "Press [F] to photograph the outcrop" + ("" if near in self.samples else f"      stake is {near_m:.0f} m ahead: walk to it to drill")
        elif eva and self.t < self.note_until:
            prompt = self.note
        elif nxt == 0:
            prompt = ("Storm: follow the arrow home now, or walk to another stake and hold [E]" if todo else "All cores sealed: follow the arrow") + "      hold [Shift] to run"
        else:
            prompt = f"Follow the arrow and the ground line to stop {nxt}      [W] walk   [Mouse] look   hold [Shift] to run"
        self.text("TxtPrompt", prompt)
        self.show("BarAction", drilling or (can_drill and self.drill > 0))
        self.bar("BarAction", self.drill)
        if not eva:
            warn = ""
        elif self.storm:
            mult = STATS["dose_rates"]["storm_mGy_day"] / STATS["dose_rates"]["quiet_mGy_day"]
            warn = (f"SOLAR STORM  dose rate x{mult:.0f}  (Curiosity RAD, 20 May 2024)\n"
                    f"Habitat {back_min:.0f} min away = +{back_min * 60 * STORM_UGY_S:.0f} µGy.  Each core here = +{SAMPLE_S * STORM_UGY_S:.0f} µGy.\n"
                    f"At the habitat you can refill, wait {STORM_WAIT_H:.0f} h for it to pass and come back out.  Your call.")
        elif self.o2 < 0.15:
            warn = f"OXYGEN {self.o2 * 100:.0f}%: head for the habitat"
        elif off_m > OFF_ROUTE_M:
            warn = f"OFF ROUTE {off_m:.0f} m: unchecked ground, return to the line"
        elif slope > SLOPE_LIMIT:
            warn = f"SLOPE {slope:.0f}°: above the {SLOPE_LIMIT:.0f}° suit limit"
        elif left < 0.75:
            warn = "LESS THAN 45 min OF DAYLIGHT: head back"
        else:
            warn = ""
        self.text("TxtWarn", warn)

        # --- cards ---
        hud = eva and not self.plan
        self.once.clear()
        self.show("ImgCursor", cursor)
        if cursor:
            mp = unreal.WidgetLayoutLibrary.get_mouse_position_on_viewport(world)
            unreal.WidgetLayoutLibrary.slot_as_canvas_slot(self.w("ImgCursor")).set_position(unreal.Vector2D(mp.x - 6.5, mp.y - 2))
        self.w("BtnEnd").set_visibility(unreal.SlateVisibility.VISIBLE if self.state == "base" else GONE)
        for n in ("ObjBox", "SuitBox", "ImgArrow", "TxtDist", "TxtNav", "TxtPrompt", "TxtKeys", "KeyBtns"):
            self.show(n, hud)
        card = near if near_m < CARD_RADIUS_M else (0 if home_m < CARD_RADIUS_M and self.left_home else -1)
        self.show("StopCard", hud and card >= 0 and not self.storm)       # the storm banner takes over
        for k in range(5):
            self.show(f"ImgStop{k}", k == card)
        if card >= 0:
            st, ph = STOPS[card], PHOTOS[card]
            self.text("TxtStop", f"{card}  {st['Title']}\n{st['Note']}\nCuriosity {ph['Camera']}, sol {ph['Sol']}, at this spot (NASA/JPL-Caltech)")
        self.show("PlanCard", self.plan)
        self.show("BigCard", self.state != "eva" and not self.plan)
        if self.state == "brief":
            self.text("TxtBigTitle", "MARSWALK  EVA-1  Boxwork ridges, Mount Sharp")
            self.text("TxtBig", brief_text())
            self.text("TxtStartBtn", "OPEN THE AIRLOCK  [Enter]")
        elif self.state == "debrief":
            self.text("TxtBigTitle", self.failed or "EVA COMPLETE")
            self.text("TxtBig", self.debrief(hour))
            self.text("TxtStartBtn", "NEW MISSION  [R]")
        elif self.state == "base":
            left_h = SUNSET - hour
            wait = REFILL_MIN + (STORM_WAIT_H * 60 if self.storm else 0)
            self.text("TxtBigTitle", "AIRLOCK  back at the habitat")
            self.text("TxtBig", f"Cores  {len(self.samples)} of {N_STOPS} sealed.   Dose  {self.dose:.0f} of {DOSE_LIMIT_UGY:.0f} µGy.   Oxygen  {self.o2 * 100:.0f}%.\n"
                                f"{clock(hour)} LMST, {hm(max(left_h, 0))} of daylight left.\n\n"
                                + (f"The storm is still up. Inside you are shielded. Waiting {STORM_WAIT_H:.0f} h for it to pass, plus {REFILL_MIN:.0f} min to refill, "
                                   f"leaves {hm(max(left_h - wait / 60, 0))} of daylight for the cores still in the ground.\n"
                                   if self.storm else f"Refilling the suit takes {REFILL_MIN:.0f} min.\n")
                                + "Go back out, or end the mission here and take the debrief.")
            self.text("TxtStartBtn", ("WAIT OUT THE STORM, REFILL, GO BACK OUT" if self.storm else "REFILL OXYGEN, GO BACK OUT") + "  [Enter]")

    def debrief(self, hour):
        got = ", ".join(STOPS[k]["Title"] for k in sorted(self.samples)) or "none"
        missed = ", ".join(STOPS[k]["Title"] for k in range(1, len(STOPS)) if k not in self.samples)
        over = self.dose - DOSE_LIMIT_UGY
        if self.failed:
            verdict = "The suit ran dry before the airlock. Pushing the pace and climbing cost more oxygen than the plan allowed."
        elif over > 0 and len(self.samples) == N_STOPS:
            verdict = f"Every core, but {over:.0f} µGy over the rule: the flight surgeon grounds you for the next EVA."
        elif over > 0:
            verdict = f"{over:.0f} µGy over the dose rule. Turning back sooner would have kept you inside it."
        elif len(self.samples) == N_STOPS:
            verdict = "Every core, inside every limit. Textbook."
        elif self.storm:
            verdict = "You gave up science to stay inside the dose rule. That is the call the rule exists for."
        else:
            verdict = "Home safe, with cores still in the ground."
        return (f"Cores  {len(self.samples)} of {N_STOPS}:  {got}\n"
                + (f"Left in the ground:  {missed}\n" if missed else "")
                + f"Outcrop photos  {len(self.photos)} of {N_STOPS}\n\n"
                f"EVA time  {hm(self.t / 3600)}  (plan {hm(STATS['eva_time_h'])}),  back at {clock(hour)} LMST, sunset {COND['sunset_lmst']}\n"
                f"Dose  {self.dose:.0f} µGy  (limit {DOSE_LIMIT_UGY:.0f}, quiet-day plan {STATS['dose_quiet_mGy'] * 1000:.0f})\n"
                f"Oxygen left  {self.o2 * 100:.0f}%\n\n{verdict}\n\n"
                f"SCORE  {score(len(self.samples), len(self.photos), self.dose, self.o2, hour, bool(self.failed))} / 100")


_state = {"hud": None}


def _game_world():
    try:  # editor: the Play-In-Editor world, if playing
        return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()
    except Exception:  # -game: the one world that has a player
        for w in unreal.ObjectIterator(unreal.World):
            try:
                if unreal.GameplayStatics.get_player_controller(w, 0):
                    return w
            except Exception:
                pass
    return None


def _tick(dt):
    hud = _state["hud"]
    w = _game_world()
    if hud is not None and w != hud.world:
        _state["hud"] = hud = None
    if hud is not None:
        try:
            hud.tick()
            return
        except Exception as e:  # world ended (PIE stopped) or reloaded
            unreal.log_warning(f"Marswalk HUD reset: {e}")
            _state["hud"] = None
            return
    if w is not None:
        _state["hud"] = Mission(w)


def press(k):
    if _state["hud"] is not None:
        _state["hud"].press(k)


def start():
    if not _state.get("handle"):
        _state["handle"] = unreal.register_slate_post_tick_callback(_tick)


def demo():
    """Self-check of the suit rules: python3 tools/ue.py -c "import marswalk_hud as m; m.demo()" """
    plan_o2 = (STATS["walk_time_min"] * 1.3 + STATS["stop_time_min"] * 0.8) / 60 / O2_HOURS
    assert 0.5 < plan_o2 < 0.9, f"the plan should use most of the oxygen but leave a reserve, uses {plan_o2:.2f}"
    quiet = STATS["eva_time_h"] * 3600 * QUIET_UGY_S
    assert quiet < DOSE_LIMIT_UGY / 4, "a quiet-day EVA must sit well inside the dose limit"
    assert SAMPLE_S * STORM_UGY_S * (N_STOPS - STORM_AFTER_SAMPLES) + quiet > DOSE_LIMIT_UGY, "staying for every core in the storm must break the limit"
    assert score(4, 4, 100, 0.3, 16.5, False) == 100 and score(4, 4, 100, 0.3, 16.5, True) == 0
    assert o2_factor(0.7, 0.0, False, False) == 1.0 and o2_factor(0.7, 0.12, True, False) > 3
    print(f"mission rules ok: plan uses {plan_o2 * 100:.0f}% oxygen, quiet dose {quiet:.0f} µGy, one core in the storm {SAMPLE_S * STORM_UGY_S:.0f} µGy")
