"""Scanned rocks (Poly Haven, CC0) as Nanite instances, placed from data/site/rocks.csv.

    python3 tools/ue.py tools/unreal/build_rocks.py

One material for all rocks: the scan gives shape, grain and shading; the colour comes from the HiRISE image
under each rock, darkened, with dust settled on the faces that look up. Earth scans end up looking like the
ground they sit on. Boulders (>= 0.9 m) block the walker; smaller clasts do not.
"""
import json
import math
import os

import unreal
from editor_toolset.toolsets.blueprint import BlueprintTools as B

from common import GAME, REPO, assets, load, mel, open_level, read_csv, save_all, site
from graph import Graph, ST

open_level()
SRC = os.path.join(REPO, "data", "assets", "polyhaven", "rocks")
SCANS = f"{GAME}/RockScans"
sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
sme = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)


def import_scans():
    for name in sorted(os.listdir(SRC)):
        if os.path.isdir(os.path.join(SRC, name)) and not assets.does_directory_exist(f"{SCANS}/{name}"):
            t = unreal.AssetImportTask()
            t.filename, t.destination_path, t.destination_name = os.path.join(SRC, name, name + ".gltf"), SCANS, name
            t.replace_existing, t.automated, t.save = True, True, True
            unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([t])


def master_material():
    path = f"{GAME}/M_RockScan"
    if assets.does_asset_exist(path):
        m = load(path)
        mel.delete_all_material_expressions(m)
    else:
        m = unreal.AssetToolsHelpers.get_asset_tools().create_asset("M_RockScan", GAME, unreal.Material, unreal.MaterialFactoryNew())
    g = Graph(m)
    P = unreal.MaterialExpressionTextureSampleParameter2D
    ref = f"{SCANS}/moon_rock_03/Textures/moon_rock_03"
    diff = g.node(P, parameter_name="Diffuse", texture=load(ref + "_diff"))
    nor = g.node(P, parameter_name="Normal", texture=load(ref + "_nor_gl"), sampler_type=ST.SAMPLERTYPE_NORMAL)
    arm_tex = load(ref + "_rough")
    arm = g.node(P, parameter_name="ARM", texture=arm_tex,
                 sampler_type=ST.SAMPLERTYPE_COLOR if arm_tex.get_editor_property("srgb") else ST.SAMPLERTYPE_LINEAR_COLOR)
    mean_inv = g.node(unreal.MaterialExpressionVectorParameter, parameter_name="MeanInv", default_value=unreal.LinearColor(4, 4, 4, 1))

    xy = g.mask(g.node(unreal.MaterialExpressionWorldPosition), "rg")
    n_site = site()["samples"]
    ortho = g.tex(load(f"{GAME}/Textures/T_Ortho"), g.add(g.mul(xy, 1.0 / (100.0 * n_site)), 0.5 / n_site), wrap=False)
    pw = g.node(unreal.MaterialExpressionPower, const_exponent=1.35)
    g.link((ortho, "RGB"), pw, "Base")
    ground = g.mul(pw, 0.8)                                           # same grade as M_Terrain

    grain = g.mul((diff, "RGB"), (mean_inv, "RGB"))                   # scan / its mean colour
    grey = g.node(unreal.MaterialExpressionDesaturation)
    g.link(grain, grey, "")
    rock = g.mul(g.mul(ground, g.lerp(grey, grain, 0.45)), 0.95)      # bare rock: a touch darker than the dust around it
    up = g.mask(g.node(unreal.MaterialExpressionPixelNormalWS), "b")
    dust = g.mul(g.ramp(up, 0.55, 0.95), 0.65)
    mel.connect_material_property(g.lerp(rock, ground, dust), "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(nor, "RGB", unreal.MaterialProperty.MP_NORMAL)
    mel.connect_material_property(g.lerp(g.lerp(0.8, 1.0, (arm, "G")), 0.95, dust), "", unreal.MaterialProperty.MP_ROUGHNESS)   # dry, dusty: never glossy
    mel.connect_material_property(arm, "R", unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)
    mel.connect_material_property(g.node(unreal.MaterialExpressionConstant, r=0.3), "", unreal.MaterialProperty.MP_SPECULAR)
    m.set_editor_property("used_with_instanced_static_meshes", True)
    m.set_editor_property("used_with_nanite", True)
    mel.recompile_material(m)
    assets.save_loaded_asset(m)
    return m


def rock_types(master):
    """mesh name -> (mesh, longest horizontal side cm, pivot-to-centre offset, min z, height); Nanite on, our material."""
    means = json.load(open(os.path.join(SRC, "means.json")))
    out = {}
    for folder in sorted(means):
        tex = {}
        for p in assets.list_assets(f"{SCANS}/{folder}/Textures"):
            p = p.split(".")[0]
            tex["Diffuse" if p.endswith("_diff") else "Normal" if p.endswith("_nor_gl") else "ARM"] = load(p)
        mi_path = f"{SCANS}/{folder}/MI_{folder}"
        if assets.does_asset_exist(mi_path):
            mi = load(mi_path)
        else:
            mi = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
                f"MI_{folder}", f"{SCANS}/{folder}", unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        mel.set_material_instance_parent(mi, master)
        for k, t in tex.items():
            mel.set_material_instance_texture_parameter_value(mi, k, t)
        mel.set_material_instance_vector_parameter_value(mi, "MeanInv", unreal.LinearColor(*[1 / c for c in means[folder]], 1))
        assets.save_loaded_asset(mi)
        for p in assets.list_assets(f"{SCANS}/{folder}/StaticMeshes"):
            p = p.split(".")[0]
            name = p.rsplit("/", 1)[1]
            if name[-5:-1] == "_LOD" and not name.endswith("_LOD0"):
                continue
            mesh = load(p)
            ns = mesh.get_editor_property("nanite_settings")
            if not ns.get_editor_property("enabled"):
                ns.set_editor_property("enabled", True)
                sme.set_nanite_settings(mesh, ns, apply_changes=True)
            mesh.set_material(0, mi)
            sme.remove_collisions(mesh)
            if "boulder" in name:
                sme.add_simple_collisions(mesh, unreal.ScriptCollisionShapeType.NDOP26)
            assets.save_loaded_asset(mesh)
            b = mesh.get_bounding_box()
            out[name] = (mesh, max(b.max.x - b.min.x, b.max.y - b.min.y), ((b.max.x + b.min.x) / 2, (b.max.y + b.min.y) / 2),
                         b.min.z, b.max.z - b.min.z)
    return out


def field_class():
    path = f"{GAME}/BP_RockField"
    if not assets.does_asset_exist(path):
        bp = B.create(GAME, "BP_RockField", unreal.Actor.static_class())
        root = sds.k2_gather_subobject_data_for_blueprint(bp)[0]
        h, fail = sds.add_new_subobject(unreal.AddNewSubobjectParams(
            parent_handle=root, new_class=unreal.HierarchicalInstancedStaticMeshComponent, blueprint_context=bp))
        sds.rename_subobject(h, unreal.Text("Rocks"))
        B.compile_blueprint(bp)
        assets.save_loaded_asset(bp)
    return load(path).generated_class()


def main():
    import_scans()
    types = rock_types(master_material())
    cls = field_class()
    for a in eas.get_all_level_actors():
        if a.get_class().get_name() in ("BP_Rocks_C", "BP_RockField_C"):
            eas.destroy_actor(a)
    by_mesh = {}
    for r in read_csv("rocks.csv"):
        by_mesh.setdefault(r["Mesh"], []).append(r)
    total = 0
    for name, rows in sorted(by_mesh.items()):
        mesh, size, centre, min_z, height = types[name]
        actor = eas.spawn_actor_from_class(cls, unreal.Vector(0, 0, 0))
        actor.set_actor_label(f"Rocks_{name}")
        c = actor.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
        c.set_static_mesh(mesh)
        c.set_editor_property("cast_shadow", True)
        c.set_cull_distances(0, 80000 if "boulder" in name else 40000)
        c.set_collision_profile_name("BlockAll" if "boulder" in name else "NoCollision")
        xs = []
        for r in rows:
            k = float(r["SizeM"]) * 100.0 / size
            yaw = math.radians(float(r["Yaw"]))
            ox = (centre[0] * math.cos(yaw) - centre[1] * math.sin(yaw)) * k      # scans are not centred on their pivot
            oy = (centre[0] * math.sin(yaw) + centre[1] * math.cos(yaw)) * k
            z = float(r["Z"]) - (min_z + 0.15 * height) * k                        # sink 15% into the regolith
            xs.append(unreal.Transform(unreal.Vector(float(r["X"]) - ox, float(r["Y"]) - oy, z),
                                       unreal.Rotator(roll=0, pitch=0, yaw=float(r["Yaw"])), unreal.Vector(k, k, k)))
        c.add_instances(xs, False, True)
        total += len(xs)
    for old in ("BP_Rocks", "M_Rock"):
        if assets.does_asset_exist(f"{GAME}/{old}"):
            assets.delete_asset(f"{GAME}/{old}")
    if assets.does_directory_exist(f"{GAME}/Rocks"):
        assets.delete_directory(f"{GAME}/Rocks")
    save_all()
    print(f"{total} rocks in {len(by_mesh)} fields")


main()
