"""Sun position on Mars: Allison & McEwen (2000) / NASA GISS Mars24 algorithm."""
import math
from datetime import datetime, timezone

TT_MINUS_UTC = 69.184  # s, valid since 2017-01-01 (37 leap s + 32.184)


def _sin(d): return math.sin(math.radians(d))
def _cos(d): return math.cos(math.radians(d))


def sun(utc: datetime, lat: float, lon_east: float):
    """Return dict with Ls, LTST (h), solar elevation and azimuth (deg, clockwise from north)."""
    jd_tt = 2440587.5 + (utc.timestamp() + TT_MINUS_UTC) / 86400.0
    dt = jd_tt - 2451545.0
    M = 19.3871 + 0.52402073 * dt
    a_fms = 270.3871 + 0.524038496 * dt
    A = (0.0071, 0.0057, 0.0039, 0.0037, 0.0021, 0.0020, 0.0018)
    T = (2.2353, 2.7543, 1.1177, 15.7866, 2.1354, 2.4694, 32.8493)
    P = (49.409, 168.173, 191.837, 21.736, 15.704, 95.528, 49.095)
    pbs = sum(a * _cos(0.985626 * dt / t + p) for a, t, p in zip(A, T, P))
    nu_m = ((10.691 + 3.0e-7 * dt) * _sin(M) + 0.623 * _sin(2 * M) + 0.050 * _sin(3 * M)
            + 0.005 * _sin(4 * M) + 0.0005 * _sin(5 * M) + pbs)
    ls = (a_fms + nu_m) % 360
    dec = math.degrees(math.asin(0.42565 * _sin(ls))) + 0.25 * _sin(ls)
    eot = 2.861 * _sin(2 * ls) - 0.071 * _sin(4 * ls) + 0.002 * _sin(6 * ls) - nu_m
    mst = (24 * ((jd_tt - 2451549.5) / 1.0274912517 + 44796.0 - 0.0009626)) % 24
    lmst = (mst + lon_east / 15) % 24
    ltst = (lmst + eot / 15) % 24
    H = 15 * (ltst - 12)
    el = math.degrees(math.asin(_sin(dec) * _sin(lat) + _cos(dec) * _cos(lat) * _cos(H)))
    az = math.degrees(math.atan2(-_sin(H) * _cos(dec),
                                 _sin(dec) * _cos(lat) - _cos(dec) * _sin(lat) * _cos(H))) % 360
    return {"ls": ls, "ltst": ltst, "lmst": lmst, "elevation": el, "azimuth": az, "declination": dec}


if __name__ == "__main__":
    # Allison & McEwen (2000) worked example: 2000-01-06 00:00 UTC -> Ls 277.18758, MST 23.99
    s = sun(datetime(2000, 1, 6, tzinfo=timezone.utc), 0.0, 0.0)
    assert abs(s["ls"] - 277.18758) < 0.01, s
    assert abs(s["lmst"] - 23.99) < 0.02 or s["lmst"] < 0.02, s
    print("mars24 ok", s)
