# SPDX-License-Identifier: MIT
"""
High-level environment builders:
  - EnvironmentBuilder: scene setup, collections, render, orchestration glue
  - CoffeeShopBuilder: interior + exterior content assembly
"""

from __future__ import annotations

import logging
from typing import Optional

import bpy

from . import config, helpers
from .architecture import ArchitectureBuilder
from .coffee_bar import CoffeeBarBuilder
from .decor import DecorBuilder
from .exterior import ExteriorBuilder
from .furniture import FurnitureBuilder
from .material_manager import MaterialManager
from .texture_manager import TextureManager

logger = logging.getLogger(__name__)


class EnvironmentBuilder:
    """
    Prepares a clean Blender scene with professional collection hierarchy,
    unit scale, Cycles render settings, and shared managers.
    """

    def __init__(self, clear: bool = True):
        self.clear = clear
        self.collections = {}
        self.texture_manager: Optional[TextureManager] = None
        self.material_manager: Optional[MaterialManager] = None

    def setup(self) -> dict:
        if self.clear:
            helpers.clear_scene(keep_world=True)
        helpers.ensure_object_mode()
        self._configure_units()
        self.collections = helpers.setup_collection_hierarchy()
        helpers.frame_range()
        self.texture_manager = TextureManager()
        self.texture_manager.create_placeholder_structure()
        self.material_manager = MaterialManager(self.texture_manager)
        self.material_manager.create_all_materials()
        self.configure_cycles()
        logger.info("Environment setup complete")
        return self.collections

    def _configure_units(self) -> None:
        scene = bpy.context.scene
        scene.unit_settings.system = "METRIC"
        scene.unit_settings.scale_length = 1.0
        scene.unit_settings.length_unit = "METERS"
        # Unity-friendly: 1 Blender unit = 1 meter

    def configure_cycles(self) -> None:
        """Photoreal Cycles configuration: path tracing, denoising, GI, volumetrics."""
        scene = bpy.context.scene
        scene.render.engine = "CYCLES"
        cycles = scene.cycles
        cycles.samples = config.CYCLES_SAMPLES
        try:
            cycles.preview_samples = config.CYCLES_PREVIEW_SAMPLES
        except Exception:
            pass
        cycles.max_bounces = config.CYCLES_MAX_BOUNCES
        cycles.diffuse_bounces = config.CYCLES_DIFFUSE_BOUNCES
        cycles.glossy_bounces = config.CYCLES_GLOSSY_BOUNCES
        cycles.transmission_bounces = config.CYCLES_TRANSMISSION_BOUNCES
        cycles.volume_bounces = config.CYCLES_VOLUME_BOUNCES
        cycles.transparent_max_bounces = 8
        cycles.caustics_reflective = config.CYCLES_CAUSTICS
        cycles.caustics_refractive = config.CYCLES_CAUSTICS
        cycles.use_animated_seed = True

        # Device
        try:
            cycles.device = "GPU"
        except Exception:
            cycles.device = "CPU"

        # Denoising
        if config.USE_DENOISING:
            scene.cycles.use_denoising = True
            try:
                scene.cycles.denoiser = "OPENIMAGEDENOISE"
            except Exception:
                try:
                    scene.cycles.denoiser = "OPTIX"
                except Exception:
                    pass

        # Film / color
        scene.render.film_transparent = False
        scene.view_settings.view_transform = "Filmic"
        try:
            scene.view_settings.look = "Medium High Contrast"
        except Exception:
            pass
        scene.view_settings.exposure = 0.0
        scene.view_settings.gamma = 1.0

        # Resolution cinematic default
        scene.render.resolution_x = 1920
        scene.render.resolution_y = 1080
        scene.render.resolution_percentage = 100
        scene.render.fps = config.FPS

        # Light paths / clamping for photorealism without fireflies
        cycles.sample_clamp_direct = 0.0
        cycles.sample_clamp_indirect = 10.0
        try:
            cycles.use_fast_gi = False
        except Exception:
            pass

        logger.info(
            "Cycles configured: %d samples, %d bounces, denoising=%s",
            config.CYCLES_SAMPLES,
            config.CYCLES_MAX_BOUNCES,
            config.USE_DENOISING,
        )


class CoffeeShopBuilder:
    """
    Assembles the full cozy coffee shop: architecture, furniture, bar,
    decor, and exterior street visible through the windows.
    """

    def __init__(self, environment: EnvironmentBuilder):
        self.env = environment
        self.objects = []

    def build(self) -> list:
        mats = self.env.material_manager
        cols = self.env.collections
        if mats is None or not cols:
            raise RuntimeError("EnvironmentBuilder.setup() must be called first")

        logger.info("Building architecture...")
        arch = ArchitectureBuilder(mats, cols)
        self.objects.extend(arch.build())

        logger.info("Building furniture / seating...")
        furn = FurnitureBuilder(mats, cols)
        self.objects.extend(furn.build())

        logger.info("Building coffee bar...")
        bar = CoffeeBarBuilder(mats, cols)
        self.objects.extend(bar.build())

        logger.info("Building decor...")
        decor = DecorBuilder(mats, cols)
        self.objects.extend(decor.build())

        logger.info("Building exterior street...")
        exterior = ExteriorBuilder(mats, cols)
        self.objects.extend(exterior.build())

        logger.info("Coffee shop content built: %d objects", len(self.objects))
        return self.objects
