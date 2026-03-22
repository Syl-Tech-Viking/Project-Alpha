#!/usr/bin/env python3
"""
File Watcher - Pure Python (no external deps)
Monitors video input folder for complete videos
"""

import os
import time
from pathlib import Path
from typing import List, Set

class FileWatcher:
    """Monitors folder for video files using polling (no external dependencies)"""
    
    def __init__(self, watch_folder: Path):
        self.watch_folder = Path(watch_folder)
        self.known_files: Set[str] = set()
    
    def scan_for_videos(self) -> List[Path]:
        """Scan folder for video files (.mov, .mp4, .mkv, etc.)"""
        videos = []
        
        if not self.watch_folder.exists():
            return videos
        
        # Video extensions
        extensions = ['.mov', '.mp4', '.mkv', '.avi', '.m4v', '.mts', '.m2ts']
        
        for ext in extensions:
            videos.extend(self.watch_folder.glob(f'*{ext}'))
            videos.extend(self.watch_folder.glob(f'*{ext.upper()}'))
        
        # Filter out hidden files and return sorted
        videos = sorted([v for v in videos if not v.name.startswith('.')])
        
        return videos
    
    def is_file_complete(self, video_path: Path, wait_seconds: int = 3) -> bool:
        """Check if file has finished being written (FCP rendering complete)"""
        try:
            # Check size is stable
            size1 = video_path.stat().st_size
            time.sleep(wait_seconds)
            size2 = video_path.stat().st_size
            
            return size1 == size2 and size1 > 0
        except:
            return False
    
    def wait_for_complete(self, video_path: Path, check_interval: int = 5, stall_threshold: int = 60) -> bool:
        """
        Wait for file to finish rendering - PROGRESS BASED
        
        Continues indefinitely as long as file is growing.
        Only fails if file size doesn't change for stall_threshold seconds AND file is still incomplete.
        """
        print(f"[WATCHER] Waiting for {video_path.name} to finish rendering...")
        print(f"[WATCHER] Will continue as long as file keeps growing...")
        
        last_size = 0
        last_growth_time = time.time()
        start_time = time.time()
        reported_progress = 0  # Track last reported MB to reduce spam
        stable_count = 0  # Count how many checks the size has been stable
        
        while True:
            try:
                current_size = video_path.stat().st_size
                current_time = time.time()
                
                # FIRST: Check if file is complete (stable size for multiple checks)
                if current_size > 0 and current_size == last_size:
                    stable_count += 1
                    # Need 2 consecutive stable checks to confirm complete (avoid false positives)
                    if stable_count >= 2:
                        print(f"[WATCHER] ✓ {video_path.name} is complete ({current_size / (1024*1024):.1f} MB)")
                        return True
                else:
                    # Size changed - reset stable counter
                    stable_count = 0
                
                # Check if file is growing
                if current_size > last_size:
                    # Progress detected - reset stall timer
                    last_growth_time = current_time
                    last_size = current_size
                    
                    # Report every 100MB to show progress
                    current_mb = current_size // (100 * 1024 * 1024)
                    if current_mb > reported_progress:
                        elapsed = int(current_time - start_time)
                        print(f"[WATCHER] Still rendering... {current_size / (1024*1024):.1f} MB ({elapsed}s elapsed)")
                        reported_progress = current_mb
                
                # SECOND: Check for stall (but only if file is NOT stable)
                # If file is stable, we already handled that above
                if stable_count == 0:  # Only check stall if file is still changing
                    time_since_growth = current_time - last_growth_time
                    if time_since_growth > stall_threshold:
                        print(f"[WATCHER] ⚠️ File appears stalled - no growth for {int(time_since_growth)}s")
                        print(f"[WATCHER] Current size: {current_size / (1024*1024):.1f} MB")
                        return False
                
                time.sleep(check_interval)
                
            except Exception as e:
                print(f"[WATCHER] ⚠️ Error checking file: {e}")
                time.sleep(check_interval)
