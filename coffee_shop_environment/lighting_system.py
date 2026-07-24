# SPDX-License-Identifier: MIT
"""
Cinematic lighting system — warm interior (2700–3200K) vs cold storm exterior.
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

import bpy

from . import config, helpers


def kelvin_to_rgb(kelvin: float) -> Tuple[float, float, float]:
    """Approximate blackbody RGB for interior practicals (normalized 0..1)."""
    # Simplified Tanner Helland approximation
    temp = max(1000.0, min(40000.0, kelvin)) / 100.0
    if temp <= 66:
        r = 255.0
        g = 99.4708025861 * math.log(temp) - 161.1195681661
        b = 0.0 if temp <= 19 else (138.5177312231 * math.log(temp - 10.0) - 305.0447927307)
    else:
        r = 329.698727446 * ((temp - 60.0) ** -0.1332047592)
        g = 288.1221695283 * ((temp - 60.0) ** -0.0755148492)
        b = 255.0
    r = max(0.0, min(255.0, r)) / 255.0
    g = max(0.0, min(255.0, g)) / 255.0
    b = max(0.0, min(255.0, b)) / 255.0
    return (r, g, b)


class LightingSystem:
    """Professional cinematic lighting for rainy-evening coffee shop."""

    def __init__(self, collections: dict):
        self.cols = collections
        self.lights: List[bpy.types.Object] = []

    def build(self) -> List[bpy.types.Object]:
        self.lights.clear()
        self._setup_world()
        self._create_exterior_storm_light()
        self._create_interior_fill()
        self._create_practical_pendants()
        self._create_bar_lights()
        self._create_reading_corner_lamp()
        self._create_candle_lights()
        self._create_street_lamps()
        self._create_window_bounce()
        return self.lights

    def _link(self, obj, key: str = "InteriorLights"):
        helpers.link_object_to_collection(obj, self.cols.get(key, key))
        self.lights.append(obj)
        return obj

    def _add_light(
        self,
        name: str,
        light_type: str,
        location: Tuple[float, float, float],
        energy: float,
        color: Tuple[float, float, float],
        rotation: Tuple[float, float, float] = (0, 0, 0),
        size: float = 0.25,
        collection: str = "InteriorLights",
    ) -> bpy.types.Object:
        bpy.ops.object.light_add(type=light_type, location=location)
        obj = bpy.context.active_object
        obj.name = name
        obj.rotation_euler = rotation
        data = obj.data
        data.energy = energy
        data.color = color
        if hasattr(data, "shadow_soft_size"):
            data.shadow_soft_size = size
        if light_type == "AREA" and hasattr(data, "size"):
            data.size = max(size, 0.3)
            data.shape = "DISK"
        if light_type == "SPOT":
            data.spot_size = math.radians(50)
            data.spot_blend = 0.35
        self._link(obj, collection)
        return obj

    def _setup_world(self) -> None:
        scene = bpy.context.scene
        world = scene.world
        if world is None:
            world = bpy.data.worlds.new("World_CoffeeShop")
            scene.world = world
        world.use_nodes = True
        nt = world.node_tree
        nodes = nt.nodes
        links = nt.links
        nodes.clear()

        output = nodes.new("ShaderNodeOutputWorld")
        output.location = (300, 0)
        bg = nodes.new("ShaderNodeBackground")
        bg.location = (0, 0)
        # Cold overcast storm sky
        bg.inputs["Color"].default_value = (*config.EXTERIOR_STORM_COLOR, 1.0)
        bg.inputs["Strength"].default_value = 0.35
        links.new(bg.outputs["Background"], output.inputs["Surface"])

        # Volume already handled by WeatherSystem; keep surface only here

    def _create_exterior_storm_light(self) -> None:
        # Soft overcast sun / skylight
        self._add_light(
            "LIGHT_StormSun",
            "SUN",
            (10, -40, 30),
            energy=0.8,
            color=config.EXTERIOR_STORM_COLOR,
            rotation=(math.radians(50), math.radians(15), math.radians(-30)),
            size=0.5,
            collection="ExteriorLights",
        )
        # Cool area fill through windows
        self._add_light(
            "LIGHT_WindowCoolFill",
            "AREA",
            (0, -config.SHOP_DEPTH * 0.5 - 1.5, 2.0),
            energy=25.0,
            color=(0.45, 0.55, 0.7),
            rotation=(math.radians(90), 0, 0),
            size=4.0,
            collection="ExteriorLights",
        )
        area = bpy.data.objects["LIGHT_WindowCoolFill"]
        if hasattr(area.data, "size_y"):
            area.data.size = 10.0
            area.data.size_y = 3.0
            area.data.shape = "RECTANGLE"

    def _create_interior_fill(self) -> None:
        warm = kelvin_to_rgb(2900)
        self._add_light(
            "LIGHT_InteriorBounce",
            "AREA",
            (0, 0, config.SHOP_HEIGHT - 0.3),
            energy=40.0,
            color=warm,
            rotation=(math.radians(180), 0, 0),
            size=6.0,
            collection="InteriorLights",
        )
        # Soft side bounce
        self._add_light(
            "LIGHT_InteriorSideBounce",
            "AREA",
            (-config.SHOP_WIDTH * 0.4, 2.0, 2.0),
            energy=15.0,
            color=kelvin_to_rgb(3000),
            rotation=(0, math.radians(90), 0),
            size=2.5,
            collection="InteriorLights",
        )

    def _create_practical_pendants(self) -> None:
        warm = kelvin_to_rgb(2700)
        for i, x in enumerate((-4.5, -2.5, -0.5, 1.5, 3.5)):
            self._add_light(
                f"LIGHT_Pendant_{i}",
                "POINT",
                (x, -config.SHOP_DEPTH * 0.5 + 1.8, config.SHOP_HEIGHT - 0.75),
                energy=80.0,
                color=warm,
                size=0.05,
                collection="Practicals",
            )

    def _create_bar_lights(self) -> None:
        warm = kelvin_to_rgb(2800)
        for i, x in enumerate((-2.0, 0.0, 2.0)):
            self._add_light(
                f"LIGHT_BarPendant_{i}",
                "SPOT",
                (x, config.SHOP_DEPTH * 0.5 - 2.2, config.SHOP_HEIGHT - 0.95),
                energy=200.0,
                color=warm,
                rotation=(math.radians(15), 0, 0),
                size=0.08,
                collection="Practicals",
            )
        # Under-cabinet strip approximation
        self._add_light(
            "LIGHT_BarStrip",
            "AREA",
            (0.0, config.SHOP_DEPTH * 0.5 - 1.9, 1.4),
            energy=30.0,
            color=kelvin_to_rgb(3200),
            rotation=(math.radians(90), 0, 0),
            size=3.0,
            collection="Practicals",
        )

    def _create_reading_corner_lamp(self) -> None:
        self._add_light(
            "LIGHT_FloorLamp",
            "POINT",
            (-5.8, 7.0, 1.55),
            energy=60.0,
            color=kelvin_to_rgb(2700),
            size=0.12,
            collection="Practicals",
        )

    def _create_candle_lights(self) -> None:
        candle_color = (1.0, 0.55, 0.2)
        for obj in bpy.data.objects:
            if obj.get("coffee_shop_flame"):
                loc = obj.location.copy()
                self._add_light(
                    f"LIGHT_{obj.name}",
                    "POINT",
                    (loc.x, loc.y, loc.z),
                    energy=8.0,
                    color=candle_color,
                    size=0.02,
                    collection="Practicals",
                )

    def _create_street_lamps(self) -> None:
        cool = (1.0, 0.85, 0.55)
        for obj in bpy.data.objects:
            if obj.get("coffee_shop_street_lamp"):
                loc = obj.location
                self._add_light(
                    f"LIGHT_Street_{obj.name}",
                    "POINT",
                    (loc.x, loc.y, loc.z),
                    energy=350.0,
                    color=cool,
                    size=0.2,
                    collection="ExteriorLights",
                )

    def _create_window_bounce(self) -> None:
        """Warm bounce onto wet sidewalk from interior spill — cinematic contrast."""
        self._add_light(
            "LIGHT_InteriorSpillExterior",
            "AREA",
            (0, -config.SHOP_DEPTH * 0.5 - 0.5, 1.2),
            energy=12.0,
            color=kelvin_to_rgb(3000),
            rotation=(math.radians(90), 0, math.radians(180)),
            size=5.0,
            collection="ExteriorLights",
        )
