# SPDX-License-Identifier: MIT
"""
Physics configuration: cloth, rigid body, soft body, particles.
Compatible with Blender 5.2 SoftBodySettings / ClothSettings RNA types.
"""

from __future__ import annotations

import logging
from typing import Any, List

import bpy

from . import config, helpers

logger = logging.getLogger(__name__)


class PhysicsSystem:
    """Configure realistic physics for curtains, chairs, cushions, particles."""

    def __init__(self, collections: dict):
        self.cols = collections
        self.configured: List[str] = []

    def build(self) -> List[str]:
        self.configured.clear()
        self._ensure_rigidbody_world()
        self._configure_cloth()
        self._configure_rigid_bodies()
        self._configure_soft_bodies()
        self._tag_particle_collections()
        return self.configured

    @staticmethod
    def _set_attr(target: Any, name: str, value: Any) -> None:
        """Assign an RNA attribute safely (handles missing attrs / type mismatches)."""
        if target is None or not hasattr(target, name):
            return
        try:
            setattr(target, name, value)
        except (TypeError, ValueError, OverflowError, RuntimeError) as exc:
            # Blender 5.2: some SoftBody ints reject floats — retry with coerced type
            try:
                prop = target.bl_rna.properties.get(name) if hasattr(target, "bl_rna") else None
                if prop is not None:
                    ptype = getattr(prop, "type", None)
                    if ptype == "INT":
                        setattr(target, name, int(value))
                        return
                    if ptype == "FLOAT":
                        setattr(target, name, float(value))
                        return
                    if ptype == "BOOLEAN":
                        setattr(target, name, bool(value))
                        return
            except Exception:
                pass
            logger.debug("Could not set %s.%s=%r: %s", type(target).__name__, name, value, exc)

    def _ensure_rigidbody_world(self) -> None:
        scene = bpy.context.scene
        if scene.rigidbody_world is None:
            try:
                bpy.ops.rigidbody.world_add()
            except RuntimeError as exc:
                logger.warning("Rigid body world add failed: %s", exc)
        if scene.rigidbody_world:
            try:
                scene.rigidbody_world.point_cache.frame_start = 1
                scene.rigidbody_world.point_cache.frame_end = config.CINEMATIC_FRAME_END
            except Exception as exc:
                logger.debug("Rigid body cache frame range skip: %s", exc)

    def _configure_cloth(self) -> None:
        for obj in bpy.data.objects:
            if not obj.get("coffee_shop_cloth"):
                continue
            if obj.type != "MESH":
                continue
            helpers.set_active(obj)
            if len(obj.data.vertices) < 64:
                helpers.subdivide_object(obj, 2, 3)
            try:
                mod = obj.modifiers.new(name="Cloth", type="CLOTH")
                cloth = mod.settings
                self._set_attr(cloth, "quality", 8)
                self._set_attr(cloth, "mass", 0.3)
                self._set_attr(cloth, "air_damping", 1.0)
                self._set_attr(cloth, "tension_stiffness", 15.0)
                self._set_attr(cloth, "compression_stiffness", 15.0)
                self._set_attr(cloth, "shear_stiffness", 5.0)
                self._set_attr(cloth, "bending_stiffness", 0.5)
                self._pin_top_vertices(obj)
                col_set = mod.collision_settings
                self._set_attr(col_set, "use_collision", True)
                self._set_attr(col_set, "distance_min", 0.01)
                helpers.link_object_to_collection(obj, self.cols.get("Cloth", "Cloth"))
                self.configured.append(obj.name)
                logger.info("Cloth enabled: %s", obj.name)
            except Exception as exc:
                logger.warning("Cloth failed for %s: %s", obj.name, exc)

        for obj in bpy.data.objects:
            if "HangingPlant_Leaf" in obj.name or "HangingPlant_Pot" in obj.name:
                if "Cloth" in [m.name for m in obj.modifiers]:
                    continue
                obj["coffee_shop_wind_anim"] = True

    def _pin_top_vertices(self, obj: bpy.types.Object) -> None:
        """Create a pin vertex group from the top-most vertices."""
        mesh = obj.data
        max_z = max(v.co.z for v in mesh.vertices)
        threshold = max_z - 0.05
        vg = obj.vertex_groups.get("Pin") or obj.vertex_groups.new(name="Pin")
        indices = [v.index for v in mesh.vertices if v.co.z >= threshold]
        if indices:
            vg.add(indices, 1.0, "REPLACE")
        for mod in obj.modifiers:
            if mod.type == "CLOTH":
                self._set_attr(mod.settings, "vertex_group_mass", "Pin")

    def _configure_rigid_bodies(self) -> None:
        passive_prefixes = ("ARCH_", "Bar_Counter", "EXT_Road", "EXT_Sidewalk", "EXT_Building")
        for obj in bpy.data.objects:
            if obj.type != "MESH":
                continue
            if any(obj.name.startswith(p) for p in passive_prefixes):
                self._add_rigidbody(obj, "PASSIVE", mass=0.0)
                helpers.link_object_to_collection(obj, self.cols.get("RigidBodies", "RigidBodies"))

        active_keywords = ("Chair_", "Mug_", "Pastry_", "Candle_", "NapkinHolder_", "Book_")
        for obj in bpy.data.objects:
            if obj.type != "MESH":
                continue
            if any(k in obj.name for k in active_keywords):
                self._add_rigidbody(obj, "PASSIVE", mass=1.0)
                obj["unity_rigidbody"] = True
                obj["unity_mass"] = 1.0 if "Chair" in obj.name else 0.2
                helpers.link_object_to_collection(obj, self.cols.get("RigidBodies", "RigidBodies"))
                self.configured.append(obj.name)

    def _add_rigidbody(self, obj: bpy.types.Object, body_type: str, mass: float) -> None:
        helpers.set_active(obj)
        try:
            if obj.rigid_body is None:
                bpy.ops.rigidbody.object_add()
            rb = obj.rigid_body
            if rb is None:
                return
            self._set_attr(rb, "type", body_type)
            self._set_attr(rb, "mass", max(mass, 0.01))
            self._set_attr(
                rb,
                "collision_shape",
                "CONVEX_HULL" if body_type == "ACTIVE" else "MESH",
            )
            self._set_attr(rb, "friction", 0.7)
            self._set_attr(rb, "restitution", 0.1)
        except Exception as exc:
            logger.debug("Rigid body skip %s: %s", obj.name, exc)

    def _configure_soft_bodies(self) -> None:
        for obj in bpy.data.objects:
            if obj.type != "MESH":
                continue
            if "Cushion" not in obj.name and "Pouf_" not in obj.name and "Couch_" not in obj.name:
                continue
            # Soft body can be heavy; enable on cushions / poufs only
            if "Cushion" not in obj.name and "Pouf_" not in obj.name:
                obj["unity_softbody"] = True
                continue
            helpers.set_active(obj)
            try:
                mod = obj.modifiers.new(name="Softbody", type="SOFT_BODY")
                sb = mod.settings
                self._set_attr(sb, "mass", 1.0)
                self._set_attr(sb, "goal_default", 0.7)
                self._set_attr(sb, "goal_min", 0.5)
                self._set_attr(sb, "goal_max", 1.0)
                self._set_attr(sb, "use_edges", True)
                # Blender 5.2: plastic is INT in [0, 100], not float
                self._set_attr(sb, "plastic", 0)
                helpers.link_object_to_collection(obj, self.cols.get("SoftBodies", "SoftBodies"))
                self.configured.append(obj.name)
                logger.info("Soft body enabled: %s", obj.name)
            except Exception as exc:
                logger.warning("Soft body failed for %s: %s", obj.name, exc)
                obj["unity_softbody"] = True

    def _tag_particle_collections(self) -> None:
        for obj in bpy.data.objects:
            if obj.particle_systems:
                helpers.link_object_to_collection(obj, self.cols.get("Particles", "Particles"))
                self.configured.append(obj.name)
