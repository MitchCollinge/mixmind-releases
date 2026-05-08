# MixMind — AI Ableton Mixer

Talk to Claude. Control Ableton Live. In a native desktop app.

## Prerequisites

- **Node.js** 18+ — https://nodejs.org
- **Python 3** — https://python.org
- **Ableton Live** with **AbletonOSC** remote script installed

## Setup AbletonOSC (one-time)

1. Download AbletonOSC: https://github.com/ideoforms/AbletonOSC
2. Copy the `AbletonOSC` folder to your Ableton MIDI Remote Scripts directory:
   - **macOS**: `~/Library/Application Support/Ableton/Live x.x.x/Resources/MIDI Remote Scripts/`
   - **Windows**: `C:\ProgramData\Ableton\Live x.x.x\Resources\MIDI Remote Scripts\`
3. Restart Ableton
4. In Ableton → **Preferences → MIDI** → Control Surface → select **AbletonOSC**

## Run in Development

```bash
npm install
npm start
```

On first launch, MixMind will automatically:
- Install Python dependencies (flask, flask-cors, python-osc)
- Start the OSC bridge on port 5005
- Open the UI window

## Build for Distribution

```bash
# macOS
npm run build:mac

# Windows
npm run build:win

# Linux
npm run build:linux
```

Output goes to `dist/`.

## Usage

1. **Label your tracks** on the setup screen — pick a type (kick, bass, lead, etc.) for each
2. Set your genre, mastering target, and mix style
3. Enter your Anthropic API key (saved locally, never transmitted except to Anthropic's API)
4. Click **Start Mixing**
5. Talk naturally: *"Gain stage everything"*, *"The kick and bass are clashing"*, *"Set up panning for a wide mix"*

## Architecture

```
MixMind (Electron)
├── main.js          — app lifecycle, spawns bridge, HTTP→IPC relay
├── preload.js       — secure context bridge for renderer
├── renderer/
│   └── index.html   — full UI, calls Claude API + Electron IPC
└── bridge.py        — Flask HTTP server → OSC → AbletonOSC → Ableton Live
```

## Ports

- `5005` — HTTP bridge (localhost only)
- `11000` — AbletonOSC (localhost only, Ableton listens here)
