import os
import time
import json
import logging
import threading
import random
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class Scheduler:
    """Manages scheduled stream checks"""

    def __init__(self, config, browser_service):
        self.config = config
        self.browser_service = browser_service
        self.schedules = []
        self.running = False
        self.thread = None
        self.lock = threading.Lock()
        
        self.load_schedules()

    def load_schedules(self):
        """Load schedules from disk"""
        if os.path.exists(self.config.SCHEDULES_FILE):
            try:
                with open(self.config.SCHEDULES_FILE, 'r') as f:
                    self.schedules = json.load(f)
                logger.info(f"Loaded {len(self.schedules)} schedules")

                # Ensure all schedules have next_check calculated
                for schedule in self.schedules:
                    if not schedule.get('next_check'):
                        self._update_next_check(schedule)

            except Exception as e:
                logger.error(f"Error loading schedules: {e}")
                self.schedules = []
        else:
            self.schedules = []

    def save_schedules(self):
        """Save schedules to disk"""
        try:
            with open(self.config.SCHEDULES_FILE, 'w') as f:
                json.dump(self.schedules, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving schedules: {e}")

    def add_schedule(self, url, start_time, end_time, repeat=False, daily=False, name=None, resolution='1080p', framerate='any', format='mp4'):
        """Add a new schedule"""
        with self.lock:
            schedule = {
                'id': str(int(time.time() * 1000)),
                'url': url,
                'name': name or url,
                'resolution': resolution,
                'framerate': framerate,
                'format': format,
                'start_time': start_time, # ISO format string or HH:MM for daily
                'end_time': end_time,     # ISO format string or HH:MM for daily
                'repeat': repeat,
                'daily': daily,           # If true, start_time and end_time are HH:MM format
                'status': 'pending',      # pending, active, completed, download_started
                'next_check': None,
                'last_check': None,
                'created_at': datetime.now().isoformat()
            }
            # Initialize next check
            self._update_next_check(schedule)

            self.schedules.append(schedule)
            self.save_schedules()
            return schedule

    def remove_schedule(self, schedule_id):
        """Remove a schedule"""
        with self.lock:
            self.schedules = [s for s in self.schedules if s['id'] != schedule_id]
            self.save_schedules()
            return True

    def update_schedule(self, schedule_id, url, start_time, end_time, repeat=False, daily=False, name=None, resolution='1080p', framerate='any', format='mp4'):
        """Update an existing schedule"""
        with self.lock:
            for schedule in self.schedules:
                if schedule['id'] == schedule_id:
                    # Update fields
                    schedule['url'] = url
                    schedule['name'] = name or url
                    schedule['start_time'] = start_time
                    schedule['end_time'] = end_time
                    schedule['repeat'] = repeat
                    schedule['daily'] = daily
                    schedule['resolution'] = resolution
                    schedule['framerate'] = framerate
                    schedule['format'] = format

                    # Reset status if times changed
                    schedule['status'] = 'pending'

                    # Update next check time
                    self._update_next_check(schedule)

                    self.save_schedules()
                    logger.info(f"Updated schedule {schedule_id}")
                    return schedule

            return None

    def get_schedules(self):
        """Get all schedules, sorted by next_check time"""
        # Sort schedules by next_check time (soonest first)
        # Schedules without next_check go to the end
        sorted_schedules = sorted(
            self.schedules,
            key=lambda s: (
                s.get('next_check') is None,  # False (0) for schedules with next_check, True (1) for those without
                s.get('next_check') or ''      # Sort by next_check if it exists
            )
        )
        return sorted_schedules

    def refresh_all_schedule_times(self):
        """Force refresh all schedule next_check times"""
        with self.lock:
            count = 0
            for schedule in self.schedules:
                self._update_next_check(schedule)
                count += 1
            self.save_schedules()
            logger.info(f"Refreshed {count} schedule next_check times")
            return count

    def start(self):
        """Start the scheduler loop"""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info("Scheduler started")

    def stop(self):
        """Stop the scheduler loop"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
            logger.info("Scheduler stopped")

    def _run_loop(self):
        """Main scheduler loop"""
        logger.info("Scheduler loop running")
        while self.running:
            try:
                self._check_schedules()
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
            
            # Sleep for a bit before next iteration (e.g., 30 seconds)
            # We don't need super high precision
            for _ in range(30):
                if not self.running: 
                    break
                time.sleep(1)

    def _check_schedules(self):
        """Check all schedules and run tasks if needed"""
        now = datetime.now()

        with self.lock:
            for schedule in self.schedules:
                if schedule['status'] == 'completed' and not schedule.get('daily'):
                    # Skip completed non-daily schedules
                    continue

                try:
                    if schedule.get('daily'):
                        # Daily schedule - handle time-based windows
                        self._check_daily_schedule(schedule, now)
                    else:
                        # Regular schedule - handle datetime-based windows
                        start_dt = datetime.fromisoformat(schedule['start_time'])
                        end_dt = datetime.fromisoformat(schedule['end_time'])

                        # Check if window passed
                        if now > end_dt:
                            if schedule['repeat']:
                                # Move to next week
                                self._reschedule_next_week(schedule)
                            else:
                                if schedule['status'] != 'download_started':
                                    schedule['status'] = 'completed'
                            continue

                        # Check if currently active window
                        if start_dt <= now <= end_dt:
                            if schedule['status'] == 'download_started':
                                # Already downloaded for this window
                                continue

                            # Transition to active status
                            schedule['status'] = 'active'

                            # Check if it's time to check stream
                            next_check = schedule.get('next_check')
                            if not next_check or now >= datetime.fromisoformat(next_check):
                                # It's time! (when next_check time arrives)
                                self._perform_check(schedule)

                        elif now < start_dt:
                             schedule['status'] = 'pending'
                             # Ensure next_check is set (only if missing or in the past)
                             next_check = schedule.get('next_check')
                             if not next_check:
                                 self._update_next_check(schedule)
                             else:
                                 try:
                                     next_check_dt = datetime.fromisoformat(next_check)
                                     # Only recalculate if next_check is in the past
                                     if next_check_dt < now:
                                         self._update_next_check(schedule)
                                 except (ValueError, TypeError):
                                     self._update_next_check(schedule)

                except Exception as e:
                    logger.error(f"Error processing schedule {schedule['id']}: {e}")

            self.save_schedules()

    def _check_daily_schedule(self, schedule, now):
        """Check a daily schedule (time-based, repeats every day)"""
        # Parse the time strings (format: "HH:MM")
        start_time_str = schedule['start_time']
        end_time_str = schedule['end_time']

        # Get today's date
        today = now.date()

        # Create datetime objects for today's window
        start_hour, start_min = map(int, start_time_str.split(':'))
        end_hour, end_min = map(int, end_time_str.split(':'))

        start_dt = datetime.combine(today, datetime.min.time().replace(hour=start_hour, minute=start_min))
        end_dt = datetime.combine(today, datetime.min.time().replace(hour=end_hour, minute=end_min))

        # Detect if this is a midnight-spanning window (e.g., 23:00 - 01:00)
        spans_midnight = end_hour < start_hour or (end_hour == start_hour and end_min < start_min)

        if spans_midnight:
            # For midnight-spanning windows, we need to check if we're in yesterday's window
            # that extends into today, OR in today's window that extends into tomorrow

            # Check if we're in yesterday's window (before today's start time)
            if now.time() < datetime.min.time().replace(hour=start_hour, minute=start_min):
                # We're in the early morning hours - check if yesterday's window extends to now
                yesterday = today - timedelta(days=1)
                start_dt = datetime.combine(yesterday, datetime.min.time().replace(hour=start_hour, minute=start_min))
                end_dt = datetime.combine(today, datetime.min.time().replace(hour=end_hour, minute=end_min))
            else:
                # We're after start time today - window extends into tomorrow
                end_dt = end_dt + timedelta(days=1)
        else:
            # Normal same-day window
            pass

        # Check if we're currently in the active window
        if start_dt <= now <= end_dt:
            if schedule['status'] == 'download_started':
                # Already downloaded for this window
                return

            # Transition to active status
            schedule['status'] = 'active'

            # Check if it's time to check stream
            next_check = schedule.get('next_check')
            if not next_check or now >= datetime.fromisoformat(next_check):
                # It's time! (when next_check time arrives)
                self._perform_check(schedule)

        elif now < start_dt:
            # Window hasn't started yet
            schedule['status'] = 'pending'
            # Ensure next_check is set (only if missing or in the past)
            next_check = schedule.get('next_check')
            if not next_check:
                self._update_next_check(schedule)
            else:
                try:
                    next_check_dt = datetime.fromisoformat(next_check)
                    # Only recalculate if next_check is in the past
                    if next_check_dt < now:
                        self._update_next_check(schedule)
                except (ValueError, TypeError):
                    self._update_next_check(schedule)

        else:
            # Window has passed - always reset to pending for next day
            if schedule['status'] in ['active', 'download_started']:
                # Reset for next day
                schedule['status'] = 'pending'
                schedule['last_check'] = None
                self._update_next_check(schedule)

    def _update_next_check(self, schedule):
        """Calculate next check time based on schedule window"""
        now = datetime.now()

        if schedule.get('daily'):
            # Daily schedule - calculate based on time
            start_time_str = schedule['start_time']
            end_time_str = schedule['end_time']

            today = now.date()
            start_hour, start_min = map(int, start_time_str.split(':'))
            end_hour, end_min = map(int, end_time_str.split(':'))

            start_dt = datetime.combine(today, datetime.min.time().replace(hour=start_hour, minute=start_min))
            end_dt = datetime.combine(today, datetime.min.time().replace(hour=end_hour, minute=end_min))

            # Detect if this is a midnight-spanning window (e.g., 23:00 - 01:00)
            spans_midnight = end_hour < start_hour or (end_hour == start_hour and end_min < start_min)

            if spans_midnight:
                # For midnight-spanning windows, determine which window we're checking
                if now.time() < datetime.min.time().replace(hour=start_hour, minute=start_min):
                    # We're in the early morning hours - check if yesterday's window extends to now
                    yesterday = today - timedelta(days=1)
                    start_dt = datetime.combine(yesterday, datetime.min.time().replace(hour=start_hour, minute=start_min))
                    end_dt = datetime.combine(today, datetime.min.time().replace(hour=end_hour, minute=end_min))
                else:
                    # We're after start time today - window extends into tomorrow
                    end_dt = end_dt + timedelta(days=1)

            # If window hasn't started yet, schedule check for start of window
            if now < start_dt:
                schedule['next_check'] = start_dt.isoformat()
                logger.debug(f"Schedule {schedule['id']}: next check set to window start: {start_dt}")
            # If we're in the window, schedule random check in 5-8 minutes
            elif start_dt <= now <= end_dt:
                minutes = random.uniform(5, 8)
                next_dt = now + timedelta(minutes=minutes)
                # Make sure we don't schedule past the end of the window
                if next_dt > end_dt:
                    next_dt = end_dt
                schedule['next_check'] = next_dt.isoformat()
                logger.debug(f"Schedule {schedule['id']}: next check in {minutes:.1f} mins: {next_dt}")
            # If window has passed, schedule for next occurrence
            else:
                # For midnight-spanning, if we're past end time but before start time,
                # the next window is today (later). Otherwise it's tomorrow.
                if spans_midnight and now.time() < datetime.min.time().replace(hour=start_hour, minute=start_min):
                    # We're past yesterday's window end, next window is today
                    next_start = datetime.combine(today, datetime.min.time().replace(hour=start_hour, minute=start_min))
                else:
                    # Next window is tomorrow
                    tomorrow = today + timedelta(days=1)
                    next_start = datetime.combine(tomorrow, datetime.min.time().replace(hour=start_hour, minute=start_min))

                schedule['next_check'] = next_start.isoformat()
                logger.debug(f"Schedule {schedule['id']}: next check set to next window start: {next_start}")

        else:
            # Regular schedule - calculate based on datetime
            start_dt = datetime.fromisoformat(schedule['start_time'])
            end_dt = datetime.fromisoformat(schedule['end_time'])

            # If window hasn't started yet, schedule check for start of window
            if now < start_dt:
                schedule['next_check'] = start_dt.isoformat()
                logger.debug(f"Schedule {schedule['id']}: next check set to window start: {start_dt}")
            # If we're in the window, schedule random check in 5-8 minutes
            elif start_dt <= now <= end_dt:
                minutes = random.uniform(5, 8)
                next_dt = now + timedelta(minutes=minutes)
                # Make sure we don't schedule past the end of the window
                if next_dt > end_dt:
                    next_dt = end_dt
                schedule['next_check'] = next_dt.isoformat()
                logger.debug(f"Schedule {schedule['id']}: next check in {minutes:.1f} mins: {next_dt}")
            # If window has passed, clear next_check (will be rescheduled)
            else:
                schedule['next_check'] = None
                logger.debug(f"Schedule {schedule['id']}: window passed, clearing next_check")

    def _reschedule_next_week(self, schedule):
        """Move schedule to next week"""
        start_dt = datetime.fromisoformat(schedule['start_time'])
        end_dt = datetime.fromisoformat(schedule['end_time'])

        new_start = start_dt + timedelta(days=7)
        new_end = end_dt + timedelta(days=7)

        schedule['start_time'] = new_start.isoformat()
        schedule['end_time'] = new_end.isoformat()
        schedule['status'] = 'pending'

        # Update next_check to the new window start
        self._update_next_check(schedule)

        logger.info(f"Rescheduled {schedule['id']} to next week: {new_start}")

    def _perform_check(self, schedule):
        """Perform the actual browser check"""
        logger.info(f"Performing scheduled check for {schedule['name']} ({schedule['url']})")
        
        # Determine duration (20-60s)
        duration = random.uniform(20, 60)
        
        # Thread logic for the check so we don't block main scheduler loop for a minute
        check_thread = threading.Thread(
            target=self._run_browser_check_task,
            args=(schedule, duration)
        )
        check_thread.start()
        
        # Update next check time immediately so we don't spawn multiple
        self._update_next_check(schedule)

    def _run_browser_check_task(self, schedule, duration):
        """The actual task running in a separate thread"""
        browser_id = f"sched_{schedule['id']}_{int(time.time())}"

        try:
            # Queue browser (will wait for previous browsers to close)
            logger.info(f"Requesting browser for schedule {schedule['id']} (will queue if needed)")
            success, detector = self.browser_service.start_browser(
                url=schedule['url'],
                browser_id=browser_id,
                auto_download=True, # Important!
                filename=None, # Auto name
                resolution=schedule.get('resolution', '1080p'),
                framerate=schedule.get('framerate', 'any'),
                output_format=schedule.get('format', 'mp4')
            )
            
            if not success:
                logger.warning(f"Failed to start browser for schedule {schedule['id']}")
                return

            # Wait for random duration or until download starts
            start_wait = time.time()
            while time.time() - start_wait < duration:
                # Check status
                status = self.browser_service.get_browser_status(browser_id)
                if not status:
                    break
                
                # Check if downloading
                # BrowserService.get_browser_status returns keys like 'started', 'finding_stream', etc.
                # If auto_download is True, it might have transitioned to download service.
                # We need to check if a download was triggered. 
                # The detector has `set_download_callback`.
                
                # If download started, the detector might be closed or status changed?
                # Actually, `start_browser` in `browser_service.py` sets callback `self.download_service.start_download`.
                # If download starts, `start_download` is called.
                
                # We can check `download_service` status for this browser_id?
                # Or check `detector.get_status()`?
                
                # Let's check if we can detect if download started.
                # In `detector.py` (not visible but inferred), likely it calls callback.
                
                # We can rely on `download_service.get_download_status(browser_id)`
                dl_status = self.browser_service.download_service.get_download_status(browser_id)
                if dl_status:
                    logger.info(f"Download started for schedule {schedule['id']}!")
                    
                    with self.lock:
                        # Re-fetch schedule to ensure we have latest state (though it's in mem)
                        # We need to find the specific dict object in self.schedules
                        # (since we are in a thread, self.schedules might have changed if reloaded, but we share reference)
                         for s in self.schedules:
                             if s['id'] == schedule['id']:
                                 s['status'] = 'download_started'
                                 # Clear next_check - no more checks needed until next window
                                 s['next_check'] = None
                                 self.save_schedules()
                                 break
                    
                    # We can close browser if we want, or let it handle it.
                    # Usually download detached from browser? 
                    # If ffmpeg, browser can close. If direct, browser can close.
                    # The `auto_download` logic in `detector` likely closes browser if stream found?
                    # Let's assume we should close it if it's still open to be safe, 
                    # BUT `download_service` might be using cookies from it?
                    # `BrowserService.start_browser` closes existing browsers.
                    
                    # If download started, we are GOOD.
                    # The loop will end.
                    break
                
                time.sleep(1)
            
            # cleanup
            logger.info(f"Closing browser for schedule {schedule['id']}")
            self.browser_service.close_browser(browser_id)

        except Exception as e:
            logger.error(f"Error in browser check task: {e}")
            try:
                self.browser_service.close_browser(browser_id)
            except:
                pass
