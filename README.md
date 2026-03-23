# Project Alpha v3.4 - New Laptop Setup

## Quick Start

```bash
# 1. Navigate to T7
cd "/Volumes/T7/Warrior Post Production"

# 2. Setup Python environment
python3 -m venv venv
source venv/bin/activate
pip install requests

# 3. Configure (edit code/config.json with your tokens)
# - Vimeo token
# - Slack webhook

# 4. Put videos in Video_input/ folder

# 5. Run
./RUN_CODE
```

## What It Does

1. Scans `Video_input/` for ALL videos
2. Waits for FCP rendering to complete
3. Uploads all videos to Vimeo
4. Sends Slack progress notifications:
   - 🟡 25% complete
   - 🟠 50% complete
   - 🔵 75% complete
   - ✅ 100% complete
5. Sends final batch notification with all embed codes
6. Moves processed videos to `/Volumes/T7/edited/`
7. Exits

## Requirements

- Python 3.x
- `requests` library (for HTTP calls)
- Vimeo API token
- Slack webhook URL

## Files

```
Warrior Post Production/
├── RUN_CODE                      # Launcher script
├── code/
│   ├── orchestrator_minimal.py # Main processor
│   ├── uploader.py              # Vimeo upload (manual TUS)
│   ├── file_watcher.py          # FCP completion detection
│   ├── notifier.py              # Slack notifications
│   ├── state_manager.py         # Processing state
│   ├── config.json              # Credentials
│   └── requirements.txt         # Dependencies
└── Video_input/                 # Put videos here
```

## Output Location

After upload, videos are moved to: `/Volumes/T7/edited/`

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

## Testing

Tested and working on T7 drive.
Uploads confirmed successful with manual TUS protocol.

---
**Version:** v3.4 Minimal  
**Date:** 2026-03-23
