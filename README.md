# Dust & Bearings — Marswalk

NASA Space Apps Challenge 2026 · Universal Event · Challenge: [Interplanetary Survival Guide: Martian Map](challenges/interplanetary-survival-guide-martian-map.md)
Team page: https://www.spaceappschallenge.org/2026/find-a-team/dust-bearings/

**Play it live:** https://play.marswalk.earth (streamed from our machine when it is online; click to start) · **Demo video (30 s):** [`media/marswalk_demo.mp4`](media/marswalk_demo.mp4) · **Full walkthrough (102 s):** [`media/marswalk_full.mp4`](media/marswalk_full.mp4)

## Summary

Marswalk is a hyperlocal map for one astronaut excursion: a 2 km × 2 km piece of Mount Sharp in Gale crater, where Curiosity explored boxwork ridges in 2025. The science goal is to sample a ridge and the hollow beside it to learn how long groundwater flowed there. We built the ground from NASA's 1 m HiRISE elevation model and 25 cm HiRISE image, layered THEMIS thermal inertia, slope and a hazard map, and planned a 2.0 km walking loop for a suited astronaut that avoids slopes over 20° and blocky rock. The loop visits four stops Curiosity actually drilled or imaged. It runs in Unreal Engine 5.8 and streams to a browser. In the habitat, the crew sees a plan view with route numbers, dose and weather. On the walk, a helmet HUD gives bearing and distance to the next stop, slope underfoot, elapsed time, radiation dose from Curiosity's RAD, time to sunset and the walk home, plus Curiosity's own photo of each stop. A solar-storm switch replays the May 2024 event RAD measured and tells the walker to turn back.

## The mission

Marswalk is played as one EVA. A brief in the habitat gives the science goal, route, oxygen, dose limit and daylight. Outside, the helmet shows a line on the ground to the next stop, a checklist, and oxygen, dose and daylight bars. At each of the four stops the walker drills a core (30 mission minutes) and can photograph the outcrop beside Curiosity's own frame of it. Oxygen drains faster on climbs and when pushing the pace. After the second core a solar storm arrives at the dose rate Curiosity measured in May 2024, and the HUD prices the choice: the dose for walking home now against the dose for each further core. Back at the airlock the walker can refill oxygen, sit out the storm inside the habitat and go out again for the remaining cores, or end the mission. A debrief then scores cores, dose against the limit, oxygen left and daylight. The walk is shown as a 10x time-lapse: the suit pace is 0.7 m/s, slower on climbs, and the clock, oxygen and dose run at mission time. The view tilts with the ground underfoot. Curiosity itself (NASA's model) stands at stop 4, where the rover was on sol 4855.

## What it shows

| Brief asks for | Marswalk |
|---|---|
| One hyperlocal location and a science goal | Boxwork ridges and hollows on Mount Sharp, Gale crater (lat −4.808°, lon 137.3815°) |
| At least 3 data types | Topographic (HiRISE 1 m DTM), optical (HiRISE 25 cm ortho), thermal (THEMIS thermal inertia), radiation (Curiosity RAD), atmospheric (Curiosity REMS) |
| Walking route that avoids obstacles, for a suited walker | 2.04 km loop, 112 m climb, steepest step 19.7°, 65 min walking + 4 × 30 min at stops = 3.1 h EVA. No-go: slope > 20° or > 0.5 m rock/ledge relief (29 % of the site) |
| Safety info | Dose for this EVA: 0.027 mGy on a quiet day vs 1.04 mGy in a storm like May 2024; live dose, sunset countdown, walk-home time, off-route and steep-slope warnings |
| Rover point-of-view images | A Curiosity Navcam frame taken at each stop (sols 4541, 4628, 4693, 4718, 4855) |
| Display format | Helmet HUD (walk view) and habitat screen (plan view), streamed to a browser |

## How it works

```
NASA files ─> tools/prep_site.py ─> terrain + layer textures, slope, roughness, thermal inertia (data/site)
              tools/plan_route.py ─> route.csv, stops.csv, route_stats.json   (+ built-in check)
              tools/conditions.py, get_photos.py, rocks.py, terrain_mesh.py, route_mesh.py
                         │
              tools/build_unreal.sh ─> Unreal level: Nanite terrain, layer material, Mars sky/Sun/dust,
                         │             route line, stop beacons, rocks, plan camera, HUD widget
                         │
              Marswalk/Content/Python/marswalk_hud.py ─> per-frame HUD + plan view logic
                         │
              Pixel Streaming 2 ─> browser
```

- **Site and data.** GDAL reprojects the HiRISE DTM, orthoimage and THEMIS mosaic onto one 2017 × 2017 grid at 1 m. Slope is taken over a 3 m baseline, because HiRISE stereo resolves about 3 m. Roughness is the height spread left in a 3 m window after removing the local plane, which picks out rocks and ledges.
- **Route.** Each 1 m cell costs walking time: 0.7 m/s on flat ground, Tobler's hiking function for slope, and up to 30 % slower on low-thermal-inertia (sandy) ground. Dijkstra links the habitat and the four stops, then the path is straightened wherever a straight line stays 1 m clear of no-go cells. `plan_route.py` then checks the result: every step is out of no-go cells and under 20°, and the loop closes.
- **Stops.** Curiosity's own positions on those sols: the ridge stop (sol 4628), the Monte Grande hollow where it drilled "Valle de la Luna" (sol 4693), the Nevado Sajama ridge drill (sol 4718), and the southern edge of the boxwork (sol 4855).
- **Radiation.** Curiosity RAD measured 0.21 mGy/day (0.64 mSv/day) on the surface (Hassler et al. 2014), and 8.1 mGy during the 20 May 2024 solar storm.
- **Conditions.** The REMS record for sol 4693 gives temperatures, pressure, UV, sunrise and sunset. The Sun is placed from the solar declination at Ls 157° and the site latitude, so shadows match the time of day.
- **Unreal 5.8.** The DTM becomes 16 Nanite tiles with collision on the real surface. One material blends the HiRISE image, slope, thermal and hazard layers, switched by a Material Parameter Collection. The sky uses Mars values: thin CO₂ plus dust with optical depth about 0.6, which gives a butterscotch sky. Mars gravity is 3.71 m/s²; because the walk is a 10x time-lapse, falls are sped up to match so the walker stays on the ground. 74,000 scanned rocks (Poly Haven, CC0) sit where the DTM is rough, and scanned sand, regolith and bedrock add close-up grain under the HiRISE colour: bedrock where the DTM is steep or blocky, sand where HiRISE is dark. The rest of the HiRISE strip (7.5 km × 18.5 km) is the backdrop, so the horizon is Mount Sharp itself. The project has no C++. Scene building and the HUD logic are Python inside the editor and game, and the HUD layout is a UMG widget.

## Run it

Needs Unreal Engine 5.8 and Xcode on macOS (Unreal compiles Metal shaders with it).

```bash
tools/editor.sh
```

Opens the project with `DEVELOPER_DIR` pointed at Xcode. In the editor, press **Play**. Pixel Streaming 2 streams the Play-In-Editor view automatically. Open http://localhost and click to start. The editor hosts the signalling server on ports 80/8888.

Standalone window instead of the editor:

```bash
open -n --env DEVELOPER_DIR=/Volumes/Transend/Apps/Xcode.app/Contents/Developer -a /Volumes/Transend/Apps/UE_5.8/Engine/Binaries/Mac/UnrealEditor.app --args "$PWD/Marswalk/Marswalk.uproject" -game -windowed -ResX=1600 -ResY=900
```

### Host it online (play.marswalk.earth)

```bash
tools/serve.sh
```

Starts the Pixel Streaming 2 signalling server (player page on port 80, streamer on 8888) and the standalone game streaming into it; closing the game or Ctrl+C stops both. The script also applies three fixes to the signalling server that ships with UE 5.8 (a leftover 5.7 package name, the commander version, and the static-file switch). A Cloudflare Tunnel running as a macOS LaunchAgent forwards https://play.marswalk.earth to port 80, so no ports are opened on the router. WebRTC uses Google's public STUN server; viewers behind strict firewalls would need a TURN server. One machine streams to one or two viewers at a time.

The game runs from the editor binary in `-game` mode rather than as a packaged build, because the HUD and mission logic are Python, which only runs with the editor.

| Key | Action |
|---|---|
| Enter | Open the airlock (starts the EVA) |
| WASD + mouse | Walk (suit pace, shown as a 10x time-lapse) |
| Shift | Run: 1.5x speed, 1.8x oxygen |
| Tab | Mouse cursor on/off, to click the HUD buttons |
| Enter / X | At the airlock: refill and go back out / end the mission |
| E (hold) | Drill a core at a stop's stake |
| F | Photograph the outcrop at a stop |
| M | Habitat plan view ↔ helmet view |
| L | Data layer: HiRISE image → slope → thermal inertia → hazards |
| K | Solar storm on/off (it also arrives by itself after the second core) |
| R | New mission |

The same commands work from the browser console through Pixel Streaming: `py import marswalk_hud; marswalk_hud.press('M')`.

## Rebuild from the NASA data

```bash
python3 tools/prep_site.py
```

```bash
python3 tools/plan_route.py
```

```bash
python3 tools/conditions.py && python3 tools/get_photos.py && python3 tools/get_assets.py && python3 tools/rocks.py && python3 tools/terrain_mesh.py && python3 tools/far_terrain.py && python3 tools/route_mesh.py && python3 tools/make_ui.py
```

```bash
tools/build_unreal.sh --terrain --route
```

The first step downloads nothing. Put the raw files listed in [DATA.md](DATA.md) in `data/raw/` first. The last step needs the editor open.

Demo videos: `python3 tools/demo_script.py` writes the chapter plan; start the standalone game with `-UseFixedTimeStep -FPS=30` added, run `python3 tools/ue.py tools/unreal/record_demo.py`, then `python3 tools/make_video.py <first frame number>` adds captions and sound and writes the 102 s walkthrough and the 30 s cut. The walkthrough shortens the walking legs; where it jumps ahead, the clock, oxygen and dose are advanced as a steady walk would have moved them.

## Assumptions

Suit pace (0.7 m/s), slope limit (20°), rock limit (0.5 m), sand slowdown (30 %) and time per stop (30 min) are planning assumptions, not measurements. They are constants at the top of `tools/plan_route.py`. The THEMIS thermal inertia is 100 m/px, so it marks sandier vs firmer ground at that scale only. HiRISE resolves features of about 3 m: smaller rocks are not in the DTM, and the walk-view clasts are placed for scale, not mapped. The suit rules (4 h of oxygen, 250 µGy dose rule, 30 min per core) are assumptions at the top of `Marswalk/Content/Python/marswalk_hud.py`.

## Super Intelligence (AI) use

The code in this repository (data pipeline, route planner, Unreal build scripts, HUD logic) and this README were written with an AI coding assistant (Anthropic's Claude), directed and reviewed by the team. All data are NASA (and NASA partner) measurements listed in [DATA.md](DATA.md). No AI-generated images or video are used. The demo videos are frames rendered by the running Unreal scene, with captions added. Their sound is the game's own suit sounds, synthesised by code in `tools/make_ui.py`. There is no voice-over.

## Layout

```
Marswalk/        UE 5.8 project (Pixel Streaming 2, Nanite, Lumen, VSM); Content/Python = HUD + job runner
tools/           data pipeline (*.py), Unreal build scripts (unreal/), editor launcher, video
data/site/       baked site data (Git LFS for images); data/raw/ is git-ignored
media/           demo videos (30 s cut and full walkthrough)
DATA.md          every dataset, tool and asset used
PLAN.md          build plan
```

## Before submitting

- [ ] Push to GitHub and make the repository public; check it opens logged out
- [ ] Upload `media/marswalk_demo.mp4` to a public link (the form needs a link)
- [ ] Confirm the Universal Event deadline on the Space Apps site
- [ ] Fill in the Project tab (summary above, details, DATA.md lists), then press **Submit for Judging**
