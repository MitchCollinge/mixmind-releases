# MixMind Remote Script for Ableton Live 12
# Install: copy this entire "MixMind" folder (not the repo root) into:
#   ~/Music/Ableton/User Library/Remote Scripts/
#   or App-Resources/MIDI Remote Scripts/
# The folder name must be "MixMind" — that is the label in Preferences → MIDI.

from __future__ import absolute_import, print_function, unicode_literals

import json
import socket
import subprocess
import sys
import threading
import traceback

try:
    import queue
except ImportError:
    import Queue as queue  # noqa: N813

import Live
from _Framework.ControlSurface import ControlSurface

HOST = "127.0.0.1"
CMD_PORT = 65432
DRAIN_INTERVAL_MS = 50


def create_instance(c_instance):
    return MixMind(c_instance)


class MixMind(ControlSurface):
    def __init__(self, c_instance):
        ControlSurface.__init__(self, c_instance)
        self._cmd_queue = queue.Queue()
        self._stop = threading.Event()
        self._server_sock = None
        self._tcp_ok = False

        with self.component_guard():
            try:
                self._start_tcp_server()
                self._tcp_ok = True
            except Exception as e:
                # Bind errors (port in use) must not prevent the script from loading;
                # otherwise MixMind disappears from the Control Surface list.
                self.log_message("MixMind: TCP server failed (fix port %d): %s" % (CMD_PORT, e))
            self._schedule_drain()

        if self._tcp_ok:
            self.log_message("MixMind: listening on %s:%d (bridge protocol)" % (HOST, CMD_PORT))

    def _get_track(self, cmd):
        """Arrangement tracks 0..n-1, or Main (master bus): track/track_index -1, master:true, target main/master."""
        song = self.song()
        if cmd.get("master") is True:
            return song.master_track
        if str(cmd.get("target", "")).lower() in ("master", "main"):
            return song.master_track
        raw = cmd.get("track_index", cmd.get("track"))
        if raw is not None and int(raw) == -1:
            return song.master_track
        idx = int(raw) if raw is not None else 0
        return song.tracks[idx]

    def disconnect(self):
        self._stop.set()
        try:
            if self._server_sock:
                self._server_sock.close()
        except Exception:
            pass
        ControlSurface.disconnect(self)

    def _schedule_drain(self):
        self._drain_timer = Live.Base.Timer(
            callback=self._drain_queue,
            interval=DRAIN_INTERVAL_MS,
            repeat=True,
        )
        self._drain_timer.start()

    def _drain_queue(self):
        while True:
            try:
                conn, cmd = self._cmd_queue.get_nowait()
            except queue.Empty:
                return
            payload = {"ok": False, "error": "internal"}
            try:
                op = cmd.get("op")
                if not op:
                    payload = {"ok": False, "error": "missing command/op"}
                else:
                    handler = getattr(self, "_op_" + str(op), None)
                    if handler is None:
                        payload = {"ok": False, "error": "unknown op: %s" % op}
                    else:
                        out = handler(cmd) or {}
                        if out.get("ok") is False:
                            payload = dict(out)
                        else:
                            payload = {"ok": True, **out}
            except Exception:
                self.log_message("MixMind exec error:\n" + traceback.format_exc())
                payload = {"ok": False, "error": traceback.format_exc()}
            self._reply_conn(conn, payload)

    def _reply_conn(self, conn, payload):
        try:
            conn.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _start_tcp_server(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((HOST, CMD_PORT))
            sock.listen(8)
            self._server_sock = sock
        except Exception:
            try:
                sock.close()
            except Exception:
                pass
            self._server_sock = None
            raise
        threading.Thread(target=self._accept_loop, name="MixMind-accept",
                         daemon=True).start()

    def _accept_loop(self):
        if self._server_sock is None:
            return
        while not self._stop.is_set():
            try:
                conn, _ = self._server_sock.accept()
            except Exception:
                if self._stop.is_set():
                    return
                continue
            threading.Thread(target=self._handle_conn, args=(conn,),
                             name="MixMind-conn", daemon=True).start()

    def _normalize_cmd(self, raw):
        """Accept bridge shape {"command","params"} or legacy {"op",...}."""
        if not isinstance(raw, dict):
            return None
        if "command" in raw:
            cmd = dict(raw.get("params") or {})
            cmd["op"] = raw["command"]
            return cmd
        if "op" in raw:
            return dict(raw)
        return None

    def _handle_conn(self, conn):
        buf = b""
        try:
            conn.settimeout(120.0)
            while b"\n" not in buf and len(buf) < 1 << 20:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                buf += chunk
            if not buf:
                return
            raw = json.loads(buf.decode("utf-8").strip())
        except Exception as e:
            self._reply_conn(conn, {"ok": False,
                                    "error": str(e) or traceback.format_exc()})
            return

        cmd = self._normalize_cmd(raw)
        if cmd is None or not cmd.get("op"):
            self._reply_conn(conn, {"ok": False, "error": "invalid request"})
            return
        try:
            self._cmd_queue.put((conn, cmd))
        except Exception:
            self._reply_conn(conn, {"ok": False, "error": "command queue failed"})

    # ---- ops: transport / session ------------------------------------------------

    def _op_start_playing(self, cmd):
        self.song().start_playing()
        return {}

    def _op_stop_playing(self, cmd):
        self.song().stop_playing()
        return {}

    def _op_set_tempo(self, cmd):
        self.song().tempo = float(cmd.get("bpm", 120))
        return {"tempo": self.song().tempo}

    def _op_undo(self, cmd):
        song = self.song()
        if not song.can_undo:
            return {"ok": False, "error": "No undo history available"}
        song.undo()
        return {"can_undo": song.can_undo, "can_redo": song.can_redo}

    def _op_redo(self, cmd):
        song = self.song()
        if not song.can_redo:
            return {"ok": False, "error": "No redo history available"}
        song.redo()
        return {"can_undo": song.can_undo, "can_redo": song.can_redo}

    def _op_open_mixmind(self, cmd):
        """Open or focus the MixMind desktop app (GitHub/Electron build). macOS/Win/Linux best-effort."""
        try:
            if sys.platform == "darwin":
                subprocess.Popen(
                    ["open", "mixmind://open"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return {"launched": True, "via": "mixmind://"}
            if sys.platform == "win32":
                subprocess.Popen(
                    "start mixmind://open",
                    shell=True,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return {"launched": True, "via": "mixmind://"}
            subprocess.Popen(
                ["xdg-open", "mixmind://open"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return {"launched": True, "via": "mixmind://"}
        except Exception as e:
            if sys.platform == "darwin":
                try:
                    subprocess.Popen(
                        ["open", "-a", "MixMind"],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    return {"launched": True, "via": "open -a MixMind"}
                except Exception:
                    pass
            return {"ok": False, "error": str(e)}

    def _op_get_session_info(self, cmd):
        song = self.song()
        name = ""
        try:
            name = getattr(song, "name", "") or ""
        except Exception:
            pass
        return {
            "tempo": song.tempo,
            "is_playing": bool(song.is_playing),
            "name": name,
        }

    # ---- ops: tracks --------------------------------------------------------------

    def _op_get_tracks(self, cmd):
        out = []
        for i, t in enumerate(self.song().tracks):
            entry = {
                "index": i,
                "name": t.name,
                "is_group": bool(t.is_foldable),
                "muted": bool(t.mute),
                "soloed": bool(t.solo),
                "volume": t.mixer_device.volume.value,
                "pan": t.mixer_device.panning.value,
                "color": int(t.color) if t.color is not None else 0,
                "has_audio_input": bool(t.has_audio_input),
                "devices": [d.name for d in t.devices],
            }
            try:
                if t.can_be_armed:
                    entry["arm"] = bool(t.arm)
            except Exception:
                pass
            out.append(entry)
        return {"tracks": out}

    def _op_get_track(self, cmd):
        song = self.song()
        t = self._get_track(cmd)
        is_master = t is song.master_track
        i = -1 if is_master else list(song.tracks).index(t)
        entry = {
            "index": i,
            "name": t.name,
            "is_group": bool(t.is_foldable),
            "muted": bool(t.mute),
            "soloed": bool(t.solo),
            "volume": t.mixer_device.volume.value,
            "pan": t.mixer_device.panning.value,
            "devices": [d.name for d in t.devices],
        }
        try:
            if t.can_be_armed:
                entry["arm"] = bool(t.arm)
        except Exception:
            pass
        return {"track": entry}

    def _op_set_track_volume(self, cmd):
        t = self._get_track(cmd)
        t.mixer_device.volume.value = float(cmd.get("volume", 0.85))
        return {}

    def _op_set_track_pan(self, cmd):
        t = self._get_track(cmd)
        t.mixer_device.panning.value = float(cmd.get("pan", 0.0))
        return {}

    def _op_set_track_mute(self, cmd):
        self._get_track(cmd).mute = bool(cmd.get("mute", True))
        return {}

    def _op_set_track_solo(self, cmd):
        self._get_track(cmd).solo = bool(cmd.get("solo", True))
        return {}

    def _op_set_track_arm(self, cmd):
        t = self._get_track(cmd)
        if t.can_be_armed:
            t.arm = bool(cmd.get("arm", True))
        return {}

    def _op_get_track_devices(self, cmd):
        t = self._get_track(cmd)
        devices = []
        for i, d in enumerate(t.devices):
            devices.append({
                "index": i,
                "name": d.name,
                "class_name": getattr(d, "class_display_name", d.name),
            })
        return {"devices": devices}

    def _op_get_device_parameters(self, cmd):
        t = self._get_track(cmd)
        di = int(cmd.get("device_index", 0))
        dev = t.devices[di]
        params = []
        for i, p in enumerate(dev.parameters):
            try:
                params.append({
                    "index": i,
                    "name": p.name,
                    "value": p.value,
                    "min": p.min,
                    "max": p.max,
                    "is_enabled": bool(p.is_enabled),
                })
            except Exception:
                continue
        return {"parameters": params}

    def _op_set_device_parameter(self, cmd):
        t = self._get_track(cmd)
        di = int(cmd.get("device_index", 0))
        pi = int(cmd.get("param_index", 0))
        dev = t.devices[di]
        dev.parameters[pi].value = float(cmd.get("value", 0))
        return {}

    def _op_load_device(self, cmd):
        device_name = str(cmd.get("device_name", cmd.get("device", ""))).strip()
        if not device_name:
            return {"ok": False, "error": "device_name required"}

        song = self.song()
        target_track = self._get_track(cmd)
        song.view.selected_track = target_track
        browser = Live.Application.get_application().browser
        item = self._find_browser_item(browser, device_name, cmd.get("category"))
        if item is None:
            return {"ok": False, "error": "device not found: %s" % device_name}
        browser.load_item(item)
        return {"loaded": True, "device": device_name}

    def _op_fire_clip(self, cmd):
        t = self._get_track(cmd)
        ci = int(cmd.get("clip_index", 0))
        t.clip_slots[ci].fire()
        return {}

    def _op_stop_track_clips(self, cmd):
        self._get_track(cmd).stop_all_clips()
        return {}

    def _op_fire_scene(self, cmd):
        si = int(cmd.get("scene_index", 0))
        self.song().scenes[si].fire()
        return {}

    # ---- browser search (device load) -------------------------------------------

    _BROWSER_ROOTS = (
        "plugins", "instruments", "audio_effects", "midi_effects",
        "drums", "samples", "max_for_live", "user_library",
    )

    def _find_browser_item(self, browser, name, category=None):
        roots = [category] if category else self._BROWSER_ROOTS
        target = name.lower().strip()
        for root in roots:
            if not root:
                continue
            node = getattr(browser, root, None)
            if node is None:
                continue
            hit = self._search_browser_node(node, target, depth=0)
            if hit is not None:
                return hit
        return None

    def _search_browser_node(self, node, target, depth):
        if depth > 6:
            return None
        try:
            children = list(node.children)
        except Exception:
            children = []
        for child in children:
            cname = (getattr(child, "name", "") or "").lower()
            if cname == target or cname.startswith(target):
                if getattr(child, "is_loadable", False):
                    return child
        for child in children:
            if getattr(child, "is_folder", False) or not getattr(child, "is_loadable", False):
                hit = self._search_browser_node(child, target, depth + 1)
                if hit is not None:
                    return hit
        return None
