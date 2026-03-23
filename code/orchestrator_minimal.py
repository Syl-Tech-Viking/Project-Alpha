#!/usr/bin/env python3
"""
Project Alpha v3.4 - One-Shot Batch Vimeo Uploader
Scans folder → Processes ALL videos → Sends batch Slack notification → Exits

NO transcription, NO Google Drive upload, NO continuous watching
"""

import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))
from state_manager import PipelineState

class BatchVimeoUploader:
    """
    One-shot batch uploader for Vimeo
    
    Flow:
    1. Scan folder for all videos
    2. Wait for FCP rendering to complete on each
    3. Upload all to Vimeo with v3.3 embed formatting
    4. Send ONE batch Slack notification with ALL embed codes
    5. Exit
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
    
    def process_video(self, video_path: Path, index: int, total: int) -> Optional[Dict]:
        """Process single video: wait for complete → upload to Vimeo"""
        self.log(f"\n{'='*60}")
        self.log(f"[{index}/{total}] PROCESSING: {video_path.name}")
        self.log(f"{'='*60}")
        
        # Check if already uploaded
        if self.state.is_video_uploaded(video_path):
            self.log(f"✓ Already uploaded to Vimeo")
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
    
    def run(self):
        """Run one-shot batch processing"""
        print("="*60)
        print("Project Alpha v3.4 - Batch Vimeo Uploader")
        print("="*60)
        print()
        
        self.log(f"🔍 Scanning for videos in: {self.video_input}")
        
        # Get ALL videos in folder
        videos = self.watcher.scan_for_videos()
        
        if len(videos) == 0:
            self.log("⚠️  No videos found in input folder")
            self.log("   Exiting...")
            return
        
        self.log(f"📁 Found {len(videos)} video(s) to process")
        
        # Process ALL videos in order
        processed_results = []
        failed_videos = []
        
        for i, video_path in enumerate(videos, 1):
            result = self.process_video(video_path, i, len(videos))
            if result:
                processed_results.append(result)
            else:
                failed_videos.append(video_path.name)
            
            # Brief pause between uploads
            if i < len(videos):
                time.sleep(2)
        
        # Send batch notification with ALL results
        if processed_results:
            self.log(f"\n{'='*60}")
            self.log(f"📤 SENDING BATCH NOTIFICATION")
            self.log(f"   {len(processed_results)} video(s) successful")
            self.log(f"{'='*60}")
            self.notifier.send_batch(processed_results)
        
        # Summary
        self.log(f"\n{'='*60}")
        self.log(f"✓ BATCH COMPLETE")
        self.log(f"   Successful: {len(processed_results)}/{len(videos)}")
        if failed_videos:
            self.log(f"   Failed: {len(failed_videos)}")
            for name in failed_videos:
                self.log(f"      - {name}")
        self.log(f"{'='*60}")
        
        # Move processed videos to edited folder on T7
        self._move_to_edited(videos)
    
    def _move_to_edited(self, videos: List[Path]):
        """Move processed videos to edited folder on T7 root"""
        edited_folder = Path("/Volumes/T7/edited")
        edited_folder.mkdir(exist_ok=True)
        
        for video_path in videos:
            try:
                dest = edited_folder / video_path.name
                video_path.rename(dest)
                self.log(f"   Moved {video_path.name} to /Volumes/T7/edited/")
            except Exception as e:
                self.log(f"   ⚠️  Could not move {video_path.name}: {e}")

def main():
    """Main entry point"""
    orchestrator = BatchVimeoUploader()
    orchestrator.run()
    print("\n✓ Done")

if __name__ == "__main__":
    main()
