#!/usr/bin/env python3
"""
Project Alpha v3.2 - Clean Production Video Pipeline
Auto-installing dependencies, corrected Whisper monitoring, session resilience

Features:
- Auto-install: Dependencies install without prompts
- Smart monitoring: Correctly detects Whisper completion (not file size based)
- Session resilience: Survives internet outages with exponential backoff
- Dual timers: 10-min batch + 2-hour session timeouts
"""

import os
import sys
import json
import subprocess
import time
import queue
import threading
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Set, Optional, Tuple
import concurrent.futures

# Import state manager and session resilience
sys.path.insert(0, str(Path(__file__).parent))
from state_manager import PipelineState
from session_resilience import SessionResilience

class AutonomousOrchestrator:
    """
    Autonomous video pipeline with:
    - State persistence (survives restarts)
    - Smart retry (avoids duplicate work)
    - Partial success handling (video uploaded but transcript failed)
    - End-of-batch retry (3 immediate + final retry)
    - Disk space monitoring
    - Slack notifications for all outcomes
    - SESSION INDEPENDENCE: Survives internet outages with exponential backoff
    """
    
    def __init__(self, config_path: str = "config.json"):
        self.script_dir = Path(__file__).parent
        self.config = self._load_config(config_path)
        
        # Folder paths - all relative to code directory
        self.video_input = self.script_dir.parent / 'Video_input'  # ../Video_input
        self.edited = self.script_dir.parent.parent / 'edited'  # ../../edited
        self.transcripts = self.script_dir.parent.parent / 'Transcripts'  # ../../Transcripts
        self.failed = self.script_dir.parent / 'failed'  # ../failed (outside code folder)
        
        # Create folders
        for folder in [self.video_input, self.edited, self.transcripts, self.failed]:
            folder.mkdir(parents=True, exist_ok=True)
        
        # Initialize state manager
        self.state = PipelineState(self.script_dir / 'pipeline_state.json')
        
        # Initialize session resilience
        self.session = SessionResilience(log_func=self.log)
        
        # Tracking
        self.processed_videos: List[Dict] = []
        self.current_batch: List[Dict] = []
        self.running = False
        
        # Dual timer system:
        # - batch_timeout: Time since last video before sending batch notification (default 10 min)
        # - session_timeout: Total time with no activity before stopping (default 2 hours)
        daemon_config = self.config.get('daemon', {})
        self.batch_timeout_minutes = daemon_config.get('batch_timeout_minutes', 10)
        self.session_timeout_minutes = daemon_config.get('session_timeout_minutes', 120)
        
        # Track activity timers
        self.last_activity = time.time()  # For session timeout (any activity)
        self.last_video_completion = time.time()  # For batch timeout (video processing)
        
        # Import components
        sys.path.insert(0, str(self.script_dir))
        from file_watcher import FileWatcher
        from transcriber import VideoTranscriber
        from uploader import VideoUploader
        from notifier import SlackNotifier
        
        self.watcher = FileWatcher(self.video_input)
        self.transcriber = VideoTranscriber(self.config)
        self.uploader = VideoUploader(self.config)
        self.notifier = SlackNotifier(self.config)
        
        # Print initial state
        self.state.print_summary()
        self.log("🌐 Session resilience enabled: Will survive internet outages with exponential backoff")
    
    def _load_config(self, path: str) -> Dict:
        """Load configuration with error handling"""
        config_file = self.script_dir / path
        if not config_file.exists():
            self.log(f"❌ Config file not found: {config_file}")
            sys.exit(1)
        try:
            with open(config_file) as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            self.log(f"❌ Invalid JSON in config: {e}")
            sys.exit(1)
    
    def log(self, msg: str):
        """Log with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {msg}")
        sys.stdout.flush()
    
    def check_disk_space(self, video_path: Path) -> bool:
        """Check if there's enough disk space for processing"""
        try:
            stat = video_path.statvfs() if hasattr(video_path, 'statvfs') else os.statvfs(str(video_path.parent))
            available = stat.f_bavail * stat.f_frsize
            required = video_path.stat().st_size * 3  # 3x for temp files, transcript, safety
            
            available_gb = available / (1024**3)
            required_gb = required / (1024**3)
            
            if available < required:
                self.log(f"❌ Insufficient disk space: {available_gb:.2f}GB available, {required_gb:.2f}GB required")
                self.notifier.send_progress(f"⚠️ DISK SPACE LOW: {available_gb:.1f}GB available. Processing paused.")
                return False
            
            return True
        except Exception as e:
            self.log(f"⚠️ Could not check disk space: {e}")
            return True  # Continue anyway, will fail naturally if really out of space
    
    def process_video(self, video_path: Path, is_retry: bool = False) -> Optional[Dict]:
        """
        Process single video with intelligent retry logic
        
        Smart reprocessing:
        - If video already uploaded: skip upload, do transcript
        - If transcript already uploaded: skip both
        - If partial: fill in what's missing
        """
        self.log(f"{'='*60}")
        if is_retry:
            self.log(f"RETRY PROCESSING: {video_path.name}")
        else:
            self.log(f"PROCESSING: {video_path.name}")
        self.log(f"{'='*60}")
        
        # Check disk space first
        if not self.check_disk_space(video_path):
            return None
        
        # Check if already fully processed
        if self.state.is_fully_processed(video_path):
            self.log(f"✓ Already fully processed (video + transcript)")
            return None
        
        # Get saved transcript path if exists
        saved_transcript_path = self.state.get_transcript_path(video_path)
        
        # Track what we accomplished
        video_uploaded = False
        transcript_uploaded = False
        drive_link = None
        vimeo_url = None
        embed_code = None
        transcript_text = ""
        
        try:
            # Step 1: Wait for file to be complete (FCP rendering) - PROGRESS BASED
            self.log("[1/5] Checking if file is complete...")
            if not self.watcher.is_file_complete(video_path):
                self.log("⏳ File still rendering, waiting indefinitely...")
                watcher_result = self.watcher.wait_for_complete(video_path)
                if not watcher_result:
                    error_msg = "File stopped growing - appears stalled"
                    self.log(f"❌ {error_msg}")
                    self.state.mark_failed(video_path, error_msg)
                    self.notifier.send_error(video_path.name, error_msg)
                    self._move_to_failed(video_path)
                    return None
            
            self.log("✓ File complete")
            
            # Step 2: Transcription (NON-FATAL - continues even if fails)
            transcript_result = None
            if not self.state.is_transcript_uploaded(video_path):
                self.log("[2/5] Transcribing with Whisper (with retry)...")
                # 🔔 SLACK: Transcription started
                self.notifier.send_progress(f"🎤 Transcription started: {video_path.name}\n⏳ This may take 5-15 minutes...")
                transcript_result = self._transcribe_with_retry(video_path, self.transcripts)
                
                if transcript_result.get('status') == 'success':
                    transcript_text = transcript_result.get('text', '')
                    self.log(f"✓ Transcription complete ({len(transcript_text)} chars)")
                    # 🔔 SLACK: Transcription success
                    self.notifier.send_progress(f"✅ Transcription complete: {video_path.name}\n📝 {len(transcript_text)} characters captured")
                else:
                    error = transcript_result.get('error', 'Unknown error')
                    self.log(f"⚠️ Transcription failed: {error}")
                    self.log("   Continuing with video upload (transcript will be empty)")
                    transcript_text = "[Transcription failed - video uploaded without transcript]"
                    # 🔔 SLACK: Transcription failed
                    self.notifier.send_progress(f"⚠️ Transcription failed: {video_path.name}\n❌ Error: {error[:100]}\n🎬 Continuing with video upload only...")
                    # Mark partial - video can still proceed
                    self.state.mark_partial(video_path, False, False, error, None)
            else:
                self.log("[2/5] ✓ Transcript already processed")
                # Load existing transcript text for metadata
                if saved_transcript_path and saved_transcript_path.exists():
                    transcript_text = saved_transcript_path.read_text()
                transcript_uploaded = True
            
            # Step 3: Upload to Vimeo (with retry) - NON-FATAL if fails
            if not self.state.is_video_uploaded(video_path):
                self.log("[3/5] Uploading to Vimeo (with retry)...")
                # 🔔 SLACK: Vimeo upload started
                file_size_mb = video_path.stat().st_size / (1024*1024)
                self.notifier.send_progress(f"📤 Vimeo upload started: {video_path.name}\n📊 File size: {file_size_mb:.1f} MB\n⏳ Uploading...")
                vimeo_result = self._upload_with_retry(video_path, {
                    'title': video_path.stem,
                    'description': transcript_text[:100] + '...' if len(transcript_text) > 100 else transcript_text
                })
                
                if vimeo_result.get('success'):
                    video_uploaded = True
                    vimeo_url = vimeo_result.get('video_url')
                    embed_code = vimeo_result.get('embed_code')
                    self.log(f"✓ Vimeo upload complete: {vimeo_url}")
                    # 🔔 SLACK: Vimeo upload success
                    self.notifier.send_progress(f"✅ Vimeo upload complete: {video_path.name}\n🔗 {vimeo_url}")
                    self.state.mark_video_uploaded(video_path, vimeo_result)
                else:
                    error = vimeo_result.get('error', 'Unknown error')
                    self.log(f"❌ Vimeo upload failed after retries: {error}")
                    # 🔔 SLACK: Vimeo upload failed
                    self.notifier.send_error(video_path.name, f"Vimeo upload failed: {error}")
                    # This is more critical - video is the main goal
                    self.state.mark_failed(video_path, f"Vimeo upload failed: {error}")
                    self._move_to_failed(video_path)
                    return None
            else:
                self.log("[3/5] ✓ Video already uploaded")
                video_uploaded = True
                # Get saved URL from state
                file_id = self.state.get_file_id(video_path)
                if file_id in self.state.data['processed']:
                    vimeo_url = self.state.data['processed'][file_id].get('vimeo_url')
                    embed_code = self.state.data['processed'][file_id].get('embed_code', '')
            
            # Step 4: Upload transcript to Google Drive (with retry) - NON-FATAL
            if not transcript_uploaded and transcript_result and transcript_result.get('status') == 'success':
                self.log("[4/5] Uploading transcript to Google Drive (with retry)...")
                # 🔔 SLACK: Drive upload started
                self.notifier.send_progress(f"📤 Google Drive upload started: {video_path.name}\n📝 Uploading transcript...")
                txt_file = Path(transcript_result.get('text_path'))
                
                if txt_file.exists():
                    drive_result = self._upload_drive_with_retry(txt_file, video_path.name)
                    
                    if drive_result.get('success'):
                        transcript_uploaded = True
                        drive_link = drive_result.get('shareable_link')
                        self.log(f"✓ Transcript uploaded: {drive_link}")
                        # 🔔 SLACK: Drive upload success
                        self.notifier.send_progress(f"✅ Google Drive upload complete: {video_path.name}\n🔗 {drive_link}")
                        self.state.mark_transcript_uploaded(video_path, drive_result)
                    else:
                        error = drive_result.get('error', 'Unknown error')
                        self.log(f"⚠️ Drive upload failed: {error}")
                        
                        # 🔔 SLACK: Drive upload failed
                        self.notifier.send_progress(f"⚠️ Google Drive upload failed: {video_path.name}\n❌ Error: {error[:100]}\n📝 Transcript saved locally")
                        
                        # CRITICAL: Check if re-authentication is needed
                        if drive_result.get('needs_reauth'):
                            self.log(f"🚨 CRITICAL: Google Drive authentication invalid")
                            self.log(f"   Token has been deleted. You MUST re-authenticate.")
                            self.log(f"")
                            self.log(f"   TO FIX:")
                            self.log(f"   1. Stop this script (Ctrl+C)")
                            self.log(f"   2. Run: ./RUN_CODE")
                            self.log(f"   3. When prompted, authenticate Google Drive")
                            self.log(f"")
                            # 🔔 SLACK: Critical auth failure
                            self.notifier.send_error(video_path.name, "Google Drive auth failed. Token deleted. Run ./RUN_CODE to re-authenticate.")
                            # Stop processing to force user to re-auth
                            self.running = False
                            return None
                        
                        # Mark partial success
                        self.state.mark_partial(
                            video_path, 
                            video_uploaded, 
                            False, 
                            f"Drive failed: {error}",
                            str(txt_file)
                        )
                else:
                    self.log(f"⚠️ Transcript file not found: {txt_file}")
            else:
                if transcript_uploaded:
                    self.log("[4/5] ✓ Transcript already uploaded")
                else:
                    self.log("[4/5] ⚠️ Skipping Drive upload (transcription failed)")
            
            # Step 5: Move to edited folder
            self.log("[5/5] Moving to edited folder...")
            edited_path = self.edited / video_path.name
            
            # Handle name collisions
            if edited_path.exists():
                timestamp = int(time.time())
                edited_path = self.edited / f"{video_path.stem}_{timestamp}{video_path.suffix}"
            
            # CRITICAL FIX: Clear from retry queue BEFORE moving file
            # (state manager needs to read file stats which won't work after move)
            self.state.clear_from_retry(video_path)
            
            video_path.rename(edited_path)
            self.log(f"✓ Moved to: {edited_path}")
            
            # Track result
            result = {
                'name': video_path.name,
                'vimeo_url': vimeo_url,
                'embed_code': embed_code,
                'drive_link': drive_link,
                'transcript_status': 'success' if transcript_uploaded else 'failed',
                'video_uploaded': video_uploaded,
                'transcript_uploaded': transcript_uploaded
            }
            
            self.current_batch.append(result)
            self.last_activity = time.time()
            self.last_video_completion = time.time()  # Reset batch timer
            
            # Send success notification
            if video_uploaded:
                self.log(f"✅ COMPLETE: {video_path.name}")
                # 🔔 SLACK: Video complete summary
                if transcript_uploaded:
                    self.notifier.send_progress(f"✅ FULLY COMPLETE: {video_path.name}\n🎬 Video: {vimeo_url}\n📝 Transcript: {drive_link}\n✓ All steps successful")
                else:
                    self.notifier.send_progress(f"⚠️ PARTIAL COMPLETE: {video_path.name}\n🎬 Video: {vimeo_url}\n❌ Transcript failed (saved locally)")
                return result
            
        except Exception as e:
            error_msg = str(e)
            self.log(f"❌ CRITICAL ERROR processing {video_path.name}: {error_msg}")
            import traceback
            traceback.print_exc()
            
            # CRITICAL FIX: Check if file still exists before marking failed
            # (it might have been moved to edited or failed folder already)
            if video_path.exists():
                # Mark as failed only if file is still in original location
                self.state.mark_failed(video_path, error_msg)
                # Move to failed folder
                self._move_to_failed(video_path)
            else:
                self.log(f"⚠️  Video file no longer at original path, failure recorded in state")
            
            # Notify (always, regardless of file location)
            self.notifier.send_error(video_path.name, f"Critical error: {error_msg}")
            
            return None
    
    def _transcribe_with_retry(self, video_path: Path, output_dir: Path) -> Dict:
        """Transcribe with 3 immediate retries"""
        max_attempts = 3
        
        for attempt in range(max_attempts):
            result = self.transcriber.transcribe(video_path, output_dir)
            
            if result.get('status') == 'success':
                return result
            
            error = result.get('error', 'Unknown error')
            
            if attempt < max_attempts - 1:
                wait_time = 10 * (attempt + 1)  # 10s, 20s, 30s
                self.log(f"⚠️ Transcription attempt {attempt + 1} failed: {error}")
                self.log(f"   Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                self.log(f"❌ Transcription failed after {max_attempts} attempts: {error}")
        
        return result
    
    def _upload_with_retry(self, video_path: Path, metadata: Dict) -> Dict:
        """Upload to Vimeo with 3 immediate retries"""
        max_attempts = 3
        
        for attempt in range(max_attempts):
            try:
                result = self.uploader.upload_to_vimeo(video_path, metadata)
                
                if result.get('success'):
                    return result
                
                error = result.get('error', 'Unknown error')
                
                # Check if retryable
                if attempt < max_attempts - 1 and ('timeout' in error.lower() or '500' in error or '503' in error):
                    wait_time = 10 * (attempt + 1)
                    self.log(f"⚠️ Vimeo upload attempt {attempt + 1} failed: {error}")
                    self.log(f"   Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    return result
                    
            except Exception as e:
                if attempt < max_attempts - 1:
                    wait_time = 10 * (attempt + 1)
                    self.log(f"⚠️ Upload attempt {attempt + 1} exception: {e}")
                    self.log(f"   Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    return {'success': False, 'error': str(e)}
        
        return result
    
    def _upload_drive_with_retry(self, transcript_path: Path, video_name: str) -> Dict:
        """Upload to Google Drive with 3 immediate retries"""
        max_attempts = 3
        
        for attempt in range(max_attempts):
            result = self.uploader.upload_to_drive(transcript_path, video_name)
            
            if result.get('success'):
                return result
            
            error = result.get('error', 'Unknown error')
            
            if attempt < max_attempts - 1:
                wait_time = 10 * (attempt + 1)
                self.log(f"⚠️ Drive upload attempt {attempt + 1} failed: {error}")
                self.log(f"   Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                self.log(f"❌ Drive upload failed after {max_attempts} attempts: {error}")
        
        return result
    
    def _move_to_failed(self, video_path: Path):
        """Move failed video to holding folder"""
        try:
            failed_path = self.failed / video_path.name
            
            # Handle name collisions
            if failed_path.exists():
                timestamp = int(time.time())
                failed_path = self.failed / f"{video_path.stem}_{timestamp}{video_path.suffix}"
            
            video_path.rename(failed_path)
            self.log(f"📁 Moved failed video to: {failed_path}")
            
            # Create error log
            error_log = failed_path.with_suffix('.error.log')
            file_id = self.state.get_file_id(video_path)
            if file_id in self.state.data['failed']:
                error_info = self.state.data['failed'][file_id]
                error_log.write_text(json.dumps(error_info, indent=2))
        except Exception as e:
            self.log(f"⚠️ Could not move to failed folder: {e}")
    
    def _process_retry_queue(self):
        """Process videos in retry queue (end-of-batch retry)"""
        retry_queue = self.state.get_retry_queue()
        
        if not retry_queue:
            return
        
        self.log(f"\n{'='*60}")
        self.log(f"END-OF-BATCH RETRY: {len(retry_queue)} video(s)")
        self.log(f"{'='*60}")
        
        for file_id in retry_queue:
            # Get video info from state
            video_path = None
            
            if file_id in self.state.data['partial']:
                video_path = Path(self.state.data['partial'][file_id]['video_path'])
            elif file_id in self.state.data['failed']:
                video_path = Path(self.state.data['failed'][file_id]['video_path'])
            
            if video_path and video_path.exists():
                self.log(f"\nRetrying: {video_path.name}")
                self.state.reset_failed(video_path)  # Reset failure count
                self.process_video(video_path, is_retry=True)
            elif video_path:
                self.log(f"⚠️ Video no longer exists: {video_path}")
        
        self.log(f"{'='*60}")
        self.log("End-of-batch retry complete")
        self.log(f"{'='*60}\n")
    
    def batch_process(self):
        """Process all videos with end-of-batch retry"""
        self.log("🎬 BATCH MODE - Processing all existing videos")
        
        # First, process failed videos in holding folder
        failed_videos = list(self.failed.glob('*.mov')) + list(self.failed.glob('*.mp4'))
        if failed_videos:
            self.log(f"📁 Found {len(failed_videos)} failed video(s) to retry")
            for video_path in failed_videos:
                # Move back to input folder
                input_path = self.video_input / video_path.name
                try:
                    video_path.rename(input_path)
                    self.log(f"   Moved {video_path.name} back to input folder")
                except:
                    pass
        
        # Now process all videos
        videos = self.watcher.scan_for_videos()
        
        if not videos:
            self.log("No videos found in input folder")
            return
        
        self.log(f"Found {len(videos)} video(s)")
        
        for video_path in videos:
            self.process_video(video_path)
            time.sleep(2)  # Small delay between videos
        
        # End-of-batch retry
        self._process_retry_queue()
        
        self.log(f"\n{'='*60}")
        self.log(f"BATCH COMPLETE")
        self.state.print_summary()
        self.log(f"{'='*60}")
        
        # Send batch notification
        if self.current_batch:
            self.notifier.send_batch(self.current_batch)
    
    def watch_mode(self):
        """
        DUAL TIMER WATCH MODE
        
        Batch Timer (10 min default):
        - After processing a video, wait 10 minutes
        - If no new videos in 10 min → send batch notification → clear batch → continue watching
        - If new videos arrive → reset batch timer
        
        Session Timer (2 hours default):
        - If NO videos processed for 2 hours total → stop completely
        - This prevents infinite running when no work is coming
        """
        self.log("👁️  DUAL TIMER WATCH MODE")
        self.log(f"   Batch notification after: {self.batch_timeout_minutes} minutes of inactivity")
        self.log(f"   Session timeout after: {self.session_timeout_minutes} minutes of total inactivity")
        self.log(f"   Press Ctrl+C to stop manually")
        self.log(f"{'='*60}")
        
        self.running = True
        self.last_activity = time.time()
        self.last_video_completion = time.time()
        
        # First, move any failed videos back for retry
        failed_videos = list(self.failed.glob('*.mov')) + list(self.failed.glob('*.mp4'))
        for video_path in failed_videos:
            input_path = self.video_input / video_path.name
            try:
                video_path.rename(input_path)
                self.log(f"📁 Moved failed video back to input: {video_path.name}")
            except:
                pass
        
        # Process existing videos
        existing = self.watcher.scan_for_videos()
        if existing:
            self.log(f"Found {len(existing)} existing video(s), processing first...")
            for video in existing:
                result = self.process_video(video)
                if result:
                    self.last_video_completion = time.time()
            self.log(f"✓ Processed {len(self.current_batch)} video(s), starting batch timer...")
        
        batch_sent = False  # Track if we just sent a batch
        
        # Watch for new videos
        while self.running:
            try:
                # Check for new videos
                new_videos = self.watcher.scan_for_videos()
                new_videos_found = False
                
                for video_path in new_videos:
                    file_id = self.state.get_file_id(video_path)
                    # Skip if fully processed
                    if not self.state.is_fully_processed(video_path):
                        self.log(f"📹 New video detected: {video_path.name}")
                        # 🔔 SLACK: New video discovered
                        self.notifier.send_progress(f"🎬 New video detected: {video_path.name}\n⏳ Beginning processing...")
                        result = self.process_video(video_path)
                        if result:
                            new_videos_found = True
                            batch_sent = False  # Reset batch sent flag
                            self.last_video_completion = time.time()
                            self.last_activity = time.time()
                
                # Calculate timers
                batch_idle_seconds = time.time() - self.last_video_completion
                batch_idle_minutes = batch_idle_seconds / 60
                session_idle_seconds = time.time() - self.last_activity
                session_idle_minutes = session_idle_seconds / 60
                
                # BATCH TIMER: Send notification after batch_timeout_minutes
                if self.current_batch and not batch_sent and batch_idle_minutes >= self.batch_timeout_minutes:
                    self.log(f"\n{'='*60}")
                    self.log(f"📦 BATCH COMPLETE - No new videos for {self.batch_timeout_minutes} minutes")
                    self.log(f"   Sending batch notification for {len(self.current_batch)} video(s)...")
                    self.log(f"{'='*60}\n")
                    
                    # Perform end-of-batch retry first
                    self._process_retry_queue()
                    
                    # Send batch notification
                    self.notifier.send_batch(self.current_batch)
                    
                    # Clear the batch and reset timer
                    self.current_batch = []
                    batch_sent = True
                    self.last_video_completion = time.time()
                    
                    self.log(f"✓ Batch notification sent")
                    self.log(f"🔄 Continuing to monitor for next batch...")
                    self.log(f"   (Will stop if no activity for {self.session_timeout_minutes} minutes total)")
                    self.log(f"{'='*60}\n")
                
                # SESSION TIMER: Stop after session_timeout_minutes of total inactivity
                if session_idle_minutes >= self.session_timeout_minutes:
                    self.log(f"\n{'='*60}")
                    self.log(f"⏰ SESSION TIMEOUT - No videos for {self.session_timeout_minutes} minutes total")
                    
                    # Send any pending batch first
                    if self.current_batch:
                        self.log(f"📤 Sending final batch notification for {len(self.current_batch)} video(s)...")
                        self._process_retry_queue()
                        self.notifier.send_batch(self.current_batch)
                    
                    self.log(f"✅ Watch mode complete. Stopping after 2 hours of inactivity.")
                    self.log(f"{'='*60}\n")
                    self.running = False
                    break
                
                # Progress updates
                if int(batch_idle_seconds) % 60 == 0 and self.current_batch and not batch_sent:
                    remaining_batch = self.batch_timeout_minutes - batch_idle_minutes
                    if remaining_batch <= 2 and remaining_batch > 0:
                        self.log(f"⏳ Batch notification in {remaining_batch:.1f}min if no new videos...")
                
                if int(session_idle_seconds) % 300 == 0:  # Every 5 minutes for session
                    remaining_session = self.session_timeout_minutes - session_idle_minutes
                    if remaining_session <= 10 and remaining_session > 0:
                        self.log(f"⏰ Session timeout in {remaining_session:.1f}min if no new videos...")
                
                time.sleep(5)
                
            except KeyboardInterrupt:
                self.log("\n🛑 Stopping watcher...")
                self.running = False
                break
            except Exception as e:
                self.log(f"⚠️ Error in watch loop: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(5)
        
        # Final cleanup
        self.log(f"\n{'='*60}")
        self.log("👋 Watch mode ended")
        
        # Final retry and notification
        self._process_retry_queue()
        
        if self.current_batch:
            self.log(f"📤 Sending final batch notification for {len(self.current_batch)} video(s)...")
            self.notifier.send_batch(self.current_batch)
        
        self.state.print_summary()
        self.session.print_summary()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Project Alpha v3.0 - Autonomous Video Pipeline')
    parser.add_argument('--mode', choices=['batch', 'watch'], default='batch',
                       help='Operation mode: batch (process all) or watch (monitor + batch)')
    parser.add_argument('--retry-failed', action='store_true',
                       help='Immediately retry all failed/partial videos')
    
    args = parser.parse_args()
    
    orchestrator = AutonomousOrchestrator()
    
    if args.retry_failed:
        orchestrator._process_retry_queue()
    elif args.mode == 'batch':
        orchestrator.batch_process()
    else:
        orchestrator.watch_mode()


if __name__ == "__main__":
    main()
