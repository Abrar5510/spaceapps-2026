"""Mars gravity, plan-view stop labels, PIE spawn at PlayerStart."""
import unreal

from common import GAME, load, open_level, read_csv, save_all

open_level()

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)

# 2. Mars surface gravity, 3.71 m/s^2.
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
ws = world.get_world_settings()
ws.set_editor_property("global_gravity_set", True)
ws.set_editor_property("global_gravity_z", -371.0)

# 3. Large flat labels for the overhead plan view (hidden in the walk view, tag PlanOnly).
for a in eas.get_all_level_actors():
    if a.get_actor_label().startswith("PlanLabel_"):
        eas.destroy_actor(a)
for st in read_csv("stops.csv"):
    k = int(st["Name"])
    t = eas.spawn_actor_from_class(unreal.TextRenderActor,
                                   unreal.Vector(float(st["X"]) + 2500, float(st["Y"]) + (3500 if k == 3 else 0), float(st["Z"]) + 3000),
                                   unreal.Rotator(roll=0, pitch=90, yaw=90))  # face up, read west-to-east from above
    t.set_actor_label(f"PlanLabel_{k}")
    tc = t.text_render
    tc.set_editor_property("text", ("H " if k == 0 else f"{k} ") + st["Title"])
    tc.set_editor_property("world_size", 3000.0)
    tc.set_editor_property("text_render_color", unreal.Color(255, 220, 120, 255))
    t.tags = ["PlanOnly"]
    t.set_actor_hidden_in_game(True)

les.save_current_level()
save_all()
print("finish ok")
