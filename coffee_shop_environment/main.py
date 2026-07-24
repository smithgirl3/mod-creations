# SPDX-License-Identifier: MIT
"""
Main entry point for the Cozy Coffee Shop procedural environment.

Run from Blender's Text Editor via CREATE_COZY_COFFEE_SHOP.py,
or call main() from the package.
"""

from __future__ import annotations

import logging
import sys
import traceback
from typing import Optional

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[CoffeeShop] %(levelname)s: %(message)s",
)
logger = logging.getLogger("coffee_shop")


def main(export: bool = True, clear_scene: bool = True) -> dict:
    """
    Build the complete hyperrealistic rainy coffee shop environment.

    Automatically:
      1. Builds the environment shell & collections
      2. Generates all PBR materials (+ AI texture hooks)
      3. Creates architecture, furniture, bar, decor, exterior
      4. Creates weather systems (rain, wind, puddles, lightning, thunder, steam)
      5. Adds cinematic lighting
      6. Configures physics
      7. Generates animations
      8. Configures cameras + 30s cinematic sequence
      9. Optimizes assets (LOD / poly tiers / texture metadata)
     10. Exports for Unity via export_for_unity()

    Returns a summary dict of what was created.
    """
    summary = {
        "success": False,
        "objects": 0,
        "materials": 0,
        "cameras": 0,
        "lights": 0,
        "exports": [],
        "error": None,
    }

    try:
        import bpy  # noqa: F401 — ensure we are inside Blender
    except ImportError:
        summary["error"] = "This script must be run inside Blender 5.2.0 (bpy not found)."
        logger.error(summary["error"])
        return summary

    try:
        from .builders import CoffeeShopBuilder, EnvironmentBuilder
        from .weather_system import WeatherSystem
        from .lighting_system import LightingSystem
        from .physics_system import PhysicsSystem
        from .animation_system import AnimationSystem
        from .camera_system import CameraSystem
        from .optimization import OptimizationSystem
        from .export_manager import export_for_unity
        from . import config

        logger.info("=" * 60)
        logger.info("Cozy Coffee Shop Environment Generator v1.0")
        logger.info("Target: Blender 5.2.0 | Unity export pipeline")
        logger.info("=" * 60)

        # 1–2. Environment + materials
        env = EnvironmentBuilder(clear=clear_scene)
        collections = env.setup()
        summary["materials"] = len(env.material_manager.materials) if env.material_manager else 0

        # 3. Shop content
        shop = CoffeeShopBuilder(env)
        shop_objects = shop.build()
        summary["objects"] = len(shop_objects)

        # 4. Weather
        logger.info("Creating weather systems...")
        weather = WeatherSystem(env.material_manager, collections)
        weather.build()

        # 5. Lighting
        logger.info("Creating cinematic lighting...")
        lighting = LightingSystem(collections)
        lights = lighting.build()
        summary["lights"] = len(lights)

        # 6. Physics
        logger.info("Configuring physics...")
        physics = PhysicsSystem(collections)
        physics.build()

        # 7. Animations
        logger.info("Generating animations...")
        anim = AnimationSystem()
        anim.build()

        # 8. Cameras
        logger.info("Configuring cameras...")
        cameras = CameraSystem(collections)
        cams = cameras.build()
        summary["cameras"] = len(cams)

        # 9. Optimization
        logger.info("Optimizing game-ready assets / LODs...")
        opt = OptimizationSystem(collections)
        opt.build()

        # 10. Export
        if export:
            logger.info("Exporting for Unity...")
            try:
                exports = export_for_unity()
                summary["exports"] = exports
            except Exception as exc:
                logger.error("Export failed (scene still built): %s", exc)
                summary["exports"] = []
                summary["export_error"] = str(exc)

        # Store summary on scene
        import bpy
        bpy.context.scene["coffee_shop_build_summary"] = {
            k: (v if not isinstance(v, list) else len(v) if k == "exports" else v)
            for k, v in summary.items()
            if k != "exports"
        }
        bpy.context.scene["coffee_shop_export_count"] = len(summary["exports"])

        summary["success"] = True
        logger.info("=" * 60)
        logger.info(
            "DONE — objects≈%d materials=%d lights=%d cameras=%d exports=%d",
            summary["objects"],
            summary["materials"],
            summary["lights"],
            summary["cameras"],
            len(summary["exports"]),
        )
        logger.info("Active cinematic camera: CAM_Cinematic")
        logger.info("=" * 60)
        return summary

    except Exception as exc:
        summary["error"] = str(exc)
        logger.error("Build failed: %s", exc)
        logger.error(traceback.format_exc())
        return summary


if __name__ == "__main__":
    # Allow `blender --python main.py` when package is on sys.path
    result = main()
    if not result.get("success"):
        sys.exit(1)
