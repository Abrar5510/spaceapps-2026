"""Marswalk helmet HUD and habitat plan view: per-frame logic for WBP_HUD (runs in PIE and in -game).

Keys: M plan view | L data layer | K solar storm | [ ] time of day | T time x10.
All numbers come from data/site (built by tools/*.py from NASA data).
"""
import csv
import json
import math
import os

import unreal

SITE = os.path.abspath(os.path.join(unreal.Paths.project_dir(), "..", "data", "site"))
PACE_CM_S = 70.0                 # suit pace (tools/plan_route.py)
SLOPE_LIMIT = 20.0
OFF_ROUTE_M = 15.0
STOP_RADIUS_M = 25.0
LAYERS = ["HiRISE 25 cm image", "Slope (green flat, red >20°)",
          None, "Hazards: no-go in red (slope >20° or rock >0.5 m)"]


def _csv(name):
    with open(os.path.join(SITE, name)) as f:
        return list(csv.DictReader(f))


def _load():
    route = [(float(r["X"]), float(r["Y"]), float(r["Z"]), int(r["Stop"])) for r in _csv("route.csv")]
    stops = _csv("stops.csv")
    photos = _csv("photos/photos.csv")
    stats = json.load(open(os.path.join(SITE, "route_stats.json")))
    cond = json.load(open(os.path.join(SITE, "conditions.json")))
    stop_idx = {}
    for i, r in enumerate(route):
        if r[3] >= 0 and r[3] not in stop_idx:
            stop_idx[r[3]] = i
    cum = [0.0]
    for a, b in zip(route, route[1:]):
        cum.append(cum[-1] + math.dist(a[:3], b[:3]))
    return route, stops, photos, stats, cond, [stop_idx[k] for k in range(len(stops))], cum


ROUTE, STOPS, PHOTOS, STATS, COND, STOP_IDX, CUM = _load()
_ti = json.load(open(os.path.join(SITE, "site.json")))["thermal_inertia_range"]
LAYERS[2] = f"THEMIS thermal inertia {_ti[0]:.0f}-{_ti[1]:.0f} SI (yellow loose, purple firm)"
_hm = lambda t: int(t[:2]) + int(t[3:]) / 60
SUNSET = _hm(COND["sunset_lmst"])
DEC = math.asin(math.sin(math.radians(25.19)) * math.sin(math.radians(COND["ls_deg"])))
LAT = math.radians(-4.808)


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


def stop_text(k):
    st, ph = STOPS[k], PHOTOS[k]
    return (f"{k}  {st['Title']}\n{st['Note']}\nCuriosity {ph['Camera']}, sol {ph['Sol']}, at this spot (NASA/JPL-Caltech)\n"
            f"On route: {float(st['DistM']):.0f} m from habitat")


def plan_text():
    s, c = STATS, COND
    legs = "\n".join(f"  {i}  {st['Title']}  ({float(st['DistM']):.0f} m)" for i, st in enumerate(STOPS) if i)
    return (f"HABITAT PLAN: Boxwork ridges, Mount Sharp\nScience goal: sample ridges and hollows to date the groundwater\n\n"
            f"Route  {s['distance_m'] / 1000:.2f} km loop | climb {s['climb_m']:.0f} m | steepest {s['steepest_slope_deg']:.0f}°\n"
            f"Walk {s['walk_time_min']:.0f} min + {s['stop_time_min']} min at stops = EVA {s['eva_time_h']:.1f} h\n"
            f"Dose (RAD, quiet Sun): {s['dose_quiet_mGy']:.3f} mGy  |  storm: {s['dose_storm_mGy']:.2f} mGy\n"
            f"Stops:\n{legs}\n\n"
            f"Conditions sol {c['sol']} (REMS): air {c['air_min_c']} to {c['air_max_c']} °C, ground {c['ground_min_c']} to "
            f"{c['ground_max_c']} °C, {c['pressure_pa']} Pa, UV {c['uv_index']}\nSunrise {c['sunrise_lmst']}, sunset {c['sunset_lmst']} LMST\n\n"
            f"No-go: slope >{SLOPE_LIMIT:.0f}° or rock/ledge >0.5 m ({s['nogo_fraction'] * 100:.0f}% of the site)")


def _key(name):
    k = unreal.Key()
    k.import_text(name)  # works in -game too (set_editor_property is editor-only for this struct)
    return k


KEYS = {n: _key(n) for n in ("M", "L", "K", "T", "LeftBracket", "RightBracket")}


class Hud:
    def __init__(self, world):
        self.world = world
        self.layer, self.storm, self.plan, self.warp = 0, False, False, False
        self.start_hour, self.elapsed, self.dose = 10.0, 0.0, 0.0
        self.widget = None
        self.mpc = unreal.load_asset("/Game/Marswalk/MPC_Marswalk")
        self.sun = unreal.GameplayStatics.get_actor_of_class(world, unreal.DirectionalLight)
        self.manager = unreal.GameplayStatics.get_actor_of_class(world, unreal.load_class(None, "/Game/Marswalk/BP_Marswalk.BP_Marswalk_C"))
        self.plan_only = unreal.GameplayStatics.get_all_actors_with_tag(world, "PlanOnly")
        self.labels = unreal.GameplayStatics.get_all_actors_with_tag(world, "BeaconLabel")
        unreal.MaterialLibrary.set_scalar_parameter_value(world, self.mpc, "Layer", 0.0)
        for a in self.plan_only:
            a.set_actor_hidden_in_game(True)

    def find_widget(self, pc):
        cls = unreal.load_class(None, "/Game/Marswalk/WBP_HUD.WBP_HUD_C")
        found = unreal.WidgetLibrary.get_all_widgets_of_class(self.world, cls, False)
        if not found:
            raise RuntimeError("WBP_HUD not on screen yet (BP_Marswalk creates it on BeginPlay)")
        return found[0]

    def w(self, name):
        return self.widget.get_editor_property(name)

    def text(self, name, s):
        self.w(name).set_text(unreal.Text(s))

    def show(self, name, on):
        self.w(name).set_visibility(unreal.SlateVisibility.HIT_TEST_INVISIBLE if on else unreal.SlateVisibility.COLLAPSED)

    def press(self, k):
        """One HUD command; also reachable from the browser: py import marswalk_hud; marswalk_hud.press('M')"""
        world = self.world
        if k == "L":
            self.layer = (self.layer + 1) % 4
            unreal.MaterialLibrary.set_scalar_parameter_value(world, self.mpc, "Layer", float(self.layer))
        elif k == "K":
            self.storm = not self.storm
        elif k == "T":
            self.warp = not self.warp
            unreal.GameplayStatics.set_global_time_dilation(world, 10.0 if self.warp else 1.0)
        elif k == "LeftBracket":
            self.start_hour -= 0.5
        elif k == "RightBracket":
            self.start_hour += 0.5
        elif k == "M":
            self.plan = not self.plan
            pc = unreal.GameplayStatics.get_player_controller(world, 0)
            target = self.manager if self.plan else unreal.GameplayStatics.get_player_pawn(world, 0)
            pc.set_view_target_with_blend(target, 1.5, unreal.ViewTargetBlendFunction.VT_BLEND_EASE_IN_OUT, 2.0, False)
            for a in self.plan_only:
                a.set_actor_hidden_in_game(not self.plan)

    def tick(self):
        world = self.world
        pc = unreal.GameplayStatics.get_player_controller(world, 0)
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        if not pc or not pawn:
            return
        if self.widget is None:
            self.widget = self.find_widget(pc)
            self.text("TxtStats", plan_text())
            warn = self.w("TxtWarn")  # readable against a bright dusty sky
            warn.set_shadow_offset(unreal.Vector2D(2, 2))
            warn.set_shadow_color_and_opacity(unreal.LinearColor(0, 0, 0, 0.9))
            warn.set_color_and_opacity(unreal.SlateColor(unreal.LinearColor(1.0, 0.18, 0.12, 1)))
            ps = unreal.GameplayStatics.get_actor_of_class(world, unreal.PlayerStart)
            if ps and (pawn.get_actor_location() - ps.get_actor_location()).length() > 500:
                # PIE can spawn at the editor camera; every walk starts at the habitat.
                pawn.set_actor_location(ps.get_actor_location(), False, True)
                pc.set_control_rotation(ps.get_actor_rotation())
        dt = unreal.GameplayStatics.get_world_delta_seconds(world)

        for k in KEYS:
            if pc.was_input_key_just_pressed(KEYS[k]):
                self.press(k)

        # clock, dose, Sun
        self.elapsed += dt
        rate = STATS["dose_rates"]["storm_mGy_day" if self.storm else "quiet_mGy_day"]
        self.dose += dt * rate / 86400.0
        hour = self.start_hour + self.elapsed / 3600.0
        el, az = sun_angles(hour)
        a = math.radians(az)
        if self.sun:
            self.sun.set_actor_rotation(unreal.Rotator(roll=0, pitch=-el, yaw=math.degrees(math.atan2(math.cos(a), -math.sin(a)))), False)

        # navigation along the planned route
        loc = pawn.get_actor_location()
        for lab in self.labels:  # stop numbers face the walker (text renders are one-sided)
            l = lab.get_actor_location()
            lab.set_actor_rotation(unreal.Rotator(roll=0, pitch=0, yaw=math.degrees(math.atan2(loc.y - l.y, loc.x - l.x))), False)
        i, off_m = nearest(loc.x, loc.y)
        nxt = next((k for k in range(1, len(STOPS)) if STOP_IDX[k] > i + 2), 0)
        tgt = ROUTE[STOP_IDX[nxt]] if nxt else ROUTE[-1]
        dx, dy = tgt[0] - loc.x, tgt[1] - loc.y
        dist_m = math.hypot(dx, dy) / 100
        heading = (pc.get_control_rotation().yaw + 90) % 360
        back_min = min(CUM[i], CUM[-1] - CUM[i]) / PACE_CM_S / 60
        hit = unreal.SystemLibrary.line_trace_single(world, loc, loc - unreal.Vector(0, 0, 600),
                                                     unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, [pawn],
                                                     unreal.DrawDebugTrace.NONE, True)
        slope = math.degrees(math.acos(max(-1.0, min(1.0, hit.to_tuple()[7].z)))) if hit else 0.0
        name = STOPS[nxt]["Title"] if nxt else "Habitat (return)"
        self.text("TxtNav", f"Heading {heading:03.0f}°   Next: {nxt or 'H'} {name}  {bearing(dx, dy):03.0f}°  {dist_m:.0f} m")
        ev = int(self.elapsed)
        hh = int(hour) % 24
        self.text("TxtStatus",
                  f"Slope {slope:.0f}° | EVA {ev // 3600:02d}:{ev % 3600 // 60:02d}:{ev % 60:02d} | Dose {self.dose:.4f} mGy ({rate:.2f} mGy/day)\n"
                  f"{hh:02d}:{int((hour - int(hour)) * 60):02d} LMST | sunset in {max(SUNSET - hour, 0):.1f} h | walk home {back_min:.0f} min"
                  f"{' | TIME x10' if self.warp else ''}\nLayer: {LAYERS[self.layer]}   |   Air {COND['air_min_c']} to {COND['air_max_c']} °C, "
                  f"{COND['pressure_pa']} Pa, UV {COND['uv_index']}")

        # warnings: storm > off route > too steep
        if self.storm:
            warn = (f"SOLAR STORM: dose rate x{STATS['dose_rates']['storm_mGy_day'] / STATS['dose_rates']['quiet_mGy_day']:.0f} "
                    f"(8.1 mGy/day, Curiosity RAD, May 2024)\nTURN BACK NOW: {back_min:.0f} min walk to the habitat")
        elif off_m > OFF_ROUTE_M:
            warn = f"OFF ROUTE {off_m:.0f} m: return to the blue line"
        elif slope > SLOPE_LIMIT:
            warn = f"SLOPE {slope:.0f}°: above the {SLOPE_LIMIT:.0f}° suit limit"
        elif hour > SUNSET - 1:
            warn = "LESS THAN 1 h OF DAYLIGHT: head back"
        else:
            warn = ""
        self.text("TxtWarn", warn)

        # rover photo card when near a stop; plan card in plan view
        card = next((k for k in range(len(STOPS))
                     if math.hypot(ROUTE[STOP_IDX[k]][0] - loc.x, ROUTE[STOP_IDX[k]][1] - loc.y) / 100 < STOP_RADIUS_M), -1)
        self.show("StopCard", card >= 0 and not self.plan and not self.storm)  # storm warning takes over
        for k in range(5):
            self.show(f"ImgStop{k}", k == card)
        if card >= 0:
            self.text("TxtStop", stop_text(card))
        self.show("PlanCard", self.plan)
        self.show("NavBox", not self.plan)


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
        _state["hud"] = Hud(w)


def press(k):
    if _state["hud"] is not None:
        _state["hud"].press(k)


def start():
    if not _state.get("handle"):
        _state["handle"] = unreal.register_slate_post_tick_callback(_tick)
