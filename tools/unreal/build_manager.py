"""BP_Marswalk: route spline + plan-view camera; BeginPlay creates the HUD. Places one in L_Marswalk."""
import unreal
from editor_toolset.toolsets.blueprint import BlueprintTools as B

from common import GAME, assets, load, open_level, read_csv, save_all

open_level()

PATH = f"{GAME}/BP_Marswalk"
sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def add_component(bp, cls, name):
    handles = sds.k2_gather_subobject_data_for_blueprint(bp)
    root = handles[0]
    params = unreal.AddNewSubobjectParams(parent_handle=root, new_class=cls, blueprint_context=bp)
    h, fail = sds.add_new_subobject(params)
    if not fail.is_empty():
        raise RuntimeError(f"add {name}: {fail}")
    sds.rename_subobject(h, unreal.Text(name))
    return h


def main():
    if not assets.does_asset_exist(PATH):
        bp = B.create(GAME, "BP_Marswalk", unreal.Actor.static_class())
        add_component(bp, unreal.SplineComponent, "Route")
        add_component(bp, unreal.CameraComponent, "PlanCam")
        B.compile_blueprint(bp)
        assets.save_loaded_asset(bp)
    bp = load(PATH)
    print("components ok")

    # One instance at the origin; route points are world positions (cm).
    for a in eas.get_all_level_actors():
        if a.get_class().get_name() == "BP_Marswalk_C":
            eas.destroy_actor(a)
    actor = eas.spawn_actor_from_class(bp.generated_class(), unreal.Vector(0, 0, 0))
    actor.set_actor_label("Marswalk")
    spline = actor.get_component_by_class(unreal.SplineComponent)
    pts = [unreal.Vector(float(r["X"]), float(r["Y"]), float(r["Z"]) + 100) for r in read_csv("route.csv")]
    spline.set_override_construction_script(True)  # keep these instance points when the BP recompiles
    spline.clear_spline_points(False)
    for i, p in enumerate(pts):
        spline.add_spline_point(p, unreal.SplineCoordinateSpace.WORLD, False)
        spline.set_spline_point_type(i, unreal.SplinePointType.LINEAR, False)
    spline.update_spline()
    print('after fill', spline.get_number_of_spline_points())
    cam = actor.get_component_by_class(unreal.CameraComponent)
    plan = next(a for a in eas.get_all_level_actors() if a.get_actor_label() == "PlanCamera")
    cam.set_world_location_and_rotation(plan.get_actor_location(), plan.get_actor_rotation(), False, True)
    cam.set_editor_property("field_of_view", 60.0)
    spline = actor.get_component_by_class(unreal.SplineComponent)
    print("spline points:", spline.get_number_of_spline_points(), "length m:", round(spline.get_spline_length() / 100, 1))
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    save_all()


main()
