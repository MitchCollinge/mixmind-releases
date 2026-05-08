#!/usr/bin/env python3
"""
MixMind AbletonOSC Patcher
--------------------------
Run this once to install device loading support into AbletonOSC.
Usage: python3 patch_abletonosc.py
"""

import os
import sys
import shutil

ABLETON_SCRIPTS = "/Applications/Ableton Live 12 Suite.app/Contents/App-Resources/MIDI Remote Scripts"
OSC_DIR = os.path.join(ABLETON_SCRIPTS, "AbletonOSC")
INIT_FILE = os.path.join(OSC_DIR, "__init__.py")
LOADER_DST = os.path.join(OSC_DIR, "mixmind_loader.py")

# The device loader — writes directly into the AbletonOSC folder
LOADER_CODE = '''"""
MixMind device loader — injected by patch_abletonosc.py
Adds /live/track/add_device OSC endpoint to AbletonOSC.
"""
import Live
import logging
logger = logging.getLogger("abletonosc")

DEVICE_MAP = {
    "eq eight":           "Eq Eight",
    "eq":                 "Eq Eight",
    "compressor":         "Compressor",
    "glue compressor":    "Glue Compressor",
    "multiband dynamics": "Multiband Dynamics",
    "limiter":            "Limiter",
    "reverb":             "Reverb",
    "hybrid reverb":      "Hybrid Reverb",
    "echo":               "Echo",
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
    "pedal":              "Pedal",
    "shifter":            "Shifter",
}

def _search_browser_items(items, name):
    for item in items:
        if hasattr(item, "name") and item.name.lower() == name.lower():
            return item
        if hasattr(item, "children"):
            found = _search_browser_items(item.children, name)
            if found:
                return found
    return None

class MixMindDeviceLoader:
    def __init__(self, manager):
        self._manager = manager
        self._osc_server = manager._osc_server
        self._song = manager._song
        self._register()

    def _register(self):
        self._osc_server.add_handler("/live/track/add_device", self._handle_add_device)
        logger.info("MixMind: /live/track/add_device registered")

    def _handle_add_device(self, params):
        if len(params) < 2:
            return [0, "Usage: track_index device_name"]
        track_index = int(params[0])
        device_name = str(params[1]).lower().strip()
        search_name = DEVICE_MAP.get(device_name, params[1])
        try:
            tracks = list(self._song.tracks) + list(self._song.return_tracks)
            if track_index >= len(tracks):
                return [0, f"Track {track_index} out of range"]
            browser = Live.Application.get_application().browser
            item = _search_browser_items(browser.audio_effects.children, search_name)
            if not item:
                item = _search_browser_items(browser.instruments.children, search_name)
            if not item:
                return [0, f"Device not found: {search_name}"]
            browser.load_item(item)
            logger.info(f"MixMind: loaded {search_name} on track {track_index}")
            return [1, f"Loaded {search_name}"]
        except Exception as e:
            logger.error(f"MixMind device loader error: {e}")
            return [0, str(e)]
'''

# The line to inject into __init__.py
INJECT_MARKER = "# MixMind patch — do not remove"
INJECT_CODE = f"""
{INJECT_MARKER}
try:
    from .mixmind_loader import MixMindDeviceLoader as _MML
    _mixmind_loader = _MML(manager)
except Exception as _e:
    import logging
    logging.getLogger("abletonosc").warning(f"MixMind loader failed: {{_e}}")
"""

def find_inject_point(content):
    """Find the right place to inject — after manager is created."""
    # Look for the line where manager is instantiated
    for keyword in ["manager = AbletonOSCManager(", "self.manager = ", "manager ="]:
        idx = content.find(keyword)
        if idx != -1:
            # Find end of that line
            end = content.find("\n", idx)
            return end + 1
    return -1

def main():
    print("MixMind AbletonOSC Patcher")
    print("=" * 40)

    # Check AbletonOSC exists
    if not os.path.isdir(OSC_DIR):
        # Try to find it
        for version in ["12", "11", "12 Suite", "11 Suite", "12 Intro", "11 Intro", "12 Lite"]:
            alt = f"/Applications/Ableton Live {version}.app/Contents/App-Resources/MIDI Remote Scripts/AbletonOSC"
            if os.path.isdir(alt):
                global OSC_DIR, INIT_FILE, LOADER_DST
                OSC_DIR = alt
                INIT_FILE = os.path.join(OSC_DIR, "__init__.py")
                LOADER_DST = os.path.join(OSC_DIR, "mixmind_loader.py")
                break
        else:
            print(f"✗ Could not find AbletonOSC at:\n  {OSC_DIR}")
            print("Make sure AbletonOSC is installed and try again.")
            sys.exit(1)

    print(f"✓ Found AbletonOSC at:\n  {OSC_DIR}")

    # Read __init__.py
    with open(INIT_FILE, "r") as f:
        content = f.read()

    # Check if already patched
    if INJECT_MARKER in content:
        print("✓ Already patched — nothing to do.")
        print("\nRestart Ableton and try 'add EQ Eight to kick' in MixMind.")
        return

    # Backup original
    backup = INIT_FILE + ".bak"
    shutil.copy2(INIT_FILE, backup)
    print(f"✓ Backed up __init__.py to __init__.py.bak")

    # Write loader file
    with open(LOADER_DST, "w") as f:
        f.write(LOADER_CODE)
    print(f"✓ Written mixmind_loader.py")

    # Find injection point
    inject_pos = find_inject_point(content)
    if inject_pos == -1:
        # Fallback: append at end
        new_content = content + "\n" + INJECT_CODE
        print("⚠ Could not find ideal injection point — appending at end")
    else:
        new_content = content[:inject_pos] + INJECT_CODE + content[inject_pos:]
        print(f"✓ Injected at position {inject_pos}")

    # Write patched __init__.py
    with open(INIT_FILE, "w") as f:
        f.write(new_content)
    print(f"✓ Patched __init__.py")

    print()
    print("=" * 40)
    print("✅ Patch complete!")
    print()
    print("Next steps:")
    print("  1. Restart Ableton Live completely")
    print("  2. Confirm AbletonOSC is still selected in Preferences → MIDI")
    print("  3. In MixMind, try: 'Add EQ Eight to track 0'")
    print()
    print("To undo this patch, restore the backup:")
    print(f"  cp '{backup}' '{INIT_FILE}'")

if __name__ == "__main__":
    main()
