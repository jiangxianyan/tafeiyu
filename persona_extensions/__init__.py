"""Shared persona-extension support for the launcher and AstrBot plugin."""

from .core import (
    PluginError,
    build_plugin_prompt,
    inspect_plugin_package,
    install_plugin_package,
    list_installed_plugins,
    set_plugin_enabled,
    uninstall_plugin,
)

__all__ = [
    "PluginError",
    "build_plugin_prompt",
    "inspect_plugin_package",
    "install_plugin_package",
    "list_installed_plugins",
    "set_plugin_enabled",
    "uninstall_plugin",
]
