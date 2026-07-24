# SPDX-License-Identifier: MIT
"""
AI Texture Management System
Supports Stable Diffusion, Flux, Midjourney, and local texture libraries.
Automatically discovers and connects PBR texture maps to materials.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import bpy

from . import config

logger = logging.getLogger(__name__)

# Map suffix tokens -> Principled BSDF / material input roles
MAP_SUFFIXES = {
    "basecolor": "Base Color",
    "base_color": "Base Color",
    "albedo": "Base Color",
    "diffuse": "Base Color",
    "color": "Base Color",
    "roughness": "Roughness",
    "rough": "Roughness",
    "metallic": "Metallic",
    "metalness": "Metallic",
    "metal": "Metallic",
    "normal": "Normal",
    "nor": "Normal",
    "nrm": "Normal",
    "displacement": "Displacement",
    "disp": "Displacement",
    "height": "Displacement",
    "ao": "AO",
    "ambientocclusion": "AO",
    "emission": "Emission Color",
    "emissive": "Emission Color",
    "alpha": "Alpha",
    "opacity": "Alpha",
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".exr", ".bmp", ".webp"}


class TextureManager:
    """
    Discovers AI-generated and local PBR textures and wires them into materials.

    Expected folder layout:
        Textures/
        ├── wood/
        │   ├── stable_diffusion/
        │   ├── flux/
        │   ├── midjourney/
        │   └── local/
        ├── leather/
        ...
    Naming: {category}_{variant}_basecolor.png (etc.)
    """

    def __init__(self, texture_root: Optional[Path] = None):
        self.texture_root = Path(texture_root or config.TEXTURE_ROOT)
        self.discovered: Dict[str, Dict[str, Path]] = {}
        self.loaded_images: Dict[str, bpy.types.Image] = {}
        config.ensure_directories()

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def create_placeholder_structure(self) -> None:
        """Ensure all AI texture category/source folders exist."""
        config.ensure_directories()
        for category in config.TEXTURE_CATEGORIES:
            for source in config.TEXTURE_SOURCES:
                path = self.texture_root / category / source
                path.mkdir(parents=True, exist_ok=True)
                placeholder = path / ".gitkeep"
                if not placeholder.exists():
                    placeholder.write_text("", encoding="utf-8")
                # Example path markers for artists / pipelines
                example = path / f"PLACEHOLDER_{category}_variant_basecolor.txt"
                if not example.exists():
                    example.write_text(
                        f"Drop {category} PBR maps here from {source}.\n"
                        f"Required: *_basecolor, *_roughness, *_metallic, *_normal, *_displacement\n",
                        encoding="utf-8",
                    )
        logger.info("Texture placeholder structure ready at %s", self.texture_root)

    def discover_textures(self) -> Dict[str, Dict[str, Path]]:
        """
        Scan texture root and group maps by material key.
        Returns {material_key: {role: path}}.
        """
        self.discovered.clear()
        if not self.texture_root.exists():
            self.create_placeholder_structure()
            return self.discovered

        for root, _dirs, files in os.walk(self.texture_root):
            for filename in files:
                ext = Path(filename).suffix.lower()
                if ext not in IMAGE_EXTENSIONS:
                    continue
                full = Path(root) / filename
                key, role = self._parse_texture_name(full)
                if key is None or role is None:
                    continue
                self.discovered.setdefault(key, {})[role] = full

        logger.info("Discovered %d texture sets", len(self.discovered))
        return self.discovered

    def _parse_texture_name(self, path: Path) -> Tuple[Optional[str], Optional[str]]:
        """Extract material key and map role from a filename."""
        stem = path.stem.lower()
        # Strip common resolution tokens
        stem = re.sub(r"[_-]?(2k|4k|8k|1k|512|1024|2048|4096|8192)$", "", stem)

        role = None
        for suffix, mapped_role in MAP_SUFFIXES.items():
            pattern = rf"[_-]{suffix}$"
            if re.search(pattern, stem):
                role = mapped_role
                stem = re.sub(pattern, "", stem)
                break

        if role is None:
            return None, None

        # Prefer category from parent folders
        parts = path.relative_to(self.texture_root).parts
        category = parts[0] if parts else "misc"
        key = f"{category}/{stem}" if not stem.startswith(category) else stem
        return key, role

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_image(self, path: Path, colorspace: str = "sRGB") -> Optional[bpy.types.Image]:
        """Load an image into bpy.data.images (cached)."""
        key = str(path.resolve())
        if key in self.loaded_images and self.loaded_images[key]:
            return self.loaded_images[key]
        if not path.exists():
            logger.warning("Texture missing: %s", path)
            return None
        try:
            img = bpy.data.images.load(str(path), check_existing=True)
            # Non-color for data maps
            if colorspace == "Non-Color":
                try:
                    img.colorspace_settings.name = "Non-Color"
                except Exception:
                    pass
            else:
                try:
                    img.colorspace_settings.name = "sRGB"
                except Exception:
                    pass
            self.loaded_images[key] = img
            return img
        except Exception as exc:
            logger.error("Failed to load %s: %s", path, exc)
            return None

    def load_stable_diffusion_textures(self, category: str) -> Dict[str, Dict[str, Path]]:
        return self._load_source(category, "stable_diffusion")

    def load_flux_textures(self, category: str) -> Dict[str, Dict[str, Path]]:
        return self._load_source(category, "flux")

    def load_midjourney_textures(self, category: str) -> Dict[str, Dict[str, Path]]:
        return self._load_source(category, "midjourney")

    def load_local_textures(self, category: str) -> Dict[str, Dict[str, Path]]:
        return self._load_source(category, "local")

    def _load_source(self, category: str, source: str) -> Dict[str, Dict[str, Path]]:
        folder = self.texture_root / category / source
        result: Dict[str, Dict[str, Path]] = {}
        if not folder.exists():
            folder.mkdir(parents=True, exist_ok=True)
            return result
        for path in folder.rglob("*"):
            if path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            key, role = self._parse_texture_name(path)
            if key and role:
                result.setdefault(key, {})[role] = path
                colorspace = "sRGB" if role == "Base Color" else "Non-Color"
                self.load_image(path, colorspace=colorspace)
        return result

    # ------------------------------------------------------------------
    # Material wiring
    # ------------------------------------------------------------------

    def connect_textures_to_material(
        self,
        material: bpy.types.Material,
        texture_set: Dict[str, Path],
        principled: Optional[bpy.types.ShaderNode] = None,
    ) -> bool:
        """
        Connect discovered PBR maps to a Principled BSDF material.
        Returns True if at least one map was connected.
        """
        if not material.use_nodes:
            material.use_nodes = True
        nodes = material.node_tree.nodes
        links = material.node_tree.links

        if principled is None:
            principled = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)
            if principled is None:
                principled = nodes.new("ShaderNodeBsdfPrincipled")
                output = next((n for n in nodes if n.type == "OUTPUT_MATERIAL"), None)
                if output:
                    links.new(principled.outputs["BSDF"], output.inputs["Surface"])

        connected = False
        x_offset = -600
        y_offset = 300

        for role, path in texture_set.items():
            colorspace = "sRGB" if role == "Base Color" else "Non-Color"
            img = self.load_image(path, colorspace=colorspace)
            if img is None:
                continue

            tex_node = nodes.new("ShaderNodeTexImage")
            tex_node.image = img
            tex_node.label = role
            tex_node.location = (x_offset, y_offset)
            y_offset -= 280

            if role == "Base Color" and "Base Color" in principled.inputs:
                links.new(tex_node.outputs["Color"], principled.inputs["Base Color"])
                connected = True
            elif role == "Roughness" and "Roughness" in principled.inputs:
                links.new(tex_node.outputs["Color"], principled.inputs["Roughness"])
                connected = True
            elif role == "Metallic" and "Metallic" in principled.inputs:
                links.new(tex_node.outputs["Color"], principled.inputs["Metallic"])
                connected = True
            elif role == "Normal":
                normal_map = nodes.new("ShaderNodeNormalMap")
                normal_map.location = (x_offset + 280, tex_node.location.y)
                links.new(tex_node.outputs["Color"], normal_map.inputs["Color"])
                if "Normal" in principled.inputs:
                    links.new(normal_map.outputs["Normal"], principled.inputs["Normal"])
                connected = True
            elif role == "Displacement":
                output = next((n for n in nodes if n.type == "OUTPUT_MATERIAL"), None)
                disp = nodes.new("ShaderNodeDisplacement")
                disp.location = (x_offset + 280, tex_node.location.y)
                links.new(tex_node.outputs["Color"], disp.inputs["Height"])
                if output and "Displacement" in output.inputs:
                    links.new(disp.outputs["Displacement"], output.inputs["Displacement"])
                connected = True
            elif role == "Emission Color" and "Emission Color" in principled.inputs:
                links.new(tex_node.outputs["Color"], principled.inputs["Emission Color"])
                connected = True
            elif role == "Alpha" and "Alpha" in principled.inputs:
                links.new(tex_node.outputs["Color"], principled.inputs["Alpha"])
                material.blend_method = "HASHED"
                connected = True
            elif role == "AO":
                # Multiply AO with base color if both present
                mix = nodes.new("ShaderNodeMixRGB")
                mix.blend_type = "MULTIPLY"
                mix.inputs["Fac"].default_value = 0.7
                mix.location = (x_offset + 280, y_offset + 400)
                # Leave unconnected unless Base Color tex exists; store for manual use
                tex_node.label = "AO (multiply with Base Color)"

        return connected

    def auto_connect_all(self, materials: Dict[str, bpy.types.Material]) -> int:
        """
        Match material names to discovered texture sets and connect them.
        Matching is fuzzy: MAT_WoodOak -> wood/wood_oak etc.
        """
        if not self.discovered:
            self.discover_textures()
        count = 0
        for mat_name, mat in materials.items():
            key = self._match_material_key(mat_name)
            if key and key in self.discovered:
                if self.connect_textures_to_material(mat, self.discovered[key]):
                    count += 1
                    logger.info("Connected textures %s -> %s", key, mat_name)
        return count

    def _match_material_key(self, mat_name: str) -> Optional[str]:
        clean = mat_name.lower().replace("mat_", "")
        # Direct category match
        for key in self.discovered:
            token = key.split("/")[-1].replace("_", "")
            if clean.replace("_", "") in token or token in clean.replace("_", ""):
                return key
        # Category folder match
        for category in config.TEXTURE_CATEGORIES:
            if category in clean:
                for key in self.discovered:
                    if key.startswith(category):
                        return key
        return None

    def get_texture_resolution_variants(self, base_path: Path) -> Dict[int, Path]:
        """Find 2K/4K/8K variants of a texture if present."""
        variants: Dict[int, Path] = {}
        stem = re.sub(r"[_-]?(2k|4k|8k)$", "", base_path.stem, flags=re.I)
        parent = base_path.parent
        for res, label in ((2048, "2k"), (4096, "4k"), (8192, "8k")):
            for candidate in parent.glob(f"{stem}*{label}*{base_path.suffix}"):
                variants[res] = candidate
            for candidate in parent.glob(f"{stem}*{res}*{base_path.suffix}"):
                variants[res] = candidate
        if not variants and base_path.exists():
            variants[config.DEFAULT_TEXTURE_RES] = base_path
        return variants
