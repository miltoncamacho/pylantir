"""
Data Source Plugin Registry

This module provides the plugin registry system for discovering and loading
data source plugins.

Version: 1.0.0
"""

from .base import DataSourcePlugin, PluginError, PluginConfigError, PluginFetchError
from .redcap_plugin import REDCapPlugin
from .calpendo_plugin import CalendoPlugin
from typing import Type, Dict, List
import logging

lgr = logging.getLogger(__name__)

# Plugin Registry - maps source type names to plugin classes
PLUGIN_REGISTRY: Dict[str, Type[DataSourcePlugin]] = {
    "redcap": REDCapPlugin,
    "calpendo": CalendoPlugin,
}


def register_plugin(source_type: str, plugin_class: Type[DataSourcePlugin]) -> None:
    """
    Register a plugin class in the registry.

    Args:
        source_type: Type identifier for the plugin (e.g., "redcap", "csv")
        plugin_class: Plugin class inheriting from DataSourcePlugin

    Raises:
        ValueError: If source_type already registered or plugin_class is invalid
    """
    if source_type in PLUGIN_REGISTRY:
        raise ValueError(f"Plugin type '{source_type}' is already registered")

    if not issubclass(plugin_class, DataSourcePlugin):
        raise ValueError(f"Plugin class must inherit from DataSourcePlugin")

    PLUGIN_REGISTRY[source_type] = plugin_class
    lgr.info(f"Registered plugin: {source_type} -> {plugin_class.__name__}")


def get_plugin(source_type: str) -> Type[DataSourcePlugin]:
    """
    Retrieve a plugin class from the registry.

    Args:
        source_type: Type identifier for the plugin

    Returns:
        Plugin class for instantiation

    Raises:
        ValueError: If source_type is not registered
    """
    if source_type not in PLUGIN_REGISTRY:
        available_types = list(PLUGIN_REGISTRY.keys())
        raise ValueError(
            f"Unknown data source type: '{source_type}'. "
            f"Available types: {available_types}"
        )

    return PLUGIN_REGISTRY[source_type]


def list_available_plugins() -> List[str]:
    """Return list of registered plugin type names."""
    return list(PLUGIN_REGISTRY.keys())


# Export public API
__all__ = [
    'DataSourcePlugin',
    'PluginError',
    'PluginConfigError',
    'PluginFetchError',
    'PLUGIN_REGISTRY',
    'register_plugin',
    'get_plugin',
    'list_available_plugins',
]
