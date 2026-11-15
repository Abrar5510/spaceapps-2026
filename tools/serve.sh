#!/bin/bash
# Host the Marswalk demo at play.marswalk.earth.
# Starts the Pixel Streaming 2 signalling server (player page on :80, streamer on :8888),
# a TURN relay, the one-player queue (:8099), then the game streaming into it with no window.
# Stop everything with: pkill -f "Marswalk.uproject -game"
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

# TURN relay for viewers whose network blocks the direct UDP video (most outside networks).
# coturn listens on 127.0.0.1:3478; Tailscale Funnel exposes it publicly as TLS on
# <this-mac>.ts.net:8443 (one-time setup: tailscale funnel --bg --tls-terminated-tcp=8443 tcp://127.0.0.1:3478).
# Browsers reach it over TCP/TLS; it relays to the game on this Mac's LAN address.
TURN_HOST="$(tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"
LAN_IP="$(ipconfig getifaddr "$(route -n get default | awk '/interface:/{print $2}')")"
TURN_PASS="$(openssl rand -hex 16)"  # new each run; browsers receive it anyway, so it only stops reuse
turnserver -n --listening-ip=127.0.0.1 --listening-port=3478 --relay-ip="$LAN_IP" \
  --lt-cred-mech --user="marswalk:$TURN_PASS" --realm=marswalk.earth \
  --no-tls --log-file=stdout > "$LOGS/turn.out" 2>&1 &
TURN=$!

# Settings go in a config file (peer_options must be a JSON object there, not a string).
cat > "$LOGS/wilbur.json" <<EOF
{ "serve": true, "http_root": "$WILBUR/www", "homepage": "player.html",
  "player_port": "80", "streamer_port": "8888", "log_folder": "$LOGS",
  "reverse_proxy": true, "reverse_proxy_num_proxies": 1,
  "peer_options": { "iceServers": [
    { "urls": ["stun:stun.l.google.com:19302"] },
    { "urls": ["turns:$TURN_HOST:8443?transport=tcp"], "username": "marswalk", "credential": "$TURN_PASS" } ] } }
EOF
(cd "$WILBUR" && exec node dist/index.js --config_file="$LOGS/wilbur.json") > "$LOGS/wilbur.out" 2>&1 &
SIGNAL=$!
# One player at a time: the tunnel sends / and /queue/* to this queue page (port 8099).
python3 "$ROOT/tools/queue_server.py" > "$LOGS/queue.out" 2>&1 &
QUEUE=$!
trap 'kill $SIGNAL $TURN $QUEUE 2>/dev/null' EXIT
sleep 2
kill -0 $SIGNAL || { cat "$LOGS/wilbur.out"; exit 1; }
kill -0 $TURN || { cat "$LOGS/turn.out"; exit 1; }
kill -0 $QUEUE || { cat "$LOGS/queue.out"; exit 1; }
echo "Signalling server up. Open http://localhost (or https://play.marswalk.earth)."
caffeinate -i -w $$ &  # keep the Mac from idle-sleeping while hosting (the display may still sleep)

# No window (-RenderOffScreen): a minimized window freezes the stream at 0 fps; offscreen runs ~34 fps.
# Bitrate: the default 40 Mbit/s cap is more than a home upload or the relay can carry.
# -muteaudio silences this Mac's speakers only: it zeroes the final output after Pixel Streaming
# has captured the main submix, so viewers still hear the game.
"$UE/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor" "$ROOT/Marswalk/Marswalk.uproject" \
  -game -RenderOffScreen -muteaudio -ResX=1600 -ResY=900 \
  -PixelStreamingConnectionURL=ws://127.0.0.1:8888 \
  -PixelStreamingWebRTCMaxBitrate=8000000 -PixelStreamingWebRTCStartBitrate=2000000 "$@"
