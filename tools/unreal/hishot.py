"""Full-quality (Lumen) editor screenshot from one CameraActor: python3 tools/ue.py tools/unreal/hishot.py PreviewCamera"""
import os
import sys

import unreal

from common import REPO

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
cam = next(a for a in eas.get_all_level_actors() if a.get_actor_label() == sys.argv[1])
out = os.path.join(REPO, ".scratch", "shots", f"hi_{sys.argv[1]}.png")
os.makedirs(os.path.dirname(out), exist_ok=True)
if os.path.exists(out):
    os.remove(out)
unreal.AutomationLibrary.take_high_res_screenshot(1600, 900, out, camera=cam, delay=1.0)
print("queued", out)
