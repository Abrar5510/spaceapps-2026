# Data, tools and assets used

Every dataset, tool, library and asset in Marswalk, with where it came from. Raw downloads go in `data/raw/` (git-ignored); `tools/*.py` rebuild everything in `data/site/` from them.

## NASA data

| What | Product / ID | Source | Fetched | Used for |
|------|--------------|--------|---------|----------|
| HiRISE stereo elevation model, 1 m/post | `DTEEC_019698_1750_019988_1750_U01` (MRO HiRISE, PDS `MRO-M-HIRISE-5-DTM-V1.0`) | https://hirise.lpl.arizona.edu/PDS/DTM/ESP/ORB_019600_019699/ESP_019698_1750_ESP_019988_1750/ (found via PDS ODE REST, https://oderest.rsl.wustl.edu/) | 2026-11-14 | Terrain mesh, slope, roughness, route planning |
| HiRISE orthoimage, 25 cm/px | `ESP_019698_1750_RED_A_01_ORTHO` | same folder as above | 2026-11-14 | Ground colour/texture, hazard layer base |
| THEMIS quantitative thermal inertia mosaic, 100 m/px | `THEMIS_TI_Mosaic_Quant_30S120E_100mpp` (Mars Odyssey THEMIS; Christensen/Fergason, USGS Astrogeology) | https://astrogeology.usgs.gov/search/map/themis_thermal_inertia_mosaic_quantitative_30s120e_100mpp (cropped remotely with GDAL) | 2026-11-14 | Thermal layer; loose-sand slowdown in the route cost |
| Curiosity rover positions by sol | MSL localization waypoints (`MSL_waypoints.json`) | https://mars.nasa.gov/mmgis-maps/MSL/Layers/json/MSL_waypoints.json | 2026-11-14 | Choosing the site box, habitat and science stops |
| Curiosity raw images (Navcam) | `NLB_800624472EDR_F1160414NCAM00289M_` (sol 4541), `NLB_808344735EDR_F1180924NCAM00293M_` (4628), `NLB_814107368EDR_F1191722NCAM00309M_` (4693), `NLB_816331121EDR_F1200082NCAM00309M_` (4718), `NLB_828493687EDR_F1212004NCAM00284M_` (4855). Credit NASA/JPL-Caltech | https://mars.nasa.gov/msl/multimedia/raw-images/ (API `https://mars.nasa.gov/api/v1/raw_image_items/`) | 2026-11-14 | "What to expect" photo at each stop |
| Curiosity REMS weather | sol 4693 record (Ls 157): air -74 to -3 °C, ground -89 to 10 °C, 686 Pa, UV moderate, sunrise 05:27, sunset 17:21 LMST | https://mars.nasa.gov/rss/api/?feed=weather&category=msl&feedtype=json (REMS by Centro de Astrobiología, CSIC-INTA) | 2026-11-14 | Conditions panel, Sun clock, daylight left |
| Curiosity RAD surface dose, quiet Sun | 0.21 mGy/day absorbed, 0.64 mSv/day dose equivalent | Hassler et al. 2014, *Science* 343, 1244797 | — | Dose for the walk |
| Curiosity RAD solar storm | 8.1 mGy (8,100 µGy) during the 20 May 2024 solar energetic particle event | NASA/JPL news release, June 2024 ("NASA Watches Mars Light Up During Epic Solar Storm") | — | Storm scenario and turn-back warning |
| Boxwork drill targets | "Valle de la Luna" (Monte Grande hollow, sol 4693), "Nevado Sajama" (ridge, sol 4718) | NASA Curiosity mission blog, sols 4689-4722 (science.nasa.gov/blog) | 2026-11-14 | Stop names and science goal |

## Tools and libraries

| What | Version | Used for |
|------|---------|----------|
| Unreal Engine (Epic Games) | 5.8.4 | Rendering, walk, HUD; Nanite, Lumen, Sky Atmosphere |
| Unreal Pixel Streaming 2 | 5.8 (UE5.8 branch servers) | Browser access |
| Unreal Engine First Person template | 5.8 | Walking character and input (Epic Games, template content) |
| Unreal EditorToolset / UMGToolSet / ToolsetRegistry (experimental plugins) | 5.8 | Scripted creation of Blueprints and the HUD widget |
| GDAL | 3.13.3 | Reprojecting and cropping NASA rasters |
| Python | 3.14 (tools), 3.11 (inside Unreal) | Data prep, route planning, scene build |
| NumPy, SciPy, Pillow | 2.4.4 / 1.16.3 / 12.0.0 | Raster maths, Dijkstra routing, images |
| ffmpeg | 9.0.2 | Demo video |
| Xcode (Metal shader compiler) | 27.2 | Required by Unreal on macOS |

## Methods and constants (assumptions)

- Suit walking pace 0.7 m/s on flat ground, Tobler hiking function for slope; slope limit 20°; roughness limit 0.5 m height spread in 3 m; up to 30 % slower on low thermal-inertia (sandy) ground. These are stated assumptions, set at the top of `tools/plan_route.py`.
- Sun position from the Mars solar declination (axial tilt 25.19°, Ls from REMS) and local time; REMS sunrise/sunset give the mean-to-true solar time offset.
- Mars sky: Rayleigh scattering ~1/150 of Earth's, dust optical depth ~0.6 over an 11 km scale height.
- Thermal layer colours are stretched to the site's own THEMIS range (323-440 SI); the HUD states the range.
- Mars surface gravity is 3.71 m/s² (world setting); the walker's gravity is scaled up 12x to suit the 10x time-lapse walk.
- On slopes the walker slows by up to 70 % uphill and speeds up by up to 35 % downhill, and slides above the 20° limit (game feel, not a suit measurement).
- Mission rules (top of `Marswalk/Content/Python/marswalk_hud.py`, all assumptions): 4 h of suit oxygen at a steady walk, more when climbing or pushing the pace; 250 µGy dose rule for one EVA; a core takes 30 min; the mission clock runs 10x real time while walking (7 m/s on screen for the 0.7 m/s suit pace; gravity is scaled up to match so the walker stays on the ground). Back at the airlock the walker can refill oxygen (10 min) and sit out the storm (1 h, no dose counted inside the habitat) before going out again. The storm dose rate is the 8.1 mGy/day Curiosity RAD measured on 20 May 2024.
- Scenery beyond the 2 km site is the same HiRISE DTM and orthoimage at 10 m per vertex (`tools/far_terrain.py`). No route or layers out there.

## Third-party assets

- Unreal Engine template content (First Person character, mannequin arms, input actions) and engine basic shapes, under the Unreal Engine EULA.
- **Poly Haven (polyhaven.com), CC0**, fetched 2026-11-14 by `tools/get_assets.py`:
  - Rock scans (glTF, 2k): `moon_rock_01`, `moon_rock_03`, `moon_rock_04`, `moon_rock_05`, `moon_rock_07`, `namaqualand_boulder_03`, `namaqualand_boulder_04`, `namaqualand_boulder_05`, `namaqualand_stones_01`, `namaqualand_rocks_01`. Placed by `tools/rocks.py` where the HiRISE DTM is blocky, and as small clasts beside the route. Their colour in the scene comes from the HiRISE image under each rock.
  - Ground scans (2k): `moon_dusted_02`, `gravelly_sand`, `dry_riverbed_rock`. Used only for close-up grain within about 40 m of the walker; colour and brightness stay HiRISE.
- **NASA Curiosity rover 3D model** (`Curiosity_static.glb`, NASA/JPL-Caltech, science.nasa.gov/resource/curiosity-rover-3d-model), fetched 2026-11-14. Stands at the rover's sol 4855 position (stop 4).
- Habitat, stakes and sample caches are built from engine basic shapes (`tools/unreal/build_props.py`).
- Helmet visor image, nav arrow and all suit sounds (breathing, fan hum, boot steps, drill, tones, dose ticks) are synthesised by `tools/make_ui.py` with NumPy. No recordings.
- No AI-generated images or video are used. The demo videos are frames rendered by the running Unreal scene with captions added; their sound is the game's own.
