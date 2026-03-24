# Project Alpha v3.4 - Unified Batch Vimeo Uploader

## Overview

Accumulates ALL videos (initial + late renders) and sends ONE batch notification at the end.

## How It Works

```
START
  │
  ▼
Scan Video_input/
  │
  ▼
Process ALL videos (wait FCP → upload)
  │ (accumulate results)
  ▼
Wait 1 minute
  │
  ▼
Check for NEW videos
  │
  ├─ YES → Add to same batch, reset 5min timer, process them
  │         ↓
  │         Wait 1 minute, check again
  │
  └─ NO → Continue waiting
          │
          ▼
     No videos for 5 minutes?
          │
          ├─ NO → Keep waiting (check every 1 min)
          │
          └─ YES → Send ONE batch notification
                   Move ALL videos to /Volumes/T7/edited/
                   EXIT
```

## Key Behavior

- **ONE batch notification** - Only after 5 minutes of no new videos
- **Accumulates all videos** - Initial + any that render during the 5-minute window
- **Progress notifications** - Still get Slack at 25%, 50%, 75%, 100% per video
- **Resets 5-minute timer** - Every time a new video is found and processed
- **Moves ALL videos at end** - Only after final notification

## Example Scenario

```
T=0:     Start, find 3 videos, process them
T=2min:  New video rendered → Add to batch, process it, reset 5min timer
T=4min:  Another new video → Add to batch, process it, reset 5min timer  
T=9min:  No new videos for 5min → Send ONE notification with all 5 videos
         Move all 5 to edited folder
         Exit
```

## Quick Start

```bash
# Navigate to T7
cd "/Volumes/T7/Warrior Post Production"

# Setup (first time)
python3 -m venv venv
source venv/bin/activate
pip install requests

# Configure
code config.json  # Add Vimeo token and Slack webhook

# Run
./RUN_CODE
```

## Files

```
Warrior Post Production/
├── RUN_CODE                    # Launcher
├── code/
│   ├── orchestrator_minimal.py # Unified batch processor
│   ├── uploader.py              # Vimeo upload (manual TUS)
│   ├── file_watcher.py          # FCP completion detection
│   ├── notifier.py              # Slack notifications
│   ├── state_manager.py         # Processing state
│   ├── config.json              # Credentials
│   └── requirements.txt         # Python dependencies
├── Video_input/                 # Put videos here
└── README.md                    # This file
```

## Timing

- **Check interval**: 1 minute (between scans)
- **Idle timeout**: 5 minutes (no new videos = exit)
- **Progress updates**: 25%, 50%, 75%, 100% per video (immediate)
- **Batch notification**: Only after 5-minute idle period

## Output

- Videos uploaded to Vimeo (unlisted)
- Individual progress notifications (Slack)
- ONE final batch notification with all embed codes
- All videos moved to `/Volumes/T7/edited/`

## Config

Edit `code/config.json`:

```json
{
  "vimeo_token": "your_vimeo_token_here",
  "slack_webhook": "your_slack_webhook_here",
  "upload": {
    "privacy": "unlisted"
  }
}
```

## Requirements

- Python 3.x
- `requests` library
- Vimeo API token
- Slack webhook URL

---

**Version:** v3.4 Unified Batch  
**Date:** 2026-03-23  
**Feature:** Single notification for all videos (initial + late renders)
