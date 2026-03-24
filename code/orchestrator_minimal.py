#!/usr/bin/env python3
"""
Project Alpha v3.4 - Unified Batch Vimeo Uploader
Accumulates all videos (initial + late renders) → Sends ONE batch notification after 5min idle

NO transcription, NO Google Drive upload
"""

import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Set

sys.path.insert(0, str(Path(__file__).parent))
from state_manager import PipelineState

class BatchVimeoUploader:
    """
    Unified batch uploader - ONE notification for all videos
    
    Flow:
    1. Scan folder for all videos
    2. Process each video (wait FCP → upload → accumulate results)
    3. Wait 1 minute
    4. Check for NEW videos
    5. If found: add to SAME batch, reset 5min timer, goto step 2
    6. If no new videos for 5 minutes: 
       - Send ONE batch notification with ALL videos
       - Move ALL videos to edited folder
       - Exit
    """
    
    def __init__(self, config_path: str = "config.json"):
        self.script_dir = Path(__file__).parent
        self.config = self._load_config(config_path)
        
        # Folder paths
        self.video_input = self.script_dir.parent / 'Video_input'
        self.video_input.mkdir(parents=True, exist_ok=True)
        
        # Edited folder (external to project)
        self.edited_folder = Path("/Volumes/T7/edited")
        self.edited_folder.mkdir(exist_ok=True)
        
        # State manager
        self.state = PipelineState(self.script_dir / 'pipeline_state.json')
        
        # Track which videos have been processed (by name)
        self.processed_names: Set[str] = set()
        
        # Accumulate ALL results here (initial + late additions)
        self.all_results: List[Dict] = []
        self.all_processed_paths: List[Path] = []
        
        # Import components
        sys.path.insert(0, str(self.script_dir))
        from file_watcher import FileWatcher
        from uploader import VideoUploader
        from notifier import SlackNotifier
        
        self.watcher = FileWatcher(self.video_input)
        self.notifier = SlackNotifier(self.config)
        
        # Initialize uploader with progress callback
        self.uploader = VideoUploader(self.config, progress_callback=self._upload_progress)
        
        self.state.print_summary()
    
    def _load_config(self, path: str) -> Dict:
        """Load configuration"""
        config_file = self.script_dir / path
        if not config_file.exists():
            print(f"❌ Config file not found: {config_file}")
            sys.exit(1)
        try:
            with open(config_file) as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON in config: {e}")
            sys.exit(1)
    
    def log(self, msg: str):
        """Log with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {msg}")
        sys.stdout.flush()
    
    def _upload_progress(self, video_name: str, percent: int):
        """Send Slack notification at 25%, 50%, 75%, 100% upload progress"""
        if percent in [25, 50, 75, 100]:
            emoji = {25: "🟡", 50: "🟠", 75: "🔵", 100: "✅"}.get(percent, "📊")
            message = f"{emoji} Upload Progress: {video_name}\n   {percent}% complete"
            self.notifier.send_progress(message)
            self.log(f"📤 Slack: {video_name} - {percent}% uploaded")
    
    def get_new_videos(self) -> List[Path]:
        """Get videos that haven't been processed yet"""
        all_videos = self.watcher.scan_for_videos()
        new_videos = [v for v in all_videos if v.name not in self.processed_names]
        return new_videos
    
    def process_video(self, video_path: Path) -> Optional[Dict]:
        """Process single video: wait for complete → upload to Vimeo"""
        self.log(f"\n{'='*60}")
        self.log(f"📹 PROCESSING: {video_path.name}")
        self.log(f"{'='*60}")
        
        # Mark as processed immediately
        self.processed_names.add(video_path.name)
        
        # Check if already uploaded (from state)
        if self.state.is_video_uploaded(video_path):
            self.log(f"✓ Already uploaded to Vimeo (cached)")
            file_id = self.state.get_file_id(video_path)
            record = self.state.data['processed'].get(file_id, {})
            return {
                'name': video_path.name,
                'vimeo_url': record.get('vimeo_url'),
                'embed_code': record.get('embed_code')
            }
        
        try:
            # Wait for FCP rendering to complete
            self.log("Checking if file is complete (FCP rendering)...")
            if not self.watcher.is_file_complete(video_path):
                self.log("⏳ File still rendering, waiting...")
                watcher_result = self.watcher.wait_for_complete(video_path)
                if not watcher_result:
                    error_msg = "File stopped growing - appears stalled"
                    self.log(f"❌ {error_msg}")
                    self.state.mark_failed(video_path, error_msg)
                    return None
            
            self.log("✓ File complete")
            
            # Upload to Vimeo
            self.log("Uploading to Vimeo...")
            metadata = {
                'title': video_path.stem,
                'description': f'Uploaded by Project Alpha - {video_path.name}'
            }
            
            vimeo_result = self.uploader.upload_to_vimeo(video_path, metadata)
            
            if vimeo_result.get('success'):
                vimeo_url = vimeo_result.get('video_url')
                embed_code = vimeo_result.get('embed_code')
                self.log(f"✓ Vimeo upload complete: {vimeo_url}")
                
                # Save to state
                self.state.mark_video_uploaded(video_path, vimeo_result)
                
                return {
                    'name': video_path.name,
                    'vimeo_url': vimeo_url,
                    'embed_code': embed_code
                }
            else:
                error = vimeo_result.get('error', 'Unknown error')
                self.log(f"❌ Vimeo upload failed: {error}")
                self.state.mark_failed(video_path, f"Vimeo upload failed: {error}")
                return None
                
        except Exception as e:
            error_msg = f"Processing error: {str(e)}"
            self.log(f"❌ {error_msg}")
            self.state.mark_failed(video_path, error_msg)
            return None
    
    def process_videos(self, videos: List[Path]):
        """Process videos and accumulate results (no notification yet)"""
        for i, video_path in enumerate(videos, 1):
            self.log(f"\n🎬 Video {i} of {len(videos)} in current batch")
            result = self.process_video(video_path)
            if result:
                self.all_results.append(result)
                self.all_processed_paths.append(video_path)
            
            # Brief pause between uploads
            if i < len(videos):
                time.sleep(2)
    
    def finalize_batch(self):
        """Send ONE notification and move ALL videos after idle timeout"""
        if self.all_results:
            self.log(f"\n{'='*60}")
            self.log(f"📤 SENDING FINAL BATCH NOTIFICATION")
            self.log(f"   Total videos: {len(self.all_results)}")
            self.log(f"{'='*60}")
            self.notifier.send_batch(self.all_results)
            
            # Summary
            self.log(f"\n{'='*60}")
            self.log(f"✅ COMPLETE BATCH SUMMARY")
            self.log(f"   Total successful: {len(self.all_results)}")
            self.log(f"   Total processed: {len(self.all_processed_paths)}")
            self.log(f"{'='*60}")
            
            # Move ALL processed videos to edited folder
            self._move_all_to_edited()
        else:
            self.log("\n⚠️  No videos were successfully processed")
    
    def _move_all_to_edited(self):
        """Move ALL processed videos to edited folder"""
        self.log(f"\n📁 Moving {len(self.all_processed_paths)} videos to edited folder...")
        for video_path in self.all_processed_paths:
            try:
                dest = self.edited_folder / video_path.name
                video_path.rename(dest)
                self.log(f"   ✓ Moved {video_path.name}")
            except Exception as e:
                self.log(f"   ⚠️  Could not move {video_path.name}: {e}")
    
    def run(self):
        """Main loop - accumulate all videos, one notification at end"""
        print("="*60)
        print("Project Alpha v3.4 - Unified Batch Vimeo Uploader")
        print("="*60)
        print()
        
        idle_timeout_seconds = 300  # 5 minutes
        check_interval_seconds = 60  # 1 minute
        last_video_time = time.time()
        
        self.log(f"🔍 Starting unified batch uploader...")
        self.log(f"   Will accumulate ALL videos (initial + late renders)")
        self.log(f"   Will check for new videos every {check_interval_seconds}s")
        self.log(f"   Will send ONE notification after {idle_timeout_seconds}s idle")
        self.log("")
        
        while True:
            # Check for new videos
            new_videos = self.get_new_videos()
            
            if new_videos:
                # Reset idle timer
                last_video_time = time.time()
                
                self.log(f"📁 Found {len(new_videos)} video(s) - adding to batch")
                self.process_videos(new_videos)
                
                # Wait 1 minute, then check again
                self.log(f"\n⏳ Waiting {check_interval_seconds}s before checking for more videos...")
                time.sleep(check_interval_seconds)
                
            else:
                # No new videos - check if we've been idle too long
                idle_time = time.time() - last_video_time
                remaining = idle_timeout_seconds - idle_time
                
                if idle_time >= idle_timeout_seconds:
                    # 5 minutes idle - finalize and exit
                    self.log(f"\n✅ No new videos for {idle_timeout_seconds}s - finalizing batch...")
                    self.finalize_batch()
                    break
                
                self.log(f"⏳ No new videos. Idle for {int(idle_time)}s. Will finalize in {int(remaining)}s...")
                time.sleep(check_interval_seconds)

def main():
    """Main entry point"""
    orchestrator = BatchVimeoUploader()
    orchestrator.run()
    print("\n✓ Done")

if __name__ == "__main__":
    main()
