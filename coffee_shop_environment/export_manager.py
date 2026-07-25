# SPDX-License-Identifier: MIT
"""
Unity export pipeline: FBX, GLB, textures — preserves transforms, pivots,
materials, and animation.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import List, Optional

import bpy

from . import config, helpers

logger = logging.getLogger(__name__)


class ExportManager:
    """Automated export for Unity game scenes."""

    def __init__(self, export_root: Optional[Path] = None):
        self.export_root = Path(export_root or config.EXPORT_ROOT)
        self.export_root.mkdir(parents=True, exist_ok=True)
        self.last_exports: List[str] = []

    def export_for_unity(self) -> List[str]:
        """
        Single entry point required by the project specification.
        Exports FBX, GLB, textures, and a Unity import sidecar JSON.
        """
        return export_for_unity(export_root=self.export_root)


def export_for_unity(export_root: Optional[Path] = None) -> List[str]:
    """
    Export the complete coffee shop environment for Unity.

    Outputs:
        export/CozyCoffeeShop.fbx
        export/CozyCoffeeShop.glb
        export/textures/   (packed / copied images)
        export/CozyCoffeeShop_unity.json  (sidecar metadata)
        export/CozyCoffeeShop.blend       (optional save)
    """
    root = Path(export_root or config.EXPORT_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    tex_out = root / "textures"
    tex_out.mkdir(parents=True, exist_ok=True)
    exported: List[str] = []

    # Ensure object mode and deselect
    helpers.ensure_object_mode()
    bpy.ops.object.select_all(action="DESELECT")

    # Select exportable objects (skip underground LOD work copies optionally —
    # include them under LODs for Unity LOD Group setup)
    exportable = [
        o for o in bpy.context.scene.objects
        if o.type in {"MESH", "EMPTY", "LIGHT", "CAMERA", "ARMATURE"}
    ]
    for obj in exportable:
        obj.select_set(True)

    fbx_path = root / "CozyCoffeeShop.fbx"
    glb_path = root / "CozyCoffeeShop.glb"

    # --- FBX ---
    try:
        bpy.ops.export_scene.fbx(
            filepath=str(fbx_path),
            use_selection=False,
            use_active_collection=False,
            global_scale=1.0,
            apply_unit_scale=True,
            apply_scale_options="FBX_SCALE_ALL",
            bake_space_transform=True,
            object_types={"MESH", "EMPTY", "CAMERA", "LIGHT", "ARMATURE", "OTHER"},
            use_mesh_modifiers=True,
            mesh_smooth_type="FACE",
            use_tspace=True,
            use_custom_props=True,
            bake_anim=True,
            bake_anim_use_all_bones=True,
            bake_anim_use_nla_strips=True,
            bake_anim_use_all_actions=True,
            bake_anim_force_startend_keying=True,
            bake_anim_step=1.0,
            bake_anim_simplify_factor=0.0,
            path_mode="COPY",
            embed_textures=True,
            axis_forward="-Z",
            axis_up="Y",
        )
        exported.append(str(fbx_path))
        logger.info("Exported FBX: %s", fbx_path)
    except Exception as exc:
        logger.error("FBX export failed: %s", exc)

    # --- GLB ---
    try:
        # Blender 3.x–5.x glTF exporter
        bpy.ops.export_scene.gltf(
            filepath=str(glb_path),
            export_format="GLB",
            use_selection=False,
            export_apply=True,
            export_texcoords=True,
            export_normals=True,
            export_materials="EXPORT",
            export_cameras=True,
            export_lights=True,
            export_animations=True,
            export_frame_range=True,
            export_force_sampling=True,
            export_extras=True,
        )
        exported.append(str(glb_path))
        logger.info("Exported GLB: %s", glb_path)
    except TypeError:
        # Older/newer signature fallback with fewer kwargs
        try:
            bpy.ops.export_scene.gltf(
                filepath=str(glb_path),
                export_format="GLB",
            )
            exported.append(str(glb_path))
        except Exception as exc:
            logger.error("GLB export failed: %s", exc)
    except Exception as exc:
        logger.error("GLB export failed: %s", exc)

    # --- Textures ---
    tex_exported = _export_textures(tex_out)
    exported.extend(tex_exported)

    # --- Sidecar JSON for Unity importers / LOD / thunder sync ---
    meta = _build_unity_metadata()
    meta_path = root / "CozyCoffeeShop_unity.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    exported.append(str(meta_path))

    # --- Save .blend ---
    try:
        blend_path = root / "CozyCoffeeShop.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), copy=True)
        exported.append(str(blend_path))
    except Exception as exc:
        logger.warning("Blend save skipped: %s", exc)

    logger.info("Unity export complete: %d files", len(exported))
    return exported


def _export_textures(dest: Path) -> List[str]:
    """Unpack / copy all images used by materials into export/textures."""
    exported: List[str] = []
    dest.mkdir(parents=True, exist_ok=True)

    # Also mirror AI texture library placeholders
    src_tex = config.TEXTURE_ROOT
    if src_tex.exists():
        for category in config.TEXTURE_CATEGORIES:
            cat_dest = dest / category
            cat_dest.mkdir(parents=True, exist_ok=True)

    for img in bpy.data.images:
        if not img or img.name == "Render Result" or img.name == "Viewer Node":
            continue
        try:
            # Determine filename
            if img.filepath:
                src = Path(bpy.path.abspath(img.filepath))
                if src.exists():
                    target = dest / src.name
                    shutil.copy2(src, target)
                    exported.append(str(target))
                    continue
            # Packed or generated — save
            safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in img.name)
            if not safe.lower().endswith((".png", ".jpg", ".exr", ".tif")):
                safe += ".png"
            target = dest / safe
            img.filepath_raw = str(target)
            img.file_format = "PNG"
            img.save()
            exported.append(str(target))
        except Exception as exc:
            logger.debug("Texture export skip %s: %s", getattr(img, "name", "?"), exc)
    return exported


def _build_unity_metadata() -> dict:
    scene = bpy.context.scene
    thunder = []
    empty = bpy.data.objects.get("WEATHER_ThunderSync")
    if empty and "thunder_frames" in empty:
        thunder = list(empty["thunder_frames"])
    else:
        thunder = [m.frame for m in scene.timeline_markers if m.name.startswith("THUNDER_")]

    cameras = [o.name for o in bpy.data.objects if o.type == "CAMERA"]
    lod_groups = [o.name for o in bpy.data.objects if o.get("unity_lod_group")]

    return {
        "product": "CozyCoffeeShop",
        "blender_version_target": "5.2.0",
        "unit_scale": "meters",
        "fps": config.FPS,
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "cinematic_duration_seconds": config.CINEMATIC_DURATION_SECONDS,
        "thunder_sync_frames": thunder,
        "cameras": cameras,
        "lod_groups": lod_groups,
        "texture_resolutions": list(config.TEXTURE_RESOLUTIONS),
        "collections": list(config.COLLECTION_HIERARCHY.keys()),
        "export_axis": {"forward": "-Z", "up": "Y"},
        "notes": (
            "Import FBX or GLB into Unity. Use CozyCoffeeShop_unity.json for "
            "LOD group wiring and thunder audio sync markers. "
            "Warm interior lights ~2700–3200K; exterior is cold storm lighting."
        ),
    }
