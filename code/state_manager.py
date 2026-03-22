#!/usr/bin/env python3
"""
State Manager for Project Alpha - Autonomous Video Pipeline
Tracks processing state, failures, and partial successes for recovery
"""

import json
import time
from pathlib import Path
from typing import Dict, Optional, Set
from datetime import datetime

class PipelineState:
    """
    Persistent state management for autonomous operation
    
    Tracks:
    - Successfully processed videos (skip on restart)
    - Failed videos (retry queue)
    - Partial successes (video uploaded but transcript failed, etc.)
    - Retry history
    """
    
    def __init__(self, state_file: Path):
        self.state_file = Path(state_file)
        self.data = self._load_state()
    
    def _load_state(self) -> Dict:
        """Load state from disk or create empty state"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[STATE] ⚠️ Could not load state file: {e}")
                return self._empty_state()
        return self._empty_state()
    
    def _empty_state(self) -> Dict:
        """Return empty state structure"""
        return {
            'processed': {},  # file_id -> {video_uploaded, transcript_uploaded, timestamp}
            'failed': {},     # file_id -> {error, attempts, last_try, video_path}
            'partial': {},    # file_id -> {video_done, transcript_done, error}
            'retry_queue': [],  # List of file_ids to retry
            'version': '3.0-autonomous',
            'last_updated': None
        }
    
    def save(self):
        """Persist state to disk"""
        try:
            self.data['last_updated'] = datetime.now().isoformat()
            # Write to temp file first, then rename (atomic)
            temp_file = self.state_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(self.data, f, indent=2)
            temp_file.rename(self.state_file)
        except Exception as e:
            print(f"[STATE] ⚠️ Could not save state: {e}")
    
    def get_file_id(self, video_path: Path) -> str:
        """Generate unique file ID from path and modification time"""
        return f"{video_path.name}_{video_path.stat().st_mtime}"
    
    def is_fully_processed(self, video_path: Path) -> bool:
        """Check if video was completely processed (both video and transcript)"""
        file_id = self.get_file_id(video_path)
        if file_id in self.data['processed']:
            record = self.data['processed'][file_id]
            return record.get('video_uploaded') and record.get('transcript_uploaded')
        return False
    
    def is_video_uploaded(self, video_path: Path) -> bool:
        """Check if video was uploaded to Vimeo"""
        file_id = self.get_file_id(video_path)
        if file_id in self.data['processed']:
            return self.data['processed'][file_id].get('video_uploaded', False)
        if file_id in self.data['partial']:
            return self.data['partial'][file_id].get('video_done', False)
        return False
    
    def is_transcript_uploaded(self, video_path: Path) -> bool:
        """Check if transcript was uploaded to Drive"""
        file_id = self.get_file_id(video_path)
        if file_id in self.data['processed']:
            return self.data['processed'][file_id].get('transcript_uploaded', False)
        if file_id in self.data['partial']:
            return self.data['partial'][file_id].get('transcript_done', False)
        return False
    
    def get_transcript_path(self, video_path: Path) -> Optional[Path]:
        """Get saved transcript path for video"""
        file_id = self.get_file_id(video_path)
        if file_id in self.data['processed']:
            return Path(self.data['processed'][file_id].get('transcript_path'))
        if file_id in self.data['partial']:
            return Path(self.data['partial'][file_id].get('transcript_path'))
        return None
    
    def mark_video_uploaded(self, video_path: Path, vimeo_data: Dict):
        """Mark that video was successfully uploaded"""
        file_id = self.get_file_id(video_path)
        
        # Update existing record or create new
        if file_id not in self.data['processed']:
            self.data['processed'][file_id] = {}
        
        self.data['processed'][file_id].update({
            'video_uploaded': True,
            'vimeo_url': vimeo_data.get('video_url'),
            'vimeo_id': vimeo_data.get('video_id'),
            'timestamp': datetime.now().isoformat(),
            'video_name': video_path.name,
            'video_path': str(video_path)
        })
        
        self.save()
    
    def mark_transcript_uploaded(self, video_path: Path, drive_data: Dict):
        """Mark that transcript was successfully uploaded"""
        file_id = self.get_file_id(video_path)
        
        if file_id not in self.data['processed']:
            self.data['processed'][file_id] = {}
        
        self.data['processed'][file_id].update({
            'transcript_uploaded': True,
            'drive_link': drive_data.get('shareable_link'),
            'transcript_path': drive_data.get('transcript_path'),
            'timestamp': datetime.now().isoformat()
        })
        
        self.save()
    
    def mark_partial(self, video_path: Path, video_done: bool, transcript_done: bool, 
                     error: str = None, transcript_path: str = None):
        """Mark partial success (one component succeeded, one failed)"""
        file_id = self.get_file_id(video_path)
        
        self.data['partial'][file_id] = {
            'video_done': video_done,
            'transcript_done': transcript_done,
            'error': error,
            'timestamp': datetime.now().isoformat(),
            'video_name': video_path.name,
            'video_path': str(video_path),
            'transcript_path': transcript_path
        }
        
        # Add to retry queue
        if file_id not in self.data['retry_queue']:
            self.data['retry_queue'].append(file_id)
        
        self.save()
    
    def mark_failed(self, video_path: Path, error: str):
        """Mark video as failed with error"""
        file_id = self.get_file_id(video_path)
        
        # Get current attempt count
        attempts = 0
        if file_id in self.data['failed']:
            attempts = self.data['failed'][file_id].get('attempts', 0)
        
        self.data['failed'][file_id] = {
            'error': error,
            'attempts': attempts + 1,
            'last_try': datetime.now().isoformat(),
            'video_name': video_path.name,
            'video_path': str(video_path)
        }
        
        # Add to retry queue if not too many attempts
        if attempts + 1 < 5 and file_id not in self.data['retry_queue']:
            self.data['retry_queue'].append(file_id)
        
        self.save()
    
    def get_retry_queue(self) -> list:
        """Get list of videos to retry"""
        return self.data['retry_queue'].copy()
    
    def clear_from_retry(self, video_path: Path):
        """Remove video from retry queue after success"""
        file_id = self.get_file_id(video_path)
        if file_id in self.data['retry_queue']:
            self.data['retry_queue'].remove(file_id)
            self.save()
    
    def get_partial_videos(self) -> list:
        """Get list of partially processed videos with details"""
        return [
            {
                'file_id': fid,
                'video_name': data['video_name'],
                'video_path': data['video_path'],
                'video_done': data['video_done'],
                'transcript_done': data['transcript_done'],
                'error': data.get('error'),
                'transcript_path': data.get('transcript_path')
            }
            for fid, data in self.data['partial'].items()
        ]
    
    def get_failed_videos(self) -> list:
        """Get list of failed videos with details"""
        return [
            {
                'file_id': fid,
                'video_name': data['video_name'],
                'video_path': data['video_path'],
                'error': data['error'],
                'attempts': data['attempts'],
                'last_try': data['last_try']
            }
            for fid, data in self.data['failed'].items()
        ]
    
    def reset_failed(self, video_path: Path):
        """Reset failure count for a video (for retry)"""
        file_id = self.get_file_id(video_path)
        if file_id in self.data['failed']:
            self.data['failed'][file_id]['attempts'] = 0
            self.save()
    
    def print_summary(self):
        """Print current state summary"""
        processed = len(self.data['processed'])
        failed = len(self.data['failed'])
        partial = len(self.data['partial'])
        retry_queue = len(self.data['retry_queue'])
        
        print(f"[STATE] Pipeline State Summary:")
        print(f"   ✓ Fully processed: {processed}")
        print(f"   ⚠️  Partial (need retry): {partial}")
        print(f"   ❌ Failed (retries exhausted): {failed}")
        print(f"   🔄 Retry queue: {retry_queue} videos")
        
        if partial > 0:
            print(f"\n[STATE] Partial videos needing retry:")
            for vid in self.get_partial_videos():
                status = []
                if vid['video_done']:
                    status.append("✓ video")
                else:
                    status.append("✗ video")
                if vid['transcript_done']:
                    status.append("✓ transcript")
                else:
                    status.append("✗ transcript")
                print(f"   - {vid['video_name']}: {', '.join(status)}")
                if vid['error']:
                    print(f"     Error: {vid['error'][:80]}")
