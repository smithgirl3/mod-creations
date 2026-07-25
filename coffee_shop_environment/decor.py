# SPDX-License-Identifier: MIT
"""
Interior decor: bookshelves, plants, artwork, rugs, curtains, lamps,
signs, candles, wall decor — with slight randomization.
"""

from __future__ import annotations

import math
import random
from typing import List, Tuple

import bpy

from . import config, helpers
from .material_manager import MaterialManager


class DecorBuilder:
    def __init__(self, materials: MaterialManager, collections: dict, seed: int = config.RANDOM_SEED):
        self.mat = materials
        self.cols = collections
        self.rng = random.Random(seed + 21)
        self.objects: List[bpy.types.Object] = []

    def build(self) -> List[bpy.types.Object]:
        self.objects.clear()
        self._build_bookshelves()
        self._build_potted_plants()
        self._build_hanging_plants()
        self._build_artwork()
        self._build_rugs()
        self._build_curtains()
        self._build_lamps()
        self._build_signs()
        self._build_candles()
        self._build_wall_decor()
        return self.objects

    def _link(self, obj, key: str):
        helpers.link_object_to_collection(obj, self.cols.get(key, key))
        self.objects.append(obj)
        return obj

    def _build_bookshelves(self) -> None:
        w, d = config.SHOP_WIDTH, config.SHOP_DEPTH
        # Tall shelf in reading corner
        x, y = -w * 0.5 + 0.4, d * 0.5 - 2.0
        frame = helpers.create_cube("Bookshelf_Frame", size=(1.2, 0.35, 2.4), location=(x, y, 1.2))
        helpers.assign_material(frame, self.mat.get("MAT_WoodOak"))
        self._link(frame, "Books")

        for i, z in enumerate((0.4, 0.9, 1.4, 1.9)):
            shelf = helpers.create_cube(
                f"Bookshelf_Shelf_{i}", size=(1.15, 0.32, 0.03), location=(x, y, z)
            )
            helpers.assign_material(shelf, self.mat.get("MAT_WoodWalnut"))
            self._link(shelf, "Books")
            # Books
            bx = x - 0.5
            book_i = 0
            while bx < x + 0.5:
                bw = self.rng.uniform(0.03, 0.07)
                bh = self.rng.uniform(0.18, 0.28)
                book = helpers.create_cube(
                    f"Book_{i}_{book_i}",
                    size=(bw, 0.2, bh),
                    location=(bx, y - 0.02, z + bh * 0.5 + 0.02),
                )
                # Alternate paper / fabric spine colors via existing mats
                helpers.assign_material(
                    book,
                    self.mat.get("MAT_PaperBook") if book_i % 2 == 0 else self.mat.get("MAT_FabricLinen"),
                )
                book.rotation_euler = (0, 0, self.rng.uniform(-0.05, 0.05))
                self._link(book, "Books")
                bx += bw + self.rng.uniform(0.005, 0.02)
                book_i += 1

    def _make_plant(self, name: str, location: Tuple[float, float, float], scale: float = 1.0) -> None:
        pot = helpers.create_cylinder(
            f"{name}_Pot",
            radius=0.12 * scale,
            depth=0.18 * scale,
            vertices=16,
            location=(location[0], location[1], location[2] + 0.09 * scale),
        )
        helpers.assign_material(pot, self.mat.get("MAT_CeramicWhite"))
        soil = helpers.create_cylinder(
            f"{name}_Soil",
            radius=0.1 * scale,
            depth=0.03 * scale,
            vertices=12,
            location=(location[0], location[1], location[2] + 0.16 * scale),
        )
        helpers.assign_material(soil, self.mat.get("MAT_Concrete"))
        self._link(pot, "Plants")
        self._link(soil, "Plants")

        # Foliage clusters
        for i in range(5):
            leaf = helpers.create_uv_sphere(
                f"{name}_Foliage_{i}",
                radius=self.rng.uniform(0.1, 0.18) * scale,
                segments=12,
                rings=8,
                location=(
                    location[0] + self.rng.uniform(-0.08, 0.08) * scale,
                    location[1] + self.rng.uniform(-0.08, 0.08) * scale,
                    location[2] + (0.28 + self.rng.uniform(0, 0.2)) * scale,
                ),
            )
            helpers.assign_material(leaf, self.mat.get("MAT_PlantLeaf"))
            helpers.shade_smooth(leaf)
            self._link(leaf, "Plants")

    def _build_potted_plants(self) -> None:
        spots = [
            (-5.5, -6.5, 0, 1.2),
            (5.5, -6.5, 0, 1.0),
            (-5.8, 3.0, 0, 0.9),
            (5.2, 5.0, 0, 1.1),
            (-3.5, 5.5, 0, 0.7),
            (0.5, 6.5, 0, 0.8),
        ]
        for i, (x, y, z, s) in enumerate(spots):
            self._make_plant(f"Plant_Floor_{i}", (x, y, z), s)

    def _build_hanging_plants(self) -> None:
        d = config.SHOP_DEPTH
        h = config.SHOP_HEIGHT
        for i, x in enumerate((-4.0, -1.5, 1.5, 4.0)):
            # Cord
            cord = helpers.create_cylinder(
                f"HangingPlant_Cord_{i}",
                radius=0.005,
                depth=0.5,
                vertices=6,
                location=(x, -d * 0.5 + 1.2, h - 0.35),
            )
            helpers.assign_material(cord, self.mat.get("MAT_MetalBlack"))
            self._link(cord, "Plants")

            pot = helpers.create_cylinder(
                f"HangingPlant_Pot_{i}",
                radius=0.1,
                depth=0.12,
                vertices=12,
                location=(x + self.rng.uniform(-0.05, 0.05), -d * 0.5 + 1.2, h - 0.65),
            )
            helpers.assign_material(pot, self.mat.get("MAT_CeramicWhite"))
            self._link(pot, "Plants")

            for j in range(4):
                foliage = helpers.create_uv_sphere(
                    f"HangingPlant_Leaf_{i}_{j}",
                    radius=self.rng.uniform(0.08, 0.14),
                    segments=10,
                    rings=6,
                    location=(
                        x + self.rng.uniform(-0.1, 0.1),
                        -d * 0.5 + 1.2 + self.rng.uniform(-0.05, 0.05),
                        h - 0.7 - j * 0.08,
                    ),
                )
                helpers.assign_material(foliage, self.mat.get("MAT_PlantLeaf"))
                helpers.shade_smooth(foliage)
                self._link(foliage, "Plants")

    def _build_artwork(self) -> None:
        w, d = config.SHOP_WIDTH, config.SHOP_DEPTH
        art_spots = [
            (-w * 0.5 + 0.14, -3.0, 1.8, 0.8, 0.6),
            (-w * 0.5 + 0.14, 0.0, 1.9, 0.6, 0.8),
            (-w * 0.5 + 0.14, 3.0, 1.7, 1.0, 0.5),
            (w * 0.5 - 0.14, -2.0, 1.85, 0.7, 0.7),
            (w * 0.5 - 0.14, 2.5, 1.9, 0.9, 0.55),
        ]
        for i, (x, y, z, aw, ah) in enumerate(art_spots):
            frame = helpers.create_cube(
                f"Art_Frame_{i}",
                size=(0.04, aw + 0.08, ah + 0.08),
                location=(x, y, z),
            )
            helpers.assign_material(frame, self.mat.get("MAT_WoodWalnut"))
            canvas = helpers.create_cube(
                f"Art_Canvas_{i}",
                size=(0.02, aw, ah),
                location=(x + (0.03 if x < 0 else -0.03), y, z),
            )
            helpers.assign_material(
                canvas,
                self.mat.get("MAT_PaperMenu") if i % 2 == 0 else self.mat.get("MAT_FabricLinen"),
            )
            self._link(frame, "Art")
            self._link(canvas, "Art")

    def _build_rugs(self) -> None:
        rugs = [
            ("Rug_Lounge", (-4.2, 5.2, 0.005), (2.4, 1.8)),
            ("Rug_Reading", (-5.0, 6.5, 0.005), (2.0, 1.6)),
            ("Rug_Center", (0.5, -1.0, 0.005), (2.8, 2.0)),
        ]
        for name, loc, size in rugs:
            rug = helpers.create_cube(name, size=(size[0], size[1], 0.01), location=loc)
            helpers.assign_material(rug, self.mat.get("MAT_FabricUpholstery"))
            rug.rotation_euler = (0, 0, self.rng.uniform(-0.15, 0.15))
            self._link(rug, "Rugs")

    def _build_curtains(self) -> None:
        """Side curtains flanking the window bank — cloth physics candidates."""
        d, h = config.SHOP_DEPTH, config.SHOP_HEIGHT
        for side, x in (("L", -config.WINDOW_BANK_WIDTH * 0.5 - 0.3), ("R", config.WINDOW_BANK_WIDTH * 0.5 + 0.3)):
            rod = helpers.create_cylinder(
                f"CurtainRod_{side}",
                radius=0.015,
                depth=0.8,
                vertices=12,
                location=(x, -d * 0.5 + 0.25, h - 0.2),
                rotation=(0, math.radians(90), 0),
            )
            helpers.assign_material(rod, self.mat.get("MAT_MetalBrushed"))
            self._link(rod, "Art")

            curtain = helpers.create_cube(
                f"Curtain_{side}",
                size=(0.35, 0.05, h - 0.4),
                location=(x, -d * 0.5 + 0.3, (h - 0.4) * 0.5),
            )
            helpers.assign_material(curtain, self.mat.get("MAT_FabricCurtain"))
            helpers.subdivide_object(curtain, 2, 3)
            # Mark for cloth — actual modifier added by PhysicsSystem
            curtain["coffee_shop_cloth"] = True
            self._link(curtain, "Art")

    def _build_lamps(self) -> None:
        """Practical hanging pendant lamps and floor lamps."""
        h = config.SHOP_HEIGHT
        # Pendants over window tables
        for i, x in enumerate((-4.5, -2.5, -0.5, 1.5, 3.5)):
            cord = helpers.create_cylinder(
                f"Pendant_Cord_{i}",
                radius=0.005,
                depth=0.6,
                vertices=6,
                location=(x, -config.SHOP_DEPTH * 0.5 + 1.8, h - 0.35),
            )
            helpers.assign_material(cord, self.mat.get("MAT_MetalBlack"))
            shade = helpers.create_cylinder(
                f"Pendant_Shade_{i}",
                radius=0.15,
                depth=0.18,
                vertices=24,
                location=(x, -config.SHOP_DEPTH * 0.5 + 1.8, h - 0.7),
            )
            helpers.assign_material(shade, self.mat.get("MAT_MetalBrushed"))
            bulb = helpers.create_uv_sphere(
                f"Pendant_Bulb_{i}",
                radius=0.04,
                segments=12,
                rings=8,
                location=(x, -config.SHOP_DEPTH * 0.5 + 1.8, h - 0.72),
            )
            # Emission via separate light objects in LightingSystem; material warm ceramic
            helpers.assign_material(bulb, self.mat.get("MAT_CeramicWhite"))
            for obj in (cord, shade, bulb):
                self._link(obj, "Lamps")

        # Pendants over bar
        for i, x in enumerate((-2.0, 0.0, 2.0)):
            shade = helpers.create_cylinder(
                f"BarPendant_{i}",
                radius=0.12,
                depth=0.2,
                vertices=20,
                location=(x, config.SHOP_DEPTH * 0.5 - 2.2, h - 0.9),
            )
            helpers.assign_material(shade, self.mat.get("MAT_MetalBlack"))
            self._link(shade, "Lamps")

        # Floor lamp in reading corner
        pole = helpers.create_cylinder(
            "FloorLamp_Pole", radius=0.02, depth=1.5, vertices=12, location=(-5.8, 7.0, 0.75)
        )
        helpers.assign_material(pole, self.mat.get("MAT_MetalBlack"))
        shade = helpers.create_cylinder(
            "FloorLamp_Shade", radius=0.22, depth=0.3, vertices=24, location=(-5.8, 7.0, 1.6)
        )
        helpers.assign_material(shade, self.mat.get("MAT_FabricLinen"))
        base = helpers.create_cylinder(
            "FloorLamp_Base", radius=0.2, depth=0.04, vertices=16, location=(-5.8, 7.0, 0.02)
        )
        helpers.assign_material(base, self.mat.get("MAT_MetalBlack"))
        for obj in (pole, shade, base):
            self._link(obj, "Lamps")

    def _build_signs(self) -> None:
        # Exterior-facing neon-style shop sign above windows (interior mount visible)
        sign = helpers.create_cube(
            "Sign_ShopName",
            size=(2.5, 0.08, 0.45),
            location=(0, -config.SHOP_DEPTH * 0.5 + 0.2, config.SHOP_HEIGHT - 0.5),
        )
        helpers.assign_material(sign, self.mat.get("MAT_MetalBlack"))
        self._link(sign, "Signs")

        letter_board = helpers.create_cube(
            "Sign_Letters",
            size=(2.3, 0.02, 0.3),
            location=(0, -config.SHOP_DEPTH * 0.5 + 0.25, config.SHOP_HEIGHT - 0.5),
        )
        helpers.assign_material(letter_board, self.mat.get("MAT_CeramicWhite"))
        self._link(letter_board, "Signs")

        # Open sign near entrance area
        open_sign = helpers.create_cube(
            "Sign_Open",
            size=(0.4, 0.05, 0.25),
            location=(5.5, -config.SHOP_DEPTH * 0.5 + 0.5, 1.8),
        )
        helpers.assign_material(open_sign, self.mat.get("MAT_MetalChrome"))
        self._link(open_sign, "Signs")

    def _build_candles(self) -> None:
        # Table candles for cozy atmosphere
        table_positions = [
            (-4.5, -config.SHOP_DEPTH * 0.5 + 1.8, 0.78),
            (-2.5, -config.SHOP_DEPTH * 0.5 + 1.8, 0.78),
            (-0.5, -config.SHOP_DEPTH * 0.5 + 1.8, 0.78),
            (1.5, -config.SHOP_DEPTH * 0.5 + 1.8, 0.78),
            (3.5, -config.SHOP_DEPTH * 0.5 + 1.8, 0.78),
            (-4.2, 5.5, 0.45),
            (-4.4, 6.8, 0.45),
        ]
        for i, (x, y, z) in enumerate(table_positions):
            if self.rng.random() < 0.25:
                continue
            wax = helpers.create_cylinder(
                f"Candle_{i}",
                radius=self.rng.uniform(0.025, 0.04),
                depth=self.rng.uniform(0.08, 0.14),
                vertices=12,
                location=(x + self.rng.uniform(-0.05, 0.05), y, z),
            )
            helpers.assign_material(wax, self.mat.get("MAT_CandleWax"))
            flame = helpers.create_uv_sphere(
                f"CandleFlame_{i}",
                radius=0.012,
                segments=8,
                rings=6,
                location=(wax.location.x, wax.location.y, z + 0.08),
            )
            helpers.assign_material(flame, self.mat.get("MAT_CandleWax"))
            flame["coffee_shop_flame"] = True
            self._link(wax, "Candles")
            self._link(flame, "Candles")

    def _build_wall_decor(self) -> None:
        # Floating shelves with small objects
        for i, y in enumerate((-4.0, -1.0, 2.0)):
            shelf = helpers.create_cube(
                f"WallShelf_{i}",
                size=(0.8, 0.2, 0.04),
                location=(-config.SHOP_WIDTH * 0.5 + 0.25, y, 1.5),
            )
            helpers.assign_material(shelf, self.mat.get("MAT_WoodOak"))
            self._link(shelf, "Art")
            vase = helpers.create_cylinder(
                f"WallVase_{i}",
                radius=0.05,
                depth=0.15,
                vertices=12,
                location=(-config.SHOP_WIDTH * 0.5 + 0.25, y, 1.6),
            )
            helpers.assign_material(vase, self.mat.get("MAT_CeramicWhite"))
            self._link(vase, "Art")
