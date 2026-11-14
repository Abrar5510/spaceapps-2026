"""BP_Rocks: 6 Nanite rock meshes on instanced components, scattered from data/site/rocks.csv."""
import os

import unreal
from editor_toolset.toolsets.blueprint import BlueprintTools as B

from common import GAME, SITE, assets, load, mel, open_level, read_csv, save_all

open_level()
sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
sme = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
TYPES = 6


def rock_material():
    path = f"{GAME}/M_Rock"
    if assets.does_asset_exist(path):
        return load(path)
    m = unreal.AssetToolsHelpers.get_asset_tools().create_asset("M_Rock", GAME, unreal.Material, unreal.MaterialFactoryNew())
    n = lambda cls, x, y: mel.create_material_expression(m, cls, x, y)
    # Colour from the HiRISE ortho under the rock (top-down projection), darkened: rocks read as bedrock.
    wp = n(unreal.MaterialExpressionWorldPosition, -1200, 0)
    xy = n(unreal.MaterialExpressionComponentMask, -1000, 0)
    xy.set_editor_property("r", True); xy.set_editor_property("g", True)
    mel.connect_material_expressions(wp, "", xy, "")
    k = n(unreal.MaterialExpressionMultiply, -800, 0)
    mel.connect_material_expressions(xy, "", k, "A")
    k.set_editor_property("const_b", 1.0 / (100.0 * 2017))
    s = n(unreal.MaterialExpressionTextureSample, -600, 0)
    s.set_editor_property("texture", load(f"{GAME}/Textures/T_Ortho"))
    mel.connect_material_expressions(k, "", s, "UVs")
    tint = n(unreal.MaterialExpressionConstant3Vector, -600, 250)
    tint.set_editor_property("constant", unreal.LinearColor(0.55, 0.42, 0.36, 1))
    mul = n(unreal.MaterialExpressionMultiply, -350, 100)
    mel.connect_material_expressions(s, "RGB", mul, "A"); mel.connect_material_expressions(tint, "", mul, "B")
    mel.connect_material_property(mul, "", unreal.MaterialProperty.MP_BASE_COLOR)
    r = n(unreal.MaterialExpressionConstant, -350, 300)
    r.set_editor_property("r", 0.82)
    mel.connect_material_property(r, "", unreal.MaterialProperty.MP_ROUGHNESS)
    m.set_editor_property("used_with_instanced_static_meshes", True)
    mel.recompile_material(m)
    assets.save_loaded_asset(m)
    return m


def import_rock(k, mat):
    folder, name = f"{GAME}/Rocks", f"rock_{k}"
    path = f"{folder}/{name}/StaticMeshes/{name}"
    if not assets.does_asset_exist(path):
        t = unreal.AssetImportTask()
        t.filename, t.destination_path, t.destination_name = os.path.join(SITE, "rocks", f"{name}.glb"), folder, name
        t.replace_existing, t.automated, t.save = True, True, True
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([t])
    mesh = load(path)
    ns = mesh.get_editor_property("nanite_settings")
    ns.set_editor_property("enabled", True)
    sme.set_nanite_settings(mesh, ns, apply_changes=True)
    mesh.set_material(0, mat)
    sme.remove_collisions(mesh)
    assets.save_loaded_asset(mesh)
    return mesh


def main():
    mat = rock_material()
    meshes = [import_rock(k, mat) for k in range(TYPES)]
    path = f"{GAME}/BP_Rocks"
    if not assets.does_asset_exist(path):
        bp = B.create(GAME, "BP_Rocks", unreal.Actor.static_class())
        root = sds.k2_gather_subobject_data_for_blueprint(bp)[0]
        for k in range(TYPES):
            h, fail = sds.add_new_subobject(unreal.AddNewSubobjectParams(
                parent_handle=root, new_class=unreal.HierarchicalInstancedStaticMeshComponent, blueprint_context=bp))
            sds.rename_subobject(h, unreal.Text(f"Rock{k}"))
        B.compile_blueprint(bp)
        assets.save_loaded_asset(bp)
    bp = load(path)

    for a in eas.get_all_level_actors():
        if a.get_class().get_name() == "BP_Rocks_C":
            eas.destroy_actor(a)
    actor = eas.spawn_actor_from_class(bp.generated_class(), unreal.Vector(0, 0, 0))
    actor.set_actor_label("Rocks")
    comps = sorted(actor.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent), key=lambda c: c.get_name())
    rows = read_csv("rocks.csv")
    for k, c in enumerate(comps):
        c.set_static_mesh(meshes[k])
        c.set_editor_property("cast_shadow", True)
        c.set_cull_distances(0, 60000)
        c.set_collision_profile_name("NoCollision")  # the route avoids rocks; off-route walking stays smooth
        xs = [unreal.Transform(unreal.Vector(float(r["X"]), float(r["Y"]), float(r["Z"])),
                               unreal.Rotator(roll=0, pitch=0, yaw=float(r["Yaw"])),
                               unreal.Vector(float(r["Scale"]), float(r["Scale"]), float(r["Scale"])))
              for r in rows if int(r["Type"]) == k]
        c.add_instances(xs, False, True)
        print(f"Rock{k}: {c.get_instance_count()} instances")
    save_all()


main()
