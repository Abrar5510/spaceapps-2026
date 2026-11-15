#!/bin/bash
# Host the Marswalk demo at play.marswalk.earth.
# Starts the Pixel Streaming 2 signalling server (player page on :80, streamer on :8888),
# then the standalone game streaming into it. Ctrl+C or closing the game stops both.
# The Cloudflare tunnel (LaunchAgent earth.marswalk.tunnel) forwards play.marswalk.earth to :80.
# Not a packaged build: the HUD and mission logic are Python, which only runs in the editor binary.
set -e
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Volumes/Transend/Apps/Xcode.app/Contents/Developer}"
UE="${UE:-/Volumes/Transend/Apps/UE_5.8}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WILBUR="$UE/Engine/Plugins/Media/PixelStreaming2/Resources/WebServers/SignallingWebServer"
LOGS="$ROOT/.scratch/serve"
mkdir -p "$LOGS"
# UE 5.8 ships the signalling server half-updated from 5.7. Three idempotent fixes:
# 1. it imports the 5.7 package name: alias it to the 5.8 package
ln -sfn ../../Signalling "$WILBUR/../node_modules/@epicgames-ps/lib-pixelstreamingsignalling-ue5.7"
# 2. it needs commander 12 (as its package.json says); 13 is hoisted and rejects every CLI option
[ -d "$WILBUR/node_modules/commander" ] || (cd "$WILBUR/.." && npm install commander@12 -w @epicgames-ps/wilbur --no-audit --no-fund)
# 3. the 5.8 web server only serves the player page when serveStatic is set, which 5.7 code never sets
grep -q serveStatic "$WILBUR/dist/index.js" || sed -i '' 's/homepageFile: options.homepage/homepageFile: options.homepage, serveStatic: true/' "$WILBUR/dist/index.js"

# Settings go in a config file: with commander 13 the server rejects "--opt value" on the command line.
cat > "$LOGS/wilbur.json" <<EOF
{ "serve": true, "http_root": "$WILBUR/www", "homepage": "player.html",
  "player_port": "80", "streamer_port": "8888", "log_folder": "$LOGS",
  "reverse_proxy": true, "reverse_proxy_num_proxies": 1,
  "peer_options": { "iceServers": [{ "urls": ["stun:stun.l.google.com:19302"] }] } }
EOF
(cd "$WILBUR" && exec node dist/index.js --config_file="$LOGS/wilbur.json") > "$LOGS/wilbur.out" 2>&1 &
SIGNAL=$!
trap 'kill $SIGNAL 2>/dev/null' EXIT
sleep 2
kill -0 $SIGNAL || { cat "$LOGS/wilbur.out"; exit 1; }
echo "Signalling server up. Open http://localhost (or https://play.marswalk.earth)."

"$UE/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor" "$ROOT/Marswalk/Marswalk.uproject" \
  -game -windowed -ResX=1600 -ResY=900 \
  -PixelStreamingConnectionURL=ws://127.0.0.1:8888 "$@"
