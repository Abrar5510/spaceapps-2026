"""The demo video's chapters: caption, narration and minimum length. One chapter per thing the challenge asks for.

    python3 tools/demo_script.py     -> .scratch/demo_plan.json + narration wavs (macOS `say`)

tools/unreal/record_demo.py films to this plan; tools/make_video.py adds the captions and sound.
"""
import json
import subprocess
import wave
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / ".scratch"
VOICE = "Samantha"
# name, minimum seconds, caption title, caption detail, narration
CHAPTERS = [
    ("map", 5.0, "MARSWALK: a map for one Mars spacewalk", "Boxwork ridges, Mount Sharp, Gale crater. Science goal: how long did groundwater flow here?",
     "Marswalk is a map for one spacewalk on Mars. Two kilometres of boxwork ridges on Mount Sharp, where Curiosity explored in 2025."),
    ("layers", 9.0, "NASA data, layered on one grid", "HiRISE 25 cm image  >  slope from HiRISE 1 m elevation  >  THEMIS thermal inertia  >  hazards",
     "It layers NASA data on one grid. The HiRISE image. Slope, from HiRISE one metre elevation. Thermal inertia from THEMIS: loose sand or firm rock. And hazards, with no-go ground in red."),
    ("route", 6.0, "A route a suited astronaut can walk", "2.0 km loop, 4 science stops, avoids slopes over 20 degrees and rock over 0.5 m. 3.1 hours.",
     "The planner finds a loop through four science stops that avoids steep slopes and large rocks, and prices it in time, oxygen and radiation."),
    ("brief", 4.5, "Safety: radiation and current conditions", "Dose from Curiosity RAD. Temperature, pressure, sunrise and sunset from Curiosity REMS.",
     "Radiation dose comes from Curiosity's RAD instrument. Weather and daylight come from REMS."),
    ("walk1", 7.0, "Helmet display", "Arrow and distance to the next stop. Oxygen, dose and daylight. Slope underfoot.",
     "Outside, the helmet display points to the next stop, and tracks oxygen, dose and daylight. Climbing slows you down and costs more oxygen."),
    ("stop1", 6.5, "What to expect at each stop", "Curiosity's own photo, taken at this spot. Hold E to drill a core.",
     "At each stop you see the photo Curiosity took right here, and you drill a core."),
    ("core2", 9.0, "Solar storm", "Dose rate from the storm Curiosity measured on 20 May 2024. Turn back, or stay for more science?",
     "After the second core, a solar storm arrives, at the dose rate Curiosity measured in May 2024. The display prices the choice: go home now, or stay for more science."),
    ("run", 4.0, "Turning back", "Walk-home time and the dose it will cost, live.", "We turn back."),
    ("airlock", 6.0, "Back at the airlock", "Refill oxygen, wait out the storm inside, go back out. Or end the mission.",
     "At the airlock you can refill, wait out the storm, and go back out."),
    ("stop3", 5.5, "The clock keeps running", "The Sun follows mission time: less daylight for the cores still in the ground.",
     "The Sun follows the mission clock, so the afternoon is running out."),
    ("stop4", 8.5, "Curiosity, where it stood on sol 4855", "NASA's rover model at the last stop, the southern edge of the boxwork.",
     "The last stop is where Curiosity itself stood, on sol 4855."),
    ("home", 5.0, "Home before sunset", "All four cores sealed.", "All four cores are sealed. Home, before sunset."),
    ("debrief", 6.5, "Debrief", "Cores, dose against the limit, oxygen and daylight make the score.",
     "The debrief scores the science you brought home against the risks you took."),
]


def main():
    OUT.mkdir(exist_ok=True)
    t, plan = 0.0, []
    for name, least, title, detail, say in CHAPTERS:
        wav = OUT / f"say_{name}.wav"
        subprocess.run(["say", "-v", VOICE, "-r", "178", "-o", str(wav), "--data-format=LEI16@44100", say], check=True)
        with wave.open(str(wav)) as w:
            spoken = w.getnframes() / w.getframerate()
        dur = round(max(least, spoken + 0.9) * 30) / 30
        plan.append({"name": name, "start": round(t, 4), "dur": dur, "title": title, "detail": detail, "wav": str(wav), "spoken": round(spoken, 2)})
        t += dur
    json.dump({"fps": 30, "frames": int(round(t * 30)), "chapters": plan}, open(OUT / "demo_plan.json", "w"), indent=1)
    assert all(c["dur"] >= c["spoken"] + 0.8 for c in plan)
    print(f"{len(plan)} chapters, {t:.1f} s:", ", ".join(f"{c['name']} {c['dur']:.1f}" for c in plan))


if __name__ == "__main__":
    main()
