#!/usr/bin/env python3
"""
Project Alpha - First-Time Setup Script
Run this on a new MacBook to check and setup all dependencies
"""

import subprocess
import sys
import json
from pathlib import Path

def check_python_version():
    """Check Python version"""
    version = sys.version_info
    print(f"Python version: {version.major}.{version.minor}.{version.micro}")
    if version.major < 3 or (version.major == 3 and version.minor < 9):
        print("❌ Python 3.9+ required")
        return False
    print("✓ Python version OK")
    return True

def check_ffmpeg():
    """Check if FFmpeg is installed"""
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            version = result.stdout.split('\n')[0]
            print(f"✓ FFmpeg installed: {version[:50]}")
            return True
    except FileNotFoundError:
        pass
    print("❌ FFmpeg not installed")
    print("   Install: brew install ffmpeg")
    return False

def check_whisper():
    """Check if OpenAI Whisper is installed"""
    try:
        import whisper
        print("✓ OpenAI Whisper installed")
        return True
    except ImportError:
        print("❌ OpenAI Whisper not installed")
        print("   Install: pip3 install --user --break-system-packages openai-whisper")
        return False

def check_python_packages():
    """Check required Python packages"""
    required = {
        'requests': 'requests',
        'google-auth': 'google.oauth2',
        'google-api-python-client': 'googleapiclient',
    }
    
    all_ok = True
    for package, import_name in required.items():
        try:
            __import__(import_name)
            print(f"✓ {package}")
        except ImportError:
            print(f"❌ {package} not installed")
            all_ok = False
    
    if not all_ok:
        print("\n📦 Install all packages:")
        print("   pip3 install --user --break-system-packages -r requirements.txt")
    
    return all_ok

def check_config():
    """Check configuration file"""
    script_dir = Path(__file__).parent
    config_file = script_dir / 'config.json'
    
    if not config_file.exists():
        print("❌ config.json not found")
        return False
    
    try:
        with open(config_file) as f:
            config = json.load(f)
        
        print("✓ config.json found")
        
        # Check required fields
        checks = [
            ('vimeo_token', config.get('vimeo_token')),
            ('slack_webhook', config.get('slack_webhook')),
            ('google_drive.enabled', config.get('google_drive', {}).get('enabled')),
            ('folder paths', config.get('folders')),
        ]
        
        all_ok = True
        for name, value in checks:
            if value:
                print(f"  ✓ {name} configured")
            else:
                print(f"  ⚠️  {name} not configured")
                all_ok = False
        
        return all_ok
    except json.JSONDecodeError:
        print("❌ config.json is invalid JSON")
        return False

def check_credentials():
    """Check Google Drive credentials"""
    script_dir = Path(__file__).parent
    client_secrets = script_dir / 'client_secrets.json'
    drive_token = script_dir / 'drive_token.json'
    
    print("\n🔐 Google Drive Authentication:")
    
    if client_secrets.exists():
        print("✓ client_secrets.json found")
        try:
            with open(client_secrets) as f:
                secrets = json.load(f)
            if 'installed' in secrets or 'web' in secrets:
                print("  ✓ Valid OAuth credentials")
            else:
                print("  ⚠️  Invalid credential format")
        except json.JSONDecodeError:
            print("  ❌ Invalid JSON in client_secrets.json")
    else:
        print("❌ client_secrets.json NOT FOUND")
        print("  📝 You need to:")
        print("     1. Go to https://console.cloud.google.com/")
        print("     2. Create a project or select existing")
        print("     3. Enable Google Drive API")
        print("     4. Create OAuth 2.0 credentials (Desktop app)")
        print("     5. Download JSON and save as client_secrets.json")
    
    if drive_token.exists():
        print("✓ drive_token.json found (authorized)")
    else:
        print("⚠️  drive_token.json NOT FOUND (will prompt for auth on first run)")

def check_folder_structure():
    """Check required folders exist"""
    print("\n📁 Folder Structure:")
    
    script_dir = Path(__file__).parent
    parent_dir = script_dir.parent
    
    folders = [
        (parent_dir / 'Video_input', 'Video input folder'),
        (parent_dir.parent / 'edited', 'Edited folder'),
        (parent_dir.parent / 'Transcripts', 'Transcripts folder'),
    ]
    
    all_ok = True
    for folder, name in folders:
        if folder.exists():
            print(f"✓ {name}: {folder}")
        else:
            print(f"⚠️  {name} missing: {folder}")
            folder.mkdir(parents=True, exist_ok=True)
            print(f"   ✓ Created: {folder}")
    
    return all_ok

def main():
    print("="*60)
    print("🔍 Project Alpha - First-Time Setup Check")
    print("="*60)
    print()
    
    checks = [
        ("Python Version", check_python_version),
        ("FFmpeg", check_ffmpeg),
        ("OpenAI Whisper", check_whisper),
        ("Python Packages", check_python_packages),
        ("Configuration", check_config),
        ("Folder Structure", check_folder_structure),
    ]
    
    results = {}
    for name, check_func in checks:
        print(f"\n{'─'*60}")
        print(f"📋 {name}")
        print("─"*60)
        results[name] = check_func()
    
    # Credentials check (info only)
    check_credentials()
    
    # Summary
    print(f"\n{'='*60}")
    print("📊 SETUP SUMMARY")
    print("="*60)
    
    all_passed = all(results.values())
    
    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
    
    print()
    if all_passed:
        print("🎉 All checks passed! Ready to run:")
        print("   python3 orchestrator_autonomous.py --mode watch")
    else:
        print("⚠️  Some checks failed. Please fix the issues above.")
        print("\nQuick fixes:")
        print("  brew install ffmpeg")
        print("  pip3 install --user --break-system-packages -r requirements.txt")
    
    print()
    print("For Google Drive setup:")
    print("  1. Get client_secrets.json from Google Cloud Console")
    print("  2. Place it in the code/ folder")
    print("  3. First run will prompt for browser authorization")
    print()

if __name__ == "__main__":
    main()
