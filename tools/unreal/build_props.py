"""Things on the ground: the visor route line, stop markers, the habitat and Curiosity.

    python3 tools/ue.py tools/unreal/build_props.py

Replaces the placeholder shapes from build_scene.py. Everything sits on the terrain by line trace.
"""
import math
import os

import unreal

from common import GAME, REPO, assets, load, mel, open_level, read_csv, save_all
from graph import Graph

open_level()
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
sme = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
V, R, LC = unreal.Vector, unreal.Rotator, unreal.LinearColor
SHAPE = {k: load(f"/Engine/BasicShapes/{k}") for k in ("Cube", "Cylinder", "Sphere", "Cone")}
MP = unreal.MaterialProperty


def ground_z(x, y):
    rocks = [a for a in eas.get_all_level_actors() if a.get_actor_label().startswith(("Rocks_", "Hab_", "Stake_", "Curiosity"))]
    for d in (0, 9, -9, 31, -31):  # a ray straight down a seam between two terrain tiles can slip through
        h = unreal.SystemLibrary.line_trace_single(world, V(x + d, y + d, 30000), V(x + d, y + d, -30000),
                                                   unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, rocks, unreal.DrawDebugTrace.NONE, True)
        if h:
            return h.to_tuple()[4].z
    raise RuntimeError(f"no terrain under ({x:.0f}, {y:.0f})")


def material(name, build, **settings):
    path = f"{GAME}/{name}"
    if assets.does_asset_exist(path):
        m = load(path)
        mel.delete_all_material_expressions(m)
    else:
        m = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, GAME, unreal.Material, unreal.MaterialFactoryNew())
    for k, v in settings.items():
        m.set_editor_property(k, v)
    build(Graph(m))
    mel.recompile_material(m)
    assets.save_loaded_asset(m)
    return m


GLOW = 0.8                 # visor-drawn glow as a screen value (EyeAdaptationInverse), so it never blows out at dusk


def solid(name, color, rough, metal=0.0, glow=0.0):
    def build(g):
        mel.connect_material_property(g.c3(*color), "", MP.MP_BASE_COLOR)
        mel.connect_material_property(g.node(unreal.MaterialExpressionConstant, r=rough), "", MP.MP_ROUGHNESS)
        mel.connect_material_property(g.node(unreal.MaterialExpressionConstant, r=metal), "", MP.MP_METALLIC)
        if glow:
            mel.connect_material_property(g.c3(*[c * glow for c in color]), "", MP.MP_EMISSIVE_COLOR)
    return material(name, build)


def fn(g, cls, a, **props):
    n = g.node(cls, **props)
    g.link(a, n, "")
    return n


def screen_glow(g, r, gr, b):
    """Emissive that keeps its on-screen brightness whatever the camera exposure (the visor draws it, not the Sun)."""
    n = g.node(unreal.MaterialExpressionEyeAdaptationInverse)
    g.link(g.c3(r, gr, b), n, "LightValueInput")
    return n


def route_material():
    """Chevrons drifting toward the next stop, drawn by the visor: bright near the walker, gone by ~250 m."""
    def build(g):
        uv = g.node(unreal.MaterialExpressionTextureCoordinate)
        u, v = g.mask(uv, "r"), g.mask(uv, "g")
        side = fn(g, unreal.MaterialExpressionAbs, g.sub(v, 0.5))                        # 0 centre .. 0.5 edge
        t = g.mul(g.node(unreal.MaterialExpressionTime), 0.9)
        phase = fn(g, unreal.MaterialExpressionFrac, g.add(g.sub(g.mul(u, 1.0 / 1.6), t), g.mul(side, 0.5)))  # U is metres: one chevron per 1.6 m
        chevron = g.ramp(phase, 0.45, 0.55)
        edge = g.one_minus(g.ramp(side, 0.38, 0.5))
        depth = g.node(unreal.MaterialExpressionPixelDepth)
        near = g.mul(g.ramp(depth, 150.0, 500.0), g.one_minus(g.ramp(depth, 9000.0, 25000.0)))
        mel.connect_material_property(screen_glow(g, 0.25 * GLOW, 0.85 * GLOW, 1.0 * GLOW), "", MP.MP_EMISSIVE_COLOR)
        mel.connect_material_property(g.mul(g.mul(g.add(g.mul(chevron, 0.75), 0.12), edge), near), "", MP.MP_OPACITY)
    return material("M_Route", build, shading_model=unreal.MaterialShadingModel.MSM_UNLIT,
                    blend_mode=unreal.BlendMode.BLEND_TRANSLUCENT, two_sided=True)


def beam_material():
    """Marker beam: a soft column that fades with height."""
    def build(g):
        v = g.mask(g.node(unreal.MaterialExpressionTextureCoordinate), "g")              # cylinder side: 0 top .. 1 bottom
        mel.connect_material_property(screen_glow(g, 1.0 * GLOW * 2, 0.72 * GLOW * 2, 0.2 * GLOW * 2), "", MP.MP_EMISSIVE_COLOR)
        mel.connect_material_property(g.mul(fn(g, unreal.MaterialExpressionPower, v, const_exponent=1.5), 0.7), "", MP.MP_OPACITY)
    return material("M_Stop", build, shading_model=unreal.MaterialShadingModel.MSM_UNLIT,
                    blend_mode=unreal.BlendMode.BLEND_TRANSLUCENT, two_sided=True)


def emissive(name, color, strength):
    def build(g):
        mel.connect_material_property(screen_glow(g, *[c * strength for c in color]), "", MP.MP_EMISSIVE_COLOR)
    return material(name, build, shading_model=unreal.MaterialShadingModel.MSM_UNLIT)


def part(label, shape, mat, loc, scale, rot=R(0, 0, 0), tags=(), shadows=True, collide=True):
    a = eas.spawn_actor_from_object(SHAPE[shape], loc, rot)
    a.set_actor_label(label)
    a.set_actor_scale3d(V(*scale))
    c = a.static_mesh_component
    c.set_material(0, mat)
    c.set_editor_property("cast_shadow", shadows)
    if not collide:
        c.set_collision_profile_name("NoCollision")
    a.tags = list(tags)
    a.set_folder_path("Props")
    return a


def clear(prefixes):
    for a in eas.get_all_level_actors():
        if a.get_actor_label().startswith(prefixes):
            eas.destroy_actor(a)


def stops(mats):
    clear(("Beacon", "Stake_"))
    for st in read_csv("stops.csv"):
        k = int(st["Name"])
        if k == 0:
            continue
        x, y = float(st["X"]), float(st["Y"])
        z = ground_z(x, y)
        part(f"Beacon_{k}", "Cylinder", mats["beam"], V(x, y, z + 1450), (0.07, 0.07, 24.0), tags=["Beacon", str(k)], shadows=False, collide=False)
        # A real object under the beam: survey stake with a flag plate and a sample cache canister.
        part(f"Stake_{k}_pole", "Cylinder", mats["metal"], V(x, y, z + 80), (0.03, 0.03, 1.7))
        part(f"Stake_{k}_flag", "Cube", mats["orange"], V(x, y + 22, z + 150), (0.01, 0.4, 0.25), collide=False)
        part(f"Stake_{k}_cache", "Cylinder", mats["white"], V(x + 45, y - 30, z + 14), (0.22, 0.22, 0.32))
        part(f"Stake_{k}_lid", "Cylinder", mats["orange"], V(x + 45, y - 30, z + 31), (0.24, 0.24, 0.03), collide=False)
        t = eas.spawn_actor_from_class(unreal.TextRenderActor, V(x, y, z + 215))
        t.set_actor_label(f"BeaconLabel_{k}")
        tc = t.text_render
        tc.set_editor_property("text", str(k))
        tc.set_editor_property("world_size", 60.0)
        tc.set_editor_property("horizontal_alignment", unreal.HorizTextAligment.EHTA_CENTER)
        tc.set_editor_property("text_render_color", unreal.Color(255, 200, 80, 255))
        t.tags = ["BeaconLabel"]
        t.set_folder_path("Props")


def habitat(mats):
    """A two-module surface habitat with airlock, solar wing and comms mast, 20 m behind the start point."""
    clear(("Habitat", "Hab_"))
    h = read_csv("stops.csv")[0]
    cx, cy = float(h["X"]) + 1900, float(h["Y"]) - 1300
    z = ground_z(cx, cy)
    white, grey, orange, solar, glow = mats["white"], mats["metal"], mats["orange"], mats["solar"], mats["window"]
    yaw = 35.0
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))

    def at(dx, dy, dz):  # local (along the module, across, up) -> world
        return V(cx + dx * c - dy * s, cy + dx * s + dy * c, z + dz)

    # Main module: a 5 m cylinder lying on its side on a cradle, domed ends.
    part("Hab_module", "Cylinder", white, at(0, 0, 330), (5.0, 5.0, 9.0), R(roll=0, pitch=90, yaw=yaw))
    for i, dx in enumerate((-450, 450)):
        part(f"Hab_dome{i}", "Sphere", white, at(dx, 0, 330), (2.2, 5.0, 5.0), R(roll=0, pitch=0, yaw=yaw))
    for i, dx in enumerate((-320, -110, 110, 320)):
        part(f"Hab_band{i}", "Cylinder", grey, at(dx, 0, 330), (5.08, 5.08, 0.12), R(roll=0, pitch=90, yaw=yaw), collide=False)
        part(f"Hab_cradle{i}", "Cube", grey, at(dx, 0, 55), (0.3, 4.2, 1.1), R(roll=0, pitch=0, yaw=yaw))
    for i, dx in enumerate((-250, 0, 250)):
        part(f"Hab_window{i}", "Cube", glow, at(dx, -246, 380), (0.9, 0.06, 0.35), R(roll=0, pitch=0, yaw=yaw), shadows=False, collide=False)
    # Second, upright module (lab) joined by a tunnel.
    part("Hab_lab", "Cylinder", white, at(-80, 620, 260), (4.2, 4.2, 5.0), R(roll=0, pitch=0, yaw=yaw))
    part("Hab_lab_roof", "Sphere", white, at(-80, 620, 510), (4.2, 4.2, 1.6), R(roll=0, pitch=0, yaw=yaw))
    part("Hab_tunnel", "Cylinder", grey, at(-80, 330, 300), (1.9, 1.9, 2.4), R(roll=90, pitch=0, yaw=yaw))
    # Airlock facing the route, with a porch, steps and a lit hatch.
    part("Hab_airlock", "Cylinder", white, at(190, -330, 210), (2.3, 2.3, 2.4), R(roll=90, pitch=0, yaw=yaw))
    part("Hab_hatch", "Cylinder", orange, at(190, -455, 210), (1.5, 1.5, 0.08), R(roll=90, pitch=0, yaw=yaw), collide=False)
    part("Hab_hatch_light", "Cube", glow, at(190, -458, 330), (0.8, 0.04, 0.08), R(roll=0, pitch=0, yaw=yaw), shadows=False, collide=False)
    part("Hab_porch", "Cube", grey, at(190, -560, 85), (2.2, 2.0, 0.08), R(roll=0, pitch=0, yaw=yaw))
    for i in range(3):
        part(f"Hab_step{i}", "Cube", grey, at(190, -690 - i * 45, 60 - i * 22), (1.4, 0.4, 0.06), R(roll=0, pitch=0, yaw=yaw))
    # Solar wing: three panels tilted to the northern Sun (the site is at 4.8 S, the Sun stands north at Ls 157).
    for i in range(3):
        px, py = cx - 1500 - i * 520, cy - 300
        pz = ground_z(px, py)
        part(f"Hab_panel{i}", "Cube", solar, V(px, py, pz + 190), (4.8, 3.0, 0.05), R(roll=-22, pitch=0, yaw=0))
        part(f"Hab_panel_leg{i}", "Cylinder", grey, V(px, py, pz + 95), (0.1, 0.1, 1.9))
    # Comms mast with a dish.
    mx, my = cx + 700, cy + 500
    mz = ground_z(mx, my)
    part("Hab_mast", "Cylinder", grey, V(mx, my, mz + 400), (0.08, 0.08, 8.0))
    part("Hab_dish", "Cone", white, V(mx, my + 35, mz + 770), (1.5, 1.5, 0.35), R(roll=70, pitch=0, yaw=20), collide=False)
    part("Hab_mast_light", "Sphere", mats["red"], V(mx, my, mz + 815), (0.12, 0.12, 0.12), shadows=False, collide=False)
    # Warm work light at the hatch so the home point reads from a distance late in the day.
    light = eas.spawn_actor_from_class(unreal.PointLight, at(190, -560, 330))
    light.set_actor_label("Hab_worklight")
    lc = light.point_light_component
    lc.set_editor_property("intensity", 60000.0)
    lc.set_editor_property("attenuation_radius", 2500.0)
    lc.set_editor_property("light_color", unreal.Color(255, 214, 170, 255))
    light.set_folder_path("Props")


def curiosity():
    """NASA's Curiosity model at the rover's sol 4855 position (stop 4), a few metres off the walking line."""
    clear(("Curiosity",))
    folder = f"{GAME}/Curiosity_static"   # Interchange names the folder after the file
    if not assets.does_directory_exist(folder):
        t = unreal.AssetImportTask()
        t.filename = os.path.join(REPO, "data", "assets", "nasa", "Curiosity_static.glb")
        t.destination_path, t.destination_name = GAME, "Curiosity_static"
        t.replace_existing, t.automated, t.save = True, True, True
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([t])
    meshes = [load(p.split(".")[0]) for p in assets.list_assets(folder, recursive=True)]
    meshes = [m for m in meshes if isinstance(m, unreal.StaticMesh)]
    st = read_csv("stops.csv")[4]
    x, y = float(st["X"]) + 500, float(st["Y"]) + 350
    z = ground_z(x, y)
    for i, m in enumerate(meshes):
        b = m.get_bounding_box()
        a = eas.spawn_actor_from_object(m, V(x, y, z), R(roll=0, pitch=0, yaw=200))
        a.set_actor_label(f"Curiosity_{i}")
        a.set_folder_path("Props")
        print("  Curiosity part", m.get_name(), "size cm", [round(v) for v in (b.max - b.min).to_tuple()], "min z", round(b.min.z))
    return meshes


def far_terrain():
    """Scenery beyond the site box (tools/far_terrain.py): Nanite, no collision, no shadow casting."""
    clear(("FarTerrain",))
    tex_path = f"{GAME}/Textures/T_FarOrtho"
    if not assets.does_asset_exist(tex_path):
        t = unreal.AssetImportTask()
        t.filename, t.destination_path, t.destination_name = os.path.join(REPO, "data", "site", "far_ortho.jpg"), f"{GAME}/Textures", "T_FarOrtho"
        t.replace_existing, t.automated, t.save = True, True, True
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([t])
    tex = load(tex_path)

    def build(g):
        s = g.node(unreal.MaterialExpressionTextureSample, texture=tex)
        pw = g.node(unreal.MaterialExpressionPower, const_exponent=1.35)
        g.link((s, "RGB"), pw, "Base")
        mel.connect_material_property(g.mul(pw, 0.8), "", MP.MP_BASE_COLOR)      # same grade as M_Terrain
        mel.connect_material_property(g.node(unreal.MaterialExpressionConstant, r=0.92), "", MP.MP_ROUGHNESS)
        mel.connect_material_property(g.node(unreal.MaterialExpressionConstant, r=0.25), "", MP.MP_SPECULAR)
    mat = material("M_FarTerrain", build, used_with_nanite=True)
    mesh_path = f"{GAME}/Terrain/far_terrain/StaticMeshes/far_terrain"
    if not assets.does_asset_exist(mesh_path):
        t = unreal.AssetImportTask()
        t.filename, t.destination_path, t.destination_name = os.path.join(REPO, "data", "site", "far_terrain.glb"), f"{GAME}/Terrain", "far_terrain"
        t.replace_existing, t.automated, t.save = True, True, True
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([t])
        m = load(mesh_path)
        ns = m.get_editor_property("nanite_settings")
        ns.set_editor_property("enabled", True)
        sme.set_nanite_settings(m, ns, apply_changes=True)
        sme.remove_collisions(m)
        assets.save_loaded_asset(m)
    a = eas.spawn_actor_from_object(load(mesh_path), V(0, 0, 0), R(0, 0, 0))
    a.set_actor_label("FarTerrain")
    c = a.static_mesh_component
    c.set_material(0, mat)
    c.set_editor_property("cast_shadow", False)
    c.set_collision_profile_name("NoCollision")


def main():
    far_terrain()
    mats = {
        "beam": beam_material(),
        "white": solid("M_HabWhite", (0.72, 0.70, 0.66), 0.55),
        "metal": solid("M_HabMetal", (0.32, 0.33, 0.35), 0.38, metal=0.9),
        "orange": solid("M_HabOrange", (0.85, 0.28, 0.04), 0.5),
        "solar": solid("M_HabSolar", (0.012, 0.02, 0.06), 0.18, metal=0.6),
        "window": solid("M_HabWindow", (1.0, 0.78, 0.45), 0.3, glow=9000.0),
        "red": solid("M_HabRed", (1.0, 0.05, 0.02), 0.3, glow=30000.0),
    }
    for name in ("route_walk", "route_plan"):       # pick up new geometry / UVs from tools/route_mesh.py
        t = unreal.AssetImportTask()
        t.filename, t.destination_path, t.destination_name = os.path.join(REPO, "data", "site", name + ".glb"), f"{GAME}/Route", name
        t.replace_existing, t.automated, t.save = True, True, True
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([t])
        sme.remove_collisions(load(f"{GAME}/Route/{name}/StaticMeshes/{name}"))
    route = route_material()
    plan = emissive("M_RoutePlan", (0.25, 0.85, 1.0), GLOW * 0.35)
    for a in eas.get_all_level_actors():
        if a.get_actor_label() in ("RouteWalk", "RoutePlan"):
            a.static_mesh_component.set_material(0, route if a.get_actor_label() == "RouteWalk" else plan)
    stops(mats)
    habitat(mats)
    curiosity()
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    save_all()
    print("props ok")


main()
