# SPDX-License-Identifier: MIT
"""
Physically Based Material Manager (Principled BSDF workflows).
Creates production-ready materials for wood, metal, leather, ceramic,
concrete, glass, fabric, paper, food, weather, and more.
"""

from __future__ import annotations

import logging
import math
from typing import Dict, Optional, Tuple

import bpy

from . import config
from .texture_manager import TextureManager

logger = logging.getLogger(__name__)

Color = Tuple[float, float, float, float]


class MaterialManager:
    """Central PBR material factory with optional AI texture auto-wiring."""

    def __init__(self, texture_manager: Optional[TextureManager] = None):
        self.texture_manager = texture_manager or TextureManager()
        self.materials: Dict[str, bpy.types.Material] = {}

    # ------------------------------------------------------------------
    # Core node helpers
    # ------------------------------------------------------------------

    def _new_material(self, name: str) -> Tuple[bpy.types.Material, bpy.types.ShaderNode, bpy.types.NodeTree]:
        mat = bpy.data.materials.get(name)
        if mat is None:
            mat = bpy.data.materials.new(name=name)
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        output = nt.nodes.new("ShaderNodeOutputMaterial")
        output.location = (300, 0)
        principled = nt.nodes.new("ShaderNodeBsdfPrincipled")
        principled.location = (0, 0)
        nt.links.new(principled.outputs["BSDF"], output.inputs["Surface"])
        self.materials[name] = mat
        return mat, principled, nt

    def _set_input(self, node: bpy.types.ShaderNode, name: str, value) -> None:
        if name in node.inputs:
            try:
                node.inputs[name].default_value = value
            except (TypeError, ValueError, AttributeError):
                # Some Blender versions use Color vs float differently
                try:
                    if hasattr(value, "__len__") and len(value) >= 3:
                        node.inputs[name].default_value = value
                    else:
                        node.inputs[name].default_value = float(value)
                except Exception as exc:
                    logger.debug("Could not set %s: %s", name, exc)

    def _add_noise_bump(
        self,
        nt: bpy.types.NodeTree,
        principled: bpy.types.ShaderNode,
        scale: float = 8.0,
        strength: float = 0.15,
        detail: float = 8.0,
    ) -> None:
        """Procedural micro-detail when external normal maps are absent."""
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = scale
        noise.inputs["Detail"].default_value = detail
        noise.location = (-600, -300)

        bump = nt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = strength
        bump.location = (-300, -300)

        nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
        if "Normal" in principled.inputs:
            nt.links.new(bump.outputs["Normal"], principled.inputs["Normal"])

    # ------------------------------------------------------------------
    # Material builders
    # ------------------------------------------------------------------

    def create_wood(
        self,
        name: str = "MAT_WoodOak",
        color: Color = (0.45, 0.28, 0.14, 1.0),
        roughness: float = 0.45,
        scale: float = 12.0,
    ) -> bpy.types.Material:
        mat, principled, nt = self._new_material(name)
        self._set_input(principled, "Base Color", color)
        self._set_input(principled, "Roughness", roughness)
        self._set_input(principled, "Metallic", 0.0)
        self._set_input(principled, "Specular IOR Level", 0.45)

        # Procedural wood grain via stretched noise
        mapping = nt.nodes.new("ShaderNodeMapping")
        mapping.inputs["Scale"].default_value = (1.0, 8.0, 1.0)
        mapping.location = (-900, 200)
        tex_coord = nt.nodes.new("ShaderNodeTexCoord")
        tex_coord.location = (-1100, 200)
        nt.links.new(tex_coord.outputs["Object"], mapping.inputs["Vector"])

        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = scale
        noise.inputs["Detail"].default_value = 12.0
        noise.inputs["Distortion"].default_value = 0.4
        noise.location = (-700, 200)
        nt.links.new(mapping.outputs["Vector"], noise.inputs["Vector"])

        color_ramp = nt.nodes.new("ShaderNodeValToRGB")
        color_ramp.location = (-500, 200)
        color_ramp.color_ramp.elements[0].color = (color[0] * 0.6, color[1] * 0.6, color[2] * 0.6, 1)
        color_ramp.color_ramp.elements[1].color = color
        nt.links.new(noise.outputs["Fac"], color_ramp.inputs["Fac"])
        nt.links.new(color_ramp.outputs["Color"], principled.inputs["Base Color"])

        self._add_noise_bump(nt, principled, scale=scale * 2, strength=0.08)
        return mat

    def create_metal(
        self,
        name: str = "MAT_MetalBrushed",
        color: Color = (0.7, 0.7, 0.72, 1.0),
        roughness: float = 0.25,
        metallic: float = 1.0,
    ) -> bpy.types.Material:
        mat, principled, nt = self._new_material(name)
        self._set_input(principled, "Base Color", color)
        self._set_input(principled, "Roughness", roughness)
        self._set_input(principled, "Metallic", metallic)
        self._add_noise_bump(nt, principled, scale=40.0, strength=0.05, detail=4.0)
        return mat

    def create_leather(
        self,
        name: str = "MAT_LeatherBrown",
        color: Color = (0.22, 0.12, 0.07, 1.0),
        roughness: float = 0.55,
    ) -> bpy.types.Material:
        mat, principled, nt = self._new_material(name)
        self._set_input(principled, "Base Color", color)
        self._set_input(principled, "Roughness", roughness)
        self._set_input(principled, "Metallic", 0.0)
        self._set_input(principled, "Sheen Weight", 0.35)
        self._set_input(principled, "Sheen Roughness", 0.4)
        self._add_noise_bump(nt, principled, scale=55.0, strength=0.2, detail=10.0)
        return mat

    def create_ceramic(
        self,
        name: str = "MAT_CeramicWhite",
        color: Color = (0.92, 0.9, 0.86, 1.0),
        roughness: float = 0.18,
    ) -> bpy.types.Material:
        mat, principled, _nt = self._new_material(name)
        self._set_input(principled, "Base Color", color)
        self._set_input(principled, "Roughness", roughness)
        self._set_input(principled, "Metallic", 0.0)
        self._set_input(principled, "Coat Weight", 0.4)
        self._set_input(principled, "Coat Roughness", 0.05)
        return mat

    def create_concrete(
        self,
        name: str = "MAT_Concrete",
        color: Color = (0.35, 0.34, 0.32, 1.0),
        roughness: float = 0.85,
    ) -> bpy.types.Material:
        mat, principled, nt = self._new_material(name)
        self._set_input(principled, "Base Color", color)
        self._set_input(principled, "Roughness", roughness)
        self._add_noise_bump(nt, principled, scale=6.0, strength=0.25, detail=12.0)
        return mat

    def create_glass(
        self,
        name: str = "MAT_GlassClear",
        color: Color = (0.95, 0.97, 1.0, 1.0),
        roughness: float = 0.02,
        ior: float = 1.52,
        with_rain: bool = False,
    ) -> bpy.types.Material:
        mat, principled, nt = self._new_material(name)
        self._set_input(principled, "Base Color", color)
        self._set_input(principled, "Roughness", roughness)
        self._set_input(principled, "Metallic", 0.0)
        self._set_input(principled, "Transmission Weight", 1.0)
        self._set_input(principled, "IOR", ior)
        self._set_input(principled, "Alpha", 0.15)
        mat.blend_method = "HASHED"
        try:
            mat.shadow_method = "HASHED"
        except Exception:
            pass
        mat.use_screen_refraction = True
        try:
            mat.refraction_depth = 0.01
        except Exception:
            pass

        if with_rain:
            # Rain droplets + streaks via noise → bump + roughness roughness
            noise = nt.nodes.new("ShaderNodeTexNoise")
            noise.inputs["Scale"].default_value = 120.0
            noise.inputs["Detail"].default_value = 8.0
            noise.location = (-700, -200)

            musgrave = nt.nodes.new("ShaderNodeTexNoise")
            musgrave.label = "Streaks"
            musgrave.inputs["Scale"].default_value = 25.0
            musgrave.inputs["Distortion"].default_value = 2.5
            musgrave.location = (-700, -500)

            mapping = nt.nodes.new("ShaderNodeMapping")
            mapping.inputs["Scale"].default_value = (1.0, 6.0, 1.0)
            mapping.location = (-950, -500)
            tex_coord = nt.nodes.new("ShaderNodeTexCoord")
            tex_coord.location = (-1150, -350)
            nt.links.new(tex_coord.outputs["UV"], mapping.inputs["Vector"])
            nt.links.new(mapping.outputs["Vector"], musgrave.inputs["Vector"])

            bump = nt.nodes.new("ShaderNodeBump")
            bump.inputs["Strength"].default_value = 0.35
            bump.location = (-350, -300)
            nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
            if "Normal" in principled.inputs:
                nt.links.new(bump.outputs["Normal"], principled.inputs["Normal"])

            # Condensation: raise roughness in streaks
            mix = nt.nodes.new("ShaderNodeMix")
            mix.data_type = "FLOAT"
            mix.location = (-350, 100)
            try:
                mix.inputs[2].default_value = 0.02  # A
                mix.inputs[3].default_value = 0.45  # B wet
            except Exception:
                pass
            nt.links.new(musgrave.outputs["Fac"], mix.inputs["Factor"])
            if "Roughness" in principled.inputs:
                try:
                    nt.links.new(mix.outputs[0], principled.inputs["Roughness"])
                except Exception:
                    self._set_input(principled, "Roughness", 0.12)
        return mat

    def create_fabric(
        self,
        name: str = "MAT_FabricLinen",
        color: Color = (0.55, 0.48, 0.40, 1.0),
        roughness: float = 0.75,
    ) -> bpy.types.Material:
        mat, principled, nt = self._new_material(name)
        self._set_input(principled, "Base Color", color)
        self._set_input(principled, "Roughness", roughness)
        self._set_input(principled, "Sheen Weight", 0.5)
        self._set_input(principled, "Sheen Roughness", 0.35)
        self._add_noise_bump(nt, principled, scale=80.0, strength=0.12, detail=6.0)
        return mat

    def create_paper(
        self,
        name: str = "MAT_PaperMenu",
        color: Color = (0.88, 0.84, 0.76, 1.0),
        roughness: float = 0.7,
    ) -> bpy.types.Material:
        mat, principled, nt = self._new_material(name)
        self._set_input(principled, "Base Color", color)
        self._set_input(principled, "Roughness", roughness)
        self._add_noise_bump(nt, principled, scale=30.0, strength=0.04)
        return mat

    def create_food(
        self,
        name: str = "MAT_FoodPastry",
        color: Color = (0.72, 0.48, 0.22, 1.0),
        roughness: float = 0.55,
        subsurface: float = 0.25,
    ) -> bpy.types.Material:
        mat, principled, _nt = self._new_material(name)
        self._set_input(principled, "Base Color", color)
        self._set_input(principled, "Roughness", roughness)
        # Subsurface / SSS for pastries and coffee liquid
        for key, val in (
            ("Subsurface Weight", subsurface),
            ("Subsurface", subsurface),
        ):
            if key in principled.inputs:
                try:
                    principled.inputs[key].default_value = val
                except Exception:
                    pass
        if "Subsurface Radius" in principled.inputs:
            principled.inputs["Subsurface Radius"].default_value = (0.8, 0.4, 0.2)
        if "Subsurface Color" in principled.inputs:
            principled.inputs["Subsurface Color"].default_value = color
        return mat

    def create_plaster(self, name: str = "MAT_PlasterWarm", color: Color = (0.78, 0.72, 0.62, 1.0)) -> bpy.types.Material:
        mat, principled, nt = self._new_material(name)
        self._set_input(principled, "Base Color", color)
        self._set_input(principled, "Roughness", 0.82)
        self._add_noise_bump(nt, principled, scale=15.0, strength=0.06)
        return mat

    def create_paint(self, name: str = "MAT_PaintWall", color: Color = (0.82, 0.76, 0.68, 1.0)) -> bpy.types.Material:
        mat, principled, _nt = self._new_material(name)
        self._set_input(principled, "Base Color", color)
        self._set_input(principled, "Roughness", 0.65)
        return mat

    def create_asphalt_wet(self, name: str = "MAT_AsphaltWet") -> bpy.types.Material:
        mat, principled, nt = self._new_material(name)
        self._set_input(principled, "Base Color", (0.04, 0.04, 0.045, 1.0))
        self._set_input(principled, "Roughness", 0.25)
        self._set_input(principled, "Metallic", 0.05)
        self._set_input(principled, "Coat Weight", 0.6)
        self._set_input(principled, "Coat Roughness", 0.08)
        self._add_noise_bump(nt, principled, scale=4.0, strength=0.3)
        return mat

    def create_brick(self, name: str = "MAT_BrickExterior") -> bpy.types.Material:
        mat, principled, nt = self._new_material(name)
        self._set_input(principled, "Base Color", (0.35, 0.18, 0.12, 1.0))
        self._set_input(principled, "Roughness", 0.8)
        brick = nt.nodes.new("ShaderNodeTexBrick")
        brick.inputs["Scale"].default_value = 4.0
        brick.inputs["Mortar Size"].default_value = 0.02
        brick.location = (-400, 200)
        nt.links.new(brick.outputs["Color"], principled.inputs["Base Color"])
        return mat

    def create_plant(self, name: str = "MAT_PlantLeaf") -> bpy.types.Material:
        mat, principled, _nt = self._new_material(name)
        self._set_input(principled, "Base Color", (0.12, 0.28, 0.08, 1.0))
        self._set_input(principled, "Roughness", 0.55)
        if "Subsurface Weight" in principled.inputs:
            principled.inputs["Subsurface Weight"].default_value = 0.15
        return mat

    def create_candle_wax(self, name: str = "MAT_CandleWax") -> bpy.types.Material:
        mat, principled, _nt = self._new_material(name)
        self._set_input(principled, "Base Color", (0.92, 0.88, 0.75, 1.0))
        self._set_input(principled, "Roughness", 0.35)
        if "Subsurface Weight" in principled.inputs:
            principled.inputs["Subsurface Weight"].default_value = 0.4
        self._set_input(principled, "Emission Color", (1.0, 0.7, 0.3, 1.0))
        self._set_input(principled, "Emission Strength", 0.0)
        return mat

    def create_water_puddle(self, name: str = "MAT_WaterPuddle") -> bpy.types.Material:
        mat, principled, _nt = self._new_material(name)
        self._set_input(principled, "Base Color", (0.15, 0.18, 0.22, 1.0))
        self._set_input(principled, "Roughness", 0.05)
        self._set_input(principled, "Metallic", 0.0)
        self._set_input(principled, "Transmission Weight", 0.85)
        self._set_input(principled, "IOR", 1.333)
        self._set_input(principled, "Alpha", 0.7)
        mat.blend_method = "BLEND"
        mat.use_screen_refraction = True
        return mat

    def create_rubber(self, name: str = "MAT_RubberFloorMat") -> bpy.types.Material:
        mat, principled, nt = self._new_material(name)
        self._set_input(principled, "Base Color", (0.08, 0.08, 0.08, 1.0))
        self._set_input(principled, "Roughness", 0.7)
        self._add_noise_bump(nt, principled, scale=20.0, strength=0.15)
        return mat

    def create_coffee_liquid(self, name: str = "MAT_FoodCoffee") -> bpy.types.Material:
        mat, principled, _nt = self._new_material(name)
        self._set_input(principled, "Base Color", (0.12, 0.06, 0.03, 1.0))
        self._set_input(principled, "Roughness", 0.15)
        self._set_input(principled, "Transmission Weight", 0.3)
        self._set_input(principled, "IOR", 1.35)
        if "Subsurface Weight" in principled.inputs:
            principled.inputs["Subsurface Weight"].default_value = 0.2
        return mat

    # ------------------------------------------------------------------
    # Batch generation
    # ------------------------------------------------------------------

    def create_all_materials(self) -> Dict[str, bpy.types.Material]:
        """Generate the full PBR material library for the coffee shop."""
        self.create_wood("MAT_WoodOak", (0.48, 0.30, 0.16, 1.0), 0.42)
        self.create_wood("MAT_WoodWalnut", (0.22, 0.12, 0.07, 1.0), 0.38)
        self.create_wood("MAT_WoodFloor", (0.40, 0.26, 0.14, 1.0), 0.35, scale=18.0)
        self.create_metal("MAT_MetalBrushed", (0.68, 0.68, 0.7, 1.0), 0.3)
        self.create_metal("MAT_MetalChrome", (0.9, 0.9, 0.92, 1.0), 0.08)
        self.create_metal("MAT_MetalBlack", (0.05, 0.05, 0.05, 1.0), 0.35)
        self.create_leather("MAT_LeatherBrown", (0.24, 0.13, 0.07, 1.0))
        self.create_leather("MAT_LeatherBlack", (0.04, 0.04, 0.04, 1.0), 0.5)
        self.create_ceramic("MAT_CeramicWhite")
        self.create_ceramic("MAT_CeramicMug", (0.85, 0.82, 0.78, 1.0), 0.22)
        self.create_concrete()
        self.create_glass("MAT_GlassClear", with_rain=False)
        self.create_glass("MAT_GlassRain", with_rain=True)
        self.create_fabric("MAT_FabricLinen", (0.58, 0.52, 0.44, 1.0))
        self.create_fabric("MAT_FabricUpholstery", (0.32, 0.22, 0.16, 1.0), 0.8)
        self.create_fabric("MAT_FabricCurtain", (0.45, 0.38, 0.32, 1.0), 0.7)
        self.create_paper("MAT_PaperMenu")
        self.create_paper("MAT_PaperBook", (0.75, 0.70, 0.60, 1.0))
        self.create_food("MAT_FoodPastry")
        self.create_coffee_liquid("MAT_FoodCoffee")
        self.create_plaster()
        self.create_paint()
        self.create_rubber()
        self.create_asphalt_wet()
        self.create_brick()
        self.create_plant()
        self.create_candle_wax()
        self.create_water_puddle()

        # Attempt AI / library texture auto-connect
        try:
            self.texture_manager.create_placeholder_structure()
            self.texture_manager.discover_textures()
            connected = self.texture_manager.auto_connect_all(self.materials)
            logger.info("Auto-connected %d material texture sets", connected)
        except Exception as exc:
            logger.warning("Texture auto-connect skipped: %s", exc)

        return self.materials

    def get(self, name: str) -> Optional[bpy.types.Material]:
        return self.materials.get(name) or bpy.data.materials.get(name)
