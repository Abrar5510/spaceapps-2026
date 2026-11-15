"""Light, sky, dust haze and camera grade for L_Marswalk (edits the actors build_scene.py placed).

    python3 tools/ue.py tools/unreal/build_sky.py [hour_lmst]

Afternoon Sun by default: low light rakes across the boxwork ridges, which is also when the walk happens.
"""
import math
import sys

import unreal

from common import open_level, read_csv, save_all

open_level()
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = {a.get_actor_label(): a for a in eas.get_all_level_actors()}
LC = unreal.LinearColor


def props(obj, values):
    for k, v in values.items():
        try:
            obj.set_editor_property(k, v)
        except Exception as e:  # property names drift between engine versions: report, keep going
            print("skipped", k, "-", str(e)[:80])


hour = float(sys.argv[1]) if len(sys.argv) > 1 else 13.75   # when the airlock opens (marswalk_hud.START_HOUR)
sun = {float(r["HourLMST"]): (float(r["ElevationDeg"]), float(r["AzimuthDeg"])) for r in read_csv("sun.csv")}
h0 = max(h for h in sun if h <= hour)
el, az = sun[h0]
a = math.radians(az)
light = actors["Sun"]
light.set_actor_rotation(unreal.Rotator(roll=0, pitch=-el, yaw=math.degrees(math.atan2(math.cos(a), -math.sin(a)))), False)
props(light.light_component, {
    "intensity": 55000.0,                 # lux at the top of the atmosphere; the dust below takes its share
    "light_source_angle": 0.6,            # 0.35 is the true disc; the dusty sky softens shadow edges further
    "contact_shadow_length": 0.03,        # small pebbles and rock bases get their own shadows
    "light_color": unreal.Color(255, 244, 232, 255),
    "atmosphere_sun_light": True,
    "atmosphere_sun_disk_color_scale": LC(1.6, 1.6, 1.6, 1),
    "cast_cloud_shadows": False,
    "shadow_amount": 1.0,
})

props(actors["MarsSky"].get_component_by_class(unreal.SkyAtmosphereComponent), {
    "bottom_radius": 3389.5, "atmosphere_height": 80.0, "multi_scattering_factor": 1.2,
    # Thin CO2 gives almost no Rayleigh blue. Suspended dust (optical depth ~0.6, 11 km scale height) scatters
    # red-orange and absorbs blue: tan sky, brighter toward the horizon, cool glow close to the Sun.
    "rayleigh_scattering_scale": 0.0002, "rayleigh_exponential_distribution": 11.0,
    "mie_scattering": LC(1.0, 0.56, 0.33, 1), "mie_scattering_scale": 0.05,
    "mie_absorption": LC(0.0, 0.42, 1.0, 1), "mie_absorption_scale": 0.035,
    "mie_anisotropy": 0.76, "mie_exponential_distribution": 11.0,
    "other_absorption_scale": 0.0, "ground_albedo": unreal.Color(150, 95, 60, 255),
    "aerial_pespective_view_distance_scale": 1.4,
})

props(actors["SkyLight"].get_component_by_class(unreal.SkyLightComponent), {
    "real_time_capture": True, "intensity": 1.25, "lower_hemisphere_is_black": False,
})

props(actors["DustHaze"].get_component_by_class(unreal.ExponentialHeightFogComponent), {
    "fog_density": 0.004, "fog_height_falloff": 0.05,
    "fog_inscattering_luminance": LC(0.66, 0.40, 0.25, 1),
    "directional_inscattering_luminance": LC(0.55, 0.55, 0.6, 1),   # forward-scattering glow around the Sun
    "directional_inscattering_exponent": 12.0,
    "directional_inscattering_start_distance": 2000.0,
    "start_distance": 500.0, "fog_max_opacity": 0.85,
})

pp = actors["PostProcess"]
st = pp.get_editor_property("settings")
grade = {
    "auto_exposure_method": unreal.AutoExposureMethod.AEM_HISTOGRAM,
    "auto_exposure_min_brightness": 9.0, "auto_exposure_max_brightness": 13.6,    # adapts as the Sun drops toward sunset
    "auto_exposure_low_percent": 10.0, "auto_exposure_high_percent": 90.0,
    "auto_exposure_speed_up": 2.0, "auto_exposure_speed_down": 1.0,
    "auto_exposure_bias": 0.9,
    "bloom_intensity": 0.5,
    "motion_blur_amount": 0.15,           # the walk is a 10x time-lapse: full blur smears the ground
    "vignette_intensity": 0.35,
    "film_grain_intensity": 0.18,
    "scene_fringe_intensity": 0.35,
    "film_slope": 0.92, "film_toe": 0.6, "film_shoulder": 0.3,
    "color_saturation": unreal.Vector4(1.08, 1.04, 0.98, 1.0),
    "color_contrast": unreal.Vector4(1.1, 1.1, 1.1, 1.0),
    "color_gain_shadows": unreal.Vector4(1.0, 1.0, 1.04, 1.0),      # cool shadows, warm highlights
    "color_gain_highlights": unreal.Vector4(1.05, 1.0, 0.94, 1.0),
    "ambient_occlusion_intensity": 0.7,
    "lens_flare_intensity": 0.0,
}
for k, v in grade.items():
    try:
        st.set_editor_property("override_" + k, True)
        st.set_editor_property(k, v)
    except Exception as e:
        print("skipped", k, "-", str(e)[:80])
pp.set_editor_property("settings", st)

unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
save_all()
print(f"sky ok: Sun at {h0:.1f} LMST, elevation {el:.0f}, azimuth {az:.0f}")
