#!/usr/bin/env python3
"""
Session Resilience Module for Project Alpha v3.0+
Handles internet connectivity loss, session interruptions, and reconnection
"""

import time
import socket
import requests
from datetime import datetime, timedelta
from typing import Callable, Optional, Dict, Any
from pathlib import Path

class SessionResilience:
    """
    Session independence with exponential backoff reconnection
    
    Features:
    - Internet connectivity monitoring
    - 5 retry attempts with exponential delay
    - Maximum 1 hour total retry window
    - Graceful degradation on connection loss
    """
    
    def __init__(self, log_func: Optional[Callable] = None):
        self.log_func = log_func or print
        self.max_retries = 5
        self.max_total_duration = 3600  # 1 hour in seconds
        self.base_delay = 60  # Start with 1 minute
        self.retry_history: list = []
        
    def log(self, msg: str):
        """Log with session resilience prefix"""
        self.log_func(f"[SESSION] {msg}")
    
    def check_internet(self, timeout: int = 5) -> bool:
        """
        Check if internet connection is available
        
        Tests multiple endpoints for reliability:
        - Vimeo API
        - Google (as fallback)
        - DNS resolution
        """
        endpoints = [
            ('https://api.vimeo.com', 'Vimeo API'),
            ('https://www.google.com', 'Google'),
            ('8.8.8.8', 53)  # Google DNS
        ]
        
        for endpoint in endpoints:
            try:
                if isinstance(endpoint[0], str) and endpoint[0].startswith('http'):
                    # HTTP endpoint
                    response = requests.get(endpoint[0], timeout=timeout, allow_redirects=True)
                    if response.status_code < 500:  # Accept any non-server-error
                        return True
                else:
                    # TCP endpoint (DNS)
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(timeout)
                    result = sock.connect_ex(endpoint)
                    sock.close()
                    if result == 0:
                        return True
            except:
                continue
        
        return False
    
    def wait_for_internet(self, context: str = "operation") -> bool:
        """
        Wait for internet connection with exponential backoff
        
        Attempts: 5 retries
        Delays: 1min, 2min, 4min, 8min, 16min (total ~31min max)
        Total window: Never exceeds 1 hour
        
        Args:
            context: Description of what needs internet (for logging)
            
        Returns:
            True if internet restored, False if all retries exhausted
        """
        if self.check_internet():
            return True
        
        self.log(f"⚠️  Internet connection lost during {context}")
        self.log(f"   Starting reconnection sequence (max {self.max_retries} attempts, max 1 hour total)")
        
        start_time = time.time()
        attempt = 0
        
        while attempt < self.max_retries:
            # Check if we've exceeded total time budget
            elapsed = time.time() - start_time
            remaining_time = self.max_total_duration - elapsed
            
            if remaining_time <= 0:
                self.log(f"❌ Total retry window (1 hour) exceeded. Giving up.")
                return False
            
            attempt += 1
            
            # Calculate exponential backoff delay
            # Attempt 1: 60s, Attempt 2: 120s, Attempt 3: 240s, Attempt 4: 480s, Attempt 5: 960s
            delay = self.base_delay * (2 ** (attempt - 1))
            
            # Cap delay at remaining time
            if delay > remaining_time:
                delay = max(30, remaining_time - 10)  # At least 30s, leave 10s buffer
            
            self.log(f"🔄 Reconnection attempt {attempt}/{self.max_retries}")
            self.log(f"   Waiting {delay} seconds before retry...")
            self.log(f"   Time elapsed: {int(elapsed)}s, Time remaining: {int(remaining_time)}s")
            
            # Wait with periodic checks
            wait_start = time.time()
            while time.time() - wait_start < delay:
                if self.check_internet():
                    self.log(f"✓ Internet connection restored!")
                    self.retry_history.append({
                        'timestamp': datetime.now().isoformat(),
                        'context': context,
                        'attempts_required': attempt,
                        'total_wait_seconds': time.time() - start_time,
                        'success': True
                    })
                    return True
                time.sleep(5)  # Check every 5 seconds
        
        # All retries exhausted
        elapsed = time.time() - start_time
        self.log(f"❌ Failed to restore internet after {self.max_retries} attempts ({int(elapsed)}s)")
        self.retry_history.append({
            'timestamp': datetime.now().isoformat(),
            'context': context,
            'attempts': self.max_retries,
            'total_wait_seconds': elapsed,
            'success': False
        })
        return False
    
    def execute_with_resilience(self, operation: Callable, context: str = "operation",
                                 allow_offline_result: Any = None) -> tuple:
        """
        Execute an operation with session resilience
        
        If operation fails due to connectivity, waits for internet and retries.
        
        Args:
            operation: Function to execute (should raise on network error)
            context: Description for logging
            allow_offline_result: Return value if offline and can't reconnect
            
        Returns:
            Tuple of (success: bool, result: Any, was_offline: bool)
        """
        was_offline = False
        
        try:
            # Try the operation first
            result = operation()
            return (True, result, was_offline)
        except (requests.exceptions.ConnectionError, 
                requests.exceptions.Timeout,
                socket.error) as e:
            # Network error - try to recover
            was_offline = True
            self.log(f"⚠️  Network error during {context}: {str(e)[:100]}")
            
            # Attempt to reconnect
            if self.wait_for_internet(context):
                # Reconnected - retry operation
                try:
                    result = operation()
                    return (True, result, was_offline)
                except Exception as retry_error:
                    self.log(f"❌ Operation still failing after reconnection: {retry_error}")
                    return (False, allow_offline_result, was_offline)
            else:
                # Could not reconnect
                return (False, allow_offline_result, was_offline)
        except Exception as e:
            # Non-network error - don't retry
            self.log(f"❌ Non-network error during {context}: {e}")
            return (False, allow_offline_result, was_offline)
    
    def get_retry_history(self) -> list:
        """Get history of all retry attempts"""
        return self.retry_history.copy()
    
    def print_summary(self):
        """Print summary of session resilience activity"""
        if not self.retry_history:
            print("[SESSION] No connection interruptions occurred")
            return
        
        total_interruptions = len(self.retry_history)
        successful_recoveries = sum(1 for h in self.retry_history if h['success'])
        total_wait_time = sum(h['total_wait_seconds'] for h in self.retry_history)
        
        print(f"[SESSION] Resilience Summary:")
        print(f"   Total interruptions: {total_interruptions}")
        print(f"   Successful recoveries: {successful_recoveries}")
        print(f"   Failed recoveries: {total_interruptions - successful_recoveries}")
        print(f"   Total wait time: {int(total_wait_time)} seconds ({total_wait_time/60:.1f} minutes)")
        
        if total_interruptions > 0:
            avg_wait = total_wait_time / total_interruptions
            print(f"   Average recovery time: {int(avg_wait)} seconds")


def test_session_resilience():
    """Test the session resilience module"""
    print("Testing Session Resilience Module...")
    
    session = SessionResilience()
    
    # Test 1: Check internet
    print("\n1. Testing internet check...")
    connected = session.check_internet()
    print(f"   Internet available: {connected}")
    
    # Test 2: Execute with resilience
    print("\n2. Testing execute_with_resilience...")
    def sample_operation():
        response = requests.get('https://api.vimeo.com', timeout=5)
        return "success"
    
    success, result, was_offline = session.execute_with_resilience(
        sample_operation, 
        "Vimeo connectivity test"
    )
    print(f"   Success: {success}, Was offline: {was_offline}")
    
    # Print summary
    print("\n3. Session resilience summary:")
    session.print_summary()
    
    print("\n✓ Session resilience tests complete")


if __name__ == "__main__":
    test_session_resilience()
