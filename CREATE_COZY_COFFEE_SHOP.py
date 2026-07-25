# SPDX-License-Identifier: MIT
"""
================================================================================
 CREATE_COZY_COFFEE_SHOP.py
 Hyperrealistic Rainy Coffee Shop — Blender 5.2.0 Procedural Environment
================================================================================

 HOW TO RUN (single click):
   1. Open Blender 5.2.0
   2. Go to the Scripting workspace
   3. Text Editor → Open → select this file FROM DISK (File → Open)
   4. Click "Run Script"

 IMPORTANT: After pulling updates, either:
   - Restart Blender, or
   - Re-open this file from disk and Run Script again
   (Blender caches imported Python modules between runs.)

 CLI:
   blender --background --python CREATE_COZY_COFFEE_SHOP.py
================================================================================
"""

from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="[CoffeeShop] %(levelname)s: %(message)s")
log = logging.getLogger("bootstrap")

# Bump whenever bootstrap / package load behavior changes — printed at run time
BOOTSTRAP_REVISION = "2026-07-24-reload-fix"


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
            fp = text.filepath.strip()
            if fp:
                candidates.append(Path(bpy.path.abspath(fp)).resolve().parent)
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
        "Keep CREATE_COZY_COFFEE_SHOP.py next to that folder, and open the script "
        "from disk (Text Editor → Open) so its filepath is set."
    )


def _purge_package_modules() -> None:
    """
    Remove cached coffee_shop_environment modules so Blender Text Editor
    re-imports from disk on every Run Script (avoids stale use_multiplier code).
    """
    doomed = [
        name
        for name in list(sys.modules)
        if name == "coffee_shop_environment" or name.startswith("coffee_shop_environment.")
    ]
    for name in doomed:
        del sys.modules[name]
    if doomed:
        log.info("Purged %d cached package module(s) for fresh import", len(doomed))


def _verify_weather_module(root: Path) -> Path:
    """Fail fast if an outdated weather_system.py is about to be loaded."""
    weather_path = root / "coffee_shop_environment" / "weather_system.py"
    if not weather_path.exists():
        raise RuntimeError(f"Missing {weather_path}")

    source = weather_path.read_text(encoding="utf-8")
    # Reject the old broken assignment (comment mentions are OK)
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "use_multiplier" in stripped:
            raise RuntimeError(
                f"Outdated weather_system.py still assigns use_multiplier:\n"
                f"  {weather_path}\n"
                f"  Offending line: {stripped}\n"
                f"Pull the latest branch (cursor/coffee-shop-blender-env-3e17) "
                f"and restart Blender."
            )

    if "_configure_rain_particle_settings" not in source:
        raise RuntimeError(
            f"weather_system.py at {weather_path} is outdated "
            f"(missing _configure_rain_particle_settings). Pull latest and restart Blender."
        )

    log.info("Using weather_system.py: %s", weather_path)
    return weather_path


def export_for_unity():
    """Export the current scene for Unity (FBX, GLB, textures, JSON)."""
    root = _resolve_package_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    _purge_package_modules()
    from coffee_shop_environment.export_manager import export_for_unity as _export

    return _export()


def main():
    """
    Required entry point — builds the environment and exports for Unity.
    Always reloads package modules from disk (Blender Text Editor safe).
    """
    log.info("Bootstrap revision: %s", BOOTSTRAP_REVISION)
    root = _resolve_package_root()
    root_str = str(root)
    # Prefer this package root over any other install on sys.path
    if root_str in sys.path:
        sys.path.remove(root_str)
    sys.path.insert(0, root_str)
    log.info("Package root: %s", root)

    _verify_weather_module(root)
    _purge_package_modules()

    from coffee_shop_environment.main import main as build_main
    from coffee_shop_environment import weather_system as _ws

    log.info("Imported weather_system from: %s", getattr(_ws, "__file__", "?"))
    # Ensure the imported module matches disk (guards against odd path shadows)
    importlib.reload(_ws)

    result = build_main(export=True, clear_scene=True)
    if not result.get("success"):
        err = result.get("error") or "Coffee shop build failed"
        raise RuntimeError(
            f"{err}\n"
            f"(bootstrap={BOOTSTRAP_REVISION}, root={root})\n"
            f"If this mentions use_multiplier, you are still on an old package — "
            f"git pull and restart Blender."
        )
    return result


# Execute on Run Script / CLI
if __name__ == "__main__":
    main()
