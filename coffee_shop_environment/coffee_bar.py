# SPDX-License-Identifier: MIT
"""
Complete coffee preparation station: counter, machines, display, props.
Detailed enough for close-up camera views.
"""

from __future__ import annotations

import math
import random
from typing import List, Tuple

import bpy

from . import config, helpers
from .material_manager import MaterialManager


class CoffeeBarBuilder:
    """Builds the barista station and service counter."""

    def __init__(self, materials: MaterialManager, collections: dict, seed: int = config.RANDOM_SEED):
        self.mat = materials
        self.cols = collections
        self.rng = random.Random(seed + 99)
        self.objects: List[bpy.types.Object] = []

    def build(self) -> List[bpy.types.Object]:
        self.objects.clear()
        # Bar along back wall
        d = config.SHOP_DEPTH
        bar_y = d * 0.5 - 2.2
        self._build_counter(bar_y)
        self._build_espresso_machine(0.5, bar_y - 0.15)
        self._build_grinder(-0.6, bar_y - 0.1, "Grinder_A")
        self._build_grinder(-1.1, bar_y - 0.1, "Grinder_B")
        self._build_brewer(1.4, bar_y - 0.1)
        self._build_sink(2.2, bar_y - 0.1)
        self._build_display_case(-2.5, bar_y - 0.3)
        self._build_pastries(-2.5, bar_y - 0.3)
        self._build_cash_register(-3.6, bar_y - 0.15)
        self._build_menus(-3.8, bar_y + 0.5)
        self._build_shelving(bar_y)
        self._build_cups_and_mugs(bar_y)
        self._build_napkin_holders(bar_y)
        self._build_bean_bags(-4.5, bar_y + 0.8)
        return self.objects

    def _link(self, obj, key: str = "Props"):
        helpers.link_object_to_collection(obj, self.cols.get(key, key))
        self.objects.append(obj)
        return obj

    def _build_counter(self, bar_y: float) -> None:
        # Main L-shaped service counter
        main = helpers.create_cube(
            "Bar_Counter_Main",
            size=(8.5, 0.7, 0.9),
            location=(0.0, bar_y, 0.45),
        )
        helpers.assign_material(main, self.mat.get("MAT_WoodWalnut"))
        helpers.bevel_object(main, 0.015, 3)
        self._link(main, "Counter")

        top = helpers.create_cube(
            "Bar_Counter_Top",
            size=(8.6, 0.75, 0.04),
            location=(0.0, bar_y, 0.92),
        )
        helpers.assign_material(top, self.mat.get("MAT_MetalBrushed"))
        helpers.bevel_object(top, 0.005, 2)
        self._link(top, "Counter")

        # Customer-facing overhang ledge
        ledge = helpers.create_cube(
            "Bar_Counter_Ledge",
            size=(8.5, 0.25, 0.05),
            location=(0.0, bar_y - 0.45, 1.0),
        )
        helpers.assign_material(ledge, self.mat.get("MAT_WoodOak"))
        self._link(ledge, "Counter")

        # Side return counter
        side = helpers.create_cube(
            "Bar_Counter_Side",
            size=(0.7, 2.5, 0.9),
            location=(-4.5, bar_y - 1.2, 0.45),
        )
        helpers.assign_material(side, self.mat.get("MAT_WoodWalnut"))
        self._link(side, "Counter")

        # Kick plate
        kick = helpers.create_cube(
            "Bar_KickPlate",
            size=(8.5, 0.02, 0.12),
            location=(0.0, bar_y - 0.35, 0.06),
        )
        helpers.assign_material(kick, self.mat.get("MAT_MetalBlack"))
        self._link(kick, "Counter")

    def _build_espresso_machine(self, x: float, y: float) -> None:
        body = helpers.create_cube(
            "Espresso_Body",
            size=(0.7, 0.5, 0.55),
            location=(x, y, 1.2),
        )
        helpers.assign_material(body, self.mat.get("MAT_MetalChrome"))
        helpers.bevel_object(body, 0.01, 3)
        helpers.shade_smooth(body)

        group = helpers.add_empty("EspressoMachine", location=(x, y, 0.95), collection=self.cols.get("Machines"))

        # Group head
        for i, ox in enumerate((-0.15, 0.15)):
            head = helpers.create_cylinder(
                f"Espresso_GroupHead_{i}",
                radius=0.05,
                depth=0.08,
                vertices=16,
                location=(x + ox, y - 0.22, 1.15),
                rotation=(math.radians(90), 0, 0),
            )
            helpers.assign_material(head, self.mat.get("MAT_MetalBlack"))
            portafilter = helpers.create_cylinder(
                f"Espresso_PF_{i}",
                radius=0.04,
                depth=0.12,
                vertices=12,
                location=(x + ox, y - 0.32, 1.05),
                rotation=(math.radians(70), 0, 0),
            )
            helpers.assign_material(portafilter, self.mat.get("MAT_MetalBlack"))
            helpers.parent_keep_transform(head, group)
            helpers.parent_keep_transform(portafilter, group)
            self._link(head, "Machines")
            self._link(portafilter, "Machines")

        # Steam wand
        wand = helpers.create_cylinder(
            "Espresso_SteamWand",
            radius=0.012,
            depth=0.28,
            vertices=8,
            location=(x + 0.32, y - 0.15, 1.15),
            rotation=(math.radians(40), 0, math.radians(20)),
        )
        helpers.assign_material(wand, self.mat.get("MAT_MetalChrome"))
        helpers.parent_keep_transform(wand, group)
        self._link(wand, "Machines")

        # Cup warmer tray on top
        tray = helpers.create_cube(
            "Espresso_CupWarmer",
            size=(0.65, 0.4, 0.02),
            location=(x, y, 1.49),
        )
        helpers.assign_material(tray, self.mat.get("MAT_MetalBlack"))
        helpers.parent_keep_transform(body, group)
        helpers.parent_keep_transform(tray, group)
        self._link(body, "Machines")
        self._link(tray, "Machines")

        # Drip tray
        drip = helpers.create_cube(
            "Espresso_DripTray",
            size=(0.65, 0.2, 0.03),
            location=(x, y - 0.2, 0.97),
        )
        helpers.assign_material(drip, self.mat.get("MAT_MetalBlack"))
        helpers.parent_keep_transform(drip, group)
        self._link(drip, "Machines")

        # Control knobs
        for i, ox in enumerate((-0.2, 0.0, 0.2)):
            knob = helpers.create_cylinder(
                f"Espresso_Knob_{i}",
                radius=0.02,
                depth=0.03,
                vertices=12,
                location=(x + ox, y - 0.26, 1.35),
                rotation=(math.radians(90), 0, 0),
            )
            helpers.assign_material(knob, self.mat.get("MAT_MetalBlack"))
            helpers.parent_keep_transform(knob, group)
            self._link(knob, "Machines")

    def _build_grinder(self, x: float, y: float, name: str) -> None:
        base = helpers.create_cube(f"{name}_Base", size=(0.22, 0.28, 0.35), location=(x, y, 1.12))
        helpers.assign_material(base, self.mat.get("MAT_MetalBlack"))
        helpers.bevel_object(base, 0.008, 2)

        hopper = helpers.create_cone(
            f"{name}_Hopper",
            radius1=0.1,
            depth=0.22,
            vertices=24,
            location=(x, y, 1.42),
        )
        # Flip cone — use cylinder hopper for simplicity
        bpy.data.objects.remove(hopper, do_unlink=True)
        hopper = helpers.create_cylinder(
            f"{name}_Hopper",
            radius=0.09,
            depth=0.2,
            vertices=24,
            location=(x, y, 1.45),
        )
        helpers.assign_material(hopper, self.mat.get("MAT_GlassClear"))
        helpers.shade_smooth(hopper)

        beans = helpers.create_uv_sphere(f"{name}_Beans", radius=0.07, location=(x, y, 1.45))
        helpers.assign_material(beans, self.mat.get("MAT_FoodCoffee"))

        chute = helpers.create_cylinder(
            f"{name}_Chute",
            radius=0.03,
            depth=0.1,
            vertices=12,
            location=(x, y - 0.12, 1.05),
            rotation=(math.radians(90), 0, 0),
        )
        helpers.assign_material(chute, self.mat.get("MAT_MetalChrome"))

        for obj in (base, hopper, beans, chute):
            self._link(obj, "Machines")

    def _build_brewer(self, x: float, y: float) -> None:
        body = helpers.create_cube("Brewer_Body", size=(0.3, 0.35, 0.45), location=(x, y, 1.18))
        helpers.assign_material(body, self.mat.get("MAT_MetalBrushed"))
        carafe = helpers.create_cylinder(
            "Brewer_Carafe", radius=0.08, depth=0.18, vertices=24, location=(x, y - 0.05, 1.0)
        )
        helpers.assign_material(carafe, self.mat.get("MAT_GlassClear"))
        liquid = helpers.create_cylinder(
            "Brewer_Coffee", radius=0.07, depth=0.1, vertices=16, location=(x, y - 0.05, 0.98)
        )
        helpers.assign_material(liquid, self.mat.get("MAT_FoodCoffee"))
        for obj in (body, carafe, liquid):
            self._link(obj, "Machines")

    def _build_sink(self, x: float, y: float) -> None:
        basin = helpers.create_cube("Sink_Basin", size=(0.45, 0.4, 0.2), location=(x, y, 0.95))
        helpers.assign_material(basin, self.mat.get("MAT_MetalChrome"))
        faucet = helpers.create_cylinder(
            "Sink_Faucet",
            radius=0.015,
            depth=0.25,
            vertices=12,
            location=(x, y + 0.1, 1.2),
            rotation=(math.radians(30), 0, 0),
        )
        helpers.assign_material(faucet, self.mat.get("MAT_MetalChrome"))
        self._link(basin, "Machines")
        self._link(faucet, "Machines")

    def _build_display_case(self, x: float, y: float) -> None:
        case = helpers.create_cube("DisplayCase_Body", size=(1.4, 0.6, 1.1), location=(x, y, 0.55))
        helpers.assign_material(case, self.mat.get("MAT_MetalBlack"))
        glass_front = helpers.create_cube(
            "DisplayCase_Glass", size=(1.3, 0.02, 0.9), location=(x, y - 0.3, 0.65)
        )
        helpers.assign_material(glass_front, self.mat.get("MAT_GlassClear"))
        shelf1 = helpers.create_cube("DisplayCase_Shelf1", size=(1.25, 0.5, 0.02), location=(x, y, 0.45))
        shelf2 = helpers.create_cube("DisplayCase_Shelf2", size=(1.25, 0.5, 0.02), location=(x, y, 0.75))
        for s in (shelf1, shelf2):
            helpers.assign_material(s, self.mat.get("MAT_GlassClear"))
        for obj in (case, glass_front, shelf1, shelf2):
            self._link(obj, "Display")

    def _build_pastries(self, x: float, y: float) -> None:
        pastry_types = [
            ("Croissant", (0.12, 0.05, 0.04), (0.72, 0.48, 0.22, 1)),
            ("Muffin", (0.07, 0.07, 0.08), (0.45, 0.28, 0.15, 1)),
            ("Cookie", (0.06, 0.06, 0.02), (0.55, 0.32, 0.12, 1)),
            ("Danish", (0.09, 0.09, 0.04), (0.8, 0.65, 0.35, 1)),
        ]
        idx = 0
        for shelf_z in (0.5, 0.8):
            for i in range(6):
                pname, size, _col = pastry_types[i % len(pastry_types)]
                px = x - 0.5 + i * 0.18 + self.rng.uniform(-0.02, 0.02)
                py = y + self.rng.uniform(-0.1, 0.1)
                if "Muffin" in pname:
                    p = helpers.create_cylinder(
                        f"Pastry_{pname}_{idx}",
                        radius=size[0],
                        depth=size[2],
                        vertices=12,
                        location=(px, py, shelf_z),
                    )
                else:
                    p = helpers.create_cube(
                        f"Pastry_{pname}_{idx}",
                        size=size,
                        location=(px, py, shelf_z),
                    )
                    p.rotation_euler = (0, 0, self.rng.uniform(0, math.pi))
                helpers.assign_material(p, self.mat.get("MAT_FoodPastry"))
                helpers.shade_smooth(p)
                self._link(p, "Display")
                idx += 1

    def _build_cash_register(self, x: float, y: float) -> None:
        base = helpers.create_cube("Register_Base", size=(0.35, 0.4, 0.12), location=(x, y, 0.98))
        helpers.assign_material(base, self.mat.get("MAT_MetalBlack"))
        screen = helpers.create_cube("Register_Screen", size=(0.28, 0.02, 0.2), location=(x, y + 0.1, 1.18))
        helpers.assign_material(screen, self.mat.get("MAT_GlassClear"))
        # Slight emission look via material already; add tablet stand
        stand = helpers.create_cube("Register_Stand", size=(0.08, 0.08, 0.15), location=(x, y + 0.05, 1.05))
        helpers.assign_material(stand, self.mat.get("MAT_MetalBrushed"))
        drawer = helpers.create_cube("Register_Drawer", size=(0.32, 0.35, 0.08), location=(x, y, 0.9))
        helpers.assign_material(drawer, self.mat.get("MAT_MetalBrushed"))
        for obj in (base, screen, stand, drawer):
            self._link(obj, "Props")

    def _build_menus(self, x: float, y: float) -> None:
        # Wall menu board behind bar
        board = helpers.create_cube(
            "Menu_Board",
            size=(2.4, 0.05, 1.4),
            location=(x + 2.0, config.SHOP_DEPTH * 0.5 - 0.2, 2.2),
        )
        helpers.assign_material(board, self.mat.get("MAT_WoodOak"))
        self._link(board, "Menus")

        for i in range(3):
            panel = helpers.create_cube(
                f"Menu_Panel_{i}",
                size=(0.7, 0.01, 1.1),
                location=(x + 1.2 + i * 0.75, config.SHOP_DEPTH * 0.5 - 0.23, 2.2),
            )
            helpers.assign_material(panel, self.mat.get("MAT_PaperMenu"))
            self._link(panel, "Menus")

        # Table tent cards near register
        for i in range(2):
            tent = helpers.create_cube(
                f"Menu_Tent_{i}",
                size=(0.12, 0.02, 0.16),
                location=(x + 0.3 + i * 0.2, y - 0.8, 1.05),
            )
            helpers.assign_material(tent, self.mat.get("MAT_PaperMenu"))
            tent.rotation_euler = (math.radians(15), 0, 0)
            self._link(tent, "Menus")

    def _build_shelving(self, bar_y: float) -> None:
        # Open shelving on back wall for cups / syrups
        for i, z in enumerate((1.5, 1.9, 2.3)):
            shelf = helpers.create_cube(
                f"Bar_Shelf_{i}",
                size=(5.0, 0.3, 0.03),
                location=(0.5, config.SHOP_DEPTH * 0.5 - 0.4, z),
            )
            helpers.assign_material(shelf, self.mat.get("MAT_WoodOak"))
            self._link(shelf, "Props")

            # Syrup bottles
            for j in range(8):
                bx = -1.5 + j * 0.35 + self.rng.uniform(-0.03, 0.03)
                bottle = helpers.create_cylinder(
                    f"Syrup_{i}_{j}",
                    radius=0.035,
                    depth=0.18,
                    vertices=12,
                    location=(bx, config.SHOP_DEPTH * 0.5 - 0.4, z + 0.1),
                )
                helpers.assign_material(bottle, self.mat.get("MAT_GlassClear"))
                self._link(bottle, "Props")

    def _build_cups_and_mugs(self, bar_y: float) -> None:
        # Stacked ceramic cups on warmer and shelves
        idx = 0
        for stack_x in (0.35, 0.55, 0.75):
            for level in range(3):
                cup = self._make_mug(f"Cup_Stack_{idx}", (stack_x, bar_y - 0.05, 1.52 + level * 0.07))
                self._link(cup, "Props")
                idx += 1

        # Scattered customer mugs on ledge
        for i, x in enumerate((-2.0, -0.5, 1.0, 2.5)):
            mug = self._make_mug(
                f"Mug_Service_{i}",
                (x + self.rng.uniform(-0.1, 0.1), bar_y - 0.55, 1.05),
            )
            self._link(mug, "Props")
            if self.rng.random() > 0.3:
                liquid = helpers.create_cylinder(
                    f"Coffee_InMug_{i}",
                    radius=0.035,
                    depth=0.03,
                    vertices=12,
                    location=(x, bar_y - 0.55, 1.08),
                )
                helpers.assign_material(liquid, self.mat.get("MAT_FoodCoffee"))
                self._link(liquid, "Props")

    def _make_mug(self, name: str, location: Tuple[float, float, float]) -> bpy.types.Object:
        body = helpers.create_cylinder(f"{name}_Body", radius=0.04, depth=0.09, vertices=24, location=location)
        helpers.assign_material(body, self.mat.get("MAT_CeramicMug"))
        helpers.shade_smooth(body)
        handle = helpers.create_torus(
            f"{name}_Handle",
            major_radius=0.03,
            minor_radius=0.008,
            location=(location[0] + 0.05, location[1], location[2]),
        )
        helpers.assign_material(handle, self.mat.get("MAT_CeramicMug"))
        handle.rotation_euler = (math.radians(90), 0, 0)
        joined = helpers.join_objects([body, handle], name)
        return joined or body

    def _build_napkin_holders(self, bar_y: float) -> None:
        for i, x in enumerate((-1.5, 0.0, 1.8)):
            holder = helpers.create_cube(
                f"NapkinHolder_{i}",
                size=(0.12, 0.08, 0.1),
                location=(x, bar_y - 0.5, 1.05),
            )
            helpers.assign_material(holder, self.mat.get("MAT_MetalBlack"))
            napkins = helpers.create_cube(
                f"Napkins_{i}",
                size=(0.1, 0.06, 0.08),
                location=(x, bar_y - 0.5, 1.05),
            )
            helpers.assign_material(napkins, self.mat.get("MAT_PaperMenu"))
            self._link(holder, "Props")
            self._link(napkins, "Props")

    def _build_bean_bags(self, x: float, y: float) -> None:
        for i in range(4):
            bag = helpers.create_cube(
                f"BeanBag_{i}",
                size=(0.35, 0.25, 0.45),
                location=(
                    x + (i % 2) * 0.4 + self.rng.uniform(-0.05, 0.05),
                    y + (i // 2) * 0.35,
                    0.22,
                ),
            )
            bag.rotation_euler = (0, 0, self.rng.uniform(-0.3, 0.3))
            helpers.assign_material(bag, self.mat.get("MAT_FabricLinen"))
            helpers.bevel_object(bag, 0.03, 3)
            helpers.subdivide_object(bag, 1, 1)
            self._link(bag, "Props")

            label = helpers.create_cube(
                f"BeanBag_Label_{i}",
                size=(0.2, 0.01, 0.15),
                location=(bag.location.x, bag.location.y - 0.13, bag.location.z + 0.05),
            )
            helpers.assign_material(label, self.mat.get("MAT_PaperMenu"))
            self._link(label, "Props")
