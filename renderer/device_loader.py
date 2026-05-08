"""
device_loader.py — MixMind extension for AbletonOSC
----------------------------------------------------
Drop this file into your AbletonOSC folder:
  MIDI Remote Scripts/AbletonOSC/device_loader.py

Then patch AbletonOSC/__init__.py to import it (see instructions at bottom).

Adds OSC endpoint:
  /live/track/add_device <track_index> <device_name>

Supported device names (case-insensitive):
  eq eight, compressor, limiter, glue compressor, multiband dynamics,
  reverb, delay, chorus, flanger, phaser, saturator, redux, vinyl distortion,
  dynamic tube, overdrive, amp, cabinet, resonators, spectrum, utility,
  auto filter, auto pan, beat repeat, looper, grain delay, ping pong delay
"""

import Live
import logging

logger = logging.getLogger("abletonosc")

# Map friendly names → Ableton browser search terms
DEVICE_MAP = {
    "eq eight":           "Eq Eight",
    "eq":                 "Eq Eight",
    "compressor":         "Compressor",
    "glue compressor":    "Glue Compressor",
    "multiband dynamics": "Multiband Dynamics",
    "limiter":            "Limiter",
    "reverb":             "Reverb",
    "delay":              "Simple Delay",
    "ping pong delay":    "Ping Pong Delay",
    "grain delay":        "Grain Delay",
    "chorus":             "Chorus-Ensemble",
    "flanger":            "Flanger",
    "phaser":             "Phaser-Flanger",
    "saturator":          "Saturator",
    "redux":              "Redux",
    "vinyl distortion":   "Vinyl Distortion",
    "dynamic tube":       "Dynamic Tube",
    "overdrive":          "Overdrive",
    "amp":                "Amp",
    "cabinet":            "Cabinet",
    "resonators":         "Resonators",
    "spectrum":           "Spectrum",
    "utility":            "Utility",
    "auto filter":        "Auto Filter",
    "auto pan":           "Auto Pan",
    "beat repeat":        "Beat Repeat",
    "looper":             "Looper",
    "drum buss":          "Drum Buss",
    "echo":               "Echo",
    "pedal":              "Pedal",
    "shifter":            "Shifter",
    "spectral resonator": "Spectral Resonator",
    "spectral blur":      "Spectral Blur",
    "hybrid reverb":      "Hybrid Reverb",
}

def add_device_to_track(song, track_index, device_name):
    """
    Load a built-in Ableton device onto a track by searching the browser.
    Returns (True, device) on success or (False, error_message) on failure.
    """
    try:
        tracks = list(song.tracks) + list(song.return_tracks)
        if track_index >= len(tracks):
            return False, f"Track index {track_index} out of range"

        track = tracks[track_index]

        # Resolve friendly name
        search_name = DEVICE_MAP.get(device_name.lower().strip(), device_name)

        # Search Ableton's browser
        browser = Live.Application.get_application().browser
        found_item = None

        def search_items(items):
            for item in items:
                if hasattr(item, 'name') and item.name.lower() == search_name.lower():
                    return item
                if hasattr(item, 'children'):
                    result = search_items(item.children)
                    if result:
                        return result
            return None

        # Search Audio Effects
        found_item = search_items(browser.audio_effects.children)

        # Search Instruments if not found
        if not found_item:
            found_item = search_items(browser.instruments.children)

        if not found_item:
            return False, f"Device '{search_name}' not found in browser"

        # Load the device onto the track
        browser.load_item(found_item)
        logger.info(f"Loaded '{search_name}' onto track {track_index}")
        return True, f"Loaded {search_name}"

    except Exception as e:
        logger.error(f"add_device_to_track error: {e}")
        return False, str(e)


def register_handlers(osc_server, song):
    """Register OSC handlers — call this from AbletonOSC __init__.py"""

    def handle_add_device(params):
        if len(params) < 2:
            return [False, "Usage: /live/track/add_device <track_index> <device_name>"]
        track_index = int(params[0])
        device_name = str(params[1])
        ok, msg = add_device_to_track(song, track_index, device_name)
        return [ok, msg]

    osc_server.add_handler("/live/track/add_device", handle_add_device)
    logger.info("MixMind device_loader handlers registered")
