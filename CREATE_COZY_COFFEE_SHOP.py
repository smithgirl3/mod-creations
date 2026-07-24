# SPDX-License-Identifier: MIT
"""
================================================================================
 CREATE_COZY_COFFEE_SHOP.py
 Hyperrealistic Rainy Coffee Shop — Blender 5.2.0 Procedural Environment
================================================================================

 HOW TO RUN (single click):
   1. Open Blender 5.2.0
   2. Go to the Scripting workspace
   3. Text Editor → Open → select this file
   4. Click "Run Script"

 CLI:
   blender --background --python CREATE_COZY_COFFEE_SHOP.py

 Calls main() which builds the full scene and runs export_for_unity().
================================================================================
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="[CoffeeShop] %(levelname)s: %(message)s")
log = logging.getLogger("bootstrap")


def _resolve_package_root() -> Path:
    """Locate the directory that contains the coffee_shop_environment package."""
    candidates = []

    try:
        candidates.append(Path(__file__).resolve().parent)
    except NameError:
        pass

    try:
        import bpy

        text = getattr(getattr(bpy.context, "space_data", None), "text", None)
        if text is None:
            text = bpy.data.texts.get("CREATE_COZY_COFFEE_SHOP.py")
        if text and getattr(text, "filepath", None):
            candidates.append(Path(bpy.path.abspath(text.filepath)).resolve().parent)
    except Exception:
        pass

    candidates.append(Path.cwd())

    for base in candidates:
        try:
            base = Path(base).resolve()
        except Exception:
            continue
        if (base / "coffee_shop_environment" / "__init__.py").exists():
            return base
        if base.name == "coffee_shop_environment" and (base / "__init__.py").exists():
            return base.parent

    raise RuntimeError(
        "Could not locate coffee_shop_environment/. "
        "Keep CREATE_COZY_COFFEE_SHOP.py next to that folder."
    )


def export_for_unity():
    """Export the current scene for Unity (FBX, GLB, textures, JSON)."""
    root = _resolve_package_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from coffee_shop_environment.export_manager import export_for_unity as _export

    return _export()


def main():
    """
    Required entry point — builds the environment and exports for Unity.
    """
    root = _resolve_package_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    log.info("Package root: %s", root)

    from coffee_shop_environment.main import main as build_main

    result = build_main(export=True, clear_scene=True)
    if not result.get("success"):
        raise RuntimeError(result.get("error") or "Coffee shop build failed")
    return result


# Execute on Run Script / CLI
if __name__ == "__main__":
    main()
