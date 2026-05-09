#!/usr/bin/env python3
"""
MixMind TCP Bridge v4
Replaces the OSC bridge entirely.
Connects to the MixMind Remote Script running inside Ableton via TCP socket.
Much more reliable than OSC — native two-way communication, no reply timeouts.
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import socket
import json
import threading
import logging

ABLETON_HOST = "127.0.0.1"
ABLETON_PORT = 65432
BRIDGE_PORT  = 5005

app = Flask(__name__)
CORS(app)
logging.getLogger("werkzeug").setLevel(logging.ERROR)

# ── TCP connection pool ────────────────────────────────────────────────────────
_lock    = threading.Lock()
_io_lock = threading.Lock()  # one in-flight request per socket (Flask is multi-threaded)
_socket  = None

def get_socket():
    global _socket
    with _lock:
        if _socket is None:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                # Live API work runs on the main thread; large sessions need headroom
                s.settimeout(60.0)
                s.connect((ABLETON_HOST, ABLETON_PORT))
                _socket = s
            except Exception as e:
                return None, str(e)
        return _socket, None

def send_command(command, params=None):
    """Send a command to Ableton and return the response."""
    global _socket
    if params is None:
        params = {}
    msg = json.dumps({"command": command, "params": params}) + "\n"

    for attempt in range(2):
        with _io_lock:
            sock, err = get_socket()
            if err:
                return {"ok": False, "error": f"Cannot connect to Ableton: {err}"}
            try:
                sock.sendall(msg.encode("utf-8"))
                response = ""
                while True:
                    chunk = sock.recv(65536)
                    if not chunk:
                        raise ConnectionError("Ableton closed the connection")
                    response += chunk.decode("utf-8")
                    if "\n" in response:
                        break
                line = response.split("\n", 1)[0]
                return json.loads(line)
            except json.JSONDecodeError as e:
                return {"ok": False, "error": f"Invalid JSON from Ableton: {e}"}
            except Exception as e:
                with _lock:
                    try:
                        _socket.close()
                    except Exception:
                        pass
                    _socket = None
                if attempt == 1:
                    return {"ok": False, "error": str(e)}

# ── Transport ──────────────────────────────────────────────────────────────────
@app.route("/play",      methods=["POST"])
def play():      return jsonify(send_command("start_playing"))

@app.route("/stop",      methods=["POST"])
def stop():      return jsonify(send_command("stop_playing"))

@app.route("/tempo",     methods=["POST"])
def tempo():
    return jsonify(send_command("set_tempo", {"bpm": float(request.json.get("bpm", 120))}))

@app.route("/undo",      methods=["POST"])
def undo():      return jsonify(send_command("undo"))

@app.route("/redo",      methods=["POST"])
def redo():      return jsonify(send_command("redo"))

@app.route("/app/open", methods=["POST"])
def open_desktop_app():
    """Ask the Ableton Remote Script to open/focus the MixMind desktop app (mixmind://)."""
    d = request.get_json(silent=True) or {}
    return jsonify(send_command("open_mixmind", dict(d)))

# ── Session info ───────────────────────────────────────────────────────────────
@app.route("/session",   methods=["GET"])
def session():   return jsonify(send_command("get_session_info"))

@app.route("/tracks",    methods=["GET"])
def tracks():    return jsonify(send_command("get_tracks"))

@app.route("/track",     methods=["GET"])
def track():
    idx = int(request.args.get("index", 0))
    return jsonify(send_command("get_track", {"track_index": idx}))

# ── Track control ──────────────────────────────────────────────────────────────
@app.route("/track/volume", methods=["POST"])
def track_volume():
    d = request.json
    return jsonify(send_command("set_track_volume", {
        "track_index": int(d.get("track", 0)),
        "volume":      float(d.get("volume", 0.85))
    }))

@app.route("/track/pan", methods=["POST"])
def track_pan():
    d = request.json
    return jsonify(send_command("set_track_pan", {
        "track_index": int(d.get("track", 0)),
        "pan":         float(d.get("pan", 0.0))
    }))

@app.route("/track/mute", methods=["POST"])
def track_mute():
    d = request.json
    return jsonify(send_command("set_track_mute", {
        "track_index": int(d.get("track", 0)),
        "mute":        bool(d.get("mute", True))
    }))

@app.route("/track/solo", methods=["POST"])
def track_solo():
    d = request.json
    return jsonify(send_command("set_track_solo", {
        "track_index": int(d.get("track", 0)),
        "solo":        bool(d.get("solo", True))
    }))

@app.route("/track/arm", methods=["POST"])
def track_arm():
    d = request.json
    return jsonify(send_command("set_track_arm", {
        "track_index": int(d.get("track", 0)),
        "arm":         bool(d.get("arm", True))
    }))

# ── Devices ────────────────────────────────────────────────────────────────────
@app.route("/track/devices", methods=["GET"])
def track_devices():
    idx = int(request.args.get("track", 0))
    return jsonify(send_command("get_track_devices", {"track_index": idx}))

@app.route("/device/parameters", methods=["GET"])
def device_params():
    return jsonify(send_command("get_device_parameters", {
        "track_index":  int(request.args.get("track", 0)),
        "device_index": int(request.args.get("device", 0)),
    }))

@app.route("/device/parameter/set", methods=["POST"])
def device_param_set():
    d = request.json
    return jsonify(send_command("set_device_parameter", {
        "track_index":  int(d.get("track", 0)),
        "device_index": int(d.get("device", 0)),
        "param_index":  int(d.get("param", 0)),
        "value":        float(d.get("value", 0)),
    }))

@app.route("/device/add", methods=["POST"])
def device_add():
    d = request.json
    return jsonify(send_command("load_device", {
        "track_index": int(d.get("track", 0)),
        "device_name": str(d.get("device", "")),
    }))

# ── Clips & scenes ─────────────────────────────────────────────────────────────
@app.route("/clip/play", methods=["POST"])
def clip_play():
    d = request.json
    return jsonify(send_command("fire_clip", {
        "track_index": int(d.get("track", 0)),
        "clip_index":  int(d.get("clip", 0)),
    }))

@app.route("/clip/stop", methods=["POST"])
def clip_stop():
    d = request.json
    return jsonify(send_command("stop_track_clips", {
        "track_index": int(d.get("track", 0))
    }))

@app.route("/scene/play", methods=["POST"])
def scene_play():
    d = request.json
    return jsonify(send_command("fire_scene", {
        "scene_index": int(d.get("scene", 0))
    }))

# ── Import tracks from Ableton (NEW) ──────────────────────────────────────────
@app.route("/import/tracks", methods=["GET"])
def import_tracks():
    """Pull all track names and info from the current Ableton project."""
    return jsonify(send_command("get_tracks"))

# ── Knowledge ─────────────────────────────────────────────────────────────────
@app.route("/knowledge", methods=["GET"])
def knowledge():
    """Load all knowledge files bundled with the app."""
    import os
    knowledge = {}
    # Look for knowledge folder next to bridge.py
    base = os.path.dirname(os.path.abspath(__file__))
    knowledge_dir = os.path.join(base, "knowledge")
    if os.path.isdir(knowledge_dir):
        for fname in sorted(os.listdir(knowledge_dir)):
            if fname.endswith(".txt"):
                key = fname.replace(".txt", "")
                try:
                    with open(os.path.join(knowledge_dir, fname), "r") as f:
                        knowledge[key] = f.read()
                except:
                    pass
    return jsonify({"ok": True, "knowledge": knowledge})

# ── Health ─────────────────────────────────────────────────────────────────────
@app.route("/ping", methods=["GET"])
def ping():
    result = send_command("get_session_info")
    return jsonify({
        "ok":      result.get("ok", False),
        "message": "MixMind bridge v4 (TCP)",
        "ableton": result.get("ok", False),
        "tempo":   result.get("tempo"),
    })

if __name__ == "__main__":
    print(f"MixMind bridge v4 → Ableton TCP :{ABLETON_PORT}")
    app.run(host="127.0.0.1", port=BRIDGE_PORT, debug=False, use_reloader=False)
