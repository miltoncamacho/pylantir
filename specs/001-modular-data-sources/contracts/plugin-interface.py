"""
Data Source Plugin Interface Contract

This module defines the abstract base class that all Pylantir data source
plugins must implement. It serves as the contract between the core sync
orchestration logic and plugin implementations.

Version: 1.0.0
Stability: Stable (no breaking changes allowed without major version bump)
Constitutional Compliance: Minimalist Dependencies (stdlib only)

USAGE:
    from pylantir.data_sources.base import DataSourcePlugin

    class MyPlugin(DataSourcePlugin):
        def validate_config(self, config):
            # Implementation
            return (True, "")

        def fetch_entries(self, field_mapping, interval):
            # Implementation
            return [{"patient_id": "...", ...}]

        def get_source_name(self):
            return "MySource"
"""

from abc import ABC, abstractmethod
from typing import Tuple, List, Dict, Optional
import logging

lgr = logging.getLogger(__name__)


class DataSourcePlugin(ABC):
    """
    Abstract base class for all data source plugins.

    Plugins provide the interface between external data sources (REDCap, CSV,
    databases, APIs) and Pylantir's worklist database. Each plugin is responsible
    for fetching, validating, and transforming data from its specific source into
    the standardized WorklistItem format.

    THREAD SAFETY:
        Plugins must be thread-safe as multiple instances may run concurrently
        when multiple sources are configured. Avoid shared mutable state.

    MEMORY MANAGEMENT:
        Plugins must follow Pylantir's memory efficiency patterns:
        - Avoid pandas DataFrames (use list[dict] instead)
        - Call gc.collect() explicitly in cleanup()
        - Process data in streaming fashion when possible
        - Follow example from redcap_to_db.py (50-100x memory improvement)

    EXAMPLE:
        class REDCapPlugin(DataSourcePlugin):
            def validate_config(self, config):
                required = ["site_id", "protocol"]
                for key in required:
                    if key not in config:
                        return (False, f"Missing required key: {key}")
                return (True, "")

            def fetch_entries(self, field_mapping, interval):
                # Fetch from REDCap API
                records = self._fetch_from_api(interval)

                # Transform to WorklistItem format
                entries = []
                for record in records:
                    entry = {}
                    for source_field, target_field in field_mapping.items():
                        if source_field in record:
                            entry[target_field] = record[source_field]
                    entries.append(entry)

                return entries

            def get_source_name(self):
                return "REDCap"
    """

    def __init__(self):
        """
        Initialize the plugin.

        Override to set up source-specific state (connections, clients, etc.).
        Remember to clean up in cleanup() method.

        EXAMPLE:
            def __init__(self):
                super().__init__()
                self._api_client = None
                self.logger.info(f"{self.get_source_name()} plugin initialized")
        """
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    def validate_config(self, config: Dict) -> Tuple[bool, str]:
        """
        Validate plugin-specific configuration before sync starts.

        Called once during Pylantir startup before any sync operations. Must
        check all required configuration keys, validate formats, and verify
        connectivity if applicable.

        IMPORTANT:
            - MUST NOT raise exceptions (return validation tuple instead)
            - SHOULD check all required config keys exist
            - SHOULD validate data types and formats
            - SHOULD test connectivity if network-based source
            - MAY cache validation results in instance variables

        Args:
            config: Dictionary from data_sources[].config in JSON configuration
                   Contains plugin-specific parameters like API tokens, file paths, etc.

        Returns:
            Tuple of (is_valid, error_message) where:
                - is_valid (bool): True if config is valid, False otherwise
                - error_message (str): Human-readable error description if invalid,
                                      empty string "" if valid

        Examples:
            # Valid configuration
            >>> plugin.validate_config({"api_token": "abc123", "site_id": "792"})
            (True, "")

            # Invalid configuration - missing key
            >>> plugin.validate_config({"api_token": "abc123"})
            (False, "Missing required configuration key: site_id")

            # Invalid configuration - wrong type
            >>> plugin.validate_config({"site_id": 123})
            (False, "site_id must be a string, got int")

            # Invalid configuration - connectivity test failed
            >>> plugin.validate_config({"api_url": "https://invalid.example.com"})
            (False, "Failed to connect to API: Connection timeout")
        """
        pass

    @abstractmethod
    def fetch_entries(
        self,
        field_mapping: Dict[str, str],
        interval: float
    ) -> List[Dict]:
        """
        Fetch worklist entries from the data source.

        Called repeatedly according to sync_interval. Must return data in a
        standardized format where keys are WorklistItem field names (after
        applying field_mapping).

        IMPORTANT:
            - MUST return list of dicts (NOT pandas DataFrame)
            - MUST apply field_mapping to transform source fields to WorklistItem fields
            - MUST handle interval parameter for incremental sync (if supported)
            - SHOULD log fetch statistics (number of entries, time taken)
            - SHOULD call gc.collect() before returning for memory efficiency
            - MAY raise exceptions (caught and logged by orchestration layer)

        Args:
            field_mapping: Maps source field names to WorklistItem field names
                          Example: {"source_patient_id": "patient_id",
                                   "source_dob": "patient_birth_date"}

            interval: Seconds since last sync. Plugins supporting incremental
                     sync should only fetch records modified in this window.
                     Use full sync if supports_incremental_sync() returns False.

        Returns:
            List of dictionaries where each dict represents one worklist entry.
            Dictionary keys must be WorklistItem field names (patient_id, patient_name,
            patient_birth_date, patient_sex, modality, scheduled_start_date, etc.)

            Required fields in each dict:
                - patient_id: Unique patient identifier
                - patient_name: Patient name in DICOM format
                - patient_birth_date: Birth date as YYYYMMDD string
                - patient_sex: Sex as M/F/O string
                - modality: Imaging modality (e.g., "MR", "CT")
                - scheduled_start_date: Exam date as YYYYMMDD string
                - scheduled_start_time: Exam time as HHMMSS string

        Raises:
            Any exceptions are caught by orchestration layer and logged. Plugins
            should not catch their own exceptions unless performing cleanup.
            Let exceptions propagate to enable proper error handling and logging.

        Examples:
            # Fetch and transform entries
            >>> field_mapping = {"pid": "patient_id", "dob": "patient_birth_date"}
            >>> entries = plugin.fetch_entries(field_mapping, interval=60.0)
            >>> entries
            [
                {
                    "patient_id": "12345",
                    "patient_name": "Doe^John",
                    "patient_birth_date": "19900101",
                    "patient_sex": "M",
                    "modality": "MR",
                    "scheduled_start_date": "20260126",
                    "scheduled_start_time": "140000"
                },
                {
                    "patient_id": "67890",
                    "patient_name": "Smith^Jane",
                    "patient_birth_date": "19850615",
                    "patient_sex": "F",
                    "modality": "MR",
                    "scheduled_start_date": "20260126",
                    "scheduled_start_time": "150000"
                }
            ]
        """
        pass

    @abstractmethod
    def get_source_name(self) -> str:
        """
        Return human-readable source type identifier.

        Used for logging, database source tracking, and error reporting.
        Should be concise, descriptive, and consistent across plugin instances.

        IMPORTANT:
            - MUST return non-empty string
            - SHOULD be concise (5-20 characters)
            - SHOULD match plugin class name pattern (e.g., "REDCap" for REDCapPlugin)
            - MUST be consistent (always return same value for same plugin type)

        Returns:
            String identifier for this source type (e.g., "REDCap", "CSV", "PostgreSQL")

        Examples:
            >>> plugin.get_source_name()
            "REDCap"

            >>> csv_plugin.get_source_name()
            "CSV"

            >>> db_plugin.get_source_name()
            "PostgreSQL"
        """
        pass

    def supports_incremental_sync(self) -> bool:
        """
        Indicate whether this plugin supports incremental synchronization.

        Incremental sync means the plugin can efficiently fetch only records
        that changed since the last sync, using the interval parameter in
        fetch_entries().

        Default implementation returns False (full sync every interval).
        Override to return True if plugin implements incremental logic.

        INCREMENTAL SYNC REQUIREMENTS:
            If returning True, fetch_entries() must:
            - Use interval parameter to filter records
            - Only return new/modified records within interval window
            - Handle edge cases (first sync, interval > record age, etc.)

        FULL SYNC (default):
            If returning False, fetch_entries() must:
            - Ignore interval parameter (or use for logging only)
            - Return all relevant records on every sync
            - Handle duplicate detection at database layer

        Returns:
            True if plugin supports incremental sync, False otherwise

        Examples:
            # REDCap plugin supports incremental sync via date filtering
            class REDCapPlugin(DataSourcePlugin):
                def supports_incremental_sync(self):
                    return True

                def fetch_entries(self, field_mapping, interval):
                    # Fetch only records modified in last `interval` seconds
                    date_begin = datetime.now() - timedelta(seconds=interval)
                    records = self._api.export_records(date_begin=date_begin)
                    ...

            # CSV plugin doesn't support incremental (reads full file)
            class CSVPlugin(DataSourcePlugin):
                def supports_incremental_sync(self):
                    return False  # Default

                def fetch_entries(self, field_mapping, interval):
                    # Always read full CSV file (interval ignored)
                    records = self._read_csv_file()
                    ...
        """
        return False

    def cleanup(self) -> None:
        """
        Perform cleanup after each sync cycle.

        Called after fetch_entries() completes (success or failure). Use for
        closing connections, freeing memory, or other resource cleanup.

        Default implementation is no-op. Override to implement source-specific
        cleanup logic.

        IMPORTANT:
            - MUST NOT raise exceptions (wrap in try/except if needed)
            - SHOULD close network connections
            - SHOULD free large memory allocations
            - SHOULD call gc.collect() for memory efficiency
            - MAY reset instance state for next sync

        MEMORY EFFICIENCY PATTERN:
            Follow Pylantir's memory optimization pattern:
            1. Delete large data structures explicitly (del variable)
            2. Call gc.collect() to free memory immediately
            3. Log memory usage before/after if psutil available

        Examples:
            # Close API connection and free memory
            def cleanup(self):
                try:
                    if hasattr(self, '_api_client') and self._api_client:
                        self._api_client.close()
                        del self._api_client

                    # Force garbage collection
                    import gc
                    gc.collect()

                    self.logger.debug(f"{self.get_source_name()} cleanup complete")
                except Exception as e:
                    self.logger.warning(f"Cleanup error: {e}")

            # Close file handles
            def cleanup(self):
                if hasattr(self, '_file_handle'):
                    self._file_handle.close()
                    del self._file_handle
        """
        pass


class PluginError(Exception):
    """
    Base exception for plugin-related errors.

    All plugin-specific exceptions should inherit from this class to enable
    catch-all error handling in orchestration layer.
    """
    pass


class PluginConfigError(PluginError):
    """
    Raised when plugin configuration is invalid.

    NOTE: Plugins should prefer returning (False, error_msg) from validate_config()
    instead of raising this exception. This exception is for runtime config errors
    discovered during fetch operations.

    Example:
        def fetch_entries(self, field_mapping, interval):
            if not os.getenv("API_TOKEN"):
                raise PluginConfigError("API_TOKEN environment variable not set")
    """
    pass


class PluginFetchError(PluginError):
    """
    Raised when plugin fails to fetch data from source.

    Use for network errors, API failures, parse errors, or other fetch-time issues.

    Example:
        def fetch_entries(self, field_mapping, interval):
            try:
                response = requests.get(self.api_url)
                response.raise_for_status()
            except requests.HTTPError as e:
                raise PluginFetchError(f"API request failed: {e}") from e
    """
    pass


# Future plugin types (not implemented in Phase 1)
# Documented here for reference in future development

class CSVPlugin(DataSourcePlugin):
    """
    Placeholder for CSV file data source plugin.

    PLANNED FEATURES:
    - Read worklist entries from CSV file
    - Watch for file changes (inotify/fswatch)
    - Support custom field mappings
    - Validate CSV schema at startup

    PHASE: P2 (Future implementation)
    """
    pass


class JSONPlugin(DataSourcePlugin):
    """
    Placeholder for JSON file data source plugin.

    PLANNED FEATURES:
    - Read worklist entries from JSON file
    - Support both JSON array and JSONL formats
    - Watch for file changes
    - Validate JSON schema at startup

    PHASE: P2 (Future implementation)
    """
    pass
