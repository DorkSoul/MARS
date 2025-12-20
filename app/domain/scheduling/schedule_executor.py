"""Schedule execution loop component for managing scheduled stream checks."""
import time
import logging
import random
import threading
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ScheduleExecutor:
    """
    Manages the execution lifecycle of scheduled stream checks.

    This component handles:
    - Starting/stopping the execution thread
    - Periodically checking schedules
    - Triggering browser checks when schedules are active
    - Rescheduling weekly repeating schedules

    The executor uses time calculators for determining when to execute
    schedules and a callback pattern for triggering browser checks.
    """

    def __init__(self, daily_calculator, regular_calculator):
        """
        Initialize the schedule executor.

        Args:
            daily_calculator (DailyTimeCalculator): Calculator for daily schedules
            regular_calculator (RegularTimeCalculator): Calculator for regular schedules
        """
        self.daily_calculator = daily_calculator
        self.regular_calculator = regular_calculator
        self.running = False
        self.thread = None

    def start(self):
        """
        Start the executor thread.

        Launches a daemon thread that runs the execution loop. The thread
        checks schedules every 30 seconds (via 1-second increments for
        responsive shutdown).
        """
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info("Schedule executor started")

    def stop(self):
        """
        Stop the executor thread.

        Signals the execution loop to stop and waits up to 2 seconds
        for the thread to terminate gracefully.
        """
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
            logger.info("Schedule executor stopped")

    def _run_loop(self):
        """
        Main execution loop (runs in dedicated thread).

        Continuously checks schedules every 30 seconds. Uses 1-second
        sleep increments to allow responsive shutdown when stop() is called.
        """
        logger.info("Schedule executor loop running")
        while self.running:
            try:
                # Note: execute_schedules is called by external code
                # This loop just ensures the thread stays alive
                # The actual checking happens when execute_schedules is called
                pass
            except Exception as e:
                logger.error(f"Schedule executor loop error: {e}")

            # Sleep for 30 seconds total, but check every 1 second for shutdown
            for _ in range(30):
                if not self.running:
                    break
                time.sleep(1)

    def execute_schedules(self, schedules, browser_service, lock, save_callback):
        """
        Check all schedules and execute browser checks if needed.

        This is the main iteration of the execution loop. It:
        1. Iterates through all schedules
        2. Determines if each schedule should be executed (using time calculators)
        3. Triggers browser checks for active schedules
        4. Handles weekly rescheduling for expired repeating schedules
        5. Saves schedule state changes

        Args:
            schedules (list): List of schedule dictionaries to check
            browser_service: Service for starting/managing browser instances
            lock (threading.Lock): Lock for thread-safe schedule access
            save_callback (callable): Function to call to persist schedule changes
        """
        now = datetime.now()

        with lock:
            for schedule in schedules:
                if schedule['status'] == 'completed' and not schedule.get('daily'):
                    # Skip completed non-daily schedules
                    continue

                try:
                    if schedule.get('daily'):
                        # Daily schedule - handle time-based windows
                        should_execute = self.daily_calculator.check_schedule(schedule, now)
                        if should_execute:
                            self._perform_check(schedule, browser_service, lock, save_callback)
                    else:
                        # Regular schedule - handle datetime-based windows
                        start_dt = datetime.fromisoformat(schedule['start_time'])
                        end_dt = datetime.fromisoformat(schedule['end_time'])

                        # Check if window passed
                        if now > end_dt:
                            if schedule['repeat']:
                                # Move to next week
                                self.reschedule_weekly(schedule)
                            else:
                                if schedule['status'] != 'download_started':
                                    schedule['status'] = 'completed'
                            continue

                        # Use calculator to check regular schedule
                        should_execute = self.regular_calculator.check_schedule(schedule, now)
                        if should_execute:
                            self._perform_check(schedule, browser_service, lock, save_callback)

                except Exception as e:
                    logger.error(f"Error processing schedule {schedule['id']}: {e}")

            save_callback()

    def check_schedule(self, schedule, browser_service):
        """
        Perform a browser check for a single schedule.

        This method:
        1. Logs the check
        2. Determines a random check duration (20-60 seconds)
        3. Spawns a separate thread to run the browser check
        4. Returns immediately (non-blocking)

        The browser check thread handles:
        - Opening the browser with the schedule's URL
        - Waiting for the random duration or until download starts
        - Detecting when a download has started
        - Updating schedule status to 'download_started'
        - Closing the browser

        Args:
            schedule (dict): The schedule to check
            browser_service: Service for managing browser instances
        """
        logger.info(f"Performing scheduled check for {schedule['name']} ({schedule['url']})")

        # Determine duration (20-60s)
        duration = random.uniform(20, 60)

        # Thread logic for the check so we don't block main scheduler loop
        check_thread = threading.Thread(
            target=self._run_browser_check_task,
            args=(schedule, browser_service, duration)
        )
        check_thread.start()

    def reschedule_weekly(self, schedule):
        """
        Reschedule a regular schedule for next week.

        This method:
        1. Parses the current start/end times
        2. Adds 7 days to both times
        3. Updates the schedule with new times
        4. Resets status to 'pending'
        5. Recalculates next_check time

        Args:
            schedule (dict): The schedule to reschedule
        """
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

    def _perform_check(self, schedule, browser_service, lock, save_callback):
        """
        Perform the actual browser check (internal helper).

        Args:
            schedule (dict): The schedule to check
            browser_service: Service for managing browser instances
            lock (threading.Lock): Lock for thread-safe schedule access
            save_callback (callable): Function to call to persist schedule changes
        """
        logger.info(f"Performing scheduled check for {schedule['name']} ({schedule['url']})")

        # Determine duration (20-60s)
        duration = random.uniform(20, 60)

        # Thread logic for the check so we don't block main scheduler loop for a minute
        check_thread = threading.Thread(
            target=self._run_browser_check_task,
            args=(schedule, browser_service, duration, lock, save_callback)
        )
        check_thread.start()

        # Update next check time immediately so we don't spawn multiple
        self._update_next_check(schedule)

    def _run_browser_check_task(self, schedule, browser_service, duration, lock=None, save_callback=None):
        """
        Run the browser check in a separate thread.

        This method:
        1. Generates a unique browser ID
        2. Starts the browser with auto_download enabled
        3. Waits for the specified duration or until download starts
        4. Polls the download service every second to detect download start
        5. Updates schedule status to 'download_started' when detected
        6. Closes the browser when done

        Args:
            schedule (dict): The schedule being checked
            browser_service: Service for managing browser instances
            duration (float): Maximum duration in seconds to keep browser open
            lock (threading.Lock, optional): Lock for thread-safe schedule access
            save_callback (callable, optional): Function to call to persist schedule changes
        """
        browser_id = f"sched_{schedule['id']}_{int(time.time())}"

        try:
            # Queue browser (will wait for previous browsers to close)
            logger.info(f"Requesting browser for schedule {schedule['id']} (will queue if needed)")
            success, detector = browser_service.start_browser(
                url=schedule['url'],
                browser_id=browser_id,
                auto_download=True,  # Important!
                filename=None,  # Auto name
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
                status = browser_service.get_browser_status(browser_id)
                if not status:
                    break

                # Check if download started
                # The browser_service.start_browser sets callback to download_service.start_download
                # We can check if download was triggered by querying download_service
                dl_status = browser_service.download_service.get_download_status(browser_id)
                if dl_status:
                    logger.info(f"Download started for schedule {schedule['id']}!")

                    if lock and save_callback:
                        with lock:
                            # Find the schedule in the list and update it
                            # (We need to update the actual dict in the list, not our local reference)
                            # The schedule dict should be the same object reference, so this update
                            # should reflect in the main list
                            schedule['status'] = 'download_started'
                            # Clear next_check - no more checks needed until next window
                            schedule['next_check'] = None
                            save_callback()
                    else:
                        # Fallback if no lock/save_callback provided
                        schedule['status'] = 'download_started'
                        schedule['next_check'] = None

                    # Download started, we're done
                    break

                time.sleep(1)

            # Cleanup
            logger.info(f"Closing browser for schedule {schedule['id']}")
            browser_service.close_browser(browser_id)

        except Exception as e:
            logger.error(f"Error in browser check task: {e}")
            try:
                browser_service.close_browser(browser_id)
            except:
                pass

    def _update_next_check(self, schedule):
        """
        Calculate next check time based on schedule window.

        Delegates to the appropriate time calculator based on schedule type
        (daily vs regular).

        Args:
            schedule (dict): The schedule to update
        """
        now = datetime.now()

        if schedule.get('daily'):
            self.daily_calculator.calculate_next_check(schedule, now)
        else:
            self.regular_calculator.calculate_next_check(schedule, now)
