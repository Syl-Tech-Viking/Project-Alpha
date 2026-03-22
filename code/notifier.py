#!/usr/bin/env python3
"""
Slack Notifier - Formats and sends batch notifications
Format per video:
Video Name
---
Vimeo Embed Code
---
Vimeo Link
---
Google Drive Link

Separator between videos: \n\n==\n\n
"""

import requests
from typing import Dict, List

class SlackNotifier:
    """Send formatted notifications to Slack"""
    
    def __init__(self, config: Dict):
        self.webhook_url = config.get('slack_webhook', '')
    
    def format_video_block(self, video: Dict) -> str:
        """Format single video for Slack"""
        name = video.get('name', 'Unknown Video')
        vimeo_url = video.get('vimeo_url', 'N/A')
        embed_code = video.get('embed_code', 'N/A')
        drive_link = video.get('drive_link', 'N/A')
        
        block = f"""{name}
---
{embed_code}
---
{vimeo_url}
---
{drive_link}"""
        
        return block
    
    def send_batch(self, videos: List[Dict]):
        """Send batch notification with all videos"""
        if not videos:
            print("[NOTIFY] No videos to notify about")
            return
        
        if not self.webhook_url:
            print("[NOTIFY] ⚠️  Slack webhook not configured")
            return
        
        print(f"[NOTIFY] Sending batch notification for {len(videos)} video(s)...")
        
        # Build message
        header = f"🎬 Video Processing Complete - {len(videos)} Video(s)\n\n"
        
        video_blocks = []
        for video in videos:
            block = self.format_video_block(video)
            video_blocks.append(block)
        
        # Join with double separator
        message = header + "\n\n==\n\n".join(video_blocks)
        
        # Send to Slack
        try:
            payload = {'text': message}
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                print("[NOTIFY] ✓ Slack notification sent")
            else:
                print(f"[NOTIFY] ⚠️  Slack error (status {response.status_code})")
                
        except Exception as e:
            print(f"[NOTIFY] ⚠️  Failed to send Slack notification: {e}")
    
    def send_progress(self, message: str):
        """Send progress notification to Slack"""
        if not self.webhook_url:
            print(f"[NOTIFY] Progress: {message}")
            return
        
        try:
            payload = {'text': message}
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                print(f"[NOTIFY] ✓ Progress notification sent")
            else:
                print(f"[NOTIFY] ⚠️  Slack error (status {response.status_code})")
                
        except Exception as e:
            print(f"[NOTIFY] ⚠️  Failed to send progress: {e}")
    
    def send_error(self, video_name: str, error: str):
        """Send error notification"""
        if not self.webhook_url:
            return
        
        message = f"❌ Error Processing: {video_name}\n\nError: {error[:500]}"
        
        try:
            requests.post(self.webhook_url, json={'text': message}, timeout=10)
        except:
            pass  # Don't fail on notification errors
