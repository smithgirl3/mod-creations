# SPDX-License-Identifier: MIT
"""
Game-ready optimization: high/medium/low poly variants, LOD0–LOD3, texture res.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import bpy

from . import config, helpers

logger = logging.getLogger(__name__)


class OptimizationSystem:
    """Automatic LOD and mesh density optimization for Unity export."""

    def __init__(self, collections: dict):
        self.cols = collections
        self.lod_objects: Dict[str, List[bpy.types.Object]] = {}

    def build(self) -> Dict[str, List[bpy.types.Object]]:
        self.lod_objects = {level: [] for level in config.LOD_LEVELS}
        self._organize_poly_tiers()
        self._generate_lods()
        self._configure_texture_slots()
        return self.lod_objects

    def _organize_poly_tiers(self) -> None:
        """
        Tag / duplicate assets into High / Medium / Low poly collections.
        High = originals; Medium/Low = decimated copies for game budgets.
        """
        high_col = self.cols.get("HighPoly") or helpers.get_or_create_collection("HighPoly")
        med_col = self.cols.get("MediumPoly") or helpers.get_or_create_collection("MediumPoly")
        low_col = self.cols.get("LowPoly") or helpers.get_or_create_collection("LowPoly")

        candidates = [
            o for o in bpy.data.objects
            if o.type == "MESH" and (
                o.get("coffee_shop_lod")
                or o.name.startswith(("Table_", "Chair_", "Booth_", "Couch_", "EXT_", "Bar_", "Espresso_"))
            )
        ]

        for obj in candidates:
            # Link original reference into HighPoly (keep original collections too)
            if obj.name not in high_col.objects:
                try:
                    high_col.objects.link(obj)
                except RuntimeError:
                    pass

            med = self._clone_decimated(obj, f"{obj.name}_MED", 0.5)
            if med:
                helpers.link_object_to_collection(med, med_col)
            low = self._clone_decimated(obj, f"{obj.name}_LOW", 0.2)
            if low:
                helpers.link_object_to_collection(low, low_col)

        logger.info("Poly tiers organized for %d candidates", len(candidates))

    def _clone_decimated(self, obj: bpy.types.Object, name: str, ratio: float) -> Optional[bpy.types.Object]:
        try:
            dup = helpers.duplicate_object(obj, name, location=tuple(obj.location))
            # Offset slightly underground to avoid viewport overlap (export-only copies)
            dup.location.z -= 50.0
            dup.hide_render = True
            helpers.decimate_object(dup, ratio)
            # Apply modifier for clean export mesh
            helpers.set_active(dup)
            for mod in list(dup.modifiers):
                if mod.type == "DECIMATE":
                    try:
                        bpy.ops.object.modifier_apply(modifier=mod.name)
                    except RuntimeError:
                        pass
            return dup
        except Exception as exc:
            logger.debug("Decimate clone failed %s: %s", obj.name, exc)
            return None

    def _generate_lods(self) -> None:
        """Create LOD0–LOD3 object sets for exterior / large props."""
        lod_root = self.cols.get("LODs") or helpers.get_or_create_collection("LODs")
        targets = [o for o in bpy.data.objects if o.get("coffee_shop_lod") and o.type == "MESH"]

        for obj in targets:
            # LOD0 = original
            obj["lod_level"] = "LOD0"
            self.lod_objects["LOD0"].append(obj)

            for level, ratio in config.LOD_DECIMATE_RATIOS.items():
                if level == "LOD0":
                    continue
                lod_name = f"{obj.name}_{level}"
                lod = self._clone_decimated(obj, lod_name, ratio)
                if lod is None:
                    continue
                lod["lod_level"] = level
                lod["lod_parent"] = obj.name
                # Stack underground by LOD index
                idx = config.LOD_LEVELS.index(level)
                lod.location.z = obj.location.z - 60.0 - idx * 5.0
                helpers.link_object_to_collection(lod, lod_root)
                self.lod_objects[level].append(lod)

        # Empty parent LOD groups for Unity naming convention
        for obj in targets:
            empty = helpers.add_empty(f"{obj.name}_LODGroup", location=tuple(obj.location))
            empty["unity_lod_group"] = True
            helpers.link_object_to_collection(empty, lod_root)
            try:
                helpers.parent_keep_transform(obj, empty)
            except Exception:
                pass
            for level in config.LOD_LEVELS[1:]:
                lod = bpy.data.objects.get(f"{obj.name}_{level}")
                if lod:
                    try:
                        helpers.parent_keep_transform(lod, empty)
                    except Exception:
                        pass

        logger.info(
            "LOD generation complete: %s",
            {k: len(v) for k, v in self.lod_objects.items()},
        )

    def _configure_texture_slots(self) -> None:
        """
        Store preferred texture resolutions (2K / 4K / 8K) as scene custom props
        and material metadata for the export pipeline.
        """
        scene = bpy.context.scene
        scene["texture_resolutions"] = list(config.TEXTURE_RESOLUTIONS)
        scene["default_texture_resolution"] = config.DEFAULT_TEXTURE_RES
        for mat in bpy.data.materials:
            mat["supported_resolutions"] = list(config.TEXTURE_RESOLUTIONS)
            # Prefer 4K for hero props, 2K for distant exterior
            if mat.name.startswith(("MAT_Wood", "MAT_Leather", "MAT_Glass")):
                mat["preferred_resolution"] = 4096
            elif mat.name.startswith(("MAT_Brick", "MAT_Asphalt", "MAT_Concrete")):
                mat["preferred_resolution"] = 2048
            else:
                mat["preferred_resolution"] = config.DEFAULT_TEXTURE_RES
