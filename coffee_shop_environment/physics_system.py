# SPDX-License-Identifier: MIT
"""
Physics configuration: cloth, rigid body, soft body, particles.
"""

from __future__ import annotations

import logging
from typing import List

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

    def _ensure_rigidbody_world(self) -> None:
        scene = bpy.context.scene
        if scene.rigidbody_world is None:
            try:
                bpy.ops.rigidbody.world_add()
            except RuntimeError as exc:
                logger.warning("Rigid body world add failed: %s", exc)
        if scene.rigidbody_world:
            scene.rigidbody_world.point_cache.frame_start = 1
            scene.rigidbody_world.point_cache.frame_end = config.CINEMATIC_FRAME_END

    def _configure_cloth(self) -> None:
        for obj in bpy.data.objects:
            if not obj.get("coffee_shop_cloth"):
                continue
            if obj.type != "MESH":
                continue
            helpers.set_active(obj)
            # Ensure enough geometry for cloth
            if len(obj.data.vertices) < 64:
                helpers.subdivide_object(obj, 2, 3)
            mod = obj.modifiers.new(name="Cloth", type="CLOTH")
            cloth = mod.settings
            cloth.quality = 8
            cloth.mass = 0.3
            cloth.air_damping = 1.0
            try:
                cloth.tension_stiffness = 15.0
                cloth.compression_stiffness = 15.0
                cloth.shear_stiffness = 5.0
                cloth.bending_stiffness = 0.5
            except Exception:
                pass
            # Pin top vertices for hanging curtains
            self._pin_top_vertices(obj)
            col_set = mod.collision_settings
            col_set.use_collision = True
            col_set.distance_min = 0.01
            helpers.link_object_to_collection(obj, self.cols.get("Cloth", "Cloth"))
            self.configured.append(obj.name)
            logger.info("Cloth enabled: %s", obj.name)

        # Hanging plant foliage — light wind deform via simple deform if no cloth flag
        for obj in bpy.data.objects:
            if "HangingPlant_Leaf" in obj.name or "HangingPlant_Pot" in obj.name:
                if "Cloth" in [m.name for m in obj.modifiers]:
                    continue
                # Soft wind wobble via keyframed rotation handled in AnimationSystem
                obj["coffee_shop_wind_anim"] = True

    def _pin_top_vertices(self, obj: bpy.types.Object) -> None:
        """Create a pin vertex group from the top-most vertices."""
        mesh = obj.data
        # Find max Z in local space
        max_z = max(v.co.z for v in mesh.vertices)
        threshold = max_z - 0.05
        vg = obj.vertex_groups.get("Pin") or obj.vertex_groups.new(name="Pin")
        indices = [v.index for v in mesh.vertices if v.co.z >= threshold]
        if indices:
            vg.add(indices, 1.0, "REPLACE")
        # Assign to cloth
        for mod in obj.modifiers:
            if mod.type == "CLOTH":
                mod.settings.vertex_group_mass = "Pin"

    def _configure_rigid_bodies(self) -> None:
        # Passive: floor, counters, architecture
        passive_prefixes = ("ARCH_", "Bar_Counter", "EXT_Road", "EXT_Sidewalk", "EXT_Building")
        for obj in bpy.data.objects:
            if obj.type != "MESH":
                continue
            if any(obj.name.startswith(p) for p in passive_prefixes):
                self._add_rigidbody(obj, "PASSIVE", mass=0.0)
                helpers.link_object_to_collection(obj, self.cols.get("RigidBodies", "RigidBodies"))

        # Active decorative / chair candidates (keep mostly kinematic for game export)
        active_keywords = ("Chair_", "Mug_", "Pastry_", "Candle_", "NapkinHolder_", "Book_")
        for obj in bpy.data.objects:
            if obj.type != "MESH":
                continue
            if any(k in obj.name for k in active_keywords):
                # Use PASSIVE with animated start to avoid simulation explosion on load;
                # mark as rigid-body capable for Unity export metadata
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
            obj.rigid_body.type = body_type
            obj.rigid_body.mass = max(mass, 0.01)
            obj.rigid_body.collision_shape = "CONVEX_HULL" if body_type == "ACTIVE" else "MESH"
            obj.rigid_body.friction = 0.7
            obj.rigid_body.restitution = 0.1
        except RuntimeError as exc:
            logger.debug("Rigid body skip %s: %s", obj.name, exc)

    def _configure_soft_bodies(self) -> None:
        for obj in bpy.data.objects:
            if obj.type != "MESH":
                continue
            if "Cushion" not in obj.name and "Pouf_" not in obj.name and "Couch_" not in obj.name:
                continue
            # Soft body can be heavy; enable on cushions only
            if "Cushion" not in obj.name and "Pouf_" not in obj.name:
                obj["unity_softbody"] = True
                continue
            helpers.set_active(obj)
            try:
                mod = obj.modifiers.new(name="Softbody", type="SOFT_BODY")
                sb = mod.settings
                sb.mass = 1.0
                sb.goal_default = 0.7
                sb.goal_min = 0.5
                sb.goal_max = 1.0
                sb.use_edges = True
                sb.plastic = 0.0
                helpers.link_object_to_collection(obj, self.cols.get("SoftBodies", "SoftBodies"))
                self.configured.append(obj.name)
                logger.info("Soft body enabled: %s", obj.name)
            except RuntimeError as exc:
                logger.warning("Soft body failed for %s: %s", obj.name, exc)
                obj["unity_softbody"] = True

    def _tag_particle_collections(self) -> None:
        for obj in bpy.data.objects:
            if obj.particle_systems:
                helpers.link_object_to_collection(obj, self.cols.get("Particles", "Particles"))
                self.configured.append(obj.name)
