# SPDX-License-Identifier: MIT
"""
Animation system: wind motion, steam, lightning already keyed in WeatherSystem,
plus helper animations for hanging decor and cinematic markers.
"""

from __future__ import annotations

import logging
import math
from typing import List

import bpy

from . import config

logger = logging.getLogger(__name__)


class AnimationSystem:
    """Scene animation helpers and timeline configuration."""

    def __init__(self):
        self.animated: List[str] = []

    def build(self) -> List[str]:
        self.animated.clear()
        self._configure_timeline()
        self._animate_hanging_decor()
        self._animate_candle_flicker()
        self._animate_steam_proxy_scales()
        return self.animated

    def _configure_timeline(self) -> None:
        scene = bpy.context.scene
        scene.frame_start = 1
        scene.frame_end = config.CINEMATIC_FRAME_END
        scene.render.fps = config.FPS
        scene.frame_current = 1

    def _animate_hanging_decor(self) -> None:
        """Subtle wind sway on hanging plants and decorations."""
        for obj in bpy.data.objects:
            if not (
                obj.get("coffee_shop_wind_anim")
                or "HangingPlant" in obj.name
                or obj.name.startswith("Curtain_")
            ):
                continue
            # Skip if cloth modifier will drive motion
            if any(m.type == "CLOTH" for m in obj.modifiers):
                continue
            base_rot = obj.rotation_euler.copy()
            amp = math.radians(2.5 if "Plant" in obj.name else 1.2)
            for frame in range(1, config.CINEMATIC_FRAME_END + 1, 6):
                t = frame / float(config.FPS)
                obj.rotation_euler[0] = base_rot[0] + amp * math.sin(t * 1.3 + hash(obj.name) % 10)
                obj.rotation_euler[2] = base_rot[2] + amp * 0.6 * math.sin(t * 0.9 + 1.7)
                obj.keyframe_insert(data_path="rotation_euler", frame=frame)
            self._ease_fcurves(obj)
            self.animated.append(obj.name)

    def _animate_candle_flicker(self) -> None:
        for obj in bpy.data.objects:
            if not obj.name.startswith("LIGHT_Candle") and "CandleFlame" not in obj.name:
                continue
            if obj.type == "LIGHT":
                base = obj.data.energy
                for frame in range(1, config.CINEMATIC_FRAME_END + 1, 3):
                    t = frame / float(config.FPS)
                    flicker = base * (
                        0.85
                        + 0.15 * math.sin(t * 17.0 + hash(obj.name) % 7)
                        + 0.08 * math.sin(t * 31.0)
                    )
                    obj.data.energy = flicker
                    obj.data.keyframe_insert(data_path="energy", frame=frame)
                self.animated.append(obj.name)
            elif obj.type == "MESH":
                base_s = obj.scale.copy()
                for frame in range(1, config.CINEMATIC_FRAME_END + 1, 4):
                    t = frame / float(config.FPS)
                    s = 0.9 + 0.15 * abs(math.sin(t * 22.0 + hash(obj.name) % 5))
                    obj.scale = (base_s.x * s, base_s.y * s, base_s.z * (0.95 + s * 0.1))
                    obj.keyframe_insert(data_path="scale", frame=frame)
                self.animated.append(obj.name)

    def _animate_steam_proxy_scales(self) -> None:
        for obj in bpy.data.objects:
            if "_Volume" not in obj.name or "Steam" not in obj.name:
                continue
            for frame in range(1, config.CINEMATIC_FRAME_END + 1, 8):
                t = frame / float(config.FPS)
                s = 1.0 + 0.35 * (0.5 + 0.5 * math.sin(t * 1.5 + hash(obj.name) % 3))
                obj.scale = (s, s, s * 1.4)
                obj.location.z = obj.location.z  # keep
                obj.keyframe_insert(data_path="scale", frame=frame)
            self.animated.append(obj.name)

    def _ease_fcurves(self, obj: bpy.types.Object) -> None:
        if not obj.animation_data or not obj.animation_data.action:
            return
        action = obj.animation_data.action
        fcurves = getattr(action, "fcurves", None)
        if not fcurves:
            return
        for fc in fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "BEZIER"
                kp.handle_left_type = "AUTO_CLAMPED"
                kp.handle_right_type = "AUTO_CLAMPED"
