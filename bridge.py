#!/usr/bin/env python3
"""
MixMind OSC Bridge v2 — with device control
Adds: list devices, get/set parameters, add devices, query parameter names
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from pythonosc import udp_client, dispatcher, osc_server
import threading
import logging

ABLETON_HOST     = "127.0.0.1"
ABLETON_OSC_PORT = 11000
ABLETON_REPLY    = 11001
BRIDGE_PORT      = 5005
REPLY_TIMEOUT    = 3.0

osc_out = udp_client.SimpleUDPClient(ABLETON_HOST, ABLETON_OSC_PORT)
app     = Flask(__name__)
CORS(app)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# ── OSC reply listener ────────────────────────────────────────────────────────
_reply_store  = {}
_reply_events = {}

def start_reply_listener():
    try:
        d = dispatcher.Dispatcher()
        def default_handler(addr, *args):
            _reply_store[addr] = list(args)
            if addr in _reply_events:
                _reply_events[addr].set()
        d.set_default_handler(default_handler)
        server = osc_server.ThreadingOSCUDPServer(("0.0.0.0", ABLETON_REPLY), d)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        print(f"OSC reply listener on port {ABLETON_REPLY}")
    except Exception as e:
        print(f"Warning: reply listener failed: {e}")

def send_and_wait(address, *args, timeout=REPLY_TIMEOUT):
    event = threading.Event()
    _reply_events[address] = event
    _reply_store.pop(address, None)
    try:
        osc_out.send_message(address, list(args) if args else [])
        event.wait(timeout=timeout)
        return _reply_store.get(address)
    finally:
        _reply_events.pop(address, None)

def send(address, *args):
    try:
        osc_out.send_message(address, list(args) if args else [])
        return {"ok": True, "osc": address, "args": list(args)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ── Transport ──────────────────────────────────────────────────────────────────
@app.route("/play",      methods=["POST"])
def play():      return jsonify(send("/live/song/start_playing"))

@app.route("/stop",      methods=["POST"])
def stop():      return jsonify(send("/live/song/stop_playing"))

@app.route("/tempo",     methods=["POST"])
def tempo():
    return jsonify(send("/live/song/set/tempo", float(request.json.get("bpm", 120))))

@app.route("/metronome", methods=["POST"])
def metronome():
    return jsonify(send("/live/song/set/metronome", int(request.json.get("on", 1))))

# ── Clips ──────────────────────────────────────────────────────────────────────
@app.route("/clip/play", methods=["POST"])
def clip_play():
    return jsonify(send("/live/clip/fire",
        int(request.json.get("track", 0)), int(request.json.get("clip", 0))))

@app.route("/clip/stop", methods=["POST"])
def clip_stop():
    return jsonify(send("/live/track/stop_all_clips", int(request.json.get("track", 0))))

# ── Tracks ─────────────────────────────────────────────────────────────────────
@app.route("/track/volume", methods=["POST"])
def track_volume():
    return jsonify(send("/live/track/set/volume",
        int(request.json.get("track", 0)), float(request.json.get("volume", 0.85))))

@app.route("/track/pan", methods=["POST"])
def track_pan():
    return jsonify(send("/live/track/set/panning",
        int(request.json.get("track", 0)), float(request.json.get("pan", 0.0))))

@app.route("/track/mute", methods=["POST"])
def track_mute():
    return jsonify(send("/live/track/set/mute",
        int(request.json.get("track", 0)), int(request.json.get("mute", 1))))

@app.route("/track/solo", methods=["POST"])
def track_solo():
    return jsonify(send("/live/track/set/solo",
        int(request.json.get("track", 0)), int(request.json.get("solo", 1))))

@app.route("/track/arm", methods=["POST"])
def track_arm():
    return jsonify(send("/live/track/set/arm",
        int(request.json.get("track", 0)), int(request.json.get("arm", 1))))

# ── Scenes ─────────────────────────────────────────────────────────────────────
@app.route("/scene/play", methods=["POST"])
def scene_play():
    return jsonify(send("/live/scene/fire", int(request.json.get("scene", 0))))

# ── Undo/Redo ──────────────────────────────────────────────────────────────────
@app.route("/undo", methods=["POST"])
def undo(): return jsonify(send("/live/song/undo"))

@app.route("/redo", methods=["POST"])
def redo(): return jsonify(send("/live/song/redo"))

# ── Device listing ─────────────────────────────────────────────────────────────
@app.route("/track/devices", methods=["GET"])
def track_devices():
    track = int(request.args.get("track", 0))
    reply = send_and_wait("/live/track/get/devices", track)
    if reply is None:
        return jsonify({"ok": False, "error": "No reply from Ableton"})
    devices = []
    i = 0
    data = reply if isinstance(reply, list) else []
    while i + 1 < len(data):
        devices.append({"index": data[i], "name": data[i+1]})
        i += 2
    return jsonify({"ok": True, "track": track, "devices": devices})

# ── Device parameters ──────────────────────────────────────────────────────────
@app.route("/device/parameters", methods=["GET"])
def device_parameters():
    track  = int(request.args.get("track", 0))
    device = int(request.args.get("device", 0))
    names  = send_and_wait("/live/device/get/parameters/name",  track, device)
    values = send_and_wait("/live/device/get/parameters/value", track, device)
    mins   = send_and_wait("/live/device/get/parameters/min",   track, device)
    maxs   = send_and_wait("/live/device/get/parameters/max",   track, device)
    if names is None:
        return jsonify({"ok": False, "error": "No reply from Ableton"})
    params = []
    for i, name in enumerate(names):
        params.append({
            "index": i,
            "name":  name,
            "value": values[i] if values and i < len(values) else None,
            "min":   mins[i]   if mins   and i < len(mins)   else None,
            "max":   maxs[i]   if maxs   and i < len(maxs)   else None,
        })
    return jsonify({"ok": True, "track": track, "device": device, "parameters": params})

@app.route("/device/parameter/set", methods=["POST"])
def device_param_set():
    d      = request.json
    track  = int(d.get("track",  0))
    device = int(d.get("device", 0))
    param  = int(d.get("param",  0))
    value  = float(d.get("value", 0))
    return jsonify(send("/live/device/set/parameter/value", track, device, param, value))

@app.route("/device/parameter/get", methods=["GET"])
def device_param_get():
    track  = int(request.args.get("track",  0))
    device = int(request.args.get("device", 0))
    param  = int(request.args.get("param",  0))
    reply  = send_and_wait("/live/device/get/parameter/value", track, device, param)
    if reply is None:
        return jsonify({"ok": False, "error": "No reply"})
    return jsonify({"ok": True, "value": reply[0] if reply else None})

# ── Add device (requires device_loader.py patch in AbletonOSC) ────────────────
@app.route("/device/add", methods=["POST"])
def device_add():
    d     = request.json
    track = int(d.get("track", 0))
    name  = str(d.get("device", ""))
    reply = send_and_wait("/live/track/add_device", track, name, timeout=5.0)
    if reply is None:
        return jsonify({
            "ok": False,
            "error": "No reply — install device_loader.py in AbletonOSC folder"
        })
    return jsonify({
        "ok":      bool(reply[0]) if reply else False,
        "message": reply[1] if len(reply) > 1 else ""
    })

# ── Device on/off ──────────────────────────────────────────────────────────────
@app.route("/device/enable", methods=["POST"])
def device_enable():
    d      = request.json
    track  = int(d.get("track",  0))
    device = int(d.get("device", 0))
    state  = int(d.get("on",     1))
    return jsonify(send("/live/device/set/enabled", track, device, state))

# ── Health ─────────────────────────────────────────────────────────────────────
@app.route("/ping", methods=["GET"])
def ping(): return jsonify({"ok": True, "message": "MixMind bridge v2 running"})

if __name__ == "__main__":
    start_reply_listener()
    print(f"MixMind bridge v2 → Ableton OSC :{ABLETON_OSC_PORT}")
    app.run(host="127.0.0.1", port=BRIDGE_PORT, debug=False, use_reloader=False)
