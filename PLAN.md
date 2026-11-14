# Marswalk — end-to-end plan

Team Dust & Bearings · NASA Space Apps 2026 · Interplanetary Survival Guide: Martian Map
Written Sat 14 Nov 2026, 11:30 PKT. Times below are PKT.

> **Confirm first:** the exact submission deadline on the Universal Event page. This plan assumes end of day Sun 15 Nov and aims to submit by 18:00 Sunday, leaving a buffer.

## 1. What we are building

A realistic, walkable 2 km × 2 km piece of Mars in Unreal Engine 5.8, opened in a browser through Pixel Streaming. An astronaut uses it two ways:

- **Plan view (habitat screen):** overhead map with switchable data layers, the walking route, and route numbers (distance, climb, time, radiation dose).
- **Walk view (helmet HUD):** first-person walk along the route with bearing and distance to the next stop, slope underfoot, time and dose so far, hazard warnings, and real rover photos at each stop.

One site, one route, one science goal. No globe, no site picker.

## 2. Site and science goal

**Site: the boxwork ridges on Mount Sharp, Gale crater.** Science goal: sample the ridges and the hollows between them to learn how long groundwater lasted there.

Why this site:

- It is the brief's own worked example, so judges see the fit at once.
- Curiosity drove through it in 2025, so there are ground photos for the "what to expect" views.
- Gale is the only place on Mars with radiation measured on the surface (Curiosity's RAD), so the safety layer uses real data, not a model.
- HiRISE covers Mount Sharp at 25 cm images and 1 m elevation.

**Fallback site** if the 1 m elevation data does not cover the boxwork area (checked in step 0): a stretch of Curiosity's earlier Mount Sharp traverse that sits inside the USGS merged Gale elevation model. Same pipeline, same data sources, different crop box.

## 3. Data layers

Five layers in the minimum build. The brief asks for three.

| # | Type | Source | Scale | What it tells the astronaut |
|---|------|--------|-------|-----------------------------|
| 1 | Topographic | HiRISE DTM (uahirise.org/dtm), or USGS "MSL Gale Merged DEM 1m" | 1 m | Terrain shape, slope, drop-offs |
| 2 | Optical | HiRISE orthoimage, or USGS "MSL Gale Merged Orthophoto Mosaic 25cm" | 25 cm | What the ground looks like, visible rocks |
| 3 | Thermal | THEMIS thermal inertia mosaic (USGS Astropedia / Mars Trek) | 100 m | Loose sand (low) vs bedrock (high): footing |
| 4 | Radiation | MSL RAD surface dose (PDS), about 0.6–0.7 mSv/day in quiet conditions (Hassler et al. 2014; replace with the value for the chosen sols) | site-wide | Dose for this walk; storm scenario |
| 5 | Atmospheric | MSL REMS (PDS Atmospheres node): pressure, air and ground temperature, UV | site-wide | Conditions panel, daylight left |

Supporting data: Curiosity raw images (Mastcam, Navcam) and the rover's sol-by-sol position for placing photo stops; the USGS geologic map for unit names.

Stretch layers: CRISM minerals (18 m), NASA DONKI space weather alerts.

Every dataset actually used gets a line in `DATA.md` with URL, product ID and date fetched. The submission form asks for this list, so write it as you download, not at the end.

## 4. How it works

```
NASA files ──> tools/prep_site.py ──> heightmap.png, ortho.png, slope.png, thermal.png, cost.npy
                                              │
                         tools/plan_route.py ─┴─> route.csv, route_stats.json
                                              │
                          Unreal: Landscape + layer material + route spline + HUD
                                              │
                               Pixel Streaming 2 ──> browser
```

All heavy work is done once, offline, in Python. Unreal only displays baked results. The project stays Blueprint-only, which also means no Xcode is needed (it is not installed on this Mac).

### 4.1 Data prep (`tools/prep_site.py`)

1. Download raw files to `data/raw/` (git-ignored).
2. `gdalwarp` each to one shared 2016 m × 2016 m box in the same projection.
3. Write:
   - `heightmap.png`: 16-bit, 2017 × 2017 (a valid Landscape size at 1 m per sample). Print min and max elevation; Unreal's Z scale is `(max − min) / 512 × 100`.
   - `ortho.png`: 8192 × 8192 (about 25 cm per pixel).
   - `slope.png`: degrees, from the DTM.
   - `rough.png`: height spread in a 3 m window. This is the rock and rubble stand-in.
   - `thermal.png`: THEMIS resampled to the same box.

### 4.2 Route (`tools/plan_route.py`)

- Cost per 1 m cell = walking time. Base pace 0.7 m/s on flat firm ground, slower with slope, with roughness and with loose sand (low thermal inertia).
- No-go cells: slope over 20°, or roughness above a threshold. These are the "large rocks and ledges" the brief mentions.
- A* from the habitat point through 3–4 science stops and back, 8-connected, then straighten the path where the straight line stays out of no-go cells.
- Outputs `route.csv` (x, y, z, slope, cumulative distance and time) and `route_stats.json` (distance, climb, steepest slope, total time, dose).
- Pace, slope limit and thresholds are constants at the top of the file. They are suit assumptions, so say so in the README and keep them easy to change.
- One check, run with the script: every step of the route is under the slope limit, no step crosses a no-go cell, and the route ends where it started.

### 4.3 Unreal (`Marswalk/`)

- **Terrain:** import `heightmap.png` through Landscape mode by hand (one-off, 5 minutes). Material: ortho as base colour, plus a tiling detail normal so the ground holds up at eye level.
- **Layers:** one material with a parameter that blends ortho → slope → thermal → hazard (no-go in red). A Material Parameter Collection drives it from UI buttons.
- **Rocks:** scatter free Megascans Mars-like rocks from Fab where `rough.png` is high. List them as a third-party asset in the submission.
- **Sky and light:** Sky Atmosphere tuned to a butterscotch day sky, directional light as the Sun, Lumen and virtual shadow maps on, light dust fog. A time-of-day slider turns the Sun.
- **Route:** import `route.csv` as a Data Table (native CSV import). A Blueprint builds a spline from the rows and draws a glowing line plus numbered stop markers.
- **Walk view:** first-person character at suit pace. HUD widget: compass bearing and metres to next stop, slope underfoot, elapsed time, dose so far, time until sunset, red warning when off route or entering a no-go cell.
- **Plan view:** same level, overhead camera, layer buttons, route stats card. One key switches between the two views.
- **Photo stops:** at each science stop, a card with one real Curiosity photo taken nearby, with sol and camera name.
- **Safety panel:** quiet-day dose for this walk next to a "solar storm" switch that uses a real storm Curiosity recorded, shows the higher dose, and tells the astronaut to turn back, with the walk-back time from the current position.

### 4.4 Browser

Pixel Streaming 2 from the editor viewport, as in the README. This is for the live demo only. Judges get the repo and the video.

## 5. Schedule

### Saturday 14 Nov

| Time | Work | Done when |
|------|------|-----------|
| 11:30–13:00 | **Step 0: go / no-go on the site.** Find the HiRISE DTM that covers the boxwork ridges, or switch to the fallback site. Pick the crop box, habitat point and 3–4 stops. Start downloads. | A DTM and orthoimage for the box are on disk |
| 13:00–16:00 | `prep_site.py`: crop, heightmap, ortho, slope, roughness, thermal | Five PNGs line up when overlaid |
| 16:00–19:00 | Unreal terrain, ortho material, sky and Sun, first-person walk | **Checkpoint A:** walking on real Mars terrain in the browser |
| 19:00–22:00 | `plan_route.py` + check, route spline and stop markers in Unreal, layer buttons | Route visible, layers switch, check passes |
| 22:00–24:00 | HUD v1 (bearing, distance, slope, time). Commit and push. | **Checkpoint B:** the full loop can be walked with a HUD |

### Sunday 15 Nov

| Time | Work | Done when |
|------|------|-----------|
| 08:00–11:00 | Radiation and weather panel, storm switch, photo stops | Safety info and rover photos show in both views |
| 11:00–13:00 | Plan view, rocks, lighting and dust polish | **Checkpoint C:** every box in section 6 is ticked |
| **13:00** | **Feature freeze.** Only fixes after this. | |
| 13:00–15:00 | Record the walk and the plan view, cut to 30 seconds or less with ffmpeg, upload to a public link | Video plays without login |
| 15:00–17:00 | README (how it works, tools, impact), `DATA.md`, SI-use disclosure, make the repo public, check the links in a private window | Repo opens logged out |
| 17:00–18:00 | Fill in the Project tab, press **Submit for Judging** | Team page shows the project as submitted |
| 18:00 on | Buffer | |

### If behind, cut in this order

1. CRISM and DONKI stretch layers (never start them before Checkpoint C).
2. Rock scatter.
3. Time-of-day slider (fix the Sun at mid-afternoon).
4. Plan view as a separate camera (use a still top-down screenshot with the route in the video instead).
5. Storm switch (keep the quiet-day dose only).

Never cut: real terrain, three layers, the route, the dose number, the video.

## 6. Done means

Brief:

- [ ] One hyperlocal site with a stated science goal
- [ ] At least three data types layered (plan has five)
- [ ] Walking route that avoids steep and rocky ground, with distance, climb and time for a suited walker
- [ ] Safety info: radiation dose and conditions
- [ ] Rover point-of-view photos at the stops
- [ ] Display format shown: helmet HUD and habitat screen

Submission:

- [ ] Project name and 50–200 word summary
- [ ] Demo video, 30 seconds or less, public link
- [ ] Repo public, opens without login
- [ ] Project details: how it works, tools, impact
- [ ] SI-use disclosure; watermark on any SI-made image or video
- [ ] Every NASA dataset and every other dataset, tool, library and asset listed
- [ ] **Submit for Judging** pressed (saving is not submitting)

## 7. Risks

| Risk | What to do |
|------|------------|
| No 1 m elevation over the boxwork ridges | Decided in step 0 by 13:00 Saturday. Use the fallback site; nothing else changes. |
| Terrain looks flat or stretched in Unreal | Set Z scale from the printed min and max. Check one known height difference with the measure tool. |
| 25 cm image looks soft at eye level | Detail normal and rocks carry the close-up; the ortho carries the distance. |
| Git LFS limit on a free GitHub account (1 GB) | Commit only baked PNGs and Unreal assets. Raw NASA files stay in `data/raw/` and are rebuilt by `prep_site.py`. |
| Pixel Streaming stutters on this Mac | Lower the stream resolution. Record the video straight from the editor, not from the browser. |
| No Xcode, so no packaged build and no C++ | Stay Blueprint-only and stream from the editor. Do not spend hackathon time installing Xcode. |
| Suit pace and slope limits are guesses | Label them as assumptions, keep them as constants, cite the source used for each. |
| Deadline misread | Confirm it before step 0. Submit early; the form can be edited until the deadline if the site allows. |

## 8. Not doing

- Global or regional map, or more than one site
- A tool that generates maps for any location
- Live data feeds (all data is a baked snapshot with its date shown)
- Multiplayer, VR, mobile build, packaged app
- Hosting the stream publicly
