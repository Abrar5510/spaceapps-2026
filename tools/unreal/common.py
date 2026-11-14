"""Shared paths and helpers for the Unreal build scripts (run inside the editor via tools/ue.py)."""
import csv
import json
import os

import unreal

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SITE = os.path.join(REPO, "data", "site")
GAME = "/Game/Marswalk"
LEVEL = f"{GAME}/L_Marswalk"

assets = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary


def site():
    return json.load(open(os.path.join(SITE, "site.json")))


def read_csv(name):
    with open(os.path.join(SITE, name)) as f:
        return list(csv.DictReader(f))


def load(path):
    a = unreal.load_asset(path)
    if a is None:
        raise RuntimeError(f"missing asset {path}")
    return a


def import_file(src, dest_folder, name, options=None):
    task = unreal.AssetImportTask()
    task.filename = src
    task.destination_path = dest_folder
    task.destination_name = name
    task.replace_existing = True
    task.automated = True
    task.save = True
    if options:
        task.options = options
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    return load(f"{dest_folder}/{name}")


def open_level():
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if not world or world.get_path_name().split(".")[0] != LEVEL:
        les.load_level(LEVEL)


def save_all():
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    unreal.EditorAssetLibrary.save_directory(GAME, only_if_is_dirty=True, recursive=True)
