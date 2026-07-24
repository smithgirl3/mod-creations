# SPDX-License-Identifier: MIT
"""
Coffee shop architecture: walls, floor, ceiling, roof, columns, trim, windows.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional

import bpy

from . import config, helpers
from .material_manager import MaterialManager


class ArchitectureBuilder:
    """Builds the structural shell of the coffee shop."""

    def __init__(self, materials: MaterialManager, collections: dict):
        self.mat = materials
        self.cols = collections
        self.objects: List[bpy.types.Object] = []

    def build(self) -> List[bpy.types.Object]:
        self.objects.clear()
        self._build_floor()
        self._build_walls()
        self._build_wood_paneling()
        self._build_baseboards_and_trim()
        self._build_columns()
        self._build_ceiling()
        self._build_roof()
        self._build_windows()
        return self.objects

    # ------------------------------------------------------------------

    def _link(self, obj: bpy.types.Object, collection_key: str) -> bpy.types.Object:
        col = self.cols.get(collection_key) or collection_key
        helpers.link_object_to_collection(obj, col)
        self.objects.append(obj)
        return obj

    def _build_floor(self) -> None:
        w, d, t = config.SHOP_WIDTH, config.SHOP_DEPTH, config.FLOOR_THICKNESS
        floor = helpers.create_cube(
            "ARCH_Floor",
            size=(w, d, t),
            location=(0, 0, -t * 0.5),
        )
        helpers.assign_material(floor, self.mat.get("MAT_WoodFloor"))
        helpers.bevel_object(floor, 0.002, 2)
        self._link(floor, "Floor")

        # Entrance mat near door (street side)
        mat_obj = helpers.create_cube(
            "ARCH_EntranceMat",
            size=(1.2, 0.8, 0.02),
            location=(0, -d * 0.5 + 1.2, 0.01),
        )
        helpers.assign_material(mat_obj, self.mat.get("MAT_RubberFloorMat"))
        self._link(mat_obj, "Floor")

    def _build_walls(self) -> None:
        w, d, h, t = config.SHOP_WIDTH, config.SHOP_DEPTH, config.SHOP_HEIGHT, config.WALL_THICKNESS
        wall_mat = self.mat.get("MAT_PaintWall")
        plaster = self.mat.get("MAT_PlasterWarm")

        # Back wall (+Y)
        back = helpers.create_cube(
            "ARCH_Wall_Back",
            size=(w + t * 2, t, h),
            location=(0, d * 0.5, h * 0.5),
        )
        helpers.assign_material(back, plaster)
        self._link(back, "Walls")

        # Left wall (-X)
        left = helpers.create_cube(
            "ARCH_Wall_Left",
            size=(t, d, h),
            location=(-w * 0.5, 0, h * 0.5),
        )
        helpers.assign_material(left, wall_mat)
        self._link(left, "Walls")

        # Right wall (+X)
        right = helpers.create_cube(
            "ARCH_Wall_Right",
            size=(t, d, h),
            location=(w * 0.5, 0, h * 0.5),
        )
        helpers.assign_material(right, wall_mat)
        self._link(right, "Walls")

        # Front wall (-Y) with large window opening — solid side piers + header/sill
        opening = config.WINDOW_BANK_WIDTH
        pier_w = (w - opening) * 0.5
        for side, x in (("L", -w * 0.5 + pier_w * 0.5), ("R", w * 0.5 - pier_w * 0.5)):
            pier = helpers.create_cube(
                f"ARCH_Wall_FrontPier_{side}",
                size=(max(pier_w, 0.3), t, h),
                location=(x, -d * 0.5, h * 0.5),
            )
            helpers.assign_material(pier, wall_mat)
            self._link(pier, "Walls")

        # Header above windows
        header_h = max(0.2, h - config.WINDOW_PANE_HEIGHT - 0.15)
        header = helpers.create_cube(
            "ARCH_Wall_FrontHeader",
            size=(opening + 0.2, t, header_h),
            location=(0, -d * 0.5, h - header_h * 0.5),
        )
        helpers.assign_material(header, wall_mat)
        self._link(header, "Walls")

        # Low sill / kick wall
        sill_h = 0.12
        sill = helpers.create_cube(
            "ARCH_Wall_FrontSill",
            size=(opening + 0.2, t * 1.2, sill_h),
            location=(0, -d * 0.5, sill_h * 0.5),
        )
        helpers.assign_material(sill, self.mat.get("MAT_WoodWalnut"))
        self._link(sill, "Walls")

        # Interior partition near coffee bar (partial wall)
        partition = helpers.create_cube(
            "ARCH_Wall_BarPartition",
            size=(0.15, 4.5, 1.1),
            location=(-w * 0.5 + 4.5, d * 0.5 - 3.5, 0.55),
        )
        helpers.assign_material(partition, self.mat.get("MAT_WoodOak"))
        helpers.bevel_object(partition, 0.01, 3)
        self._link(partition, "Walls")

    def _build_wood_paneling(self) -> None:
        w, d, h = config.SHOP_WIDTH, config.SHOP_DEPTH, config.SHOP_HEIGHT
        panel_h = 1.2
        wood = self.mat.get("MAT_WoodWalnut")

        # Wainscoting on left and right walls
        for name, x in (("Left", -w * 0.5 + 0.14), ("Right", w * 0.5 - 0.14)):
            panel = helpers.create_cube(
                f"ARCH_Panel_{name}",
                size=(0.03, d - 0.5, panel_h),
                location=(x, 0, panel_h * 0.5),
            )
            helpers.assign_material(panel, wood)
            helpers.bevel_object(panel, 0.003, 2)
            self._link(panel, "Walls")

        # Vertical panel battens
        spacing = 0.6
        y = -d * 0.5 + 1.0
        idx = 0
        while y < d * 0.5 - 1.0:
            for x_sign, x_base in (("L", -w * 0.5 + 0.16), ("R", w * 0.5 - 0.16)):
                batten = helpers.create_cube(
                    f"ARCH_Batten_{x_sign}_{idx}",
                    size=(0.04, 0.02, panel_h),
                    location=(x_base, y, panel_h * 0.5),
                )
                helpers.assign_material(batten, self.mat.get("MAT_WoodOak"))
                self._link(batten, "Trim")
            y += spacing
            idx += 1

    def _build_baseboards_and_trim(self) -> None:
        w, d = config.SHOP_WIDTH, config.SHOP_DEPTH
        bh = config.BASEBOARD_HEIGHT
        wood = self.mat.get("MAT_WoodOak")

        # Perimeter baseboards (simplified as long boxes)
        specs = [
            ("Base_Back", (w, 0.03, bh), (0, d * 0.5 - 0.14, bh * 0.5)),
            ("Base_Left", (0.03, d, bh), (-w * 0.5 + 0.14, 0, bh * 0.5)),
            ("Base_Right", (0.03, d, bh), (w * 0.5 - 0.14, 0, bh * 0.5)),
            ("Base_FrontL", ((w - config.WINDOW_BANK_WIDTH) * 0.5, 0.03, bh),
             (-(config.WINDOW_BANK_WIDTH + (w - config.WINDOW_BANK_WIDTH) * 0.5) * 0.5, -d * 0.5 + 0.14, bh * 0.5)),
            ("Base_FrontR", ((w - config.WINDOW_BANK_WIDTH) * 0.5, 0.03, bh),
             ((config.WINDOW_BANK_WIDTH + (w - config.WINDOW_BANK_WIDTH) * 0.5) * 0.5, -d * 0.5 + 0.14, bh * 0.5)),
        ]
        for name, size, loc in specs:
            bb = helpers.create_cube(f"ARCH_{name}", size=size, location=loc)
            helpers.assign_material(bb, wood)
            self._link(bb, "Trim")

        # Crown molding along ceiling perimeter
        ch = 0.08
        z = config.SHOP_HEIGHT - ch * 0.5
        crown_specs = [
            ("Crown_Back", (w, 0.06, ch), (0, d * 0.5 - 0.16, z)),
            ("Crown_Left", (0.06, d, ch), (-w * 0.5 + 0.16, 0, z)),
            ("Crown_Right", (0.06, d, ch), (w * 0.5 - 0.16, 0, z)),
            ("Crown_Front", (w, 0.06, ch), (0, -d * 0.5 + 0.16, z)),
        ]
        for name, size, loc in crown_specs:
            c = helpers.create_cube(f"ARCH_{name}", size=size, location=loc)
            helpers.assign_material(c, wood)
            self._link(c, "Trim")

    def _build_columns(self) -> None:
        w, d, h = config.SHOP_WIDTH, config.SHOP_DEPTH, config.SHOP_HEIGHT
        cs = config.COLUMN_SIZE
        wood = self.mat.get("MAT_WoodOak")
        positions = [
            (-w * 0.25, -d * 0.15),
            (w * 0.25, -d * 0.15),
            (-w * 0.25, d * 0.2),
            (w * 0.25, d * 0.2),
        ]
        for i, (x, y) in enumerate(positions):
            col = helpers.create_cube(
                f"ARCH_Column_{i}",
                size=(cs, cs, h),
                location=(x, y, h * 0.5),
            )
            helpers.assign_material(col, wood)
            helpers.bevel_object(col, 0.02, 3)
            self._link(col, "Columns")

            # Capital / base trim rings
            for suffix, z in (("Base", 0.08), ("Cap", h - 0.08)):
                ring = helpers.create_cube(
                    f"ARCH_Column_{i}_{suffix}",
                    size=(cs + 0.08, cs + 0.08, 0.1),
                    location=(x, y, z),
                )
                helpers.assign_material(ring, self.mat.get("MAT_WoodWalnut"))
                self._link(ring, "Columns")

    def _build_ceiling(self) -> None:
        w, d, h = config.SHOP_WIDTH, config.SHOP_DEPTH, config.SHOP_HEIGHT
        ceiling = helpers.create_cube(
            "ARCH_Ceiling",
            size=(w, d, 0.08),
            location=(0, 0, h + 0.04),
        )
        helpers.assign_material(ceiling, self.mat.get("MAT_PlasterWarm"))
        self._link(ceiling, "Ceiling")

        # Exposed wood beams
        beam_mat = self.mat.get("MAT_WoodWalnut")
        spacing = 2.0
        y = -d * 0.5 + 1.5
        idx = 0
        while y < d * 0.5 - 1.0:
            beam = helpers.create_cube(
                f"ARCH_CeilingBeam_{idx}",
                size=(w - 0.4, 0.18, 0.22),
                location=(0, y, h - 0.05),
            )
            helpers.assign_material(beam, beam_mat)
            helpers.bevel_object(beam, 0.01, 2)
            self._link(beam, "Ceiling")
            y += spacing
            idx += 1

    def _build_roof(self) -> None:
        w, d, h = config.SHOP_WIDTH, config.SHOP_DEPTH, config.SHOP_HEIGHT
        # Low-slope commercial roof volume (for exterior silhouette)
        roof = helpers.create_cube(
            "ARCH_Roof",
            size=(w + 0.8, d + 0.8, config.ROOF_THICKNESS),
            location=(0, 0, h + 0.3 + config.ROOF_THICKNESS * 0.5),
        )
        helpers.assign_material(roof, self.mat.get("MAT_Concrete"))
        self._link(roof, "Roof")

        # Parapet
        for name, size, loc in (
            ("Parapet_N", (w + 1.0, 0.2, 0.5), (0, d * 0.5 + 0.3, h + 0.55)),
            ("Parapet_S", (w + 1.0, 0.2, 0.5), (0, -d * 0.5 - 0.3, h + 0.55)),
            ("Parapet_E", (0.2, d + 1.0, 0.5), (w * 0.5 + 0.3, 0, h + 0.55)),
            ("Parapet_W", (0.2, d + 1.0, 0.5), (-w * 0.5 - 0.3, 0, h + 0.55)),
        ):
            p = helpers.create_cube(f"ARCH_{name}", size=size, location=loc)
            helpers.assign_material(p, self.mat.get("MAT_BrickExterior"))
            self._link(p, "Roof")

    def _build_windows(self) -> None:
        """Floor-to-ceiling window bank with rain glass, mullions, frames."""
        w, d = config.SHOP_WIDTH, config.SHOP_DEPTH
        pane_w = config.WINDOW_PANE_WIDTH
        pane_h = config.WINDOW_PANE_HEIGHT
        mullion = config.WINDOW_MULLION
        glass_t = config.GLASS_THICKNESS
        glass_mat = self.mat.get("MAT_GlassRain")
        frame_mat = self.mat.get("MAT_MetalBlack")
        y = -d * 0.5 + glass_t * 0.5 + 0.02
        z = pane_h * 0.5 + 0.12

        total_span = config.WINDOW_BANK_WIDTH
        count = max(1, int(total_span / (pane_w + mullion)))
        start_x = -total_span * 0.5 + pane_w * 0.5

        for i in range(count):
            x = start_x + i * (pane_w + mullion)

            # Glass pane
            glass = helpers.create_cube(
                f"WIN_Glass_{i}",
                size=(pane_w, glass_t, pane_h),
                location=(x, y, z),
            )
            helpers.assign_material(glass, glass_mat)
            helpers.shade_smooth(glass)
            self._link(glass, "Windows")

            # Outer frame
            frame = helpers.create_cube(
                f"WIN_Frame_{i}",
                size=(pane_w + mullion * 1.5, 0.06, pane_h + mullion * 1.5),
                location=(x, y - 0.02, z),
            )
            helpers.assign_material(frame, frame_mat)
            # Hollow look via second inset — approximated with thinner overlay removed;
            # use solidify-style visual: scale down inner void via boolean not needed for game LOD
            self._link(frame, "Windows")

            # Vertical mullion between panes
            if i < count - 1:
                mx = x + pane_w * 0.5 + mullion * 0.5
                mull = helpers.create_cube(
                    f"WIN_Mullion_{i}",
                    size=(mullion, 0.07, pane_h + 0.1),
                    location=(mx, y - 0.01, z),
                )
                helpers.assign_material(mull, frame_mat)
                self._link(mull, "Windows")

        # Horizontal transom bar
        transom = helpers.create_cube(
            "WIN_Transom",
            size=(total_span, 0.07, mullion * 1.2),
            location=(0, y - 0.01, z + pane_h * 0.15),
        )
        helpers.assign_material(transom, frame_mat)
        self._link(transom, "Windows")

        # Rain droplet decals as small spheres on glass (close-up detail)
        import random
        rng = random.Random(config.RANDOM_SEED + 7)
        for i in range(60):
            gx = rng.uniform(-total_span * 0.45, total_span * 0.45)
            gz = rng.uniform(0.4, pane_h + 0.05)
            drop = helpers.create_uv_sphere(
                f"WIN_RainDrop_{i}",
                radius=rng.uniform(0.004, 0.012),
                segments=8,
                rings=6,
                location=(gx, y + glass_t * 0.6, gz),
            )
            helpers.assign_material(drop, self.mat.get("MAT_WaterPuddle"))
            helpers.shade_smooth(drop)
            self._link(drop, "Windows")
