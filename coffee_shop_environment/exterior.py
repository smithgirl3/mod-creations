# SPDX-License-Identifier: MIT
"""
Exterior street environment visible through coffee shop windows.
Includes sidewalks, road, buildings, street props, vehicles, LOD variants.
"""

from __future__ import annotations

import math
import random
from typing import List, Tuple

import bpy

from . import config, helpers
from .material_manager import MaterialManager


class ExteriorBuilder:
    """City street strip optimized for window views (LOD-aware)."""

    def __init__(self, materials: MaterialManager, collections: dict, seed: int = config.RANDOM_SEED):
        self.mat = materials
        self.cols = collections
        self.rng = random.Random(seed + 55)
        self.objects: List[bpy.types.Object] = []
        self.lod_groups: dict = {}

    def build(self) -> List[bpy.types.Object]:
        self.objects.clear()
        self._build_sidewalk()
        self._build_road()
        self._build_buildings()
        self._build_street_lights()
        self._build_traffic_signals()
        self._build_benches()
        self._build_parked_vehicles()
        self._build_trash_cans()
        self._build_utility_poles()
        self._build_storefronts()
        return self.objects

    def _link(self, obj, key: str = "StreetProps"):
        helpers.link_object_to_collection(obj, self.cols.get(key, key))
        self.objects.append(obj)
        return obj

    def _street_y_origin(self) -> float:
        """Street extends in -Y beyond the shop front."""
        return -config.SHOP_DEPTH * 0.5

    def _build_sidewalk(self) -> None:
        front = self._street_y_origin()
        sw = config.SIDEWALK_WIDTH
        sidewalk = helpers.create_cube(
            "EXT_Sidewalk",
            size=(config.EXTERIOR_EXTENT, sw, 0.12),
            location=(0, front - sw * 0.5 - 0.1, -0.02),
        )
        helpers.assign_material(sidewalk, self.mat.get("MAT_Concrete"))
        self._link(sidewalk, "Sidewalk")

        # Curb
        curb = helpers.create_cube(
            "EXT_Curb",
            size=(config.EXTERIOR_EXTENT, 0.15, 0.18),
            location=(0, front - sw - 0.1, -0.02),
        )
        helpers.assign_material(curb, self.mat.get("MAT_Concrete"))
        self._link(curb, "Sidewalk")

    def _build_road(self) -> None:
        front = self._street_y_origin()
        sw = config.SIDEWALK_WIDTH
        road_y = front - sw - config.STREET_WIDTH * 0.5 - 0.2
        road = helpers.create_cube(
            "EXT_Road",
            size=(config.EXTERIOR_EXTENT, config.STREET_WIDTH, 0.08),
            location=(0, road_y, -0.08),
        )
        helpers.assign_material(road, self.mat.get("MAT_AsphaltWet"))
        self._link(road, "Road")

        # Center dashed line
        for i, x in enumerate(range(-18, 19, 3)):
            dash = helpers.create_cube(
                f"EXT_RoadDash_{i}",
                size=(1.2, 0.12, 0.01),
                location=(float(x), road_y, -0.035),
            )
            helpers.assign_material(dash, self.mat.get("MAT_CeramicWhite"))
            self._link(dash, "Road")

    def _build_buildings(self) -> None:
        """Opposing building row across the street — LOD0 detailed, tagged for LOD gen."""
        front = self._street_y_origin()
        sw = config.SIDEWALK_WIDTH
        road_y = front - sw - config.STREET_WIDTH - 0.5
        row_y = road_y - config.BUILDING_ROW_DEPTH * 0.5

        widths = [6.0, 5.0, 7.5, 4.5, 6.5, 5.5]
        x = -18.0
        for i, bw in enumerate(widths):
            height = self.rng.uniform(8.0, 18.0)
            depth = config.BUILDING_ROW_DEPTH + self.rng.uniform(-1, 1)
            bldg = helpers.create_cube(
                f"EXT_Building_{i}",
                size=(bw - 0.3, depth, height),
                location=(x + bw * 0.5, row_y, height * 0.5 - 0.1),
            )
            helpers.assign_material(
                bldg,
                self.mat.get("MAT_BrickExterior") if i % 2 == 0 else self.mat.get("MAT_Concrete"),
            )
            bldg["coffee_shop_lod"] = True
            self._link(bldg, "Buildings")

            # Window grid (simple insets as emissive planes for night glow)
            floors = int(height / 3.2)
            cols = max(2, int(bw / 2.0))
            for fi in range(floors):
                for ci in range(cols):
                    wx = x + 0.8 + ci * ((bw - 1.6) / max(cols - 1, 1))
                    wz = 1.5 + fi * 3.0
                    win = helpers.create_cube(
                        f"EXT_BldgWin_{i}_{fi}_{ci}",
                        size=(0.9, 0.05, 1.4),
                        location=(wx, row_y + depth * 0.5 - 0.02, wz),
                    )
                    helpers.assign_material(win, self.mat.get("MAT_GlassClear"))
                    # Some lit windows
                    if self.rng.random() < 0.35:
                        win["coffee_shop_lit_window"] = True
                    self._link(win, "Buildings")

            # Rooftop parapet box (LOD detail)
            roof = helpers.create_cube(
                f"EXT_BuildingRoof_{i}",
                size=(bw - 0.1, depth - 0.1, 0.4),
                location=(x + bw * 0.5, row_y, height + 0.1),
            )
            helpers.assign_material(roof, self.mat.get("MAT_MetalBlack"))
            self._link(roof, "Buildings")
            x += bw

    def _build_storefronts(self) -> None:
        """Neighboring storefronts on same block as coffee shop (sides)."""
        front = self._street_y_origin()
        for i, x in enumerate((-12.0, -9.0, 9.0, 12.0)):
            store = helpers.create_cube(
                f"EXT_Storefront_{i}",
                size=(2.8, 0.4, 3.5),
                location=(x, front + 0.5, 1.75),
            )
            helpers.assign_material(store, self.mat.get("MAT_BrickExterior"))
            glass = helpers.create_cube(
                f"EXT_StoreGlass_{i}",
                size=(2.2, 0.05, 2.4),
                location=(x, front + 0.25, 1.5),
            )
            helpers.assign_material(glass, self.mat.get("MAT_GlassRain"))
            awning = helpers.create_cube(
                f"EXT_Awning_{i}",
                size=(2.6, 0.8, 0.06),
                location=(x, front - 0.2, 2.8),
            )
            helpers.assign_material(awning, self.mat.get("MAT_FabricCurtain"))
            for obj in (store, glass, awning):
                self._link(obj, "Buildings")

    def _build_street_lights(self) -> None:
        front = self._street_y_origin()
        sw = config.SIDEWALK_WIDTH
        for i, x in enumerate((-15, -9, -3, 3, 9, 15)):
            pole = helpers.create_cylinder(
                f"EXT_StreetLightPole_{i}",
                radius=0.06,
                depth=5.5,
                vertices=12,
                location=(x, front - sw * 0.4, 2.75),
            )
            helpers.assign_material(pole, self.mat.get("MAT_MetalBlack"))
            arm = helpers.create_cylinder(
                f"EXT_StreetLightArm_{i}",
                radius=0.04,
                depth=1.2,
                vertices=8,
                location=(x, front - sw * 0.4 - 0.5, 5.3),
                rotation=(math.radians(90), 0, 0),
            )
            helpers.assign_material(arm, self.mat.get("MAT_MetalBlack"))
            lamp = helpers.create_uv_sphere(
                f"EXT_StreetLightLamp_{i}",
                radius=0.18,
                segments=12,
                rings=8,
                location=(x, front - sw * 0.4 - 1.0, 5.15),
            )
            helpers.assign_material(lamp, self.mat.get("MAT_CeramicWhite"))
            lamp["coffee_shop_street_lamp"] = True
            for obj in (pole, arm, lamp):
                self._link(obj, "StreetProps")

    def _build_traffic_signals(self) -> None:
        front = self._street_y_origin()
        sw = config.SIDEWALK_WIDTH
        for i, x in enumerate((-16.0, 16.0)):
            pole = helpers.create_cylinder(
                f"EXT_TrafficPole_{i}",
                radius=0.08,
                depth=4.5,
                vertices=12,
                location=(x, front - sw - 0.5, 2.25),
            )
            helpers.assign_material(pole, self.mat.get("MAT_MetalBlack"))
            housing = helpers.create_cube(
                f"EXT_TrafficSignal_{i}",
                size=(0.3, 0.25, 0.9),
                location=(x, front - sw - 0.5, 4.2),
            )
            helpers.assign_material(housing, self.mat.get("MAT_MetalBlack"))
            for j, (color_name, zoff) in enumerate(
                (("Red", 0.28), ("Yellow", 0.0), ("Green", -0.28))
            ):
                lens = helpers.create_cylinder(
                    f"EXT_TrafficLens_{i}_{color_name}",
                    radius=0.08,
                    depth=0.04,
                    vertices=12,
                    location=(x, front - sw - 0.62, 4.2 + zoff),
                    rotation=(math.radians(90), 0, 0),
                )
                helpers.assign_material(lens, self.mat.get("MAT_MetalChrome"))
                self._link(lens, "StreetProps")
            self._link(pole, "StreetProps")
            self._link(housing, "StreetProps")

    def _build_benches(self) -> None:
        front = self._street_y_origin()
        for i, x in enumerate((-6.0, 0.0, 6.0)):
            seat = helpers.create_cube(
                f"EXT_BenchSeat_{i}",
                size=(1.5, 0.4, 0.08),
                location=(x, front - 1.2, 0.42),
            )
            helpers.assign_material(seat, self.mat.get("MAT_WoodOak"))
            back = helpers.create_cube(
                f"EXT_BenchBack_{i}",
                size=(1.5, 0.08, 0.45),
                location=(x, front - 1.0, 0.7),
            )
            helpers.assign_material(back, self.mat.get("MAT_WoodOak"))
            for j, lx in enumerate((-0.6, 0.6)):
                leg = helpers.create_cube(
                    f"EXT_BenchLeg_{i}_{j}",
                    size=(0.08, 0.35, 0.4),
                    location=(x + lx, front - 1.2, 0.2),
                )
                helpers.assign_material(leg, self.mat.get("MAT_MetalBlack"))
                self._link(leg, "StreetProps")
            self._link(seat, "StreetProps")
            self._link(back, "StreetProps")

    def _build_parked_vehicles(self) -> None:
        """Simple vehicle proxies (convincing through rainy glass)."""
        front = self._street_y_origin()
        sw = config.SIDEWALK_WIDTH
        road_y = front - sw - 2.0
        for i, x in enumerate((-12.0, -5.0, 4.0, 11.0)):
            body = helpers.create_cube(
                f"EXT_CarBody_{i}",
                size=(4.4, 1.8, 1.2),
                location=(x, road_y, 0.7),
            )
            helpers.assign_material(
                body,
                self.mat.get("MAT_MetalChrome") if i % 2 else self.mat.get("MAT_MetalBlack"),
            )
            helpers.bevel_object(body, 0.05, 3)
            cabin = helpers.create_cube(
                f"EXT_CarCabin_{i}",
                size=(2.2, 1.7, 0.9),
                location=(x - 0.3, road_y, 1.5),
            )
            helpers.assign_material(cabin, self.mat.get("MAT_GlassClear"))
            for wi, wx in enumerate((-1.5, 1.5)):
                for side, sy in enumerate((-0.9, 0.9)):
                    wheel = helpers.create_cylinder(
                        f"EXT_CarWheel_{i}_{wi}_{side}",
                        radius=0.35,
                        depth=0.25,
                        vertices=16,
                        location=(x + wx, road_y + sy, 0.35),
                        rotation=(math.radians(90), 0, 0),
                    )
                    helpers.assign_material(wheel, self.mat.get("MAT_RubberFloorMat"))
                    self._link(wheel, "Vehicles")
            body["coffee_shop_lod"] = True
            self._link(body, "Vehicles")
            self._link(cabin, "Vehicles")

    def _build_trash_cans(self) -> None:
        front = self._street_y_origin()
        for i, x in enumerate((-8.0, 2.0, 10.0)):
            can = helpers.create_cylinder(
                f"EXT_TrashCan_{i}",
                radius=0.25,
                depth=0.9,
                vertices=16,
                location=(x, front - 1.5, 0.45),
            )
            helpers.assign_material(can, self.mat.get("MAT_MetalBlack"))
            lid = helpers.create_cylinder(
                f"EXT_TrashLid_{i}",
                radius=0.27,
                depth=0.05,
                vertices=16,
                location=(x, front - 1.5, 0.92),
            )
            helpers.assign_material(lid, self.mat.get("MAT_MetalBrushed"))
            self._link(can, "StreetProps")
            self._link(lid, "StreetProps")

    def _build_utility_poles(self) -> None:
        front = self._street_y_origin()
        for i, x in enumerate((-17.0, 17.0)):
            pole = helpers.create_cylinder(
                f"EXT_UtilPole_{i}",
                radius=0.12,
                depth=8.0,
                vertices=10,
                location=(x, front - 2.5, 4.0),
            )
            helpers.assign_material(pole, self.mat.get("MAT_Concrete"))
            cross = helpers.create_cube(
                f"EXT_UtilCross_{i}",
                size=(1.5, 0.1, 0.1),
                location=(x, front - 2.5, 7.5),
            )
            helpers.assign_material(cross, self.mat.get("MAT_MetalBlack"))
            transformer = helpers.create_cube(
                f"EXT_Transformer_{i}",
                size=(0.4, 0.35, 0.5),
                location=(x, front - 2.5, 6.5),
            )
            helpers.assign_material(transformer, self.mat.get("MAT_MetalBrushed"))
            for obj in (pole, cross, transformer):
                self._link(obj, "StreetProps")
