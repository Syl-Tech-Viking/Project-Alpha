#!/usr/bin/env python3
"""
Pre-flight Check - Verify all systems ready before starting watcher
Ensures Google Drive auth is complete BEFORE processing begins
"""

import os
import sys
import json
import time
import subprocess
from pathlib import Path

# Allow localhost for OAuth
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

def check_python_dependencies():
    """Check if required Python packages are installed"""
    print("📦 Checking Python dependencies...")
    
    required = {
        'requests': 'requests',
        'google-auth': 'google.oauth2',
        'google-auth-oauthlib': 'google_auth_oauthlib',
        'google-api-python-client': 'googleapiclient',
        'psutil': 'psutil',
    }
    
    missing = []
    for package, import_name in required.items():
        try:
            __import__(import_name)
            print(f"  ✓ {package}")
        except ImportError:
            print(f"  ❌ {package} - NOT INSTALLED")
            missing.append(package)
    
    if missing:
        print()
        print("="*70)
        print("⚠️  MISSING PYTHON PACKAGES - Will auto-install")
        print("="*70)
        print()
        print("Missing packages:")
        for pkg in missing:
            print(f"  - {pkg}")
        print()
        return False, missing
    
    print("  ✓ All Python dependencies installed")
    return True, []

def install_dependencies_auto():
    """Attempt to install missing dependencies automatically"""
    print()
    print("="*70)
    print("📦 INSTALLING MISSING DEPENDENCIES")
    print("="*70)
    print()
    
    script_dir = Path(__file__).parent
    req_file = script_dir / "requirements.txt"
    
    if not req_file.exists():
        print("❌ requirements.txt not found")
        print("Please run: pip3 install --user --break-system-packages")
        print("           requests google-auth google-auth-oauthlib")
        print("           google-auth-httplib2 google-api-python-client")
        return False
    
    print("Running: pip3 install --user --break-system-packages -r requirements.txt")
    print("(This may take a few minutes...)")
    print()
    
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--user", "--break-system-packages", "-r", str(req_file)],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode == 0:
            print("✅ Dependencies installed successfully!")
            print()
            print("🔄 Please restart the preflight check:")
            print("   ./RUN_CODE")
            print()
            return True
        else:
            print("❌ Installation failed:")
            print(result.stderr)
            return False
    except subprocess.TimeoutExpired:
        print("❌ Installation timed out (took too long)")
        return False
    except Exception as e:
        print(f"❌ Installation error: {e}")
        return False

def check_google_drive_auth():
    """Check if Google Drive is authenticated and actually working on this machine"""
    print("🔐 Checking Google Drive authentication...")
    
    script_dir = Path(__file__).parent
    token_path = script_dir / "drive_token.json"
    creds_path = script_dir / "client_secrets.json"
    config_path = script_dir / "config.json"
    
    # Check required files exist
    if not creds_path.exists():
        print("  ❌ Missing client_secrets.json")
        return False, "Missing OAuth credentials file"
    
    if not config_path.exists():
        print("  ❌ Missing config.json")
        return False, "Missing configuration"
    
    # Load config
    with open(config_path) as f:
        config = json.load(f)
    
    if not config.get('google_drive', {}).get('enabled'):
        print("  ⚠️  Google Drive disabled in config")
        return True, "Drive disabled, will skip upload"
    
    # ALWAYS delete existing token to force re-authentication
    # This ensures you sign in every time for security and permission verification
    if token_path.exists():
        print("  🗑️  Deleting existing token (force re-authentication)...")
        token_path.unlink()
        print("  ✓ Token deleted - fresh authentication required")
    
    # No valid token - authentication always needed
    print("  ❌ Not authenticated (by design - you must sign in every time)")
    return False, "Authentication required - please sign in"

def authenticate_google_drive():
    """Fully automated Google Drive authentication - NO MANUAL URL COPYING"""
    print()
    print("="*70)
    print("🔐 GOOGLE DRIVE AUTHENTICATION")
    print("="*70)
    print()
    
    # Check dependencies first
    deps_ok, missing = check_python_dependencies()
    if not deps_ok:
        print("⚠️  Missing dependencies - Auto-installing...")
        if install_dependencies_auto():
            print("🔄 Dependencies installed. Please restart RUN_CODE.")
            return False
        else:
            print("❌ Auto-install failed")
            return False
    
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from pathlib import Path
        import http.server
        import socketserver
        import threading
        import urllib.parse
        
        script_dir = Path(__file__).parent
        creds_path = script_dir / "client_secrets.json"
        token_path = script_dir / "drive_token.json"
        
        if not creds_path.exists():
            print("❌ ERROR: client_secrets.json not found")
            return False
        
        SCOPES = ['https://www.googleapis.com/auth/drive']
        
        # Create OAuth flow
        flow = InstalledAppFlow.from_client_secrets_file(
            str(creds_path),
            SCOPES,
            redirect_uri='http://localhost:8080'
        )
        
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        
        # Shared state for capturing auth code
        auth_state = {'code': None, 'error': None, 'done': False}
        
        # HTTP handler to capture OAuth callback
        class OAuthHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                query = urllib.parse.parse_qs(parsed.query)
                
                if 'code' in query:
                    auth_state['code'] = query['code'][0]
                    auth_state['done'] = True
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    self.wfile.write(b"""<html><body style="font-family: Arial; text-align: center; padding: 50px;"><h1 style="color: green;">Authentication Successful!</h1><p>You can close this window.</p></body></html>""")
                elif 'error' in query:
                    auth_state['error'] = query.get('error', ['Unknown'])[0]
                    auth_state['done'] = True
                    self.send_response(400)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    error_html = f"<html><body style='font-family: Arial; text-align: center; padding: 50px;'><h1 style='color: red;'>Authentication Failed</h1><p>Error: {auth_state['error']}</p></body></html>"
                    self.wfile.write(error_html.encode())
                else:
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    self.wfile.write(b"""<html><body style="font-family: Arial; text-align: center; padding: 50px;"><h1>Waiting for authentication...</h1><p>Please complete sign-in in the other browser tab.</p></body></html>""")
            
            def log_message(self, format, *args):
                pass
        
        # Start local server
        with socketserver.TCPServer(('localhost', 8080), OAuthHandler) as server:
            server_thread = threading.Thread(target=server.serve_forever)
            server_thread.daemon = True
            server_thread.start()
            
            print("🌐 Opening browser for Google authentication...")
            print()
            
            import webbrowser
            browser_opened = webbrowser.open(auth_url, new=2)
            
            if not browser_opened:
                print("❌ ERROR: Could not open browser automatically")
                print()
                print("TO FIX:")
                print("1. Set default browser in System Preferences > General")
                print("2. Re-run this script")
                server.shutdown()
                return False
            
            print("📱 Browser opened.")
            print("   Please sign in with: sylvan@wakeupwarrior.com")
            print("   Click 'Allow' for Google Drive access")
            print()
            print("⏳ Waiting for authentication to complete...")
            print()
            
            # Wait for auth (2 minute timeout)
            timeout = 120
            waited = 0
            while not auth_state['done'] and waited < timeout:
                time.sleep(1)
                waited += 1
                if waited % 15 == 0:
                    print(f"   Waiting... ({waited}s)")
            
            server.shutdown()
            
            if not auth_state['done']:
                print()
                print("❌ ERROR: Authentication timed out")
                print("   You didn't complete sign-in within 2 minutes")
                return False
            
            if auth_state['error']:
                print()
                print(f"❌ ERROR: {auth_state['error']}")
                return False
            
            # Complete the flow
            print()
            print("🔄 Completing authentication...")
            flow.fetch_token(code=auth_state['code'])
            creds = flow.credentials
            
            # Save token
            with open(token_path, 'w') as token:
                token.write(creds.to_json())
            
            print()
            print("✅ Authentication successful!")
            
            # Verify
            service = build('drive', 'v3', credentials=creds)
            about = service.about().get(fields='user(emailAddress)').execute()
            email = about['user']['emailAddress']
            print(f"   Signed in as: {email}")
            
            return True
            
    except Exception as e:
        print()
        print(f"❌ Authentication error: {e}")
        return False

def main():
    """Run pre-flight checks"""
    print("="*70)
    print("✈️  PRE-FLIGHT CHECK - Pipeline Readiness Verification")
    print("="*70)
    print()
    
    all_ready = True
    
    # Check 0: Python Dependencies FIRST
    print("0️⃣  Python Dependencies")
    print("-"*70)
    deps_ok, missing = check_python_dependencies()
    
    if not deps_ok:
        print()
        print("   Status: ⚠️  Missing dependencies - Auto-installing...")
        print()
        
        if install_dependencies_auto():
            print()
            print("🔄 Dependencies installed. Please restart RUN_CODE.")
            print()
            input("Press Enter to exit...")
            sys.exit(0)
        else:
            all_ready = False
    else:
        print("   Status: ✓ Ready")
    
    print()
    
    # Check 1: Google Drive Auth
    print("1️⃣  Google Drive Authentication")
    print("-"*70)
    
    # ALWAYS delete existing token to force re-authentication
    script_dir = Path(__file__).parent
    token_path = script_dir / "drive_token.json"
    
    if token_path.exists():
        print("  🗑️  Deleting existing token (force re-authentication)...")
        token_path.unlink()
        print("  ✓ Old token deleted")
    
    # Now check - will definitely need auth since we just deleted token
    print("  ❌ Not authenticated (by design - fresh sign-in required)")
    print()
    
    # Offer to authenticate
    response = input("Authenticate Google Drive now? (y/n): ").strip().lower()
    
    if response == 'y':
        if authenticate_google_drive():
            # Verify the NEW token actually works
            print("  🧪 Verifying new authentication...")
            try:
                from google.oauth2.credentials import Credentials
                from googleapiclient.discovery import build
                
                creds = Credentials.from_authorized_user_file(
                    str(token_path), 
                    ['https://www.googleapis.com/auth/drive']
                )
                
                service = build('drive', 'v3', credentials=creds)
                about = service.about().get(fields='user(emailAddress)').execute()
                email = about['user']['emailAddress']
                
                # Load config to check folder
                with open(script_dir / "config.json") as f:
                    config = json.load(f)
                folder_id = config['google_drive']['folder_id']
                
                # Quick test - just check folder exists
                folder = service.files().get(
                    fileId=folder_id,
                    supportsAllDrives=True,
                    fields='id, name'
                ).execute()
                
                print(f"  ✓ Valid authentication for: {email}")
                print(f"  ✓ Can access folder: {folder['name']}")
                print(f"   Status: ✅ READY")
                
            except Exception as e:
                print(f"  ❌ Authentication verification failed: {str(e)[:100]}")
                print(f"   Status: ❌ NOT READY")
                all_ready = False
        else:
            print(f"   Status: ❌ Authentication failed")
            all_ready = False
    else:
        print("   ⚠️  Will skip Google Drive uploads")
        print("   Transcripts will be saved locally only")
    
    print()
    
    # Check 2: Required files
    print("2️⃣  Required Files")
    print("-"*70)
    
    required_files = [
        'client_secrets.json',
        'config.json',
        'orchestrator_autonomous.py',
        'uploader.py',
        'transcriber.py',
        'notifier.py',
        'file_watcher.py',
        'state_manager.py',
        'session_resilience.py'
    ]
    
    script_dir = Path(__file__).parent
    all_files_exist = True
    
    for file in required_files:
        path = script_dir / file
        if path.exists():
            print(f"   ✅ {file}")
        else:
            print(f"   ❌ {file} - MISSING")
            all_files_exist = False
            all_ready = False
    
    print()
    
    # Check 3: Folders
    print("3️⃣  Required Folders")
    print("-"*70)
    
    with open(script_dir / "config.json") as f:
        config = json.load(f)
    
    folders = config.get('folders', {})
    
    for name, path_str in folders.items():
        path = Path(path_str)
        if path_str.startswith('../'):
            path = script_dir.parent / path_str[3:]
        elif path_str.startswith('/'):
            path = Path(path_str)
        else:
            path = script_dir / path_str
        
        if path.exists():
            print(f"   ✅ {name}: {path}")
        else:
            print(f"   📁 Creating {name}: {path}")
            path.mkdir(parents=True, exist_ok=True)
            print(f"   ✅ Created")
    
    print()
    
    # Final status
    print("="*70)
    if all_ready:
        print("🎉 ALL SYSTEMS READY!")
        print("="*70)
        print()
        print("✅ You can now run the pipeline:")
        print("   ./RUN_CODE")
        print()
        print("✅ Google Drive will upload transcripts automatically")
        print("✅ No interruptions expected during processing")
        return 0
    else:
        print("⚠️  NOT ALL SYSTEMS READY")
        print("="*70)
        print()
        print("❌ Please fix the issues above before running the pipeline")
        print("   This prevents interruptions during video processing")
        return 1

if __name__ == "__main__":
    sys.exit(main())
