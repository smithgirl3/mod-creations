# SPDX-License-Identifier: MIT
"""
Cinematic camera system with interior/exterior cameras and a 30s dolly sequence.
"""

from __future__ import annotations

import logging
import math
from typing import List, Optional, Tuple

import bpy
from mathutils import Vector, Euler

from . import config, helpers

logger = logging.getLogger(__name__)


class CameraSystem:
    """Multiple cinematic cameras + animated 30-second sequence."""

    def __init__(self, collections: dict):
        self.cols = collections
        self.cameras: List[bpy.types.Object] = []
        self.cinematic: Optional[bpy.types.Object] = None

    def build(self) -> List[bpy.types.Object]:
        self.cameras.clear()
        self._create_interior_cameras()
        self._create_exterior_cameras()
        self._create_cinematic_sequence()
        return self.cameras

    def _link(self, obj, key: str = "InteriorCams"):
        helpers.link_object_to_collection(obj, self.cols.get(key, key))
        self.cameras.append(obj)
        return obj

    def _add_camera(
        self,
        name: str,
        location: Tuple[float, float, float],
        look_at: Tuple[float, float, float],
        lens: float = 35.0,
        fstop: float = config.DOF_FSTOP,
        collection: str = "InteriorCams",
    ) -> bpy.types.Object:
        bpy.ops.object.camera_add(location=location)
        cam = bpy.context.active_object
        cam.name = name
        cam.data.lens = lens
        cam.data.clip_start = 0.05
        cam.data.clip_end = 200.0
        cam.data.dof.use_dof = True
        cam.data.dof.aperture_fstop = fstop
        # Aim camera
        self._aim_at(cam, Vector(look_at))
        # DOF focus empty
        focus = helpers.add_empty(f"{name}_Focus", location=look_at)
        helpers.link_object_to_collection(focus, self.cols.get(collection, collection))
        cam.data.dof.focus_object = focus
        self._link(cam, collection)
        return cam

    def _aim_at(self, obj: bpy.types.Object, target: Vector) -> None:
        direction = target - obj.location
        if direction.length < 1e-6:
            return
        quat = direction.to_track_quat("-Z", "Y")
        obj.rotation_euler = quat.to_euler()

    def _create_interior_cameras(self) -> None:
        # Coffee counter
        self._add_camera(
            "CAM_CoffeeCounter",
            location=(2.5, config.SHOP_DEPTH * 0.5 - 4.5, 1.5),
            look_at=(0.5, config.SHOP_DEPTH * 0.5 - 2.2, 1.2),
            lens=40.0,
            collection="InteriorCams",
        )
        # Reading corner
        self._add_camera(
            "CAM_ReadingCorner",
            location=(-3.5, config.SHOP_DEPTH * 0.5 - 4.0, 1.3),
            look_at=(-5.0, config.SHOP_DEPTH * 0.5 - 2.2, 1.0),
            lens=50.0,
            fstop=2.0,
            collection="InteriorCams",
        )
        # Window seating
        self._add_camera(
            "CAM_WindowSeating",
            location=(0.0, -config.SHOP_DEPTH * 0.5 + 4.0, 1.2),
            look_at=(0.0, -config.SHOP_DEPTH * 0.5 + 1.5, 1.0),
            lens=35.0,
            collection="InteriorCams",
        )
        # Wide room view
        self._add_camera(
            "CAM_WideRoom",
            location=(5.5, -6.0, 2.2),
            look_at=(0.0, 2.0, 1.4),
            lens=24.0,
            fstop=4.0,
            collection="InteriorCams",
        )
        # Detail espresso close-up
        self._add_camera(
            "CAM_EspressoCloseup",
            location=(0.9, config.SHOP_DEPTH * 0.5 - 2.8, 1.25),
            look_at=(0.5, config.SHOP_DEPTH * 0.5 - 2.3, 1.2),
            lens=85.0,
            fstop=1.8,
            collection="InteriorCams",
        )

    def _create_exterior_cameras(self) -> None:
        front = -config.SHOP_DEPTH * 0.5
        self._add_camera(
            "CAM_StreetView",
            location=(0.0, front - 8.0, 1.6),
            look_at=(0.0, front, 1.8),
            lens=35.0,
            collection="ExteriorCams",
        )
        self._add_camera(
            "CAM_RainScene",
            location=(-6.0, front - 5.0, 1.4),
            look_at=(0.0, front - 2.0, 1.0),
            lens=28.0,
            fstop=2.4,
            collection="ExteriorCams",
        )
        self._add_camera(
            "CAM_ThroughWindow",
            location=(0.0, front - 3.0, 1.5),
            look_at=(0.0, 0.0, 1.4),
            lens=40.0,
            collection="ExteriorCams",
        )

    def _create_cinematic_sequence(self) -> None:
        """
        30-second cinematic camera:
        0–8s   dolly toward window seating
        8–16s  crane/orbit toward coffee bar
        16–24s slow push into espresso close-up with focus pull
        24–30s pull back to wide room establishing shot
        """
        cam = self._add_camera(
            "CAM_Cinematic",
            location=(4.0, -5.0, 1.4),
            look_at=(0.0, -config.SHOP_DEPTH * 0.5 + 1.8, 1.0),
            lens=35.0,
            fstop=2.8,
            collection="Cinematic",
        )
        self.cinematic = cam
        bpy.context.scene.camera = cam

        focus = bpy.data.objects.get("CAM_Cinematic_Focus")
        fps = config.FPS
        # Key poses: (frame, location, look_at, lens, fstop)
        keys = [
            (1, (5.0, -6.5, 1.5), (-1.0, -config.SHOP_DEPTH * 0.5 + 2.0, 1.0), 32.0, 3.2),
            (int(8 * fps), (1.0, -config.SHOP_DEPTH * 0.5 + 3.5, 1.25), (0.0, -config.SHOP_DEPTH * 0.5 + 1.5, 0.95), 40.0, 2.4),
            (int(16 * fps), (2.8, config.SHOP_DEPTH * 0.5 - 5.0, 1.45), (0.5, config.SHOP_DEPTH * 0.5 - 2.2, 1.2), 50.0, 2.2),
            (int(24 * fps), (0.95, config.SHOP_DEPTH * 0.5 - 2.9, 1.28), (0.5, config.SHOP_DEPTH * 0.5 - 2.25, 1.22), 85.0, 1.8),
            (config.CINEMATIC_FRAME_END, (6.0, -7.0, 2.4), (0.0, 1.0, 1.3), 24.0, 4.0),
        ]

        for frame, loc, look, lens, fstop in keys:
            cam.location = loc
            cam.keyframe_insert(data_path="location", frame=frame)
            self._aim_at(cam, Vector(look))
            cam.keyframe_insert(data_path="rotation_euler", frame=frame)
            cam.data.lens = lens
            cam.data.keyframe_insert(data_path="lens", frame=frame)
            cam.data.dof.aperture_fstop = fstop
            cam.data.dof.keyframe_insert(data_path="aperture_fstop", frame=frame)
            if focus:
                focus.location = look
                focus.keyframe_insert(data_path="location", frame=frame)

        self._smooth_camera_fcurves(cam)
        if focus:
            self._smooth_camera_fcurves(focus)

        # Timeline markers for editorial sync
        scene = bpy.context.scene
        for name, frame in (
            ("CINEMATIC_START", 1),
            ("CINEMATIC_WINDOW", int(8 * fps)),
            ("CINEMATIC_BAR", int(16 * fps)),
            ("CINEMATIC_ESPRESSO", int(24 * fps)),
            ("CINEMATIC_END", config.CINEMATIC_FRAME_END),
        ):
            if name not in scene.timeline_markers:
                scene.timeline_markers.new(name, frame=frame)

        logger.info("Cinematic camera sequence created (%d frames)", config.CINEMATIC_FRAME_END)

    def _smooth_camera_fcurves(self, obj: bpy.types.Object) -> None:
        ad = obj.animation_data
        if not ad or not ad.action:
            return
        fcurves = getattr(ad.action, "fcurves", None)
        if not fcurves and hasattr(obj, "data") and obj.data and obj.data.animation_data:
            ad = obj.data.animation_data
            fcurves = getattr(ad.action, "fcurves", None) if ad and ad.action else None
        # Also smooth DOF on camera data
        targets = []
        if obj.animation_data and obj.animation_data.action:
            targets.append(obj.animation_data.action)
        if obj.type == "CAMERA" and obj.data.animation_data and obj.data.animation_data.action:
            targets.append(obj.data.animation_data.action)
        for action in targets:
            fcs = getattr(action, "fcurves", None)
            if not fcs:
                continue
            for fc in fcs:
                for kp in fc.keyframe_points:
                    kp.interpolation = "BEZIER"
                    kp.handle_left_type = "AUTO_CLAMPED"
                    kp.handle_right_type = "AUTO_CLAMPED"
