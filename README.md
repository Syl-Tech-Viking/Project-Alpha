# Project Alpha v3.4 - Smart Batch Vimeo Uploader

## Overview

Smart uploader that processes videos in batches and waits for new ones with an idle timeout.

## How It Works

```
1. Scans Video_input/ for ALL videos
2. Processes each video:
   - Waits for FCP rendering to complete
   - Uploads to Vimeo
   - Sends Slack progress (25%, 50%, 75%, 100%)
3. Sends batch notification with all embed codes
4. Moves videos to /Volumes/T7/edited/
5. Waits 1 minute
6. Checks for NEW videos
   - If found: Process them (go to step 1)
   - If not found: Continue checking
7. After 5 minutes of no new videos: EXIT
```

## Behavior

- **Initial Scan**: Finds and processes all videos currently in folder
- **New Video Detection**: After each batch, waits 1 minute then checks again
- **Idle Timeout**: If no new videos for 5 minutes, program exits
- **Progress Notifications**: Slack notified at 25%, 50%, 75%, 100% per video
- **Batch Notification**: One final Slack message with all embed codes

## Quick Start

```bash
# Navigate to project
cd "/Volumes/T7/Warrior Post Production"

# Setup environment (first time only)
python3 -m venv venv
source venv/bin/activate
pip install requests

# Configure credentials
# Edit code/config.json with your Vimeo token and Slack webhook

# Run
./RUN_CODE
```

## Files

```
Warrior Post Production/
├── RUN_CODE                    # Launcher
├── code/
│   ├── orchestrator_minimal.py # Smart batch processor with idle timeout
│   ├── uploader.py              # Vimeo upload (manual TUS)
│   ├── file_watcher.py          # FCP completion detection
│   ├── notifier.py              # Slack notifications
│   ├── state_manager.py         # Processing state
│   ├── config.json              # Credentials (Vimeo + Slack)
│   └── requirements.txt         # Python dependencies
├── Video_input/                 # Put videos here
└── README.md                    # This file
```

## Output

- Videos uploaded to Vimeo
- Slack notifications at each 25% milestone
- Final batch notification with embed codes
- Videos moved to: `/Volumes/T7/edited/`

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

## Timing

- **Batch processing**: As fast as videos upload
- **Between batches**: 1 minute wait
- **Idle timeout**: 5 minutes (program exits if no new videos)

---

**Version:** v3.4 Smart Batch  
**Date:** 2026-03-23  
**Features:** Idle timeout, new video detection, batch processing
