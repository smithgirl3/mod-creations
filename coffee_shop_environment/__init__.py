# SPDX-License-Identifier: MIT
"""
Cozy Coffee Shop Environment — Blender 5.2.0 Procedural Generator
================================================================
Production-quality procedural coffee shop for Unity game scenes.

Run from Blender Text Editor:
    Open CREATE_COZY_COFFEE_SHOP.py and click Run Script.

Or from Blender CLI:
    blender --background --python CREATE_COZY_COFFEE_SHOP.py
"""

__version__ = "1.0.0"
__blender_version__ = "5.2.0"

from .main import main

__all__ = ["main", "__version__"]
