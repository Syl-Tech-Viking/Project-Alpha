#!/usr/bin/env python3
"""
Video Uploader - Vimeo Only (v3.4 Minimal)
Uploads video to Vimeo with v3.3 embed formatting (56.25% padding)
Uses manual TUS implementation (not tuspy library)
"""

import requests
import time
from pathlib import Path
from typing import Dict, Callable, Optional

class VideoUploader:
    """Upload videos to Vimeo with progress notifications"""
    
    def __init__(self, config: Dict, progress_callback: Optional[Callable] = None):
        self.config = config
        self.vimeo_token = config.get('vimeo_token', '')
        self.progress_callback = progress_callback
    
    def upload_to_vimeo(self, video_path: Path, metadata: Dict) -> Dict:
        """Upload video to Vimeo using TUS protocol with progress tracking"""
        print(f"[UPLOAD] Starting Vimeo upload: {video_path.name}")
        
        if not self.vimeo_token:
            return {'success': False, 'error': 'Vimeo token not configured'}
        
        max_session_retries = 2
        session_attempt = 0
        last_uploaded_offset = 0
        
        while session_attempt <= max_session_retries:
            try:
                if session_attempt == 0:
                    print(f"[UPLOAD] Creating new Vimeo upload session...")
                else:
                    print(f"[UPLOAD] Re-initializing upload session (attempt {session_attempt}/{max_session_retries})...")
                
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
                    'description': metadata.get('description', '')[:2000],
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
                
                if response.status_code not in [200, 201]:
                    if session_attempt < max_session_retries:
                        print(f"[UPLOAD] Session creation failed: HTTP {response.status_code}")
                        time.sleep(10)
                        session_attempt += 1
                        continue
                    return {
                        'success': False,
                        'error': f'Vimeo API error (status {response.status_code}): {response.text[:200]}'
                    }
                
                video_data = response.json()
                
                if 'uri' not in video_data or 'upload' not in video_data:
                    if session_attempt < max_session_retries:
                        print(f"[UPLOAD] Vimeo API returned incomplete data")
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
                
                video_url = video_data.get('link', f'https://vimeo.com/{video_id}')
                player_url = video_data.get('player_embed_url', f'https://player.vimeo.com/video/{video_id}')
                
                print(f"[UPLOAD] Created Vimeo video: {video_url}")
                print(f"[UPLOAD] Starting TUS upload...")
                
                # Send 0% notification
                if self.progress_callback:
                    self.progress_callback(video_path.name, 0)
                
                # Manual TUS Upload (matching v3.3 implementation)
                try:
                    last_uploaded_offset = self._tus_upload_manual(
                        video_path, upload_link, resume_offset=last_uploaded_offset,
                        video_name=video_path.name
                    )
                    
                    print(f"[UPLOAD] Vimeo upload complete")
                    
                    # Send 100% notification
                    if self.progress_callback:
                        self.progress_callback(video_path.name, 100)
                    
                    # Create responsive embed code with 56.25% padding (v3.3 format)
                    embed_code = f'''<div style="padding:56.25% 0 0 0;position:relative;"><iframe src="{player_url}?h={video_data.get('embed', {}).get('hash', '')}&amp;title=0&amp;byline=0&amp;portrait=0&amp;badge=0&amp;autopause=0&amp;player_id=0&amp;app_id=58479" frameborder="0" allow="autoplay; fullscreen; picture-in-picture; clipboard-write; encrypted-media; web-share" referrerpolicy="strict-origin-when-cross-origin" style="position:absolute;top:0;left:0;width:100%;height:100%;" title="{metadata.get('title', video_path.stem)}"></iframe></div><script src="https://player.vimeo.com/api/player.js"></script>'''
                    
                    return {
                        'success': True,
                        'video_id': video_id,
                        'video_url': video_url,
                        'embed_code': embed_code
                    }
                    
                except Exception as tus_error:
                    error_str = str(tus_error)
                    print(f"[UPLOAD] TUS upload failed: {error_str[:200]}")
                    
                    if session_attempt < max_session_retries and (
                        'chunk failed' in error_str.lower() or 
                        'timeout' in error_str.lower() or
                        'connection' in error_str.lower()
                    ):
                        print(f"[UPLOAD] Session failure detected. Will re-initialize...")
                        session_attempt += 1
                        time.sleep(5)
                        continue
                    else:
                        raise
                
            except Exception as e:
                error_str = str(e)
                print(f"[UPLOAD] Vimeo upload error: {error_str[:200]}")
                
                if session_attempt < max_session_retries:
                    session_attempt += 1
                    time.sleep(10)
                    continue
                
                return {'success': False, 'error': f'Vimeo upload error: {error_str}'}
        
        return {'success': False, 'error': 'Max session retries exceeded'}
    
    def _tus_upload_manual(self, video_path: Path, upload_link: str, 
                            resume_offset: int = 0, video_name: str = "") -> int:
        """Manual TUS upload implementation (matching v3.3) with progress notifications"""
        file_size = video_path.stat().st_size
        chunk_size = 10 * 1024 * 1024  # 10MB chunks
        
        offset = resume_offset
        last_successful_offset = resume_offset
        last_progress_time = time.time()
        stall_threshold = 300
        max_resume_attempts = 5
        resume_attempts = 0
        start_time = time.time()
        reported_progress = int((resume_offset / file_size) * 10) - 1 if resume_offset > 0 else -1
        
        # Track notification thresholds (25%, 50%, 75%, 100%)
        notified_thresholds = set()
        if resume_offset > 0:
            # Mark thresholds already passed
            for threshold in [25, 50, 75]:
                if (resume_offset / file_size) * 100 >= threshold:
                    notified_thresholds.add(threshold)
        
        if resume_offset > 0:
            print(f"[UPLOAD] Resuming TUS upload from {resume_offset / (1024*1024):.1f} MB ({(resume_offset/file_size)*100:.1f}%)...")
        else:
            print(f"[UPLOAD] Starting TUS upload ({file_size / (1024*1024):.1f} MB)...")
        
        with open(video_path, 'rb') as f:
            f.seek(offset)
            
            while offset < file_size:
                # Check for stall
                time_without_progress = time.time() - last_progress_time
                
                if time_without_progress > stall_threshold and offset > last_successful_offset:
                    print(f"[UPLOAD] No progress for {int(time_without_progress)}s - attempting TUS resume...")
                    
                    try:
                        head_headers = {'Tus-Resumable': '1.0.0'}
                        head_resp = requests.head(upload_link, headers=head_headers, timeout=30)
                        
                        if head_resp.status_code == 200:
                            server_offset = int(head_resp.headers.get('Upload-Offset', 0))
                            
                            if server_offset > offset:
                                print(f"[UPLOAD] Resuming from server offset: {server_offset}/{file_size}")
                                offset = server_offset
                                f.seek(offset)
                                last_successful_offset = offset
                                last_progress_time = time.time()
                                resume_attempts = 0
                            elif server_offset == offset:
                                resume_attempts += 1
                                if resume_attempts >= max_resume_attempts:
                                    print(f"[UPLOAD] Upload stalled at offset {offset}")
                                    return offset
                                time.sleep(5 * resume_attempts)
                                last_progress_time = time.time()
                            else:
                                offset = server_offset
                                f.seek(offset)
                                last_successful_offset = offset
                                last_progress_time = time.time()
                        else:
                            resume_attempts += 1
                            if resume_attempts >= max_resume_attempts:
                                return offset
                            time.sleep(5 * resume_attempts)
                            
                    except Exception as e:
                        resume_attempts += 1
                        if resume_attempts >= max_resume_attempts:
                            return offset
                        time.sleep(5 * resume_attempts)
                        last_progress_time = time.time()
                
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
                            last_progress_time = time.time()
                            resume_attempts = 0
                        else:
                            print(f"[UPLOAD] Chunk failed: HTTP {response.status_code}, retrying...")
                            chunk_retries += 1
                            time.sleep(2 ** chunk_retries)
                            
                    except requests.exceptions.Timeout:
                        print(f"[UPLOAD] Chunk timeout (60s), retrying...")
                        chunk_retries += 1
                        time.sleep(2 ** chunk_retries)
                    except Exception as e:
                        print(f"[UPLOAD] Chunk error: {e}, retrying...")
                        chunk_retries += 1
                        time.sleep(2 ** chunk_retries)
                
                if not chunk_uploaded:
                    raise Exception(f'Failed to upload chunk at offset {offset} after {max_chunk_retries} retries')
                
                offset += len(chunk)
                progress = (offset / file_size) * 100
                
                # Check and send notifications at 25%, 50%, 75%, 100%
                for threshold in [25, 50, 75, 100]:
                    if threshold not in notified_thresholds and progress >= threshold:
                        if self.progress_callback:
                            self.progress_callback(video_name, threshold)
                        notified_thresholds.add(threshold)
                        break
                
                # Print progress every 10%
                current_10pct = int(progress / 10)
                if current_10pct > reported_progress:
                    elapsed = time.time() - start_time
                    speed = (offset / (1024*1024)) / elapsed if elapsed > 0 else 0
                    print(f"[UPLOAD] Progress: {progress:.1f}% ({offset/(1024*1024):.1f} MB @ {speed:.2f} MB/s)")
                    reported_progress = current_10pct
        
        print(f"[UPLOAD] TUS upload complete ({file_size / (1024*1024):.1f} MB)")
        return file_size
