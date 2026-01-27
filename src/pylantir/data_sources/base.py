"""
Data Source Plugin Interface

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
from typing import Tuple, List, Dict
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
    """

    def __init__(self):
        """Initialize the plugin. Override to set up source-specific state."""
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    def validate_config(self, config: Dict) -> Tuple[bool, str]:
        """
        Validate plugin-specific configuration before sync starts.

        Args:
            config: Dictionary from data_sources[].config in JSON configuration

        Returns:
            Tuple of (is_valid, error_message) where error_message is "" if valid
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

        Args:
            field_mapping: Maps source field names to WorklistItem field names
            interval: Seconds since last sync (for incremental sync support)

        Returns:
            List of dictionaries with WorklistItem field names as keys
        """
        pass

    @abstractmethod
    def get_source_name(self) -> str:
        """Return human-readable source type identifier (e.g., 'REDCap')."""
        pass

    def supports_incremental_sync(self) -> bool:
        """Override to return True if plugin supports incremental sync."""
        return False

    def cleanup(self) -> None:
        """Perform cleanup after sync (close connections, free memory)."""
        pass


class PluginError(Exception):
    """Base exception for plugin-related errors."""
    pass


class PluginConfigError(PluginError):
    """Raised when plugin configuration is invalid."""
    pass


class PluginFetchError(PluginError):
    """Raised when plugin fails to fetch data from source."""
    pass
