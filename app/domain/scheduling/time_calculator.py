"""Time calculation strategies for different schedule types."""
import logging
import random
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class TimeCalculator(ABC):
    """Abstract base class for time calculation strategies."""

    @abstractmethod
    def check_schedule(self, schedule, now):
        """
        Check if a schedule should be executed and update its status.

        Args:
            schedule (dict): The schedule dictionary to check
            now (datetime): Current datetime

        Returns:
            bool: True if schedule should be executed, False otherwise
        """
        pass

    @abstractmethod
    def calculate_next_check(self, schedule, now):
        """
        Calculate and set the next check time for a schedule.

        Args:
            schedule (dict): The schedule dictionary to update
            now (datetime): Current datetime
        """
        pass


class DailyTimeCalculator(TimeCalculator):
    """
    Time calculator for daily recurring schedules.

    Handles time-based windows (HH:MM format) that repeat every day,
    including complex midnight-spanning windows (e.g., 23:00 - 01:00).
    """

    def check_schedule(self, schedule, now):
        """
        Check a daily schedule (time-based, repeats every day).

        This method handles:
        - Same-day windows (e.g., 09:00 - 17:00)
        - Midnight-spanning windows (e.g., 23:00 - 01:00)
        - Status transitions (pending -> active -> download_started)

        Args:
            schedule (dict): The schedule dictionary to check
            now (datetime): Current datetime

        Returns:
            bool: True if schedule should be executed, False otherwise
        """
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
                return False

            # Check if transitioning from pending to active (first time in window)
            was_pending = schedule['status'] == 'pending'
            schedule['status'] = 'active'

            # Check if it's time to check stream
            next_check = schedule.get('next_check')
            if was_pending or not next_check or now >= datetime.fromisoformat(next_check):
                # It's time! (immediately on window start, or when next_check time arrives)
                return True

            return False

        elif now < start_dt:
            # Window hasn't started yet
            schedule['status'] = 'pending'
            # Ensure next_check is set correctly (at window start)
            next_check = schedule.get('next_check')
            if not next_check or datetime.fromisoformat(next_check) != start_dt:
                self.calculate_next_check(schedule, now)
            return False

        else:
            # Window has passed - always reset to pending for next day
            if schedule['status'] in ['active', 'download_started']:
                # Reset for next day
                schedule['status'] = 'pending'
                schedule['last_check'] = None
                self.calculate_next_check(schedule, now)
            return False

    def calculate_next_check(self, schedule, now):
        """
        Calculate next check time for a daily schedule.

        This method handles:
        - Scheduling at window start for pending schedules
        - Random 5-8 minute intervals during active window
        - Next day scheduling for passed windows
        - Midnight-spanning window edge cases

        Args:
            schedule (dict): The schedule dictionary to update
            now (datetime): Current datetime
        """
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


class RegularTimeCalculator(TimeCalculator):
    """
    Time calculator for one-time or weekly recurring schedules.

    Handles datetime-based windows (ISO format) that occur once
    or repeat weekly.
    """

    def check_schedule(self, schedule, now):
        """
        Check a regular schedule (datetime-based).

        This method handles:
        - One-time schedules
        - Weekly repeating schedules
        - Status transitions (pending -> active -> completed/download_started)

        Args:
            schedule (dict): The schedule dictionary to check
            now (datetime): Current datetime

        Returns:
            bool: True if schedule should be executed, False otherwise
        """
        # Regular schedule - handle datetime-based windows
        start_dt = datetime.fromisoformat(schedule['start_time'])
        end_dt = datetime.fromisoformat(schedule['end_time'])

        # Check if window passed
        if now > end_dt:
            # Window has passed - handled by scheduler (reschedule or complete)
            # We don't execute in this state
            return False

        # Check if currently active window
        if start_dt <= now <= end_dt:
            if schedule['status'] == 'download_started':
                # Already downloaded for this window
                return False

            # Check if transitioning from pending to active (first time in window)
            was_pending = schedule['status'] == 'pending'
            schedule['status'] = 'active'

            # Check if it's time to check stream
            next_check = schedule.get('next_check')
            if was_pending or not next_check or now >= datetime.fromisoformat(next_check):
                # It's time! (immediately on window start, or when next_check time arrives)
                return True

            return False

        elif now < start_dt:
            schedule['status'] = 'pending'
            # Ensure next_check is set correctly (at window start)
            next_check = schedule.get('next_check')
            if not next_check or datetime.fromisoformat(next_check) != start_dt:
                self.calculate_next_check(schedule, now)
            return False

        return False

    def calculate_next_check(self, schedule, now):
        """
        Calculate next check time for a regular schedule.

        This method handles:
        - Scheduling at window start for pending schedules
        - Random 5-8 minute intervals during active window
        - Clearing next_check for passed windows

        Args:
            schedule (dict): The schedule dictionary to update
            now (datetime): Current datetime
        """
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
