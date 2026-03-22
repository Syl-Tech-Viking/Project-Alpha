#!/usr/bin/env python3
"""
Video Transcriber - Basic Whisper (no diarization)
Outputs: All formats (whisper doesn't support selective output)
Only TXT file is uploaded to Drive
"""

import subprocess
import sys
from pathlib import Path
from typing import Dict

class VideoTranscriber:
    """Transcribe videos using OpenAI Whisper (basic, no diarization)"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.model = config.get('processing', {}).get('whisper_model', 'base')
    
    def ensure_whisper(self) -> bool:
        """Auto-install whisper if not present (no prompts)"""
        try:
            subprocess.run(
                [sys.executable, '-c', 'import whisper'],
                capture_output=True, timeout=5
            )
            return True
        except:
            print("[TRANSCRIBER] Auto-installing Whisper...")
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '--user', '--break-system-packages', 'openai-whisper'],
                capture_output=True, timeout=300
            )
            if result.returncode == 0:
                print("[TRANSCRIBER] ✓ Whisper installed")
                return True
            else:
                print(f"[TRANSCRIBER] ❌ Whisper install failed: {result.stderr[:200]}")
                return False
    
    def transcribe(self, video_path: Path, output_dir: Path) -> Dict:
        """
        Transcribe video using Whisper
        Returns: JSON, SRT, and TXT files
        Only TXT gets uploaded to Google Drive
        
        NOTE: Whisper creates all output files at the END, not progressively!
        A 10-minute video takes 3-8 minutes to process with no file output during that time.
        """
        print(f"[TRANSCRIBER] Starting: {video_path.name}")
        
        # Auto-install whisper if needed
        if not self.ensure_whisper():
            return {'status': 'failed', 'error': 'Could not install Whisper'}
        
        # Create output paths
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        base_name = video_path.stem
        txt_path = output_dir / f"{base_name}.txt"
        
        # Skip if already transcribed
        if txt_path.exists():
            print(f"[TRANSCRIBER] Using existing transcript: {txt_path.name}")
            text_content = txt_path.read_text()
            return {
                'status': 'success',
                'text_path': str(txt_path),
                'text': text_content,
                'cached': True
            }
        
        try:
            print(f"[TRANSCRIBER] Running Whisper (may take 30-120 min for long videos on CPU)...")
            print(f"[TRANSCRIBER] Model: {self.model}")
            print(f"[TRANSCRIBER] ⏳ Letting Whisper run to completion - no timeout...")
            
            # Run whisper and wait for completion - NO MONITORING, NO TIMEOUT
            # Generate all formats (whisper doesn't support multiple format selection)
            cmd = [
                sys.executable, '-m', 'whisper',
                str(video_path),
                '--model', self.model,
                '--output_format', 'all',  # Generate all formats
                '--output_dir', str(output_dir),
                '--verbose', 'False'
            ]
            
            # Simple subprocess - wait for Whisper to complete naturally
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Just wait - let Whisper take as long as it needs
            stdout, stderr = process.communicate()
            
            print(f"[TRANSCRIBER] Whisper process completed")
            
            returncode = process.returncode
            
            if returncode != 0:
                # Check for "no speech" error (this is OK)
                stderr_lower = stderr.lower()
                if 'no speech' in stderr_lower or 'no audio' in stderr_lower:
                    print("[TRANSCRIBER] ⚠️  No speech detected (this is OK)")
                    txt_path.write_text("[No speech detected in video]")
                    return {
                        'status': 'success',
                        'text_path': str(txt_path),
                        'text': "[No speech detected in video]",
                        'no_speech': True
                    }
                
                print(f"[TRANSCRIBER] ❌ Whisper error: {stderr[:300]}")
                return {'status': 'failed', 'error': stderr[:200]}
            
            # Find created files
            txt_files = list(output_dir.glob(f"{base_name}*.txt"))
            
            if txt_files:
                text_content = txt_files[0].read_text()
                # Rename to standard format if needed
                if txt_files[0].name != f"{base_name}.txt":
                    txt_files[0].rename(txt_path)
                
                print(f"[TRANSCRIBER] ✓ Complete: {len(text_content)} characters")
                
                return {
                    'status': 'success',
                    'text_path': str(txt_path),
                    'text': text_content
                }
            else:
                # No transcript generated - might be no speech
                txt_path.write_text("[No speech detected in video]")
                return {
                    'status': 'success',
                    'text_path': str(txt_path),
                    'text': "[No speech detected in video]",
                    'no_speech': True
                }
                
        except Exception as e:
            return {'status': 'failed', 'error': str(e)}
