# SPDX-License-Identifier: MIT
"""
Weather system: rain particles, wind, puddles, lightning, thunder markers.
"""

from __future__ import annotations

import logging
import math
import random
from typing import List, Optional, Tuple

import bpy
from mathutils import Vector

from . import config, helpers
from .material_manager import MaterialManager

logger = logging.getLogger(__name__)


class WeatherSystem:
    """Heavy rainstorm atmosphere for the cozy coffee shop scene."""

    def __init__(
        self,
        materials: MaterialManager,
        collections: dict,
        intensity: float = config.RAIN_INTENSITY,
        seed: int = config.RANDOM_SEED,
    ):
        self.mat = materials
        self.cols = collections
        self.intensity = max(0.0, min(1.0, intensity))
        self.rng = random.Random(seed + 77)
        self.objects: List[bpy.types.Object] = []
        self.lightning_light: Optional[bpy.types.Object] = None
        self.thunder_markers: List[int] = []

    def build(self) -> List[bpy.types.Object]:
        self.objects.clear()
        self._create_rain()
        self._create_puddles()
        self._create_wet_streets_sheen()
        self._create_wind_forces()
        self._create_lightning()
        self._create_thunder_markers()
        self._create_steam_emitters()
        return self.objects

    def set_intensity(self, intensity: float) -> None:
        """Adjustable rain intensity (0..1). Updates particle counts when possible."""
        self.intensity = max(0.0, min(1.0, intensity))
        rain = bpy.data.objects.get("WEATHER_RainEmitter")
        if rain and rain.particle_systems:
            ps = rain.particle_systems[0]
            ps.settings.count = int(config.RAIN_PARTICLE_COUNT * self.intensity)

    def _link(self, obj, key: str = "Rain"):
        helpers.link_object_to_collection(obj, self.cols.get(key, key))
        self.objects.append(obj)
        return obj

    # ------------------------------------------------------------------
    # Rain
    # ------------------------------------------------------------------

    def _create_rain(self) -> None:
        """Particle-based rain with collision-enabled droplets."""
        # Emitter plane above street + shop
        emitter = helpers.create_plane(
            "WEATHER_RainEmitter",
            size=max(config.EXTERIOR_EXTENT, config.SHOP_WIDTH) + 10.0,
            location=(0, -config.SHOP_DEPTH * 0.25, config.SHOP_HEIGHT + 8.0),
        )
        # Hide emitter geometry visually
        emitter.display_type = "WIRE"
        self._link(emitter, "Rain")

        helpers.set_active(emitter)
        try:
            bpy.ops.object.particle_system_add()
        except RuntimeError as exc:
            logger.warning("Particle system add failed: %s", exc)
            self._create_mesh_rain_fallback()
            return

        ps = emitter.particle_systems[-1]
        ps.name = "RainParticles"
        settings = ps.settings
        settings.name = "RainParticleSettings"
        settings.type = "EMITTER"
        settings.count = int(config.RAIN_PARTICLE_COUNT * self.intensity)
        settings.frame_start = 1
        settings.frame_end = config.CINEMATIC_FRAME_END
        settings.lifetime = 40
        settings.lifetime_random = 0.3
        settings.emit_from = "FACE"
        settings.normal_factor = -2.5
        settings.factor_random = 0.2
        settings.particle_size = 0.015
        settings.size_random = 0.4
        settings.brownian_factor = 0.05 * config.WIND_STRENGTH
        try:
            settings.effector_weights.gravity = 1.0
            settings.effector_weights.wind = 1.0
        except Exception:
            pass
        # Collision
        settings.use_multiplier = True
        try:
            settings.collision_collection = None
        except Exception:
            pass

        # Droplet instance object
        drop = helpers.create_uv_sphere(
            "WEATHER_RainDropInstance",
            radius=0.012,
            segments=6,
            rings=4,
            location=(0, 0, -50),
        )
        helpers.assign_material(drop, self.mat.get("MAT_WaterPuddle"))
        drop.hide_render = True
        drop.hide_viewport = True
        self._link(drop, "Rain")
        try:
            settings.render_type = "OBJECT"
            settings.instance_object = drop
        except Exception:
            settings.render_type = "HALO"

        # Collision ground for rain
        ground = bpy.data.objects.get("EXT_Road") or bpy.data.objects.get("ARCH_Floor")
        if ground:
            helpers.set_active(ground)
            try:
                bpy.ops.object.modifier_add(type="COLLISION")
            except RuntimeError:
                mod = ground.modifiers.new(name="Collision", type="COLLISION")
                _ = mod

    def _create_mesh_rain_fallback(self) -> None:
        """Instanced streak meshes if particles unavailable."""
        count = int(2000 * self.intensity)
        for i in range(count):
            streak = helpers.create_cube(
                f"WEATHER_RainStreak_{i}",
                size=(0.005, 0.005, self.rng.uniform(0.15, 0.4)),
                location=(
                    self.rng.uniform(-20, 20),
                    self.rng.uniform(-25, 5),
                    self.rng.uniform(1, 10),
                ),
            )
            helpers.assign_material(streak, self.mat.get("MAT_WaterPuddle"))
            self._link(streak, "Rain")

    # ------------------------------------------------------------------
    # Puddles / wet streets
    # ------------------------------------------------------------------

    def _create_puddles(self) -> None:
        front = -config.SHOP_DEPTH * 0.5
        for i in range(config.PUDDLE_COUNT):
            scale = self.rng.uniform(0.4, 1.8)
            puddle = helpers.create_cylinder(
                f"WEATHER_Puddle_{i}",
                radius=scale,
                depth=0.008,
                vertices=24,
                location=(
                    self.rng.uniform(-18, 18),
                    front - self.rng.uniform(0.5, config.SIDEWALK_WIDTH + config.STREET_WIDTH),
                    -0.03,
                ),
            )
            helpers.assign_material(puddle, self.mat.get("MAT_WaterPuddle"))
            helpers.shade_smooth(puddle)
            puddle.scale.x = self.rng.uniform(0.7, 1.4)
            puddle.scale.y = self.rng.uniform(0.6, 1.3)
            self._link(puddle, "Puddles")

    def _create_wet_streets_sheen(self) -> None:
        """Thin reflective plane over sidewalk for wet look."""
        front = -config.SHOP_DEPTH * 0.5
        sheen = helpers.create_plane(
            "WEATHER_WetSheen",
            size=1.0,
            location=(0, front - config.SIDEWALK_WIDTH * 0.5, 0.005),
        )
        sheen.scale = (config.EXTERIOR_EXTENT * 0.5, config.SIDEWALK_WIDTH * 0.5, 1)
        helpers.apply_transforms(sheen, location=False, rotation=False, scale=True)
        helpers.assign_material(sheen, self.mat.get("MAT_WaterPuddle"))
        self._link(sheen, "Puddles")

    # ------------------------------------------------------------------
    # Wind
    # ------------------------------------------------------------------

    def _create_wind_forces(self) -> None:
        bpy.ops.object.effector_add(type="WIND", location=(0, -15, 3))
        wind = bpy.context.active_object
        wind.name = "WEATHER_Wind"
        wind.field.strength = 1.5 * config.WIND_STRENGTH * self.intensity
        wind.field.flow = 0.5
        wind.field.noise = 0.4
        wind.rotation_euler = (math.radians(90), 0, math.radians(15))
        self._link(wind, "Wind")

        # Turbulence for hanging plants / decorations
        bpy.ops.object.effector_add(type="TURBULENCE", location=(0, 0, 2))
        turb = bpy.context.active_object
        turb.name = "WEATHER_Turbulence"
        turb.field.strength = 0.8 * config.WIND_STRENGTH
        turb.field.size = 1.5
        self._link(turb, "Wind")

        # Animate subtle wind strength
        scene = bpy.context.scene
        for frame in range(1, config.CINEMATIC_FRAME_END + 1, 12):
            t = frame / config.FPS
            strength = 1.5 * config.WIND_STRENGTH * self.intensity * (
                0.85 + 0.15 * math.sin(t * 1.7) + 0.1 * math.sin(t * 3.1)
            )
            wind.field.strength = strength
            wind.field.keyframe_insert(data_path="strength", frame=frame)

    # ------------------------------------------------------------------
    # Lightning / thunder
    # ------------------------------------------------------------------

    def _create_lightning(self) -> None:
        bpy.ops.object.light_add(type="SUN", location=(5, -30, 25))
        light = bpy.context.active_object
        light.name = "WEATHER_Lightning"
        light.data.energy = 0.0
        light.data.color = config.LIGHTNING_COLOR
        light.rotation_euler = (math.radians(45), math.radians(10), math.radians(-20))
        self.lightning_light = light
        self._link(light, "Lightning")

        # Periodic random flashes
        frame = 30
        while frame < config.CINEMATIC_FRAME_END - 20:
            interval = self.rng.randint(config.LIGHTNING_MIN_INTERVAL, config.LIGHTNING_MAX_INTERVAL)
            flash_peak = self.rng.uniform(40.0, 120.0)
            # Keyframes: off -> peak -> secondary flicker -> off
            light.data.energy = 0.0
            light.data.keyframe_insert(data_path="energy", frame=frame)
            light.data.energy = flash_peak
            light.data.keyframe_insert(data_path="energy", frame=frame + 1)
            light.data.energy = flash_peak * 0.15
            light.data.keyframe_insert(data_path="energy", frame=frame + 3)
            light.data.energy = flash_peak * self.rng.uniform(0.4, 0.9)
            light.data.keyframe_insert(data_path="energy", frame=frame + 5)
            light.data.energy = 0.0
            light.data.keyframe_insert(data_path="energy", frame=frame + 8)

            # Interpolation: constant-ish flashes
            if light.data.animation_data and light.data.animation_data.action:
                self._set_constant_interpolation(light.data)

            thunder_frame = frame + config.THUNDER_DELAY_FRAMES + self.rng.randint(0, 10)
            self.thunder_markers.append(thunder_frame)
            frame += interval

    def _set_constant_interpolation(self, datablock) -> None:
        try:
            action = datablock.animation_data.action
            # Blender 4.4+/5.x may use layered actions; handle both
            fcurves = getattr(action, "fcurves", None)
            if fcurves is None and hasattr(action, "layers"):
                return
            for fc in fcurves or []:
                for kp in fc.keyframe_points:
                    kp.interpolation = "CONSTANT"
        except Exception as exc:
            logger.debug("Keyframe interpolation skip: %s", exc)

    def _create_thunder_markers(self) -> None:
        """Timeline markers for thunder audio sync in Unity / Blender VSE."""
        scene = bpy.context.scene
        # Clear old thunder markers
        for m in list(scene.timeline_markers):
            if m.name.startswith("THUNDER_"):
                scene.timeline_markers.remove(m)
        for i, f in enumerate(self.thunder_markers):
            scene.timeline_markers.new(f"THUNDER_{i:02d}", frame=f)
        # Also store on empty for export
        empty = helpers.add_empty("WEATHER_ThunderSync", location=(0, 0, 5))
        empty["thunder_frames"] = self.thunder_markers
        self._link(empty, "Lightning")

    # ------------------------------------------------------------------
    # Coffee steam
    # ------------------------------------------------------------------

    def _create_steam_emitters(self) -> None:
        """Volumetric-style steam from espresso machine and cups."""
        emitters = [
            ("Steam_Espresso", (0.5, config.SHOP_DEPTH * 0.5 - 2.35, 1.35)),
            ("Steam_Cup_A", (-2.0, config.SHOP_DEPTH * 0.5 - 2.75, 1.12)),
            ("Steam_Cup_B", (1.0, config.SHOP_DEPTH * 0.5 - 2.75, 1.12)),
            ("Steam_WindowMug_0", (-4.5, -config.SHOP_DEPTH * 0.5 + 1.8, 0.9)),
            ("Steam_WindowMug_1", (-0.5, -config.SHOP_DEPTH * 0.5 + 1.8, 0.9)),
        ]
        for name, loc in emitters:
            emitter = helpers.create_uv_sphere(name, radius=0.05, segments=8, rings=4, location=loc)
            emitter.display_type = "WIRE"
            helpers.set_active(emitter)
            try:
                bpy.ops.object.particle_system_add()
                ps = emitter.particle_systems[-1]
                ps.name = f"{name}_Particles"
                s = ps.settings
                s.count = int(80 * self.intensity)
                s.lifetime = 60
                s.frame_start = 1
                s.frame_end = config.CINEMATIC_FRAME_END
                s.particle_size = 0.08
                s.size_random = 0.5
                s.normal_factor = 0.15
                s.factor_random = 0.3
                s.brownian_factor = 0.4
                try:
                    s.effector_weights.gravity = -0.15  # rises
                except Exception:
                    pass
                s.render_type = "HALO"
            except RuntimeError:
                # Mesh volume proxy
                steam_mesh = helpers.create_uv_sphere(
                    f"{name}_Volume",
                    radius=0.12,
                    location=(loc[0], loc[1], loc[2] + 0.15),
                )
                helpers.assign_material(steam_mesh, self.mat.get("MAT_GlassClear"))
                steam_mesh.display_type = "WIRE"
                self._link(steam_mesh, "Steam")
            self._link(emitter, "Steam")

        # World / scene volume scatter for atmospheric humidity
        self._ensure_volume_scatter()

    def _ensure_volume_scatter(self) -> None:
        if not config.USE_VOLUME_SCATTER:
            return
        scene = bpy.context.scene
        world = scene.world
        if world is None:
            world = bpy.data.worlds.new("World_CoffeeShop")
            scene.world = world
        world.use_nodes = True
        nt = world.node_tree
        # Add volume scatter if missing
        nodes = nt.nodes
        output = next((n for n in nodes if n.type == "OUTPUT_WORLD"), None)
        if output is None:
            return
        vol = next((n for n in nodes if n.type == "VOLUME_SCATTER"), None)
        if vol is None:
            vol = nodes.new("ShaderNodeVolumeScatter")
            vol.location = (0, -300)
        vol.inputs["Density"].default_value = 0.015
        vol.inputs["Anisotropy"].default_value = 0.3
        if "Color" in vol.inputs:
            vol.inputs["Color"].default_value = (0.7, 0.75, 0.85, 1.0)
        if "Volume" in output.inputs:
            try:
                nt.links.new(vol.outputs["Volume"], output.inputs["Volume"])
            except Exception:
                pass
