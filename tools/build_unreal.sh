#!/bin/bash
# Rebuild the Marswalk Unreal scene from data/site (editor must be open: tools/editor.sh). Pass --terrain / --route to reimport meshes.
set -e
cd "$(dirname "$0")/.."
for s in build_assets build_scene build_manager finish_scene build_ground build_sky build_rocks build_props build_hud; do
  echo "== $s"; python3 tools/ue.py tools/unreal/$s.py "$@" | tail -3
done
