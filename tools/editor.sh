#!/bin/bash
# Open Marswalk in Unreal Editor 5.8. Unreal needs Xcode's Metal compiler; Xcode lives on the Transend drive.
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Volumes/Transend/Apps/Xcode.app/Contents/Developer}"
UE="${UE:-/Volumes/Transend/Apps/UE_5.8}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
open -n --env DEVELOPER_DIR="$DEVELOPER_DIR" -a "$UE/Engine/Binaries/Mac/UnrealEditor.app" --args "$ROOT/Marswalk/Marswalk.uproject" "$@"
