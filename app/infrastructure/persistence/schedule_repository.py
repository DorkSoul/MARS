"""Repository for schedule persistence operations."""

import os
import json
import logging
import threading
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class ScheduleRepository:
    """
    Repository for managing schedule persistence to/from JSON file.

    This class handles all CRUD operations for schedules, providing
    thread-safe access to the schedules file.
    """

    def __init__(self, config):
        """
        Initialize the schedule repository.

        Args:
            config: Configuration object containing SCHEDULES_FILE path
        """
        self.config = config
        self.lock = threading.Lock()
        self._schedules_cache = None

    def load_schedules(self) -> List[Dict]:
        """
        Load schedules from disk.

        Returns:
            List[Dict]: List of schedule dictionaries

        Note:
            Returns empty list if file doesn't exist or on error.
            Errors are logged but not raised.
        """
        with self.lock:
            if os.path.exists(self.config.SCHEDULES_FILE):
                try:
                    with open(self.config.SCHEDULES_FILE, 'r') as f:
                        schedules = json.load(f)
                    logger.info(f"Loaded {len(schedules)} schedules")
                    self._schedules_cache = schedules
                    return schedules
                except Exception as e:
                    logger.error(f"Error loading schedules: {e}")
                    self._schedules_cache = []
                    return []
            else:
                logger.info("No schedules file found, starting with empty list")
                self._schedules_cache = []
                return []

    def save_schedules(self, schedules: List[Dict]) -> None:
        """
        Save schedules to disk.

        Args:
            schedules: List of schedule dictionaries to save

        Note:
            Errors are logged but not raised to maintain existing behavior.
        """
        with self.lock:
            try:
                with open(self.config.SCHEDULES_FILE, 'w') as f:
                    json.dump(schedules, f, indent=2)
                self._schedules_cache = schedules
                logger.debug(f"Saved {len(schedules)} schedules to disk")
            except Exception as e:
                logger.error(f"Error saving schedules: {e}")

    def add_schedule(self, schedule: Dict) -> Dict:
        """
        Add a new schedule to the repository.

        Args:
            schedule: Schedule dictionary to add

        Returns:
            Dict: The added schedule

        Note:
            This method loads existing schedules, adds the new one,
            and saves them back to disk.
        """
        with self.lock:
            schedules = self._load_for_modification()
            schedules.append(schedule)
            self.save_schedules(schedules)
            logger.info(f"Added schedule {schedule.get('id')}")
            return schedule

    def remove_schedule(self, schedule_id: str) -> bool:
        """
        Remove a schedule from the repository.

        Args:
            schedule_id: ID of the schedule to remove

        Returns:
            bool: True if schedule was found and removed, False otherwise
        """
        with self.lock:
            schedules = self._load_for_modification()
            initial_count = len(schedules)
            schedules = [s for s in schedules if s['id'] != schedule_id]

            if len(schedules) < initial_count:
                self.save_schedules(schedules)
                logger.info(f"Removed schedule {schedule_id}")
                return True
            else:
                logger.warning(f"Schedule {schedule_id} not found for removal")
                return False

    def update_schedule(self, schedule_id: str, updates: Dict) -> Optional[Dict]:
        """
        Update an existing schedule with new values.

        Args:
            schedule_id: ID of the schedule to update
            updates: Dictionary of fields to update

        Returns:
            Optional[Dict]: Updated schedule if found, None otherwise
        """
        with self.lock:
            schedules = self._load_for_modification()

            for schedule in schedules:
                if schedule['id'] == schedule_id:
                    # Apply all updates
                    schedule.update(updates)
                    self.save_schedules(schedules)
                    logger.info(f"Updated schedule {schedule_id}")
                    return schedule

            logger.warning(f"Schedule {schedule_id} not found for update")
            return None

    def get_all_schedules(self) -> List[Dict]:
        """
        Get all schedules from the repository.

        Returns:
            List[Dict]: List of all schedule dictionaries

        Note:
            This loads fresh data from disk to ensure consistency.
        """
        return self.load_schedules()

    def get_schedule_by_id(self, schedule_id: str) -> Optional[Dict]:
        """
        Get a specific schedule by its ID.

        Args:
            schedule_id: ID of the schedule to retrieve

        Returns:
            Optional[Dict]: Schedule dictionary if found, None otherwise
        """
        schedules = self.get_all_schedules()
        for schedule in schedules:
            if schedule['id'] == schedule_id:
                return schedule
        return None

    def _load_for_modification(self) -> List[Dict]:
        """
        Load schedules for modification operations.

        Returns:
            List[Dict]: Fresh list of schedules from disk

        Note:
            This is an internal method that always loads fresh data
            to ensure consistency during modifications.
        """
        if os.path.exists(self.config.SCHEDULES_FILE):
            try:
                with open(self.config.SCHEDULES_FILE, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading schedules for modification: {e}")
                return []
        return []
