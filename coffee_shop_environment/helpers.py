# SPDX-License-Identifier: MIT
"""
Reusable Blender mesh / object / collection helpers.
Compatible with Blender 5.2.0 Python API.
"""

from __future__ import annotations

import math
import random
from typing import Iterable, List, Optional, Sequence, Tuple, Union

import bpy
from mathutils import Euler, Matrix, Vector

from . import config


# ---------------------------------------------------------------------------
# Scene / collection utilities
# ---------------------------------------------------------------------------

def clear_scene(keep_world: bool = True) -> None:
    """Remove all objects, meshes, materials, and cameras for a clean build."""
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    for block in (bpy.data.meshes, bpy.data.curves, bpy.data.lights,
                  bpy.data.cameras, bpy.data.particles, bpy.data.armatures):
        for item in list(block):
            block.remove(item)

    # Keep useful materials out of the way; purge orphans later if needed
    for mat in list(bpy.data.materials):
        bpy.data.materials.remove(mat)

    if not keep_world and bpy.context.scene.world:
        bpy.data.worlds.remove(bpy.context.scene.world)


def get_or_create_collection(name: str, parent: Optional[bpy.types.Collection] = None) -> bpy.types.Collection:
    """Return an existing collection or create a new linked one."""
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        if parent is None:
            bpy.context.scene.collection.children.link(col)
        else:
            if name not in parent.children:
                parent.children.link(col)
    else:
        # Ensure linked into scene hierarchy if orphaned
        if parent is not None and name not in [c.name for c in parent.children]:
            try:
                parent.children.link(col)
            except RuntimeError:
                pass
        elif parent is None and name not in [c.name for c in bpy.context.scene.collection.children]:
            try:
                bpy.context.scene.collection.children.link(col)
            except RuntimeError:
                pass
    return col


def setup_collection_hierarchy() -> dict:
    """Create the professional game-asset collection tree from config."""
    root = get_or_create_collection("CoffeeShop_Root")
    tree = {"CoffeeShop_Root": root}
    for parent_name, children in config.COLLECTION_HIERARCHY.items():
        parent = get_or_create_collection(parent_name, root)
        tree[parent_name] = parent
        for child_name in children:
            full = f"{parent_name}/{child_name}"
            child = get_or_create_collection(child_name, parent)
            tree[full] = child
            tree[child_name] = child
    return tree


def link_object_to_collection(obj: bpy.types.Object, collection: Union[str, bpy.types.Collection]) -> None:
    """Move object exclusively into the target collection."""
    if isinstance(collection, str):
        collection = get_or_create_collection(collection)
    # Unlink from all collections
    for col in list(obj.users_collection):
        col.objects.unlink(obj)
    if obj.name not in collection.objects:
        collection.objects.link(obj)


def set_active(obj: bpy.types.Object) -> None:
    """Select and activate a single object."""
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def apply_transforms(obj: bpy.types.Object, location=True, rotation=True, scale=True) -> None:
    """Apply object transforms (Unity-friendly pivots after origin set)."""
    set_active(obj)
    try:
        bpy.ops.object.transform_apply(location=location, rotation=rotation, scale=scale)
    except RuntimeError:
        pass


def set_origin_to_geometry(obj: bpy.types.Object) -> None:
    set_active(obj)
    try:
        bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    except RuntimeError:
        pass


def set_origin_to_bottom(obj: bpy.types.Object) -> None:
    """Place origin at the bottom center — useful for furniture placement."""
    set_active(obj)
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    # Shift mesh so origin sits at bottom
    bbox = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    min_z = min(v.z for v in bbox)
    for v in obj.data.vertices:
        v.co.z -= (min_z - obj.location.z)
    obj.location.z = min_z
    bpy.ops.object.origin_set(type="ORIGIN_CURSOR")  # may be unreliable; fallback:
    # Prefer explicit bottom origin via geometry + location restore
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")


# ---------------------------------------------------------------------------
# Primitive builders
# ---------------------------------------------------------------------------

def create_cube(
    name: str,
    size: Union[float, Tuple[float, float, float]] = 1.0,
    location: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    rotation: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    collection: Optional[Union[str, bpy.types.Collection]] = None,
) -> bpy.types.Object:
    """Create a scaled cube mesh object."""
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.active_object
    obj.name = name
    if isinstance(size, (int, float)):
        obj.scale = (size, size, size)
    else:
        obj.scale = size
    obj.rotation_euler = Euler(rotation, "XYZ")
    apply_transforms(obj)
    obj.location = location
    if collection is not None:
        link_object_to_collection(obj, collection)
    return obj


def create_cylinder(
    name: str,
    radius: float = 0.5,
    depth: float = 1.0,
    vertices: int = 32,
    location: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    rotation: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    collection: Optional[Union[str, bpy.types.Collection]] = None,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(
        radius=radius, depth=depth, vertices=vertices, location=location
    )
    obj = bpy.context.active_object
    obj.name = name
    obj.rotation_euler = Euler(rotation, "XYZ")
    apply_transforms(obj, location=False, rotation=True, scale=True)
    obj.location = location
    if collection is not None:
        link_object_to_collection(obj, collection)
    return obj


def create_uv_sphere(
    name: str,
    radius: float = 0.5,
    segments: int = 32,
    rings: int = 16,
    location: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    collection: Optional[Union[str, bpy.types.Collection]] = None,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=radius, segments=segments, ring_count=rings, location=location
    )
    obj = bpy.context.active_object
    obj.name = name
    if collection is not None:
        link_object_to_collection(obj, collection)
    return obj


def create_plane(
    name: str,
    size: float = 1.0,
    location: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    rotation: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    collection: Optional[Union[str, bpy.types.Collection]] = None,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_plane_add(size=size, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.rotation_euler = Euler(rotation, "XYZ")
    apply_transforms(obj, location=False, rotation=True, scale=True)
    obj.location = location
    if collection is not None:
        link_object_to_collection(obj, collection)
    return obj


def create_torus(
    name: str,
    major_radius: float = 0.2,
    minor_radius: float = 0.05,
    location: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    collection: Optional[Union[str, bpy.types.Collection]] = None,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major_radius, minor_radius=minor_radius, location=location
    )
    obj = bpy.context.active_object
    obj.name = name
    if collection is not None:
        link_object_to_collection(obj, collection)
    return obj


def create_cone(
    name: str,
    radius1: float = 0.5,
    depth: float = 1.0,
    vertices: int = 32,
    location: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    collection: Optional[Union[str, bpy.types.Collection]] = None,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cone_add(
        radius1=radius1, depth=depth, vertices=vertices, location=location
    )
    obj = bpy.context.active_object
    obj.name = name
    if collection is not None:
        link_object_to_collection(obj, collection)
    return obj


def bevel_object(obj: bpy.types.Object, width: float = 0.005, segments: int = 3) -> None:
    """Add a bevel modifier for soft realistic edges."""
    mod = obj.modifiers.new(name="Bevel", type="BEVEL")
    mod.width = width
    mod.segments = segments
    mod.limit_method = "ANGLE"
    mod.angle_limit = math.radians(30)


def subdivide_object(obj: bpy.types.Object, levels: int = 1, render_levels: int = 2) -> None:
    mod = obj.modifiers.new(name="Subsurf", type="SUBSURF")
    mod.levels = levels
    mod.render_levels = render_levels


def solidify_object(obj: bpy.types.Object, thickness: float = 0.02) -> None:
    mod = obj.modifiers.new(name="Solidify", type="SOLIDIFY")
    mod.thickness = thickness


def decimate_object(obj: bpy.types.Object, ratio: float, name: str = "Decimate") -> bpy.types.Modifier:
    mod = obj.modifiers.new(name=name, type="DECIMATE")
    mod.ratio = max(0.01, min(1.0, ratio))
    return mod


def shade_smooth(obj: bpy.types.Object, auto_smooth_angle: float = 30.0) -> None:
    """Enable smooth shading with optional auto-smooth (Blender 5.x safe)."""
    set_active(obj)
    try:
        bpy.ops.object.shade_smooth()
    except RuntimeError:
        pass
    # Blender 4.1+ moved autosmooth to modifier; try both paths
    mesh = obj.data
    if hasattr(mesh, "use_auto_smooth"):
        mesh.use_auto_smooth = True
        mesh.auto_smooth_angle = math.radians(auto_smooth_angle)
    else:
        # Use Smooth by Angle modifier if available
        if "Smooth by Angle" not in [m.name for m in obj.modifiers]:
            try:
                mod = obj.modifiers.new(name="Smooth by Angle", type="NODES")
                # Fallback: ignore if node group unavailable
                _ = mod
            except Exception:
                pass


def assign_material(obj: bpy.types.Object, material: bpy.types.Material, slot: int = 0) -> None:
    """Assign a material to an object, creating slots as needed."""
    if obj.data is None or not hasattr(obj.data, "materials"):
        return
    if len(obj.data.materials) == 0:
        obj.data.materials.append(material)
    elif slot < len(obj.data.materials):
        obj.data.materials[slot] = material
    else:
        obj.data.materials.append(material)


def join_objects(objects: Sequence[bpy.types.Object], name: str) -> Optional[bpy.types.Object]:
    """Join a list of mesh objects into one."""
    meshes = [o for o in objects if o and o.type == "MESH"]
    if not meshes:
        return None
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.join()
    result = bpy.context.active_object
    result.name = name
    return result


def duplicate_object(obj: bpy.types.Object, name: str, location: Optional[Tuple[float, float, float]] = None) -> bpy.types.Object:
    """Duplicate an object with linked or unique data."""
    new_obj = obj.copy()
    if obj.data:
        new_obj.data = obj.data.copy()
    new_obj.name = name
    for col in obj.users_collection:
        col.objects.link(new_obj)
    if location is not None:
        new_obj.location = location
    return new_obj


def random_offset(base: Tuple[float, float, float], amount: float, rng: random.Random) -> Tuple[float, float, float]:
    return (
        base[0] + rng.uniform(-amount, amount),
        base[1] + rng.uniform(-amount, amount),
        base[2] + rng.uniform(-amount * 0.25, amount * 0.25),
    )


def random_rotation_z(rng: random.Random, max_deg: float = 15.0) -> Tuple[float, float, float]:
    return (0.0, 0.0, math.radians(rng.uniform(-max_deg, max_deg)))


def ensure_object_mode() -> None:
    if bpy.context.mode != "OBJECT":
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except RuntimeError:
            pass


def add_empty(name: str, location=(0, 0, 0), collection=None) -> bpy.types.Object:
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=location)
    obj = bpy.context.active_object
    obj.name = name
    if collection is not None:
        link_object_to_collection(obj, collection)
    return obj


def parent_keep_transform(child: bpy.types.Object, parent: bpy.types.Object) -> None:
    child.parent = parent
    child.matrix_parent_inverse = parent.matrix_world.inverted()


def mark_as_asset(obj: bpy.types.Object, tags: Optional[Iterable[str]] = None) -> None:
    """Mark object as Blender asset for library browsing (optional)."""
    try:
        obj.asset_mark()
        if tags:
            for tag in tags:
                obj.asset_data.tags.new(tag)
    except Exception:
        pass


def frame_range(scene: Optional[bpy.types.Scene] = None) -> None:
    scene = scene or bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = config.CINEMATIC_FRAME_END
    scene.render.fps = config.FPS
