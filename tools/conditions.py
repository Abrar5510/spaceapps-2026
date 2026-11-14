"""Conditions panel data for the mission day: Curiosity REMS weather plus Sun geometry for the site.

Run from the repo root:  python3 tools/conditions.py
Input: data/raw/rems_weather.json (https://mars.nasa.gov/rss/api/?feed=weather&category=msl&feedtype=json)
Output: data/site/conditions.json and data/site/sun.csv (Sun elevation/azimuth through the sol).
"""
import csv
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MISSION_SOL = 4693       # the sol Curiosity drilled 'Valle de la Luna' in the Monte Grande hollow
LAT = -4.808             # site latitude, deg
OBLIQUITY = 25.19        # Mars axial tilt, deg


def hm(s):
    h, m = s.split(":")
    return int(h) + int(m) / 60


def sun(ls_deg, local_hour):
    """Sun elevation and azimuth (deg, azimuth clockwise from north) at local solar time."""
    dec = math.asin(math.sin(math.radians(OBLIQUITY)) * math.sin(math.radians(ls_deg)))
    h = math.radians((local_hour - 12) * 15)
    lat = math.radians(LAT)
    el = math.asin(math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec) * math.cos(h))
    az = math.atan2(-math.sin(h) * math.cos(dec),
                    math.cos(lat) * math.sin(dec) - math.sin(lat) * math.cos(dec) * math.cos(h))
    return math.degrees(el), math.degrees(az) % 360


def main():
    soles = json.loads((ROOT / "data" / "raw" / "rems_weather.json").read_text())["soles"]
    rec = next(s for s in soles if s["sol"] == str(MISSION_SOL))
    ls = float(rec["ls"])
    # REMS times are local mean solar time (LMST); true solar noon sits midway between sunrise and sunset.
    lmst_to_ltst = 12 - (hm(rec["sunrise"]) + hm(rec["sunset"])) / 2
    cond = {
        "sol": MISSION_SOL, "earth_date": rec["terrestrial_date"], "ls_deg": ls, "season": rec["season"],
        "air_min_c": int(rec["min_temp"]), "air_max_c": int(rec["max_temp"]),
        "ground_min_c": int(rec["min_gts_temp"]), "ground_max_c": int(rec["max_gts_temp"]),
        "pressure_pa": int(rec["pressure"]), "uv_index": rec["local_uv_irradiance_index"],
        "opacity": rec["atmo_opacity"], "sunrise_lmst": rec["sunrise"], "sunset_lmst": rec["sunset"], "lmst_to_ltst_h": round(lmst_to_ltst, 3),
        "source": "Curiosity REMS via mars.nasa.gov weather API (Centro de Astrobiologia / NASA JPL)",
    }
    (ROOT / "data" / "site" / "conditions.json").write_text(json.dumps(cond, indent=2))
    with open(ROOT / "data" / "site" / "sun.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Name", "HourLMST", "ElevationDeg", "AzimuthDeg"])
        for k in range(0, 97):
            hour = k / 4
            el, az = sun(ls, hour + lmst_to_ltst)
            w.writerow([k, hour, round(el, 2), round(az, 2)])
    el_noon, _ = sun(ls, 12)
    assert -90 <= el_noon <= 90 and el_noon > 60, el_noon  # near-equatorial site: high noon Sun
    for t in (rec["sunrise"], rec["sunset"]):  # Sun on the horizon at REMS sunrise/sunset
        assert abs(sun(ls, hm(t) + lmst_to_ltst)[0]) < 2, t
    print(json.dumps(cond, indent=2), "\nnoon elevation", round(el_noon, 1))


if __name__ == "__main__":
    main()
