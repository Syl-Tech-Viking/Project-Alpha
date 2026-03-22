# Project Alpha - New MacBook Setup Guide

**Complete setup instructions for running on a fresh MacBook**

---

## Quick Start (5 minutes)

```bash
# 1. Navigate to the code folder
cd "/Volumes/T7/Warrior Post Production/code"

# 2. Run setup check
python3 setup.py

# 3. Install missing dependencies (if any)
pip3 install --user --break-system-packages -r requirements.txt

# 4. Run the pipeline
python3 orchestrator_autonomous.py --mode watch
```

---

## Prerequisites

### 1. System Requirements
- macOS 12+ (Monterey or newer)
- Python 3.9+ (usually pre-installed)
- ~2GB free space for dependencies
- Internet connection for Vimeo/Drive/Slack

### 2. Required Software

**Install Homebrew (if not installed):**
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

**Install FFmpeg:**
```bash
brew install ffmpeg
```

**Install Python packages:**
```bash
pip3 install --user --break-system-packages -r requirements.txt
```

---

## First-Time Setup Steps

### Step 1: Run Setup Check

```bash
cd "/Volumes/T7/Warrior Post Production/code"
python3 setup.py
```

This will check:
- ✅ Python version
- ✅ FFmpeg installation
- ✅ Required Python packages
- ✅ Configuration files
- ✅ Folder structure
- 🔐 Google Drive authentication status

### Step 2: Install Missing Dependencies

If `setup.py` shows missing packages:

```bash
# Install all at once
pip3 install --user --break-system-packages -r requirements.txt

# Or install individually:
pip3 install --user --break-system-packages requests
pip3 install --user --break-system-packages google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
pip3 install --user --break-system-packages openai-whisper
```

### Step 3: Google Drive Authentication (One-Time)

**The pipeline needs Google Drive access to upload transcripts.**

**Already configured?**
- If `drive_token.json` exists → you're already authorized ✅
- If only `client_secrets.json` exists → first run will prompt for auth

**First-time authorization:**

1. Make sure `client_secrets.json` is in the code/ folder
2. Run the pipeline: `python3 orchestrator_autonomous.py --mode batch`
3. A browser window will open asking you to sign in
4. Sign in with: **sylvan@wakeupwarrior.com**
5. Click "Allow" to grant Drive access
6. The token will be saved automatically as `drive_token.json`

**No browser opens?**
- Check that your default browser works
- Try: `python3 -c "import webbrowser; webbrowser.open('https://google.com')"`
- If that doesn't open a browser, set a default browser in System Preferences

---

## Running the Pipeline

### Watch Mode (Recommended)
Continuously monitors for new videos:

```bash
cd "/Volumes/T7/Warrior Post Production/code"
python3 orchestrator_autonomous.py --mode watch
```

**What it does:**
1. Processes any existing videos in Video_input/
2. Waits for new videos to be added
3. After 10 minutes of inactivity, sends Slack batch notification
4. Continues monitoring indefinitely
5. Stops after 2 hours of total inactivity (or Ctrl+C)

### Batch Mode
Process all existing videos immediately:

```bash
python3 orchestrator_autonomous.py --mode batch
```

---

## Troubleshooting

### "No module named 'requests'"
```bash
pip3 install --user --break-system-packages requests
```

### "No module named 'whisper'"
```bash
pip3 install --user --break-system-packages openai-whisper
```

### "FFmpeg not found"
```bash
brew install ffmpeg
```

### Google Drive "Access Denied" or Auth Failed
1. Check that `client_secrets.json` exists in code/ folder
2. Delete `drive_token.json` if it exists (forces re-auth)
3. Re-run: `python3 orchestrator_autonomous.py --mode batch`
4. Browser should open - sign in and allow access

### "Token has been expired or revoked"
```bash
rm "/Volumes/T7/Warrior Post Production/code/drive_token.json"
python3 orchestrator_autonomous.py --mode batch
```
Then re-authenticate in browser.

### Videos not being detected
- Check that videos are in: `/Volumes/T7/Warrior Post Production/Video_input/`
- Supported formats: `.mov`, `.mp4`
- Files must finish copying (not mid-transfer)

---

## File Structure

```
/Volumes/T7/
├── Warrior Post Production/
│   ├── Video_input/          ← Drop videos here
│   └── code/
│       ├── orchestrator_autonomous.py  ← Main script
│       ├── setup.py           ← Setup checker
│       ├── requirements.txt   ← Python dependencies
│       ├── config.json        ← Configuration
│       ├── client_secrets.json ← Google OAuth credentials
│       ├── drive_token.json   ← Google auth token (created on first run)
│       └── pipeline_state.json ← State tracking (created automatically)
├── edited/                  ← Processed videos moved here
└── Transcripts/             ← Generated transcripts saved here
```

---

## Configuration

Edit `config.json` to customize:

```json
{
  "vimeo_token": "your_token_here",
  "slack_webhook": "your_webhook_url",
  "google_drive": {
    "enabled": true,
    "folder_id": "your_folder_id"
  },
  "daemon": {
    "batch_timeout_minutes": 10,
    "session_timeout_minutes": 120
  }
}
```

---

## Support

If setup fails:
1. Run `python3 setup.py` and check which step fails
2. Check error messages in the output
3. Ensure T7 drive is properly mounted
4. Try re-installing dependencies

---

**Last Updated:** 2026-03-16  
**Version:** 3.1  
**Status:** Production Ready
