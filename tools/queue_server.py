"""One-player-at-a-time queue for the live stream at play.marswalk.earth.

The Cloudflare tunnel sends / and /queue/* here; everything else goes to the signalling server.
Visitors get tools/queue.html, which joins the line and polls /queue/status every 2 s.
Whoever is first plays (the page embeds /player.html); when they leave, stop polling,
or run out of time while others wait, the next visitor is up and the mission is reset.

    python3 tools/queue_server.py            # serves on 127.0.0.1:8099 (started by tools/serve.sh)
    python3 tools/queue_server.py --test     # self-check of the queue logic, no network
"""
import json
import os
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT = 8099
TURN_SECONDS = 10 * 60   # a turn is cut short only when someone is waiting
GRACE_SECONDS = 2 * 60   # warning a solo player gets when someone joins after their time is up
STALE_SECONDS = 15      # a visitor who stops polling this long loses their place
PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "queue.html")


class Queue:
    def __init__(self, on_new_player=lambda: None, clock=time.monotonic):
        self.line = []        # ticket ids, first one is playing
        self.seen = {}        # id -> last poll time
        self.player = None    # id of whoever is playing
        self.started = None   # when their turn began
        self.lock = threading.Lock()
        self.on_new_player = on_new_player
        self.clock = clock

    def join(self):
        with self.lock:
            tid = uuid.uuid4().hex
            now = self.clock()
            self.line.append(tid)
            self.seen[tid] = now
            if len(self.line) == 2:  # first person waiting: a long solo turn still gets GRACE_SECONDS warning
                self.started = max(self.started, now - TURN_SECONDS + GRACE_SECONDS)
            self._settle()
            return tid

    def leave(self, tid):
        with self.lock:
            if tid in self.seen:
                self.line.remove(tid)
                del self.seen[tid]
            self._settle()

    def status(self, tid):
        """pos 0 = your turn, n = n people ahead of you, -1 = not in line (left, timed out or turn over)."""
        with self.lock:
            if tid in self.seen:
                self.seen[tid] = self.clock()
            self._settle()
            if tid not in self.seen:
                return {"pos": -1}
            pos = self.line.index(tid)
            left = None
            if len(self.line) > 1:
                left = max(0, int(TURN_SECONDS - (self.clock() - self.started)))
            return {"pos": pos, "waiting": len(self.line) - 1, "turn_left": left, "turn_seconds": TURN_SECONDS}

    def _settle(self):
        now = self.clock()
        for tid in [t for t in self.line if now - self.seen[t] > STALE_SECONDS]:
            self.line.remove(tid)
            del self.seen[tid]
        if self.line and self.line[0] == self.player and len(self.line) > 1 and now - self.started > TURN_SECONDS:
            del self.seen[self.line.pop(0)]   # time is up and someone is waiting
        head = self.line[0] if self.line else None
        if head != self.player:
            self.player, self.started = head, now
            if head:
                self.on_new_player()


def reset_mission():
    """Fresh mission for each player: press R in the game through its job folder (tools/ue.py)."""
    def run():
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import ue
            ue.run("import marswalk_hud; marswalk_hud.press('R')", timeout=15)
        except BaseException as e:  # ue.run exits on timeout; never take the server down
            print("mission reset failed:", e, file=sys.stderr)
    threading.Thread(target=run, daemon=True).start()


QUEUE = Queue(on_new_player=reset_mission)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _tid(self):
        return parse_qs(urlparse(self.path).query).get("id", [""])[0]

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            with open(PAGE, "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        elif path == "/queue/status":
            self._send(200, QUEUE.status(self._tid()))
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/queue/join":
            self._send(200, {"id": QUEUE.join()})
        elif path == "/queue/leave":
            QUEUE.leave(self._tid())
            self._send(200, {"ok": True})
        else:
            self._send(404, {"error": "not found"})

    def log_message(self, *args):
        pass  # polling every 2 s would flood the log


def _test():
    t = [0.0]
    resets = []
    q = Queue(on_new_player=lambda: resets.append(1), clock=lambda: t[0])
    a, b, c = q.join(), q.join(), q.join()
    assert [q.status(x)["pos"] for x in (a, b, c)] == [0, 1, 2] and len(resets) == 1
    q.leave(a)                                   # player leaves: next is up, mission reset
    assert q.status(b)["pos"] == 0 and q.status(c)["pos"] == 1 and len(resets) == 2
    t[0] += STALE_SECONDS + 1
    q.status(b)                                  # c stopped polling: dropped, b keeps playing
    assert q.status(c)["pos"] == -1 and q.status(b)["pos"] == 0 and q.status(b)["turn_left"] is None
    t[0] += TURN_SECONDS + 1                     # alone: no time limit
    assert q.status(b)["pos"] == 0
    d = q.join()
    assert q.status(d)["pos"] == 1 and q.status(b)["turn_left"] == GRACE_SECONDS  # b is warned, not cut off
    for _ in range(GRACE_SECONDS // 10):         # both keep polling through the warning
        t[0] += 10
        assert q.status(b)["pos"] == 0 and q.status(d)["pos"] == 1
    t[0] += 1                                    # time is up while someone waits: d's turn
    assert q.status(d)["pos"] == 0 and q.status(b)["pos"] == -1 and len(resets) == 3
    print("queue self-check ok")


if __name__ == "__main__":
    if "--test" in sys.argv:
        _test()
    else:
        print(f"queue on http://127.0.0.1:{PORT}")
        ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
