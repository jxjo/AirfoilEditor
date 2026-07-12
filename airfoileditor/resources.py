#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Resource management helper

Supports both pip-installed packages and PyInstaller frozen executables.
"""

import sys
from pathlib import Path
from typing import Optional

# subdirectory for resources in PyInstaller frozen executable onedir mode
FROZEN_RESOURCES_SUBDIR   = '_internal/airfoileditor'

# directory for xo2 examples relative to resources directory
XO2_EXAMPLE_DIR             = "examples_optimize"


def _is_frozen() -> bool:
    """Check if running as PyInstaller frozen executable."""
    return getattr(sys, 'frozen', False)


def _is_resource_root(path: Path) -> bool:
    """A valid resource root contains at least one expected subdirectory."""
    return any((path / subdir).is_dir() for subdir in ("icons", "assets", XO2_EXAMPLE_DIR))


def get_resources_root() -> Optional[Path]:
    """Resolve the resource root for frozen, pip, and development layouts."""
    if _is_frozen():
        exe_dir = Path(sys.executable).parent
        for candidate in (
            exe_dir / FROZEN_RESOURCES_SUBDIR,
            exe_dir / "_internal",
            exe_dir,
        ):
            if _is_resource_root(candidate):
                return candidate
        return None

    for candidate in (
        Path(__file__).parent,
        Path(__file__).parent.parent,
    ):
        if _is_resource_root(candidate):
            return candidate

    return None


def _get_resources_dir_pip() -> Path:
    """ Get resources directory for pip-installed package."""
    return Path(__file__).parent


def _get_resources_dir_dev() -> Path:
    """ Get resources directory for local development"""
    return Path(__file__).parent.parent



def get_resource_path(resource_type: str, *path_parts: str) -> Path:
    """
    Get path to a resource (icon, template, example).
    
    Works for pip packages, dev mode and PyInstaller executables.
    
    Args:
        resource_type: 'icons', 'templates', or 'examples'
        *path_parts: Additional path components (e.g., 'PC2.ico')
    
    Returns:
        Path to the resource
        
    Examples:
        >>> get_resource_path('icons', 'PC2.ico')
        >>> get_resource_path('examples', 'VJX.glide', 'VJX.glide.pc2')
    """
    base = get_resources_root()
    if base is None:
        # Safe fallback keeps previous behavior for unexpected layouts.
        base = _get_resources_dir_pip()
        if not (base / resource_type).exists():
            base = _get_resources_dir_dev()
    
    resource_path = base / resource_type / Path(*path_parts) if path_parts else base / resource_type

    return resource_path


def get_icon_path(icon_file_name: str) -> Path:
    """
    Get path to an icon file.
    """
    if icon_file_name:
        icon_path = get_resource_path('icons', icon_file_name)
        if icon_path.is_file():
            return icon_path
    return None


def get_icons_path() -> Path:
    """Get the icons directory path."""
    return get_resource_path('icons')


def get_template_dir() -> Path:
    """Get the templates directory path."""
    return get_resource_path('templates')


def get_examples_dir() -> Path:
    """Get the examples directory path."""
    return get_resource_path('examples')


def get_assets_dir() -> Path:
    """Get the assets directory path."""
    return get_resource_path('assets')


def get_xo2_examples_dir() -> Path:
    """Get the xo2 examples directory path."""
    return get_resource_path('examples_optimize')


def get_icon_as_string(icon_name: str) -> str:
    """
    Get icon path as string for compatibility with existing code.
    
    Args:
        icon_name: Icon filename
        
    Returns:
        Path as string
    """
    return str(get_icon_path(icon_name))

