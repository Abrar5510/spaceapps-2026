# Dust & Bearings — Marswalk

NASA Space Apps Challenge 2026 · Universal Event · Challenge: [Interplanetary Survival Guide: Martian Map](challenges/interplanetary-survival-guide-martian-map.md)
Team page: https://www.spaceappschallenge.org/2026/find-a-team/dust-bearings/

A realistic Unreal Engine 5.8 view of **one** Martian site that an astronaut uses to plan and walk a route on foot (a Marswalk). It runs in the browser through Pixel Streaming.

## What the brief asks for

- [ ] One hyperlocal location or route, not a global map. Global tools like Mars Trek don't go down to this scale.
- [ ] A science objective that justifies the site. The brief's example is boxwork at Mount Sharp, which Curiosity studied in 2025.
- [ ] At least 3 data types layered together: optical, thermal, spectral, topographic, geophysical, atmospheric, radiation or chemical.
- [ ] A walking route that avoids obstacles such as large rocks. Plan it for someone moving slowly in a suit with gear.
- [ ] Safety info, e.g. radiation and space weather.
- [ ] Optional: rover point-of-view images so the crew knows what to expect.
- [ ] A display format: habitat screen, handheld tablet, or helmet HUD.

## Layout

```
Marswalk/        UE 5.8 project (Pixel Streaming 2 enabled; Lumen, Nanite, VSM on)
data/raw/        NASA downloads, git-ignored
challenges/      all 14 challenge briefs + resources (reference)
CHALLENGES.md    challenge index
RESOURCES.md     every resource link by challenge
```

Unreal assets (`.uasset`, `.umap`) and imagery are stored in Git LFS.

## Run in the browser (Pixel Streaming 2)

The signalling and web server is already installed: Epic's `UE5.8` branch, built on 2026-11-14 and tested.

1. Start the server and leave it running:
   `/Volumes/Transend/Apps/UE_5.8/Engine/Plugins/Media/PixelStreaming2/Resources/WebServers/SignallingWebServer/platform_scripts/bash/start.sh --nosudo --publicip 127.0.0.1`
   It serves the browser page on port 80 and waits for Unreal on port 8888.
2. Open `Marswalk/Marswalk.uproject` in UE 5.8. On the Pixel Streaming toolbar, start streaming the viewport to `ws://127.0.0.1:8888`.
3. Open http://localhost in a browser. To reach it from another device, open `http://<this-mac-ip>` on the same network.

If it ever needs reinstalling, run `get_ps_servers.sh -b UE5.8` from that `WebServers` folder. Without `-b`, the script that ships with 5.8 fetches the UE5.7 branch.
Don't run `node dist/index.js` directly. The downloaded `config.json` points its web root at a Windows path, and `start.sh` overrides that.

The stream only works while this Mac is running the editor or a packaged build. Judging happens later, so the submission's public links have to be the repo and the demo video. The live stream is for presenting.

## Submission form (Project tab) needs

- Project name and a 50–200 word summary
- **Demo**: a video of 30 seconds or less, or at most 7 slides, at a public link
- **Project link**: public with no login, so this repo must be made public before submitting
- Project details: how it works, tools used, impact
- Super Intelligence (SI) use disclosure. Any SI-generated images or video need a visible watermark. Code and data need the SI use acknowledged in text or metadata.
- Every NASA dataset used, plus every other dataset, tool, code library, text or image
- Original-work and terms checkboxes, then **Submit for Judging** (saving alone does not submit)
