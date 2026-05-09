# MixMind v5 Setup

## What's new in v5
- **Three modes** — Mixing, Production, Mastering — each with dedicated AI knowledge
- **Import from Ableton** — reads your project tracks automatically
- **Third-party plugin support** — load Serum, FabFilter, Waves etc by name
- **Production mode** — instrument loading, sound design advice, arrangement help
- **Mastering mode** — full chain building, LUFS targeting, release checklist
- **New UI** — completely redesigned with mode-specific colour coding

## Install the Remote Script (one-time)

Ableton shows the **folder name** in Preferences → MIDI → Control Surface. Copy the
`MixMind` folder from this repo (the one that contains `__init__.py`), not the repo root.

### macOS (User Library — recommended)
```bash
cp -r /path/to/mixmind/MixMind \
  ~/Music/Ableton/User\ Library/Remote\ Scripts/
```

Or install system-wide:
```bash
cp -r /path/to/mixmind/MixMind \
  "/Applications/Ableton Live 12 Suite.app/Contents/App-Resources/MIDI Remote Scripts/"
```

If MixMind does not appear, open **Live’s Log.txt** (Help → Get Support, or
`~/Library/Preferences/Ableton/`) and search for `MixMind` to see Python errors.
Port **65432** must be free for the bridge; if TCP fails to bind, the script still
loads but the app cannot control Live until that port is released.

## Activate in Ableton
1. Restart Ableton
2. Preferences → MIDI → Control Surface → select **MixMind**
3. No Input/Output needed

## Run (from your GitHub clone)
```bash
git clone <your-repo-url> mixmind
cd mixmind && npm install && npm start
```

The Electron app starts the Python bridge automatically. Keep this window open while you use MixMind.

### Install the built desktop app (recommended for `mixmind://`)
```bash
npm run build:mac   # or build:win — creates MixMind in dist/
```
Drag **MixMind.app** to **`/Applications/MixMind.app`** (bundle id `com.mixmind.app`). Rebuilds from this repo include **`mixmind://`** in `Info.plist`; after installing, run the app once so macOS associates the URL scheme. Older builds without that key still work via **`open -a MixMind`** from the remote script fallback.

### Open MixMind from Ableton (while Live is running)
With **Preferences → MIDI → Control Surface → MixMind** active, the remote script listens on **127.0.0.1:65432**. You can:

1. **From the repo** (Terminal):
   ```bash
   ./scripts/launch-mixmind-from-live.sh
   ```
2. **One-liner**:
   ```bash
   printf '%s\n' '{"command":"open_mixmind","params":{}}' | nc -w 3 127.0.0.1 65432
   ```
3. **From MixMind’s bridge** (if the app is already running): `POST http://127.0.0.1:5005/app/open` with body `{}`.

This runs **`open mixmind://open`** (macOS), which launches or focuses the installed **MixMind** app. If the URL scheme is not registered yet, the script falls back to **`open -a MixMind`**.

**Dev mode (`npm start`):** register the protocol once with Electron’s dev helper, or rely on the **`open -a MixMind`** fallback after you’ve built and copied the `.app` to `/Applications`.

## Third-party plugins
In Production mode, say: *"Add Serum to track 2"*
MixMind will search your Ableton browser for the plugin by name.
The plugin must be installed and appear in your Ableton browser.
