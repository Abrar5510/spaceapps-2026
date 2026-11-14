"""Build L_Marswalk: Nanite terrain tiles, Mars sky and Sun, dust fog, route lines, stop beacons, plan camera."""
import glob
import sys
import math
import os

import unreal

from common import GAME, LEVEL, SITE, assets, import_file, load, read_csv, save_all, site

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
sme = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
V = unreal.Vector
R = unreal.Rotator


def import_mesh(src, folder, name, nanite=False, complex_collision=False, reimport=False):
    mesh_path = f"{folder}/{name}/StaticMeshes/{name}"  # Interchange puts glTF meshes in <name>/StaticMeshes
    if reimport or not assets.does_asset_exist(mesh_path):
        task = unreal.AssetImportTask()
        task.filename, task.destination_path, task.destination_name = src, folder, name
        task.replace_existing, task.automated, task.save = True, True, True
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    m = load(mesh_path)
    if nanite:
        ns = m.get_editor_property("nanite_settings")
        ns.set_editor_property("enabled", True)
        ns.set_editor_property("fallback_percent_triangles", 1.0)  # keep full detail for collision
        sme.set_nanite_settings(m, ns, apply_changes=True)
    if complex_collision:
        # Walk on the real DTM surface: drop the importer's convex hull and use the triangles for all queries.
        sme.remove_collisions(m)
        body = m.get_editor_property("body_setup")
        body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        m.set_editor_property("body_setup", body)
        sme.set_nanite_settings(m, m.get_editor_property("nanite_settings"), apply_changes=True)  # forces a rebuild
    assets.save_loaded_asset(m)
    return m


def place_mesh(mesh, label, material=None, loc=V(0, 0, 0), rot=R(0, 0, 0), scale=V(1, 1, 1), shadows=True, collide=True):
    a = eas.spawn_actor_from_object(mesh, loc, rot)
    a.set_actor_label(label)
    a.set_actor_scale3d(scale)
    c = a.static_mesh_component
    if material:
        for i in range(c.get_num_materials()):
            c.set_material(i, material)
    c.set_editor_property("cast_shadow", shadows)
    if not collide:
        sme.remove_collisions(mesh)  # the importer's convex hull would span the whole route
        c.set_collision_profile_name("NoCollision")
    return a


def sun_rotation(el, az):
    """Directional light rotation for a Sun at elevation/azimuth (deg). UE: X east, Y south (north = -Y)."""
    a = math.radians(az)
    return R(pitch=-el, yaw=math.degrees(math.atan2(math.cos(a), -math.sin(a))), roll=0)


def main():
    s = site()
    route = read_csv("route.csv")
    stops = read_csv("stops.csv")
    sun = {float(r["HourLMST"]): (float(r["ElevationDeg"]), float(r["AzimuthDeg"])) for r in read_csv("sun.csv")}

    if not les.new_level(LEVEL):
        les.load_level(LEVEL)
        for a in eas.get_all_level_actors():
            eas.destroy_actor(a)

    # Terrain: 16 Nanite tiles of the 1 m HiRISE DTM.
    terrain_mat = load(f"{GAME}/M_Terrain")
    for f in sorted(glob.glob(os.path.join(SITE, "terrain", "terrain_*.glb"))):
        name = os.path.splitext(os.path.basename(f))[0]
        m = import_mesh(f, f"{GAME}/Terrain", name, nanite=True, complex_collision=True, reimport="--terrain" in sys.argv)
        place_mesh(m, name, terrain_mat)

    # Route lines (walk + plan) and stop beacons.
    walk = place_mesh(import_mesh(os.path.join(SITE, "route_walk.glb"), f"{GAME}/Route", "route_walk", reimport="--route" in sys.argv),
                      "RouteWalk", load(f"{GAME}/M_Route"), shadows=False, collide=False)
    plan = place_mesh(import_mesh(os.path.join(SITE, "route_plan.glb"), f"{GAME}/Route", "route_plan"),
                      "RoutePlan", load(f"{GAME}/M_Route"), shadows=False, collide=False)
    plan.tags = ["PlanOnly"]
    plan.set_actor_hidden_in_game(True)

    cyl = load("/Engine/BasicShapes/Cylinder")
    stop_mat = load(f"{GAME}/M_Stop")
    for st in stops:
        k = int(st["Name"])
        x, y, z = float(st["X"]), float(st["Y"]), float(st["Z"])
        if k == 0:
            continue  # the habitat dome marks the start
        b = place_mesh(cyl, f"Beacon_{k}", stop_mat, V(x, y, z + 150), scale=V(0.15, 0.15, 3.0), shadows=False)
        b.tags = ["Beacon", str(k)]
        t = eas.spawn_actor_from_class(unreal.TextRenderActor, V(x, y, z + 420))
        t.set_actor_label(f"BeaconLabel_{k}")
        tc = t.text_render
        tc.set_editor_property("text", "H" if k == 0 else str(k))
        tc.set_editor_property("world_size", 120.0)
        tc.set_editor_property("horizontal_alignment", unreal.HorizTextAligment.EHTA_CENTER)
        tc.set_editor_property("text_render_color", unreal.Color(255, 200, 80, 255))
        t.tags = ["BeaconLabel"]

    # Habitat: a low dome at the start point.
    h = stops[0]
    place_mesh(load("/Engine/BasicShapes/Sphere"), "Habitat", None,
               V(float(h["X"]) + 1500, float(h["Y"]) - 800, float(h["Z"]) - 250), scale=V(12, 12, 6))

    # Sun at 10:00 local mean solar time on the mission sol.
    el, az = sun[10.0]
    light = eas.spawn_actor_from_class(unreal.DirectionalLight, V(0, 0, 50000), sun_rotation(el, az))
    light.set_actor_label("Sun")
    lc = light.light_component
    lc.set_editor_property("intensity", 55000.0)          # lux; Mars gets ~43% of Earth's sunlight
    lc.set_editor_property("light_source_angle", 0.35)    # the Sun is smaller seen from Mars
    lc.set_editor_property("atmosphere_sun_light", True)
    lc.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)

    sky = eas.spawn_actor_from_class(unreal.SkyAtmosphere, V(0, 0, 0))
    sky.set_actor_label("MarsSky")
    sc = sky.get_component_by_class(unreal.SkyAtmosphereComponent)
    for k, v in {
        "bottom_radius": 3389.5, "atmosphere_height": 80.0, "multi_scattering_factor": 1.0,
        # Thin CO2 (~1/150 of Earth's Rayleigh) and suspended dust: optical depth ~0.6 over an 11 km
        # scale height (~0.05/km), absorbing blue more than red -> butterscotch sky, bluish near the Sun.
        "rayleigh_scattering_scale": 0.0002, "rayleigh_exponential_distribution": 11.0,
        "mie_scattering": unreal.LinearColor(1.0, 0.6, 0.36, 1), "mie_scattering_scale": 0.045,
        "mie_absorption": unreal.LinearColor(0.03, 0.3, 0.95, 1), "mie_absorption_scale": 0.035,
        "mie_anisotropy": 0.7, "mie_exponential_distribution": 11.0,
        "other_absorption_scale": 0.0, "ground_albedo": unreal.Color(170, 110, 70, 255),
    }.items():
        sc.set_editor_property(k, v)

    sl = eas.spawn_actor_from_class(unreal.SkyLight, V(0, 0, 1000))
    sl.set_actor_label("SkyLight")
    slc = sl.get_component_by_class(unreal.SkyLightComponent)
    slc.set_editor_property("real_time_capture", True)
    slc.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)

    fog = eas.spawn_actor_from_class(unreal.ExponentialHeightFog, V(100000, 100000, -5000))
    fog.set_actor_label("DustHaze")
    fc = fog.get_component_by_class(unreal.ExponentialHeightFogComponent)
    fc.set_editor_property("fog_density", 0.003)         # suspended dust: tens of km visibility
    fc.set_editor_property("fog_height_falloff", 0.08)
    fc.set_editor_property("fog_inscattering_luminance", unreal.LinearColor(0.55, 0.36, 0.22, 1))
    fc.set_editor_property("start_distance", 300.0)

    pp = eas.spawn_actor_from_class(unreal.PostProcessVolume, V(0, 0, 0))
    pp.set_actor_label("PostProcess")
    pp.set_editor_property("unbound", True)
    st = pp.get_editor_property("settings")
    for k, v in {"override_auto_exposure_method": True, "auto_exposure_method": unreal.AutoExposureMethod.AEM_HISTOGRAM,
                 "override_auto_exposure_min_brightness": True, "auto_exposure_min_brightness": 13.6,
                 "override_auto_exposure_max_brightness": True, "auto_exposure_max_brightness": 13.6,
                 "override_vignette_intensity": True, "vignette_intensity": 0.35}.items():
        st.set_editor_property(k, v)
    pp.set_editor_property("settings", st)

    # Player start at the habitat, facing the first stop.
    r0, r1 = route[0], route[40]
    yaw = math.degrees(math.atan2(float(r1["Y"]) - float(r0["Y"]), float(r1["X"]) - float(r0["X"])))
    ps = eas.spawn_actor_from_class(unreal.PlayerStart, V(float(r0["X"]), float(r0["Y"]), float(r0["Z"]) + 120), R(pitch=0, yaw=yaw, roll=0))
    ps.set_actor_label("PlayerStart_Habitat")

    # Overhead camera for the habitat plan view: whole route in frame.
    xs = [float(r["X"]) for r in route]; ys = [float(r["Y"]) for r in route]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    cam = eas.spawn_actor_from_class(unreal.CameraActor, V(cx, cy, 160000), R(pitch=-90, yaw=-90, roll=0))
    cam.set_actor_label("PlanCamera")
    cam.camera_component.set_editor_property("field_of_view", 60.0)
    cam.camera_component.set_editor_property("constrain_aspect_ratio", False)
    cam.tags = ["PlanCamera"]

    # Ground-level camera for scripted screenshots (walk view preview).
    p = route[60]
    gc = eas.spawn_actor_from_class(unreal.CameraActor, V(float(p["X"]), float(p["Y"]), float(p["Z"]) + 170), R(pitch=-4, yaw=yaw, roll=0))
    gc.set_actor_label("PreviewCamera")
    gc.camera_component.set_editor_property("field_of_view", 80.0)

    les.save_current_level()
    save_all()
    print("scene ok:", len(eas.get_all_level_actors()), "actors")


main()
