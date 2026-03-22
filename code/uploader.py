#!/usr/bin/env python3
"""
Video Uploader - Vimeo and Google Drive
Uploads video to Vimeo, transcript to Drive
"""

import requests
import time
from pathlib import Path
from typing import Dict

class VideoUploader:
    """Upload videos to Vimeo and transcripts to Google Drive"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.vimeo_token = config.get('vimeo_token', '')
        self.google_drive_config = config.get('google_drive', {})
    
    def upload_to_vimeo(self, video_path: Path, metadata: Dict) -> Dict:
        """Upload video to Vimeo using TUS protocol with session re-initialization"""
        print(f"[UPLOAD] Starting Vimeo upload: {video_path.name}")
        
        if not self.vimeo_token:
            return {'success': False, 'error': 'Vimeo token not configured'}
        
        # Session re-initialization tracking
        max_session_retries = 2
        session_attempt = 0
        last_uploaded_offset = 0
        video_uri = None
        video_id = None
        video_url = None
        player_url = None
        
        while session_attempt <= max_session_retries:
            try:
                # Step 1: Create upload ticket (or re-create for session retry)
                if session_attempt == 0:
                    print(f"[UPLOAD] Creating new Vimeo upload session...")
                else:
                    print(f"[UPLOAD] 🔄 Re-initializing upload session (attempt {session_attempt}/{max_session_retries})...")
                    print(f"[UPLOAD]    Resuming from offset: {last_uploaded_offset}")
                
                headers = {
                    'Authorization': f'Bearer {self.vimeo_token}',
                    'Content-Type': 'application/json'
                }
                
                upload_data = {
                    'upload': {
                        'approach': 'tus',
                        'size': video_path.stat().st_size
                    },
                    'name': metadata.get('title', video_path.stem),
                    'description': metadata.get('description', '')[:2000],  # Vimeo limit
                    'privacy': {
                        'view': self.config.get('upload', {}).get('privacy', 'unlisted')
                    }
                }
                
                response = requests.post(
                    'https://api.vimeo.com/me/videos',
                    headers=headers,
                    json=upload_data,
                    timeout=30
                )
                
                # Accept both 200 and 201
                if response.status_code not in [200, 201]:
                    if session_attempt < max_session_retries:
                        print(f"[UPLOAD] ⚠️  Session creation failed: HTTP {response.status_code}")
                        print(f"[UPLOAD]    Retrying in 10 seconds...")
                        time.sleep(10)
                        session_attempt += 1
                        continue
                    return {
                        'success': False,
                        'error': f'Vimeo API error (status {response.status_code}): {response.text[:200]}'
                    }
                
                video_data = response.json()
                
                # Check for required fields
                if 'uri' not in video_data or 'upload' not in video_data:
                    if session_attempt < max_session_retries:
                        print(f"[UPLOAD] ⚠️  Vimeo API returned incomplete data")
                        print(f"[UPLOAD]    Retrying in 10 seconds...")
                        time.sleep(10)
                        session_attempt += 1
                        continue
                    return {
                        'success': False,
                        'error': 'Vimeo API returned incomplete data'
                    }
                
                upload_link = video_data['upload']['upload_link']
                video_uri = video_data['uri']
                video_id = video_uri.split('/')[-1]
                
                # Get URLs from response or construct them
                video_url = video_data.get('link', f'https://vimeo.com/{video_id}')
                player_url = video_data.get('player_embed_url', f'https://player.vimeo.com/video/{video_id}')
                
                if session_attempt == 0:
                    print(f"[UPLOAD] Created Vimeo video: {video_url}")
                else:
                    print(f"[UPLOAD] ✓ New session created: {video_url}")
                print(f"[UPLOAD] Starting TUS upload...")
                
                # Step 2: TUS Upload (with resume capability)
                try:
                    last_uploaded_offset = self._tus_upload(video_path, upload_link, resume_offset=last_uploaded_offset)
                    
                    # Upload succeeded!
                    print(f"[UPLOAD] ✓ Vimeo upload complete")
                    
                    # Create responsive embed code matching Vimeo's official embed
                    embed_code = f'''<div style="padding:56.25% 0 0 0;position:relative;"><iframe src="{player_url}?h={video_data.get('embed', {}).get('hash', '')}&amp;title=0&amp;byline=0&amp;portrait=0&amp;badge=0&amp;autopause=0&amp;player_id=0&amp;app_id=58479" frameborder="0" allow="autoplay; fullscreen; picture-in-picture; clipboard-write; encrypted-media; web-share" referrerpolicy="strict-origin-when-cross-origin" style="position:absolute;top:0;left:0;width:100%;height:100%;" title="{metadata.get('title', video_path.stem)}"></iframe></div><script src="https://player.vimeo.com/api/player.js"></script>'''
                    
                    return {
                        'success': True,
                        'video_id': video_id,
                        'video_url': video_url,
                        'embed_code': embed_code
                    }
                    
                except Exception as tus_error:
                    # TUS upload failed - check if we should retry with new session
                    error_str = str(tus_error)
                    print(f"[UPLOAD] ❌ TUS upload failed: {error_str[:200]}")
                    
                    # Check if it's a session-related error
                    if session_attempt < max_session_retries and (
                        'chunk failed' in error_str.lower() or 
                        'timeout' in error_str.lower() or
                        'connection' in error_str.lower() or
                        'session' in error_str.lower()
                    ):
                        print(f"[UPLOAD] 🔄 Session failure detected. Will re-initialize...")
                        print(f"[UPLOAD]    (Progress saved: {last_uploaded_offset} bytes uploaded)")
                        session_attempt += 1
                        time.sleep(5)  # Brief pause before re-initializing
                        continue
                    else:
                        # Not a session error or out of retries
                        raise
                
            except Exception as e:
                error_str = str(e)
                print(f"[UPLOAD] ❌ Upload error: {error_str[:200]}")
                
                # Check if we should retry with new session
                if session_attempt < max_session_retries and (
                    'chunk failed' in error_str.lower() or 
                    'timeout' in error_str.lower() or
                    'connection' in error_str.lower() or
                    'session' in error_str.lower()
                ):
                    print(f"[UPLOAD] 🔄 Will attempt session re-initialization ({session_attempt + 1}/{max_session_retries})...")
                    session_attempt += 1
                    time.sleep(5)
                    continue
                
                return {'success': False, 'error': f'Vimeo upload error: {error_str}'}
        
        # Exhausted all session retries
        return {'success': False, 'error': f'Upload failed after {max_session_retries + 1} session attempts'}
    
    def _tus_upload(self, video_path: Path, upload_link: str, resume_offset: int = 0) -> int:
        """
        Perform TUS resumable upload to Vimeo - PROGRESS BASED
        
        Only fails if no bytes transmitted for stall_threshold seconds.
        Otherwise continues indefinitely as long as progress is being made.
        
        Returns:
            int: Final uploaded offset (for session re-initialization)
        """
        file_size = video_path.stat().st_size
        chunk_size = 10 * 1024 * 1024  # 10MB chunks for efficiency
        
        # Progress tracking - PROGRESS BASED ERROR HANDLING
        offset = resume_offset  # Start from resume position if provided
        last_successful_offset = resume_offset
        last_progress_time = time.time()
        stall_threshold = 300  # 5 minutes without progress = potential stall
        max_resume_attempts = 5  # Try to resume up to 5 times
        resume_attempts = 0
        start_time = time.time()
        reported_progress = int((resume_offset / file_size) * 10) - 1 if resume_offset > 0 else -1
        
        if resume_offset > 0:
            print(f"[UPLOAD] Resuming TUS upload from {resume_offset / (1024*1024):.1f} MB ({(resume_offset/file_size)*100:.1f}%)...")
        else:
            print(f"[UPLOAD] Starting TUS upload ({file_size / (1024*1024):.1f} MB)...")
        print(f"[UPLOAD] Progress-based monitoring: will continue as long as bytes flow...")
        
        with open(video_path, 'rb') as f:
            f.seek(offset)  # Start from resume position
            
            while offset < file_size:
                # Check for stall - no progress for stall_threshold seconds
                time_without_progress = time.time() - last_progress_time
                
                if time_without_progress > stall_threshold and offset > last_successful_offset:
                    print(f"[UPLOAD] ⚠️  No progress for {int(time_without_progress)}s - attempting TUS resume...")
                    
                    # Try to resume from server offset
                    try:
                        head_headers = {'Tus-Resumable': '1.0.0'}
                        head_resp = requests.head(upload_link, headers=head_headers, timeout=30)
                        
                        if head_resp.status_code == 200:
                            server_offset = int(head_resp.headers.get('Upload-Offset', 0))
                            
                            if server_offset > offset:
                                print(f"[UPLOAD] ✓ Resuming from server offset: {server_offset}/{file_size}")
                                offset = server_offset
                                f.seek(offset)
                                last_successful_offset = offset
                                last_progress_time = time.time()
                                resume_attempts = 0
                            elif server_offset == offset:
                                print(f"[UPLOAD] ⚠️  Server at same offset ({offset}), chunk may have failed")
                                resume_attempts += 1
                                if resume_attempts >= max_resume_attempts:
                                    # Return current offset for session re-initialization
                                    print(f"[UPLOAD] ❌ Upload stalled at offset {offset}")
                                    return offset
                                time.sleep(5 * resume_attempts)  # Exponential backoff
                                last_progress_time = time.time()  # Reset timer for another try
                            else:
                                print(f"[UPLOAD] ⚠️  Server offset ({server_offset}) < local offset ({offset}), using server's position")
                                offset = server_offset
                                f.seek(offset)
                                last_successful_offset = offset
                                last_progress_time = time.time()
                        else:
                            print(f"[UPLOAD] ⚠️  HEAD request failed: {head_resp.status_code}")
                            resume_attempts += 1
                            if resume_attempts >= max_resume_attempts:
                                # Return current offset for session re-initialization
                                print(f"[UPLOAD] ❌ Cannot determine upload position after {max_resume_attempts} attempts")
                                return offset
                            time.sleep(5 * resume_attempts)
                            
                    except Exception as e:
                        print(f"[UPLOAD] ⚠️  Resume attempt failed: {e}")
                        resume_attempts += 1
                        if resume_attempts >= max_resume_attempts:
                            # Return current offset for session re-initialization
                            print(f"[UPLOAD] ❌ Resume failed after {max_resume_attempts} attempts: {e}")
                            return offset
                        time.sleep(5 * resume_attempts)
                        last_progress_time = time.time()  # Reset to give another chance
                
                # Read and upload chunk
                f.seek(offset)
                chunk = f.read(chunk_size)
                
                # Upload with retry
                chunk_uploaded = False
                chunk_retries = 0
                max_chunk_retries = 5
                
                while not chunk_uploaded and chunk_retries < max_chunk_retries:
                    try:
                        headers = {
                            'Tus-Resumable': '1.0.0',
                            'Content-Type': 'application/offset+octet-stream',
                            'Upload-Offset': str(offset)
                        }
                        
                        response = requests.patch(upload_link, headers=headers, data=chunk, timeout=60)
                        
                        if response.status_code in [200, 204]:
                            chunk_uploaded = True
                            last_successful_offset = offset
                            last_progress_time = time.time()  # Reset progress timer
                            resume_attempts = 0  # Reset resume counter on success
                        else:
                            print(f"[UPLOAD] ⚠️  Chunk failed: HTTP {response.status_code}, retrying...")
                            chunk_retries += 1
                            time.sleep(2 ** chunk_retries)  # Exponential backoff
                            
                    except requests.exceptions.Timeout:
                        print(f"[UPLOAD] ⚠️  Chunk timeout (60s), retrying...")
                        chunk_retries += 1
                        time.sleep(2 ** chunk_retries)
                    except Exception as e:
                        print(f"[UPLOAD] ⚠️  Chunk error: {e}, retrying...")
                        chunk_retries += 1
                        time.sleep(2 ** chunk_retries)
                
                if not chunk_uploaded:
                    raise Exception(f'Failed to upload chunk at offset {offset} after {max_chunk_retries} retries')
                
                offset += len(chunk)
                progress = (offset / file_size) * 100
                
                # Print progress every 10% or every 500MB for large files
                current_10pct = int(progress / 10)
                if current_10pct > reported_progress:
                    elapsed = time.time() - start_time
                    speed = (offset / (1024*1024)) / elapsed if elapsed > 0 else 0
                    print(f"[UPLOAD] Progress: {progress:.1f}% ({offset/(1024*1024):.1f} MB @ {speed:.2f} MB/s)")
                    reported_progress = current_10pct
        
        print(f"[UPLOAD] ✓ TUS upload complete ({file_size / (1024*1024):.1f} MB)")
        return file_size  # Return complete offset
    
    def upload_to_drive(self, transcript_path: Path, video_name: str) -> Dict:
        """Upload transcript to Google Drive"""
        print(f"[DRIVE] Uploading transcript: {transcript_path.name}")
        
        if not self.google_drive_config.get('enabled'):
            return {'success': False, 'error': 'Google Drive not enabled'}
        
        try:
            # Import Google libraries
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload
            
            SCOPES = ['https://www.googleapis.com/auth/drive']
            
            creds = None
            token_file = self.google_drive_config.get('token_file', 'drive_token.json')
            credentials_file = self.google_drive_config.get('credentials_file', 'client_secrets.json')
            
            # Load existing token
            if Path(token_file).exists():
                creds = Credentials.from_authorized_user_file(token_file, SCOPES)
            
            # Refresh or create new credentials
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    from google.auth.transport.requests import Request
                else:
                    if not Path(credentials_file).exists():
                        print(f"[DRIVE] ⚠️  {credentials_file} not found")
                        print(f"[DRIVE] Please download OAuth credentials from Google Cloud Console")
                        return {
                            'success': False,
                            'error': f'Missing {credentials_file}. See setup instructions.'
                        }
                    
                    print("[DRIVE] Opening browser for Google authorization...")
                    print("[DRIVE] Please sign in with sylvan@wakeupwarrior.com")
                    
                    flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
                    creds = flow.run_local_server(port=0)
                    
                    # Save token
                    with open(token_file, 'w') as token:
                        token.write(creds.to_json())
                    
                    print("[DRIVE] ✓ Authorization complete")
            
            # Build Drive service
            service = build('drive', 'v3', credentials=creds)
            
            # Get folder ID
            folder_id = self.google_drive_config.get('folder_id')
            if not folder_id:
                return {'success': False, 'error': 'Google Drive folder ID not configured'}
            
            # Upload file
            file_metadata = {
                'name': transcript_path.name,
                'parents': [folder_id],
                'mimeType': 'text/plain'
            }
            
            media = MediaFileUpload(str(transcript_path), mimetype='text/plain', resumable=True)
            
            file = service.files().create(
                body=file_metadata,
                media_body=media,
                supportsAllDrives=True,  # CRITICAL: Required for shared folders
                fields='id, name, webViewLink'
            ).execute()
            
            file_id = file.get('id')
            web_link = file.get('webViewLink')
            
            # Make shareable
            try:
                permission = {'type': 'anyone', 'role': 'reader'}
                service.permissions().create(fileId=file_id, body=permission).execute()
            except Exception as perm_error:
                # Permission error - likely the folder is shared but we don't have edit rights
                error_str = str(perm_error)
                if '404' in error_str or 'notFound' in error_str:
                    print(f"[DRIVE] ⚠️  Cannot set permissions (404) - folder access issue")
                    print(f"[DRIVE]   File uploaded but cannot make shareable")
                    # Delete the token to force re-auth on next run
                    token_file = self.google_drive_config.get('token_file', 'drive_token.json')
                    if Path(token_file).exists():
                        print(f"[DRIVE]   Deleting invalid token: {token_file}")
                        Path(token_file).unlink()
                    return {
                        'success': False,
                        'error': 'Google Drive permission denied. Token deleted. Please run ./RUN_CODE to re-authenticate with proper folder permissions.',
                        'needs_reauth': True
                    }
                else:
                    # Some other permission error, but file is uploaded
                    print(f"[DRIVE] ⚠️  Could not make file shareable: {perm_error}")
                    # Still return success since file is uploaded
            
            print(f"[DRIVE] ✓ Uploaded: {web_link}")
            
            return {
                'success': True,
                'file_id': file_id,
                'shareable_link': web_link
            }
            
        except Exception as e:
            error_str = str(e)
            # Check if this is a 404 error on the folder itself
            if '404' in error_str or 'notFound' in error_str:
                print(f"[DRIVE] ❌ Folder not found or no access (404)")
                print(f"[DRIVE]    Deleting token to force re-authentication...")
                token_file = self.google_drive_config.get('token_file', 'drive_token.json')
                if Path(token_file).exists():
                    Path(token_file).unlink()
                return {
                    'success': False,
                    'error': 'Google Drive folder access denied (404). Token deleted. Run ./RUN_CODE to re-authenticate.',
                    'needs_reauth': True
                }
            return {'success': False, 'error': f'Google Drive error: {error_str}'}
