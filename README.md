# Project Alpha v3.3

Automated video processing pipeline for Warrior Post Production.

## Quick Start

```bash
cd "/Volumes/T7/Warrior Post Production"
./RUN_CODE
```

## Setup

1. Copy `code/config.json.example` to `code/config.json`
2. Add your credentials to `config.json`:
   - Vimeo token
   - Slack webhook URL
   - Google Drive folder ID
3. Add `client_secrets.json` from Google Cloud Console
4. Run the pipeline

## Features

- ✅ Session re-initialization for internet outages
- ✅ Force fresh authentication every run
- ✅ Enhanced Slack notifications
- ✅ TUS resumable uploads
- ✅ Automatic retry with exponential backoff

## Version

v3.3 - March 2026
