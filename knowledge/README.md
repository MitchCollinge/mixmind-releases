# MixMind Knowledge Base

This folder contains the knowledge that Claude reads on every conversation.
Users cannot see or edit this — it's baked into the app and controlled by you.

## How it works
Every .txt file in this folder is loaded by the bridge and injected into 
Claude's system prompt before every session. Claude treats it as expert 
knowledge to draw from when answering.

## Files
- mixing.txt      — mixing philosophy, techniques, settings
- production.txt  — sound design, instrument recommendations, arrangement
- mastering.txt   — mastering standards, chains, LUFS targets
- plugins.txt     — plugin recommendations and settings

## Adding your own knowledge

Just create a new .txt file, e.g. `clients.txt`:

```
# MY CLIENTS

## Club/DJ releases
Always master to -9 LUFS. Heavy low end. Beatport ready.
Reference: Fisher, Chris Lake, John Summit

## Sync/Licensing
Master to -24 LUFS (EBU R128). Wide dynamic range. No hard limiting.
```

Or `my_preferences.txt`:
```
# MY PERSONAL PREFERENCES
I always use parallel compression on drums.
I never hard clip — always limit with true peak on.
My reference monitors are Genelec 8030s — slightly bright, compensate.
```

## Releasing updates
When you update knowledge files, bump the version in package.json 
and run npm run build:mac — the new knowledge ships with the new version.
All users get it automatically via the auto-updater.

## Format tips
- Use # headings to organise sections
- Be specific — "boost 80Hz by 2dB" is more useful than "boost the low end"
- Include specific dB values, frequencies, ratios wherever possible
- Write as if explaining to a skilled audio engineer
