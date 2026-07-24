# SPDX-License-Identifier: MIT
"""
Seating furniture: tables, chairs, booths, armchairs, couches, reading corner.
Realistic dimensions in meters.
"""

from __future__ import annotations

import math
import random
from typing import List, Optional, Tuple

import bpy

from . import config, helpers
from .material_manager import MaterialManager


class FurnitureBuilder:
    """Procedural seating and table generation with slight randomization."""

    def __init__(self, materials: MaterialManager, collections: dict, seed: int = config.RANDOM_SEED):
        self.mat = materials
        self.cols = collections
        self.rng = random.Random(seed)
        self.objects: List[bpy.types.Object] = []

    def build(self) -> List[bpy.types.Object]:
        self.objects.clear()
        self._layout_window_seating()
        self._layout_center_tables()
        self._layout_booths()
        self._layout_lounge_couches()
        self._layout_reading_corner()
        return self.objects

    def _link(self, obj, key: str):
        helpers.link_object_to_collection(obj, self.cols.get(key, key))
        self.objects.append(obj)
        return obj

    # ------------------------------------------------------------------
    # Primitive furniture pieces
    # ------------------------------------------------------------------

    def create_table_round(
        self,
        name: str,
        location: Tuple[float, float, float],
        diameter: float = 0.75,
        height: float = 0.75,
    ) -> bpy.types.Object:
        top = helpers.create_cylinder(
            f"{name}_Top",
            radius=diameter * 0.5,
            depth=0.04,
            vertices=32,
            location=(location[0], location[1], height),
        )
        helpers.assign_material(top, self.mat.get("MAT_WoodOak"))
        helpers.bevel_object(top, 0.005, 3)
        helpers.shade_smooth(top)

        pedestal = helpers.create_cylinder(
            f"{name}_Pedestal",
            radius=0.06,
            depth=height - 0.08,
            vertices=16,
            location=(location[0], location[1], (height - 0.08) * 0.5),
        )
        helpers.assign_material(pedestal, self.mat.get("MAT_MetalBlack"))

        base = helpers.create_cylinder(
            f"{name}_Base",
            radius=0.28,
            depth=0.03,
            vertices=24,
            location=(location[0], location[1], 0.02),
        )
        helpers.assign_material(base, self.mat.get("MAT_MetalBlack"))

        joined = helpers.join_objects([top, pedestal, base], name)
        if joined:
            self._link(joined, "Tables")
            return joined
        return top

    def create_table_square(
        self,
        name: str,
        location: Tuple[float, float, float],
        width: float = 0.8,
        height: float = 0.75,
    ) -> bpy.types.Object:
        top = helpers.create_cube(
            f"{name}_Top",
            size=(width, width, 0.04),
            location=(location[0], location[1], height),
        )
        helpers.assign_material(top, self.mat.get("MAT_WoodWalnut"))
        helpers.bevel_object(top, 0.006, 3)

        parts = [top]
        inset = width * 0.4
        for i, (lx, ly) in enumerate(
            [(-inset, -inset), (inset, -inset), (-inset, inset), (inset, inset)]
        ):
            leg = helpers.create_cube(
                f"{name}_Leg_{i}",
                size=(0.05, 0.05, height - 0.04),
                location=(location[0] + lx, location[1] + ly, (height - 0.04) * 0.5),
            )
            helpers.assign_material(leg, self.mat.get("MAT_MetalBlack"))
            parts.append(leg)

        joined = helpers.join_objects(parts, name)
        if joined:
            self._link(joined, "Tables")
            return joined
        return top

    def create_coffee_table(
        self,
        name: str,
        location: Tuple[float, float, float],
        width: float = 1.1,
        depth: float = 0.55,
        height: float = 0.42,
    ) -> bpy.types.Object:
        top = helpers.create_cube(
            f"{name}_Top",
            size=(width, depth, 0.04),
            location=(location[0], location[1], height),
        )
        helpers.assign_material(top, self.mat.get("MAT_WoodOak"))
        helpers.bevel_object(top, 0.008, 3)

        shelf = helpers.create_cube(
            f"{name}_Shelf",
            size=(width * 0.9, depth * 0.9, 0.025),
            location=(location[0], location[1], height * 0.35),
        )
        helpers.assign_material(shelf, self.mat.get("MAT_WoodWalnut"))

        parts = [top, shelf]
        for i, (lx, ly) in enumerate(
            [(-width * 0.42, -depth * 0.38), (width * 0.42, -depth * 0.38),
             (-width * 0.42, depth * 0.38), (width * 0.42, depth * 0.38)]
        ):
            leg = helpers.create_cube(
                f"{name}_Leg_{i}",
                size=(0.04, 0.04, height),
                location=(location[0] + lx, location[1] + ly, height * 0.5),
            )
            helpers.assign_material(leg, self.mat.get("MAT_MetalBlack"))
            parts.append(leg)

        joined = helpers.join_objects(parts, name)
        if joined:
            self._link(joined, "Tables")
            return joined
        return top

    def create_chair_upholstered(
        self,
        name: str,
        location: Tuple[float, float, float],
        rotation_z: float = 0.0,
    ) -> bpy.types.Object:
        """Dining chair ~0.45m seat width, 0.45m seat height, 0.9m total."""
        seat_h = 0.45
        seat = helpers.create_cube(
            f"{name}_Seat",
            size=(0.45, 0.42, 0.06),
            location=(0, 0, seat_h),
        )
        helpers.assign_material(seat, self.mat.get("MAT_FabricUpholstery"))
        helpers.bevel_object(seat, 0.015, 3)

        back = helpers.create_cube(
            f"{name}_Back",
            size=(0.45, 0.06, 0.42),
            location=(0, -0.18, seat_h + 0.24),
        )
        helpers.assign_material(back, self.mat.get("MAT_FabricUpholstery"))
        helpers.bevel_object(back, 0.012, 3)

        parts = [seat, back]
        for i, (lx, ly) in enumerate([(-0.18, -0.16), (0.18, -0.16), (-0.18, 0.16), (0.18, 0.16)]):
            leg = helpers.create_cube(
                f"{name}_Leg_{i}",
                size=(0.04, 0.04, seat_h),
                location=(lx, ly, seat_h * 0.5),
            )
            helpers.assign_material(leg, self.mat.get("MAT_WoodOak"))
            parts.append(leg)

        joined = helpers.join_objects(parts, name)
        if joined:
            joined.location = location
            joined.rotation_euler = (0, 0, rotation_z)
            helpers.apply_transforms(joined, location=False, rotation=True, scale=True)
            joined.location = location
            self._link(joined, "Chairs")
            return joined
        return seat

    def create_armchair(
        self,
        name: str,
        location: Tuple[float, float, float],
        rotation_z: float = 0.0,
    ) -> bpy.types.Object:
        seat = helpers.create_cube(f"{name}_Seat", size=(0.7, 0.65, 0.14), location=(0, 0, 0.4))
        helpers.assign_material(seat, self.mat.get("MAT_LeatherBrown"))
        helpers.bevel_object(seat, 0.03, 4)

        back = helpers.create_cube(f"{name}_Back", size=(0.7, 0.12, 0.55), location=(0, -0.28, 0.72))
        helpers.assign_material(back, self.mat.get("MAT_LeatherBrown"))
        helpers.bevel_object(back, 0.03, 4)

        parts = [seat, back]
        for side, x in (("L", -0.38), ("R", 0.38)):
            arm = helpers.create_cube(
                f"{name}_Arm_{side}",
                size=(0.1, 0.55, 0.18),
                location=(x, 0.0, 0.55),
            )
            helpers.assign_material(arm, self.mat.get("MAT_LeatherBrown"))
            helpers.bevel_object(arm, 0.02, 3)
            parts.append(arm)

        # Wooden legs
        for i, (lx, ly) in enumerate([(-0.28, -0.25), (0.28, -0.25), (-0.28, 0.25), (0.28, 0.25)]):
            leg = helpers.create_cylinder(
                f"{name}_Leg_{i}", radius=0.03, depth=0.33, vertices=12,
                location=(lx, ly, 0.165),
            )
            helpers.assign_material(leg, self.mat.get("MAT_WoodWalnut"))
            parts.append(leg)

        joined = helpers.join_objects(parts, name)
        if joined:
            joined.location = location
            joined.rotation_euler = (0, 0, rotation_z)
            helpers.apply_transforms(joined, location=False, rotation=True, scale=True)
            joined.location = location
            self._link(joined, "Chairs")
            return joined
        return seat

    def create_booth(
        self,
        name: str,
        location: Tuple[float, float, float],
        width: float = 1.4,
        depth: float = 0.6,
        rotation_z: float = 0.0,
    ) -> bpy.types.Object:
        seat = helpers.create_cube(
            f"{name}_Seat",
            size=(width, depth, 0.12),
            location=(0, 0, 0.42),
        )
        helpers.assign_material(seat, self.mat.get("MAT_LeatherBrown"))
        helpers.bevel_object(seat, 0.02, 3)

        back = helpers.create_cube(
            f"{name}_Back",
            size=(width, 0.1, 0.7),
            location=(0, -depth * 0.5 + 0.05, 0.8),
        )
        helpers.assign_material(back, self.mat.get("MAT_LeatherBrown"))

        base = helpers.create_cube(
            f"{name}_Base",
            size=(width, depth, 0.36),
            location=(0, 0, 0.18),
        )
        helpers.assign_material(base, self.mat.get("MAT_WoodOak"))

        joined = helpers.join_objects([seat, back, base], name)
        if joined:
            joined.location = location
            joined.rotation_euler = (0, 0, rotation_z)
            helpers.apply_transforms(joined, location=False, rotation=True, scale=True)
            joined.location = location
            self._link(joined, "Booths")
            return joined
        return seat

    def create_couch(
        self,
        name: str,
        location: Tuple[float, float, float],
        width: float = 1.9,
        rotation_z: float = 0.0,
    ) -> bpy.types.Object:
        seat = helpers.create_cube(f"{name}_Seat", size=(width, 0.85, 0.18), location=(0, 0, 0.4))
        helpers.assign_material(seat, self.mat.get("MAT_FabricUpholstery"))
        helpers.bevel_object(seat, 0.04, 4)
        helpers.subdivide_object(seat, 1, 2)

        back = helpers.create_cube(f"{name}_Back", size=(width, 0.16, 0.55), location=(0, -0.38, 0.75))
        helpers.assign_material(back, self.mat.get("MAT_FabricUpholstery"))
        helpers.bevel_object(back, 0.04, 4)

        parts = [seat, back]
        for side, x in (("L", -width * 0.5 + 0.08), ("R", width * 0.5 - 0.08)):
            arm = helpers.create_cube(
                f"{name}_Arm_{side}", size=(0.14, 0.8, 0.35), location=(x, 0, 0.55)
            )
            helpers.assign_material(arm, self.mat.get("MAT_FabricUpholstery"))
            helpers.bevel_object(arm, 0.03, 3)
            parts.append(arm)

        # Cushions (soft-body candidates)
        for i, cx in enumerate((-width * 0.28, width * 0.28)):
            cushion = helpers.create_cube(
                f"{name}_Cushion_{i}",
                size=(width * 0.4, 0.55, 0.1),
                location=(cx, 0.05, 0.52),
            )
            helpers.assign_material(cushion, self.mat.get("MAT_FabricLinen"))
            helpers.bevel_object(cushion, 0.03, 4)
            helpers.subdivide_object(cushion, 1, 2)
            parts.append(cushion)

        joined = helpers.join_objects(parts, name)
        if joined:
            joined.location = location
            joined.rotation_euler = (0, 0, rotation_z)
            helpers.apply_transforms(joined, location=False, rotation=True, scale=True)
            joined.location = location
            self._link(joined, "Sofas")
            return joined
        return seat

    # ------------------------------------------------------------------
    # Layouts
    # ------------------------------------------------------------------

    def _layout_window_seating(self) -> None:
        """Tables and chairs along the floor-to-ceiling windows (-Y)."""
        d = config.SHOP_DEPTH
        y = -d * 0.5 + 1.8
        for i, x in enumerate((-4.5, -2.5, -0.5, 1.5, 3.5)):
            jitter = self.rng.uniform(-0.08, 0.08)
            self.create_table_round(
                f"Table_Window_{i}",
                location=(x + jitter, y + self.rng.uniform(-0.05, 0.1), 0),
                diameter=self.rng.uniform(0.7, 0.8),
            )
            # Two chairs facing window / inward
            self.create_chair_upholstered(
                f"Chair_Window_{i}_A",
                location=(x - 0.45, y + 0.55, 0),
                rotation_z=math.pi + self.rng.uniform(-0.1, 0.1),
            )
            self.create_chair_upholstered(
                f"Chair_Window_{i}_B",
                location=(x + 0.45, y + 0.55, 0),
                rotation_z=math.pi + self.rng.uniform(-0.1, 0.1),
            )

    def _layout_center_tables(self) -> None:
        positions = [(-3.0, -2.0), (-1.0, -1.5), (1.2, -2.2), (3.2, -1.2), (-2.0, 1.0), (2.0, 0.8)]
        for i, (x, y) in enumerate(positions):
            if i % 2 == 0:
                self.create_table_square(f"Table_Center_{i}", (x, y, 0), width=0.85)
            else:
                self.create_table_round(f"Table_Center_{i}", (x, y, 0), diameter=0.7)
            for j, (ox, oy, rz) in enumerate(
                [(-0.55, 0, math.pi * 0.5), (0.55, 0, -math.pi * 0.5),
                 (0, -0.55, 0), (0, 0.55, math.pi)]
            ):
                if self.rng.random() < 0.75:
                    self.create_chair_upholstered(
                        f"Chair_Center_{i}_{j}",
                        (x + ox, y + oy, 0),
                        rz + self.rng.uniform(-0.15, 0.15),
                    )

    def _layout_booths(self) -> None:
        """Booth pairs along the right wall."""
        w = config.SHOP_WIDTH
        x = w * 0.5 - 1.5
        for i, y in enumerate((-4.0, -1.5, 1.0, 3.5)):
            self.create_booth(f"Booth_{i}_A", (x, y - 0.55, 0), rotation_z=0)
            self.create_booth(f"Booth_{i}_B", (x, y + 0.55, 0), rotation_z=math.pi)
            self.create_table_square(f"BoothTable_{i}", (x - 0.3, y, 0), width=0.7)

    def _layout_lounge_couches(self) -> None:
        self.create_couch("Couch_Lounge_A", (-4.5, 4.5, 0), width=2.0, rotation_z=math.pi * 0.15)
        self.create_armchair("Armchair_Lounge_A", (-2.8, 5.2, 0), rotation_z=-math.pi * 0.4)
        self.create_armchair("Armchair_Lounge_B", (-5.5, 5.8, 0), rotation_z=math.pi * 0.6)
        self.create_coffee_table("CoffeeTable_Lounge", (-4.2, 5.5, 0))

    def _layout_reading_corner(self) -> None:
        """Quiet reading nook in back-left corner."""
        w, d = config.SHOP_WIDTH, config.SHOP_DEPTH
        base_x = -w * 0.5 + 2.2
        base_y = d * 0.5 - 2.5
        self.create_armchair("Armchair_Reading_A", (base_x, base_y, 0), rotation_z=math.pi * 0.25)
        self.create_armchair("Armchair_Reading_B", (base_x + 1.4, base_y + 0.3, 0), rotation_z=-math.pi * 0.35)
        self.create_coffee_table("CoffeeTable_Reading", (base_x + 0.6, base_y + 0.9, 0), width=0.9, depth=0.5)
        # Floor cushion pouf
        pouf = helpers.create_cylinder(
            "Pouf_Reading",
            radius=0.28,
            depth=0.35,
            vertices=24,
            location=(base_x - 0.6, base_y + 0.4, 0.175),
        )
        helpers.assign_material(pouf, self.mat.get("MAT_FabricLinen"))
        helpers.shade_smooth(pouf)
        helpers.bevel_object(pouf, 0.02, 3)
        self._link(pouf, "ReadingCorner")
