"""
================================================================================
 Ultra-Realistic Rainstorm Environment Generator
 Blender 5.2.0 Compatible · Procedural · Cinematic Quality
================================================================================

Run this script from Blender's Scripting workspace (Text Editor → Run Script)
or via the command line:

    blender --background --python blender_rainstorm_environment.py

Creates a complete storm scene with volumetric clouds, high-performance rain
instancing, splash effects, reflective puddles, wind forces, storm lighting,
optional lightning, and a 300-frame animated sequence.

All major parameters are adjustable in the CONFIGURATION section below.
================================================================================
"""

from __future__ import annotations

import math
import random
import traceback
from typing import Any, Optional

import bpy
from mathutils import Euler


# =============================================================================
# CONFIGURATION — tweak these values before running
# =============================================================================

# --- Rain ---
RAIN_INTENSITY: float = 0.85          # 0.0 – 1.0 (controls drop count / density)
DROP_SIZE_MIN: float = 0.008          # meters
DROP_SIZE_MAX: float = 0.035          # meters
WIND_STRENGTH: float = 4.5            # horizontal wind bias on rain

# --- Splash ---
SPLASH_SCALE: float = 1.0             # overall splash size multiplier
SPLASH_DENSITY: float = 0.7           # 0.0 – 1.0

# --- Puddles ---
PUDDLE_COVERAGE: float = 0.55         # 0.0 – 1.0
PUDDLE_DEPTH: float = 0.85            # visual depth / wetness strength

# --- Wind ---
WIND_SPEED: float = 6.0               # force field strength
WIND_TURBULENCE: float = 2.5          # turbulence force strength
GUST_FACTOR: float = 1.4              # gust intensity multiplier

# --- Lighting ---
ENABLE_LIGHTNING: bool = True

# --- Animation ---
FRAME_START: int = 1
FRAME_END: int = 300
FPS: int = 24

# --- Scene scale ---
GROUND_SIZE: float = 80.0             # ground plane extent (meters)
CLOUD_ALTITUDE: float = 45.0          # cloud volume base height
CLOUD_THICKNESS: float = 55.0
RAIN_VOLUME_HEIGHT: float = 40.0

# --- Performance ---
RAIN_BASE_COUNT: int = 250_000        # base rain instances (scaled by intensity)
SPLASH_BASE_COUNT: int = 8_000
CLOUD_DOMAIN_RES: int = 128           # volume display resolution hint
USE_CYCLES: bool = True               # True = Cycles, False = EEVEE


# =============================================================================
# UTILITIES
# =============================================================================

def _log(msg: str) -> None:
    """Print a prefixed status message."""
    print(f"[Rainstorm] {msg}")


def _safe_remove_data(collection_attr: str, name_prefix: str) -> None:
    """Remove datablocks whose names start with name_prefix."""
    data = getattr(bpy.data, collection_attr, None)
    if data is None:
        return
    for block in list(data):
        if block.name.startswith(name_prefix):
            try:
                data.remove(block)
            except (ReferenceError, RuntimeError):
                pass


def get_or_create_collection(name: str, parent: Optional[bpy.types.Collection] = None) -> bpy.types.Collection:
    """Return an existing collection or create a new one under parent/scene."""
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
    scene_col = bpy.context.scene.collection
    target_parent = parent if parent is not None else scene_col
    # Link if not already present in the target hierarchy
    if col.name not in target_parent.children:
        try:
            target_parent.children.link(col)
        except RuntimeError:
            # Already linked elsewhere; ensure it is reachable from the scene
            if col.name not in scene_col.children and all(
                col.name not in c.children for c in bpy.data.collections
            ):
                scene_col.children.link(col)
    return col


def link_object(obj: bpy.types.Object, collection: bpy.types.Collection) -> None:
    """Link an object exclusively into the given collection."""
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    if obj.name not in collection.objects:
        collection.objects.link(obj)


def new_object(name: str, data: Any, collection: bpy.types.Collection) -> bpy.types.Object:
    """Create an object, clear prior users of the same name, and link it."""
    existing = bpy.data.objects.get(name)
    if existing is not None:
        bpy.data.objects.remove(existing, do_unlink=True)
    obj = bpy.data.objects.new(name, data)
    link_object(obj, collection)
    return obj


def set_active(obj: bpy.types.Object) -> None:
    """Make obj the active selected object."""
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def ensure_cycles_or_eevee(scene: bpy.types.Scene) -> None:
    """Select Cycles or EEVEE with Blender 5.x engine identifiers."""
    if USE_CYCLES:
        scene.render.engine = "CYCLES"
        # Prefer GPU if available
        try:
            prefs = bpy.context.preferences.addons["cycles"].preferences
            prefs.compute_device_type = "CUDA"
            for device in prefs.devices:
                device.use = True
            scene.cycles.device = "GPU"
        except Exception:
            scene.cycles.device = "CPU"
        scene.cycles.samples = 128
        scene.cycles.volume_bounces = 4
        scene.cycles.transparent_max_bounces = 16
        scene.cycles.use_animated_seed = True
        # Motion blur for rain streaks
        scene.render.use_motion_blur = True
        scene.render.motion_blur_shutter = 0.5
    else:
        # Blender 5.0+ renamed EEVEE Next → BLENDER_EEVEE
        scene.render.engine = "BLENDER_EEVEE"
        eevee = scene.eevee
        if hasattr(eevee, "use_raytracing"):
            eevee.use_raytracing = True
        if hasattr(eevee, "use_volumetric_shadows"):
            eevee.use_volumetric_shadows = True
        if hasattr(eevee, "volumetric_tile_size"):
            eevee.volumetric_tile_size = "4"
        if hasattr(eevee, "volumetric_samples"):
            eevee.volumetric_samples = 64


def set_gn_modifier_input(modifier: bpy.types.NodesModifier, identifier: str, value: Any) -> bool:
    """
    Set a Geometry Nodes modifier input, supporting Blender 5.2 RNA properties
    and the older custom-property dictionary API.
    """
    # Blender 5.2+: modifier.properties.inputs.<id>.value
    try:
        inputs = modifier.properties.inputs
        sock = getattr(inputs, identifier, None)
        if sock is not None and hasattr(sock, "value"):
            sock.value = value
            return True
    except Exception:
        pass

    # Fallback: custom property access (Blender ≤ 5.1)
    try:
        # Prefer socket identifier keys used by the modifier
        if identifier in modifier:
            modifier[identifier] = value
            return True
        # Try with leading underscore variants / integer keys
        for key in list(modifier.keys()):
            if str(key).endswith(identifier) or str(key) == identifier:
                modifier[key] = value
                return True
    except Exception:
        pass

    return False


def new_geometry_node_group(name: str) -> bpy.types.GeometryNodeTree:
    """Create (or recreate) a Geometry Node tree with default I/O sockets."""
    existing = bpy.data.node_groups.get(name)
    if existing is not None:
        bpy.data.node_groups.remove(existing)

    ng = bpy.data.node_groups.new(name, type="GeometryNodeTree")

    # Blender 4.0+ interface API
    try:
        ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    except Exception:
        # Extremely old fallback (should not be needed on 5.2)
        pass

    return ng


def add_group_socket(
    ng: bpy.types.GeometryNodeTree,
    name: str,
    in_out: str,
    socket_type: str,
    default: Any = None,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
) -> Any:
    """Add an interface socket and optionally set default / range."""
    sock = ng.interface.new_socket(name=name, in_out=in_out, socket_type=socket_type)
    if default is not None and hasattr(sock, "default_value"):
        try:
            sock.default_value = default
        except Exception:
            pass
    if min_value is not None and hasattr(sock, "min_value"):
        sock.min_value = min_value
    if max_value is not None and hasattr(sock, "max_value"):
        sock.max_value = max_value
    return sock


def find_socket_identifier(ng: bpy.types.GeometryNodeTree, name: str, in_out: str = "INPUT") -> str:
    """Resolve the RNA identifier for an interface socket by display name."""
    for item in ng.interface.items_tree:
        if getattr(item, "item_type", "SOCKET") != "SOCKET":
            continue
        if item.name == name and item.in_out == in_out:
            return item.identifier
    return name


def keyframe(obj: Any, data_path: str, frame: int, value: Any, index: int = -1) -> None:
    """Assign a value and insert a keyframe."""
    if index >= 0:
        parts = data_path.rsplit(".", 1)
        # Support paths like location[0]
        attr = getattr(obj, data_path) if not data_path.endswith("]") else None
        if attr is not None:
            attr[index] = value
        else:
            # Fallback for array props via eval-safe setattr pattern
            current = getattr(obj, data_path)
            current[index] = value
        obj.keyframe_insert(data_path=data_path, frame=frame, index=index)
    else:
        # Nested paths e.g. "energy"
        tokens = data_path.split(".")
        target = obj
        for t in tokens[:-1]:
            target = getattr(target, t)
        setattr(target, tokens[-1], value)
        obj.keyframe_insert(data_path=data_path, frame=frame)


# =============================================================================
# 1. SCENE SETUP
# =============================================================================

def setup_scene() -> dict[str, bpy.types.Collection]:
    """
    Reset / configure the scene for a cinematic storm render.
    Returns a dict of organizational collections.
    """
    _log("Setting up scene…")
    scene = bpy.context.scene

    # Clear previous storm objects (safe re-run)
    prefixes = (
        "STORM_",
        "Rain_",
        "Splash_",
        "Cloud_",
        "Puddle_",
        "Wind_",
        "Lightning_",
        "Ground_",
        "Atmos_",
        "Cam_",
    )
    for obj in list(bpy.data.objects):
        if any(obj.name.startswith(p) for p in prefixes):
            bpy.data.objects.remove(obj, do_unlink=True)

    for ng_name in list(bpy.data.node_groups.keys()):
        if ng_name.startswith("STORM_"):
            bpy.data.node_groups.remove(bpy.data.node_groups[ng_name])

    for mat in list(bpy.data.materials):
        if mat.name.startswith("STORM_"):
            bpy.data.materials.remove(mat)

    # Timeline
    scene.frame_start = FRAME_START
    scene.frame_end = FRAME_END
    scene.frame_current = FRAME_START
    scene.render.fps = FPS
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False

    # Color management — cinematic contrast
    scene.view_settings.view_transform = "AgX"
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        try:
            scene.view_settings.look = "Medium High Contrast"
        except TypeError:
            pass
    scene.view_settings.exposure = -0.35
    scene.view_settings.gamma = 1.0

    ensure_cycles_or_eevee(scene)

    # World gravity for particle physics
    scene.use_gravity = True
    scene.gravity = (0.0, 0.0, -9.81)

    # Units
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0

    # Collections
    root = get_or_create_collection("STORM_Root")
    collections = {
        "root": root,
        "clouds": get_or_create_collection("STORM_Clouds", root),
        "rain": get_or_create_collection("STORM_Rain", root),
        "splash": get_or_create_collection("STORM_Splash", root),
        "ground": get_or_create_collection("STORM_Ground", root),
        "lighting": get_or_create_collection("STORM_Lighting", root),
        "wind": get_or_create_collection("STORM_Wind", root),
        "camera": get_or_create_collection("STORM_Camera", root),
        "atmosphere": get_or_create_collection("STORM_Atmosphere", root),
    }

    # Camera — low cinematic angle looking into the storm
    cam_data = bpy.data.cameras.new("Cam_Storm_Data")
    cam_data.lens = 35.0
    cam_data.dof.use_dof = True
    cam_data.dof.aperture_fstop = 2.8
    cam_data.clip_start = 0.1
    cam_data.clip_end = 500.0
    cam = new_object("Cam_Storm", cam_data, collections["camera"])
    cam.location = (18.0, -28.0, 3.2)
    cam.rotation_euler = Euler((math.radians(82), 0.0, math.radians(28)), "XYZ")
    scene.camera = cam
    cam_data.dof.focus_distance = 22.0

    # Empty focus target for subtle camera drift later
    focus = new_object("Cam_Storm_Focus", None, collections["camera"])
    focus.location = (0.0, 0.0, 1.5)
    cam_data.dof.focus_object = focus

    _log("Scene setup complete.")
    return collections


# =============================================================================
# 8. MATERIALS AND SHADERS
# =============================================================================

def create_storm_cloud_material(name: str = "STORM_CloudVolume") -> bpy.types.Material:
    """
    Multi-layer volumetric cumulonimbus material.
    Dense, dark lower body with softer upper scattering and turbulent edges.
    """
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nodes = nt.nodes
    links = nt.links
    nodes.clear()

    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (900, 0)

    # Principled Volume — Blender's physically based volume shader
    vol = nodes.new("ShaderNodeVolumePrincipled")
    vol.location = (650, 0)
    vol.inputs["Color"].default_value = (0.12, 0.13, 0.16, 1.0)
    vol.inputs["Anisotropy"].default_value = 0.35
    if "Absorption Color" in vol.inputs:
        vol.inputs["Absorption Color"].default_value = (0.05, 0.055, 0.07, 1.0)

    # --- Density layering via procedural 3D noise ---
    tex_coord = nodes.new("ShaderNodeTexCoord")
    tex_coord.location = (-1100, 0)

    mapping = nodes.new("ShaderNodeMapping")
    mapping.location = (-900, 0)
    mapping.inputs["Scale"].default_value = (0.035, 0.035, 0.05)
    links.new(tex_coord.outputs["Object"], mapping.inputs["Vector"])

    # Large-scale cloud bodies
    noise_large = nodes.new("ShaderNodeTexNoise")
    noise_large.location = (-650, 200)
    noise_large.noise_dimensions = "3D"
    noise_large.inputs["Scale"].default_value = 1.8
    noise_large.inputs["Detail"].default_value = 12.0
    noise_large.inputs["Roughness"].default_value = 0.55
    if "Distortion" in noise_large.inputs:
        noise_large.inputs["Distortion"].default_value = 0.4
    links.new(mapping.outputs["Vector"], noise_large.inputs["Vector"])

    # Mid-scale turbulence
    noise_mid = nodes.new("ShaderNodeTexNoise")
    noise_mid.location = (-650, 0)
    noise_mid.noise_dimensions = "3D"
    noise_mid.inputs["Scale"].default_value = 4.5
    noise_mid.inputs["Detail"].default_value = 10.0
    noise_mid.inputs["Roughness"].default_value = 0.65
    links.new(mapping.outputs["Vector"], noise_mid.inputs["Vector"])

    # Fine edge breakup
    noise_fine = nodes.new("ShaderNodeTexNoise")
    noise_fine.location = (-650, -200)
    noise_fine.noise_dimensions = "3D"
    noise_fine.inputs["Scale"].default_value = 14.0
    noise_fine.inputs["Detail"].default_value = 6.0
    noise_fine.inputs["Roughness"].default_value = 0.75
    links.new(mapping.outputs["Vector"], noise_fine.inputs["Vector"])

    # Musgrave / Noise for billowing (Voronoi for cellular clumps)
    voronoi = nodes.new("ShaderNodeTexVoronoi")
    voronoi.location = (-650, -400)
    voronoi.voronoi_dimensions = "3D"
    voronoi.feature = "F1"
    voronoi.inputs["Scale"].default_value = 2.2
    links.new(mapping.outputs["Vector"], voronoi.inputs["Vector"])

    # Combine density layers
    mix_lm = nodes.new("ShaderNodeMix")
    mix_lm.data_type = "FLOAT"
    mix_lm.location = (-350, 120)
    mix_lm.inputs["Factor"].default_value = 0.45
    links.new(noise_large.outputs["Fac"], mix_lm.inputs["A"])
    links.new(noise_mid.outputs["Fac"], mix_lm.inputs["B"])

    mix_fine = nodes.new("ShaderNodeMix")
    mix_fine.data_type = "FLOAT"
    mix_fine.location = (-150, 80)
    mix_fine.inputs["Factor"].default_value = 0.25
    links.new(mix_lm.outputs["Result"], mix_fine.inputs["A"])
    links.new(noise_fine.outputs["Fac"], mix_fine.inputs["B"])

    # Invert voronoi slightly for denser cores
    vor_inv = nodes.new("ShaderNodeMath")
    vor_inv.operation = "SUBTRACT"
    vor_inv.location = (-350, -250)
    vor_inv.inputs[0].default_value = 1.0
    links.new(voronoi.outputs["Distance"], vor_inv.inputs[1])

    mix_vor = nodes.new("ShaderNodeMix")
    mix_vor.data_type = "FLOAT"
    mix_vor.location = (50, 40)
    mix_vor.inputs["Factor"].default_value = 0.3
    links.new(mix_fine.outputs["Result"], mix_vor.inputs["A"])
    links.new(vor_inv.outputs["Value"], mix_vor.inputs["B"])

    # Height-based density: denser bottoms, softer tops
    sep = nodes.new("ShaderNodeSeparateXYZ")
    sep.location = (-650, 450)
    links.new(tex_coord.outputs["Object"], sep.inputs["Vector"])

    # Remap Z (object space 0–1 across volume cube) to density bias
    height_ramp = nodes.new("ShaderNodeMapRange")
    height_ramp.location = (-350, 450)
    height_ramp.inputs["From Min"].default_value = -1.0
    height_ramp.inputs["From Max"].default_value = 1.0
    height_ramp.inputs["To Min"].default_value = 1.35   # denser at base
    height_ramp.inputs["To Max"].default_value = 0.35   # softer at top
    links.new(sep.outputs["Z"], height_ramp.inputs["Value"])

    density_mul = nodes.new("ShaderNodeMath")
    density_mul.operation = "MULTIPLY"
    density_mul.location = (250, 80)
    links.new(mix_vor.outputs["Result"], density_mul.inputs[0])
    links.new(height_ramp.outputs["Result"], density_mul.inputs[1])

    # Soft threshold for realistic cloud edges
    edge = nodes.new("ShaderNodeMapRange")
    edge.location = (450, 80)
    edge.clamp = True
    edge.inputs["From Min"].default_value = 0.28
    edge.inputs["From Max"].default_value = 0.72
    edge.inputs["To Min"].default_value = 0.0
    edge.inputs["To Max"].default_value = 4.5  # peak density
    links.new(density_mul.outputs["Value"], edge.inputs["Value"])

    links.new(edge.outputs["Result"], vol.inputs["Density"])

    # Color variation — cooler / darker in dense cores
    color_ramp = nodes.new("ShaderNodeValToRGB")
    color_ramp.location = (250, -200)
    color_ramp.color_ramp.elements[0].position = 0.15
    color_ramp.color_ramp.elements[0].color = (0.04, 0.045, 0.06, 1.0)
    color_ramp.color_ramp.elements[1].position = 0.85
    color_ramp.color_ramp.elements[1].color = (0.22, 0.24, 0.28, 1.0)
    links.new(mix_vor.outputs["Result"], color_ramp.inputs["Fac"])
    links.new(color_ramp.outputs["Color"], vol.inputs["Color"])

    links.new(vol.outputs["Volume"], out.inputs["Volume"])

    # Slight emission for distant atmospheric glow (very subtle)
    if "Emission Strength" in vol.inputs:
        vol.inputs["Emission Strength"].default_value = 0.02
        vol.inputs["Emission Color"].default_value = (0.35, 0.4, 0.5, 1.0)

    return mat


def create_rain_drop_material(name: str = "STORM_RainDrop") -> bpy.types.Material:
    """Transparent refractive raindrop / streak material with motion-friendly shading."""
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nodes = nt.nodes
    links = nt.links
    nodes.clear()

    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (400, 0)

    glass = nodes.new("ShaderNodeBsdfGlass")
    glass.location = (150, 0)
    glass.inputs["Color"].default_value = (0.75, 0.82, 0.9, 1.0)
    glass.inputs["Roughness"].default_value = 0.02
    glass.inputs["IOR"].default_value = 1.333

    # Mix with slight glossy for streak highlights under storm light
    glossy = nodes.new("ShaderNodeBsdfGlossy")
    glossy.location = (150, -200)
    glossy.inputs["Color"].default_value = (0.85, 0.9, 0.95, 1.0)
    glossy.inputs["Roughness"].default_value = 0.05

    mix = nodes.new("ShaderNodeMixShader")
    mix.location = (280, -50)
    mix.inputs["Fac"].default_value = 0.15
    links.new(glass.outputs["BSDF"], mix.inputs[1])
    links.new(glossy.outputs["BSDF"], mix.inputs[2])
    links.new(mix.outputs["Shader"], out.inputs["Surface"])

    mat.blend_method = "HASHED" if hasattr(mat, "blend_method") else mat.blend_method
    if hasattr(mat, "shadow_method"):
        mat.shadow_method = "NONE"  # rain shadows are too costly / invisible at scale
    if hasattr(mat, "use_screen_refraction"):
        mat.use_screen_refraction = True

    return mat


def create_splash_material(name: str = "STORM_Splash") -> bpy.types.Material:
    """Small splash droplet material."""
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nodes = nt.nodes
    links = nt.links
    nodes.clear()

    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (300, 0)
    glass = nodes.new("ShaderNodeBsdfGlass")
    glass.location = (100, 0)
    glass.inputs["Color"].default_value = (0.8, 0.88, 0.95, 1.0)
    glass.inputs["Roughness"].default_value = 0.04
    glass.inputs["IOR"].default_value = 1.333
    links.new(glass.outputs["BSDF"], out.inputs["Surface"])
    return mat


def create_wet_ground_material(
    name: str = "STORM_WetGround",
    puddle_coverage: float = PUDDLE_COVERAGE,
    puddle_depth: float = PUDDLE_DEPTH,
) -> bpy.types.Material:
    """
    Physically based wet asphalt / concrete with procedural puddle masks,
    roughness variation, reflections, and water accumulation zones.
    """
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nodes = nt.nodes
    links = nt.links
    nodes.clear()

    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (1200, 0)

    # Base wet ground
    ground = nodes.new("ShaderNodeBsdfPrincipled")
    ground.name = "GroundBSDF"
    ground.location = (700, 200)
    ground.inputs["Base Color"].default_value = (0.045, 0.045, 0.05, 1.0)
    ground.inputs["Roughness"].default_value = 0.35
    if "Specular IOR Level" in ground.inputs:
        ground.inputs["Specular IOR Level"].default_value = 0.55
    if "Specular" in ground.inputs:
        ground.inputs["Specular"].default_value = 0.55

    # Water / puddle BSDF — mirror-like with slight absorption tint
    water = nodes.new("ShaderNodeBsdfPrincipled")
    water.name = "PuddleBSDF"
    water.location = (700, -250)
    water.inputs["Base Color"].default_value = (0.02, 0.03, 0.04, 1.0)
    water.inputs["Roughness"].default_value = 0.02
    water.inputs["Metallic"].default_value = 0.0
    if "Transmission Weight" in water.inputs:
        water.inputs["Transmission Weight"].default_value = 0.85
    elif "Transmission" in water.inputs:
        water.inputs["Transmission"].default_value = 0.85
    water.inputs["IOR"].default_value = 1.333
    if "Coat Weight" in water.inputs:
        water.inputs["Coat Weight"].default_value = 1.0
        water.inputs["Coat Roughness"].default_value = 0.03
    if "Specular IOR Level" in water.inputs:
        water.inputs["Specular IOR Level"].default_value = 1.0

    # --- Procedural puddle mask ---
    tex_coord = nodes.new("ShaderNodeTexCoord")
    tex_coord.location = (-1000, 0)

    mapping = nodes.new("ShaderNodeMapping")
    mapping.location = (-800, 0)
    mapping.inputs["Scale"].default_value = (0.15, 0.15, 0.15)
    links.new(tex_coord.outputs["Object"], mapping.inputs["Vector"])

    # Large puddle basins
    noise_puddle = nodes.new("ShaderNodeTexNoise")
    noise_puddle.location = (-550, 100)
    noise_puddle.noise_dimensions = "2D"
    noise_puddle.inputs["Scale"].default_value = 3.5
    noise_puddle.inputs["Detail"].default_value = 8.0
    noise_puddle.inputs["Roughness"].default_value = 0.45
    links.new(mapping.outputs["Vector"], noise_puddle.inputs["Vector"])

    # Secondary breakup for irregular edges
    noise_edge = nodes.new("ShaderNodeTexNoise")
    noise_edge.location = (-550, -120)
    noise_edge.noise_dimensions = "2D"
    noise_edge.inputs["Scale"].default_value = 9.0
    noise_edge.inputs["Detail"].default_value = 6.0
    links.new(mapping.outputs["Vector"], noise_edge.inputs["Vector"])

    mix_noise = nodes.new("ShaderNodeMix")
    mix_noise.data_type = "FLOAT"
    mix_noise.location = (-300, 0)
    mix_noise.inputs["Factor"].default_value = 0.3
    links.new(noise_puddle.outputs["Fac"], mix_noise.inputs["A"])
    links.new(noise_edge.outputs["Fac"], mix_noise.inputs["B"])

    # Coverage threshold — PUDDLE_COVERAGE controls how much ground is wet water
    # Higher coverage → lower threshold
    threshold = 1.0 - max(0.05, min(0.95, puddle_coverage))
    puddle_ramp = nodes.new("ShaderNodeMapRange")
    puddle_ramp.location = (-80, 0)
    puddle_ramp.clamp = True
    puddle_ramp.inputs["From Min"].default_value = threshold * 0.85
    puddle_ramp.inputs["From Max"].default_value = threshold * 0.85 + 0.12
    puddle_ramp.inputs["To Min"].default_value = 0.0
    puddle_ramp.inputs["To Max"].default_value = 1.0
    links.new(mix_noise.outputs["Result"], puddle_ramp.inputs["Value"])

    # Store coverage as a value node for easy re-tweak / animation
    coverage_val = nodes.new("ShaderNodeValue")
    coverage_val.name = "PuddleCoverage"
    coverage_val.label = "Puddle Coverage"
    coverage_val.location = (-300, 220)
    coverage_val.outputs[0].default_value = puddle_coverage

    depth_val = nodes.new("ShaderNodeValue")
    depth_val.name = "PuddleDepth"
    depth_val.label = "Puddle Depth"
    depth_val.location = (-300, 320)
    depth_val.outputs[0].default_value = puddle_depth

    # Depth modulates water roughness / wet blend strength
    depth_influence = nodes.new("ShaderNodeMath")
    depth_influence.operation = "MULTIPLY"
    depth_influence.location = (120, -50)
    links.new(puddle_ramp.outputs["Result"], depth_influence.inputs[0])
    links.new(depth_val.outputs[0], depth_influence.inputs[1])

    # Ground albedo variation (asphalt grit)
    noise_alb = nodes.new("ShaderNodeTexNoise")
    noise_alb.location = (-550, 350)
    noise_alb.inputs["Scale"].default_value = 40.0
    noise_alb.inputs["Detail"].default_value = 12.0
    links.new(mapping.outputs["Vector"], noise_alb.inputs["Vector"])

    alb_ramp = nodes.new("ShaderNodeValToRGB")
    alb_ramp.location = (-300, 400)
    alb_ramp.color_ramp.elements[0].color = (0.025, 0.025, 0.028, 1.0)
    alb_ramp.color_ramp.elements[1].color = (0.08, 0.078, 0.075, 1.0)
    links.new(noise_alb.outputs["Fac"], alb_ramp.inputs["Fac"])
    links.new(alb_ramp.outputs["Color"], ground.inputs["Base Color"])

    # Wet ground roughness: generally glossy, drier grit in high spots
    rough_map = nodes.new("ShaderNodeMapRange")
    rough_map.location = (120, 250)
    rough_map.inputs["From Min"].default_value = 0.0
    rough_map.inputs["From Max"].default_value = 1.0
    rough_map.inputs["To Min"].default_value = 0.55   # dry grit
    rough_map.inputs["To Max"].default_value = 0.12   # wet sheen
    links.new(noise_alb.outputs["Fac"], rough_map.inputs["Value"])

    # Areas near puddles get wetter (lower roughness)
    wet_mix = nodes.new("ShaderNodeMix")
    wet_mix.data_type = "FLOAT"
    wet_mix.location = (350, 200)
    links.new(depth_influence.outputs["Value"], wet_mix.inputs["Factor"])
    links.new(rough_map.outputs["Result"], wet_mix.inputs["A"])
    wet_mix.inputs["B"].default_value = 0.08
    links.new(wet_mix.outputs["Result"], ground.inputs["Roughness"])

    # Mix ground ↔ water using puddle mask
    mix_shader = nodes.new("ShaderNodeMixShader")
    mix_shader.location = (950, 0)
    links.new(depth_influence.outputs["Value"], mix_shader.inputs["Fac"])
    links.new(ground.outputs["BSDF"], mix_shader.inputs[1])
    links.new(water.outputs["BSDF"], mix_shader.inputs[2])
    links.new(mix_shader.outputs["Shader"], out.inputs["Surface"])

    # Subtle displacement for surface grit (optional bump)
    bump = nodes.new("ShaderNodeBump")
    bump.location = (350, 50)
    bump.inputs["Strength"].default_value = 0.08
    bump.inputs["Distance"].default_value = 0.02
    links.new(noise_alb.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], ground.inputs["Normal"])

    # Ripple normal on puddles (animated later via Mapping location)
    wave = nodes.new("ShaderNodeTexWave")
    wave.name = "PuddleRipples"
    wave.location = (-550, -350)
    wave.bands_direction = "DIAGONAL"
    wave.wave_profile = "SIN"
    wave.inputs["Scale"].default_value = 55.0
    wave.inputs["Distortion"].default_value = 4.0
    wave.inputs["Detail"].default_value = 3.0
    links.new(mapping.outputs["Vector"], wave.inputs["Vector"])

    ripple_bump = nodes.new("ShaderNodeBump")
    ripple_bump.location = (350, -250)
    ripple_bump.inputs["Strength"].default_value = 0.15 * puddle_depth
    ripple_bump.inputs["Distance"].default_value = 0.01
    links.new(wave.outputs["Fac"], ripple_bump.inputs["Height"])
    links.new(ripple_bump.outputs["Normal"], water.inputs["Normal"])

    return mat


def create_atmosphere_material(name: str = "STORM_AtmosphereFog") -> bpy.types.Material:
    """Thin volumetric fog for atmospheric depth and light shafts."""
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nodes = nt.nodes
    links = nt.links
    nodes.clear()

    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (400, 0)
    vol = nodes.new("ShaderNodeVolumePrincipled")
    vol.location = (150, 0)
    vol.inputs["Density"].default_value = 0.012
    vol.inputs["Color"].default_value = (0.35, 0.38, 0.42, 1.0)
    vol.inputs["Anisotropy"].default_value = 0.2
    links.new(vol.outputs["Volume"], out.inputs["Volume"])
    return mat


def create_world_storm_shader() -> None:
    """Overcast storm world with cool sky gradient and subtle horizon glow."""
    world = bpy.context.scene.world
    if world is None:
        world = bpy.data.worlds.new("STORM_World")
        bpy.context.scene.world = world
    else:
        world.name = "STORM_World"

    world.use_nodes = True
    nt = world.node_tree
    nodes = nt.nodes
    links = nt.links
    nodes.clear()

    out = nodes.new("ShaderNodeOutputWorld")
    out.location = (600, 0)

    bg = nodes.new("ShaderNodeBackground")
    bg.location = (350, 0)
    bg.inputs["Strength"].default_value = 0.45

    # Sky-like gradient via Nishita if available, else procedural
    try:
        sky = nodes.new("ShaderNodeTexSky")
        sky.location = (50, 100)
        sky.sky_type = "NISHITA"
        sky.sun_elevation = math.radians(8)
        sky.sun_rotation = math.radians(40)
        sky.altitude = 100.0
        sky.air_density = 2.5
        sky.dust_density = 4.0
        sky.ozone_density = 1.0
        links.new(sky.outputs["Color"], bg.inputs["Color"])
    except Exception:
        # Fallback gradient
        tex_coord = nodes.new("ShaderNodeTexCoord")
        tex_coord.location = (-400, 0)
        sep = nodes.new("ShaderNodeSeparateXYZ")
        sep.location = (-200, 0)
        links.new(tex_coord.outputs["Generated"], sep.inputs["Vector"])
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.location = (50, 0)
        ramp.color_ramp.elements[0].color = (0.02, 0.025, 0.035, 1.0)
        ramp.color_ramp.elements[1].color = (0.12, 0.14, 0.18, 1.0)
        links.new(sep.outputs["Z"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], bg.inputs["Color"])

    links.new(bg.outputs["Background"], out.inputs["Surface"])

    # Optional world volume mist (kept light — scene fog cube handles local mist)
    if hasattr(world, "use_nodes"):
        pass


# =============================================================================
# 2. CLOUD SYSTEM
# =============================================================================

def create_cloud_system(collections: dict) -> list[bpy.types.Object]:
    """
    Generate large volumetric storm cloud formations using volume cubes
    and procedural density shaders. Multiple overlapping domains create
    depth and turbulent cumulonimbus structure.
    """
    _log("Creating volumetric storm cloud system…")
    col = collections["clouds"]
    mat = create_storm_cloud_material()
    clouds: list[bpy.types.Object] = []

    # Multiple large cloud slabs / mounds for layered storm banks
    cloud_specs = [
        # name, location, scale
        ("Cloud_Core_Main",      (0.0, 5.0, CLOUD_ALTITUDE + 10),  (70, 55, CLOUD_THICKNESS)),
        ("Cloud_Bank_Left",      (-45.0, 10.0, CLOUD_ALTITUDE + 5), (40, 50, 40)),
        ("Cloud_Bank_Right",     (50.0, 0.0, CLOUD_ALTITUDE + 8),   (45, 48, 42)),
        ("Cloud_Anvil_Upper",    (5.0, 15.0, CLOUD_ALTITUDE + 38),  (90, 70, 28)),
        ("Cloud_Shelf_Front",    (0.0, -25.0, CLOUD_ALTITUDE - 5),  (60, 35, 25)),
        ("Cloud_Cell_Distant",   (-20.0, 55.0, CLOUD_ALTITUDE + 15),(55, 45, 45)),
    ]

    for name, loc, scale in cloud_specs:
        mesh = bpy.data.meshes.new(f"{name}_Mesh")
        # Unit cube — scaled via object transforms for volume bounds
        verts = [
            (-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
            (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1),
        ]
        faces = [
            (0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
            (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7),
        ]
        mesh.from_pydata(verts, [], faces)
        mesh.update()

        obj = new_object(name, mesh, col)
        obj.location = loc
        obj.scale = scale
        obj.display_type = "WIRE"
        obj.hide_render = False

        # Assign volume material
        if obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)

        # Cycles / EEVEE volume object settings
        obj.is_shadow_catcher = False
        if hasattr(obj, "cycles_visibility"):
            obj.visible_camera = True
            obj.visible_shadow = True
            obj.visible_volume_scatter = True

        clouds.append(obj)

    # Secondary denser "core" volumes with slightly different material instance
    core_mat = create_storm_cloud_material("STORM_CloudVolume_Dense")
    # Boost density via node tweak
    try:
        edge = core_mat.node_tree.nodes.get("Map Range") or [
            n for n in core_mat.node_tree.nodes if n.type == "MAP_RANGE"
        ][-1]
        edge.inputs["To Max"].default_value = 7.0
        vol = [n for n in core_mat.node_tree.nodes if n.type == "PRINCIPLED_VOLUME"][0]
        vol.inputs["Color"].default_value = (0.07, 0.075, 0.09, 1.0)
    except Exception:
        pass

    dense = bpy.data.meshes.new("Cloud_DenseCore_Mesh")
    dense.from_pydata(
        [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
         (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)],
        [],
        [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
         (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)],
    )
    dense.update()
    dense_obj = new_object("Cloud_DenseCore", dense, col)
    dense_obj.location = (8.0, 8.0, CLOUD_ALTITUDE)
    dense_obj.scale = (35, 30, 30)
    dense_obj.display_type = "WIRE"
    dense_obj.data.materials.append(core_mat)
    clouds.append(dense_obj)

    _log(f"Created {len(clouds)} volumetric cloud domains.")
    return clouds


# =============================================================================
# 3. RAIN SYSTEM (Geometry Nodes instancing — millions of drops)
# =============================================================================

def _create_raindrop_mesh(name: str = "Rain_DropMesh") -> bpy.types.Object:
    """Create an elongated teardrop-ish mesh for rain instancing."""
    col = bpy.context.scene.collection
    # UV sphere stretched into a streak-friendly capsule
    mesh = bpy.data.meshes.new(name)
    # Simple icosphere-like low-poly drop (octahedron extruded) for performance
    # Using a stretched UV sphere via bmesh-free primitives through ops
    bpy.ops.mesh.primitive_uv_sphere_add(segments=8, ring_count=6, radius=1.0, location=(0, 0, -1000))
    tmp = bpy.context.active_object
    tmp.name = name
    tmp.scale = (0.35, 0.35, 1.8)  # elongated along Z (fall direction)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    # Move to origin
    tmp.location = (0.0, 0.0, 0.0)
    mat = create_rain_drop_material()
    if tmp.data.materials:
        tmp.data.materials[0] = mat
    else:
        tmp.data.materials.append(mat)

    # Hide original — only instances render meaningfully
    tmp.hide_render = True
    tmp.hide_viewport = True
    return tmp


def _math_fract(nodes, location=(0, 0)):
    """Create a Math node configured for fractional part (looping phases)."""
    node = nodes.new("ShaderNodeMath")
    node.location = location
    try:
        node.operation = "FRACT"
    except TypeError:
        node.operation = "MODULO"
        node.inputs[1].default_value = 1.0
    return node


def _new_align_rotation_node(nodes, location=(0, 0)):
    """Create Align Rotation to Vector (Blender 4+/5), with Euler fallback."""
    try:
        align = nodes.new("FunctionNodeAlignRotationToVector")
    except RuntimeError:
        align = nodes.new("FunctionNodeAlignEulerToVector")
    align.location = location
    if hasattr(align, "axis"):
        align.axis = "Z"
    return align


def _set_random_float_range(node, min_v: float, max_v: float) -> None:
    """Set Min/Max on a Random Value node across Blender socket layouts."""
    if "Min" in node.inputs:
        node.inputs["Min"].default_value = min_v
        node.inputs["Max"].default_value = max_v
    else:
        # Older positional sockets for FLOAT mode
        try:
            node.inputs[2].default_value = min_v
            node.inputs[3].default_value = max_v
        except (TypeError, IndexError):
            pass


def create_rain_geometry_nodes(
    intensity: float = RAIN_INTENSITY,
    drop_min: float = DROP_SIZE_MIN,
    drop_max: float = DROP_SIZE_MAX,
    wind_strength: float = WIND_STRENGTH,
) -> bpy.types.GeometryNodeTree:
    """
    Build a high-performance Geometry Nodes rain system:
    distribute points on a sky grid → instance elongated drops → animate
    continuous fall with wind tilt via Scene Time (fractional looping).
    """
    ng = new_geometry_node_group("STORM_RainGN")

    add_group_socket(ng, "Count", "INPUT", "NodeSocketInt",
                     default=int(RAIN_BASE_COUNT * intensity), min_value=100, max_value=5_000_000)
    add_group_socket(ng, "Area Size", "INPUT", "NodeSocketFloat",
                     default=GROUND_SIZE, min_value=1.0, max_value=500.0)
    add_group_socket(ng, "Height", "INPUT", "NodeSocketFloat",
                     default=RAIN_VOLUME_HEIGHT, min_value=1.0, max_value=200.0)
    add_group_socket(ng, "Drop Min", "INPUT", "NodeSocketFloat",
                     default=drop_min, min_value=0.001, max_value=1.0)
    add_group_socket(ng, "Drop Max", "INPUT", "NodeSocketFloat",
                     default=drop_max, min_value=0.001, max_value=1.0)
    add_group_socket(ng, "Fall Speed", "INPUT", "NodeSocketFloat",
                     default=18.0, min_value=0.1, max_value=100.0)
    add_group_socket(ng, "Wind", "INPUT", "NodeSocketFloat",
                     default=wind_strength, min_value=0.0, max_value=50.0)
    add_group_socket(ng, "Seed", "INPUT", "NodeSocketInt",
                     default=42, min_value=0, max_value=999999)

    nodes = ng.nodes
    links = ng.links

    n_in = nodes.new("NodeGroupInput")
    n_in.location = (-1400, 0)
    n_out = nodes.new("NodeGroupOutput")
    n_out.location = (1600, 0)

    # Horizontal emission grid (sky plane) — classic cinematic rain setup
    grid = nodes.new("GeometryNodeMeshGrid")
    grid.location = (-1100, 200)
    grid.inputs["Vertices X"].default_value = 2
    grid.inputs["Vertices Y"].default_value = 2
    links.new(n_in.outputs["Area Size"], grid.inputs["Size X"])
    links.new(n_in.outputs["Area Size"], grid.inputs["Size Y"])

    # Lift grid to top of rain volume
    half_h = nodes.new("ShaderNodeMath")
    half_h.operation = "MULTIPLY"
    half_h.location = (-1100, 40)
    half_h.inputs[1].default_value = 0.5
    links.new(n_in.outputs["Height"], half_h.inputs[0])

    top_offset = nodes.new("ShaderNodeCombineXYZ")
    top_offset.location = (-900, 40)
    links.new(half_h.outputs["Value"], top_offset.inputs["Z"])

    set_top = nodes.new("GeometryNodeSetPosition")
    set_top.location = (-900, 200)
    links.new(grid.outputs["Mesh"], set_top.inputs["Geometry"])
    links.new(top_offset.outputs["Vector"], set_top.inputs["Offset"])

    dist = nodes.new("GeometryNodeDistributePointsOnFaces")
    dist.location = (-650, 200)
    dist.distribute_method = "RANDOM"
    links.new(set_top.outputs["Geometry"], dist.inputs["Mesh"])
    links.new(n_in.outputs["Seed"], dist.inputs["Seed"])

    # density = count / area²
    area_sq = nodes.new("ShaderNodeMath")
    area_sq.operation = "MULTIPLY"
    area_sq.location = (-1100, -120)
    links.new(n_in.outputs["Area Size"], area_sq.inputs[0])
    links.new(n_in.outputs["Area Size"], area_sq.inputs[1])

    dens = nodes.new("ShaderNodeMath")
    dens.operation = "DIVIDE"
    dens.location = (-900, -80)
    links.new(n_in.outputs["Count"], dens.inputs[0])
    links.new(area_sq.outputs["Value"], dens.inputs[1])
    links.new(dens.outputs["Value"], dist.inputs["Density"])

    index = nodes.new("GeometryNodeInputIndex")
    index.location = (-650, -200)

    # --- Continuous fall via Scene Time + fractional phase ---
    scene_time = nodes.new("GeometryNodeInputSceneTime")
    scene_time.location = (-650, -350)

    rand_phase = nodes.new("FunctionNodeRandomValue")
    rand_phase.data_type = "FLOAT"
    rand_phase.location = (-400, -400)
    _set_random_float_range(rand_phase, 0.0, 1.0)
    seed2 = nodes.new("ShaderNodeMath")
    seed2.operation = "ADD"
    seed2.location = (-550, -500)
    seed2.inputs[1].default_value = 17.0
    links.new(n_in.outputs["Seed"], seed2.inputs[0])
    links.new(seed2.outputs["Value"], rand_phase.inputs["Seed"])
    links.new(index.outputs["Index"], rand_phase.inputs["ID"])

    speed_div = nodes.new("ShaderNodeMath")
    speed_div.operation = "DIVIDE"
    speed_div.location = (-400, -250)
    links.new(n_in.outputs["Fall Speed"], speed_div.inputs[0])
    links.new(n_in.outputs["Height"], speed_div.inputs[1])

    time_mul = nodes.new("ShaderNodeMath")
    time_mul.operation = "MULTIPLY"
    time_mul.location = (-200, -280)
    links.new(scene_time.outputs["Seconds"], time_mul.inputs[0])
    links.new(speed_div.outputs["Value"], time_mul.inputs[1])

    phase_add = nodes.new("ShaderNodeMath")
    phase_add.operation = "ADD"
    phase_add.location = (0, -320)
    links.new(time_mul.outputs["Value"], phase_add.inputs[0])
    links.new(rand_phase.outputs["Value"], phase_add.inputs[1])

    fraction = _math_fract(nodes, (200, -320))
    links.new(phase_add.outputs["Value"], fraction.inputs[0])

    # Speed variation per drop
    speed_var = nodes.new("FunctionNodeRandomValue")
    speed_var.data_type = "FLOAT"
    speed_var.location = (200, -500)
    _set_random_float_range(speed_var, 0.7, 1.35)
    seed3 = nodes.new("ShaderNodeMath")
    seed3.operation = "ADD"
    seed3.inputs[1].default_value = 91.0
    seed3.location = (0, -500)
    links.new(n_in.outputs["Seed"], seed3.inputs[0])
    links.new(seed3.outputs["Value"], speed_var.inputs["Seed"])
    links.new(index.outputs["Index"], speed_var.inputs["ID"])

    # Z = -fraction * height * speed_var  (from sky toward ground)
    z_travel = nodes.new("ShaderNodeMath")
    z_travel.operation = "MULTIPLY"
    z_travel.location = (400, -280)
    links.new(fraction.outputs["Value"], z_travel.inputs[0])
    links.new(n_in.outputs["Height"], z_travel.inputs[1])

    z_var = nodes.new("ShaderNodeMath")
    z_var.operation = "MULTIPLY"
    z_var.location = (600, -280)
    links.new(z_travel.outputs["Value"], z_var.inputs[0])
    links.new(speed_var.outputs["Value"], z_var.inputs[1])

    z_neg = nodes.new("ShaderNodeMath")
    z_neg.operation = "MULTIPLY"
    z_neg.location = (800, -280)
    z_neg.inputs[1].default_value = -1.0
    links.new(z_var.outputs["Value"], z_neg.inputs[0])

    # Wind drift grows with fall progress
    wind_amt = nodes.new("ShaderNodeMath")
    wind_amt.operation = "MULTIPLY"
    wind_amt.location = (400, -420)
    links.new(fraction.outputs["Value"], wind_amt.inputs[0])
    links.new(n_in.outputs["Wind"], wind_amt.inputs[1])

    wind_y = nodes.new("ShaderNodeMath")
    wind_y.operation = "MULTIPLY"
    wind_y.location = (600, -450)
    wind_y.inputs[1].default_value = 0.28
    links.new(wind_amt.outputs["Value"], wind_y.inputs[0])

    fall_vec = nodes.new("ShaderNodeCombineXYZ")
    fall_vec.location = (1000, -300)
    links.new(wind_amt.outputs["Value"], fall_vec.inputs["X"])
    links.new(wind_y.outputs["Value"], fall_vec.inputs["Y"])
    links.new(z_neg.outputs["Value"], fall_vec.inputs["Z"])

    set_fall = nodes.new("GeometryNodeSetPosition")
    set_fall.location = (-200, 200)
    links.new(dist.outputs["Points"], set_fall.inputs["Geometry"])
    links.new(fall_vec.outputs["Vector"], set_fall.inputs["Offset"])

    # --- Instance raindrops ---
    obj_info = nodes.new("GeometryNodeObjectInfo")
    obj_info.name = "RainDropObjectInfo"
    obj_info.location = (0, 40)
    obj_info.transform_space = "RELATIVE"

    rand_scale = nodes.new("FunctionNodeRandomValue")
    rand_scale.data_type = "FLOAT"
    rand_scale.location = (0, -80)
    links.new(
        n_in.outputs["Drop Min"],
        rand_scale.inputs["Min"] if "Min" in rand_scale.inputs else rand_scale.inputs[2],
    )
    links.new(
        n_in.outputs["Drop Max"],
        rand_scale.inputs["Max"] if "Max" in rand_scale.inputs else rand_scale.inputs[3],
    )
    seed4 = nodes.new("ShaderNodeMath")
    seed4.operation = "ADD"
    seed4.inputs[1].default_value = 5.0
    seed4.location = (-200, -80)
    links.new(n_in.outputs["Seed"], seed4.inputs[0])
    links.new(seed4.outputs["Value"], rand_scale.inputs["Seed"])
    links.new(index.outputs["Index"], rand_scale.inputs["ID"])

    # Align drop long axis to velocity (wind-tilted fall)
    align = _new_align_rotation_node(nodes, (200, -40))
    align.name = "RainAlign"

    vel = nodes.new("ShaderNodeCombineXYZ")
    vel.location = (0, 160)
    links.new(n_in.outputs["Wind"], vel.inputs["X"])
    wind_y2 = nodes.new("ShaderNodeMath")
    wind_y2.operation = "MULTIPLY"
    wind_y2.inputs[1].default_value = 0.28
    wind_y2.location = (-200, 180)
    links.new(n_in.outputs["Wind"], wind_y2.inputs[0])
    links.new(wind_y2.outputs["Value"], vel.inputs["Y"])
    fall_neg = nodes.new("ShaderNodeMath")
    fall_neg.operation = "MULTIPLY"
    fall_neg.inputs[1].default_value = -1.0
    fall_neg.location = (-200, 100)
    links.new(n_in.outputs["Fall Speed"], fall_neg.inputs[0])
    links.new(fall_neg.outputs["Value"], vel.inputs["Z"])
    links.new(vel.outputs["Vector"], align.inputs["Vector"])

    instance = nodes.new("GeometryNodeInstanceOnPoints")
    instance.location = (450, 180)
    links.new(set_fall.outputs["Geometry"], instance.inputs["Points"])
    links.new(obj_info.outputs["Geometry"], instance.inputs["Instance"])
    links.new(rand_scale.outputs["Value"], instance.inputs["Scale"])
    if "Rotation" in instance.inputs:
        links.new(align.outputs["Rotation"], instance.inputs["Rotation"])

    # Keep instances unrealized for performance (millions of drops)
    links.new(instance.outputs["Instances"], n_out.inputs["Geometry"])

    return ng


def create_rain_system(collections: dict) -> dict[str, Any]:
    """
    Create the rain emitter object with Geometry Nodes instancing and
    a secondary classic particle layer for near-camera streak density.
    """
    _log("Creating rainfall system…")
    col = collections["rain"]

    # Drop prototype
    drop = _create_raindrop_mesh("Rain_DropPrototype")
    link_object(drop, col)
    drop.hide_viewport = True
    drop.hide_render = True
    drop.hide_set(True)

    # Rain domain host — GN replaces mesh; keep at world origin
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 0.0))
    rain_obj = bpy.context.active_object
    rain_obj.name = "Rain_System"
    link_object(rain_obj, col)

    # Hide host mesh surface — GN replaces geometry
    rain_mat_hide = bpy.data.materials.new("STORM_RainHostInvisible")
    rain_mat_hide.use_nodes = True
    n = rain_mat_hide.node_tree.nodes
    n.clear()
    # No surface output → invisible host if GN fails partially
    out = n.new("ShaderNodeOutputMaterial")
    rain_obj.data.materials.append(rain_mat_hide)

    ng = create_rain_geometry_nodes(
        intensity=RAIN_INTENSITY,
        drop_min=DROP_SIZE_MIN,
        drop_max=DROP_SIZE_MAX,
        wind_strength=WIND_STRENGTH,
    )

    mod = rain_obj.modifiers.new(name="STORM_RainNodes", type="NODES")
    mod.node_group = ng

    # Wire drop object into Object Info node
    obj_info = ng.nodes.get("RainDropObjectInfo")
    if obj_info is not None:
        obj_info.inputs["Object"].default_value = drop

    # Set modifier inputs (5.2 + fallback)
    count = int(RAIN_BASE_COUNT * max(0.05, RAIN_INTENSITY))
    id_count = find_socket_identifier(ng, "Count")
    id_wind = find_socket_identifier(ng, "Wind")
    id_dmin = find_socket_identifier(ng, "Drop Min")
    id_dmax = find_socket_identifier(ng, "Drop Max")
    set_gn_modifier_input(mod, id_count, count)
    set_gn_modifier_input(mod, id_wind, WIND_STRENGTH)
    set_gn_modifier_input(mod, id_dmin, DROP_SIZE_MIN)
    set_gn_modifier_input(mod, id_dmax, DROP_SIZE_MAX)

    # --- Secondary near-camera particle streak layer ---
    bpy.ops.mesh.primitive_plane_add(
        size=GROUND_SIZE * 0.7,
        location=(5.0, -10.0, RAIN_VOLUME_HEIGHT * 0.85),
    )
    streak_emitter = bpy.context.active_object
    streak_emitter.name = "Rain_StreakEmitter"
    link_object(streak_emitter, col)
    streak_emitter.rotation_euler = (0, 0, 0)
    streak_emitter.hide_render = True

    set_active(streak_emitter)
    psys_mod = streak_emitter.modifiers.new(name="RainStreaks", type="PARTICLE_SYSTEM")
    psys = streak_emitter.particle_systems[-1]
    psys.name = "Rain_Streaks"
    settings = psys.settings
    settings.name = "STORM_RainStreakSettings"
    settings.type = "EMITTER"
    settings.count = int(15_000 * RAIN_INTENSITY)
    settings.frame_start = FRAME_START
    settings.frame_end = FRAME_END
    settings.lifetime = 28
    settings.lifetime_random = 0.4
    settings.emit_from = "FACE"
    settings.normal_factor = 0.0
    settings.factor_gravity = 1.15
    settings.brownian_factor = 0.05
    settings.damping = 0.02
    settings.particle_size = (DROP_SIZE_MIN + DROP_SIZE_MAX) * 0.5
    settings.size_random = 0.5
    settings.render_type = "OBJECT"
    settings.instance_object = drop
    settings.use_scale_instance = True
    settings.use_rotations = True
    settings.rotation_mode = "VEL"
    # Wind influence
    settings.effector_weights.wind = 1.0
    settings.effector_weights.gravity = 1.0
    settings.effector_weights.turbulence = 0.8

    # Layered density: third distant sheet
    bpy.ops.mesh.primitive_plane_add(
        size=GROUND_SIZE,
        location=(-5.0, 20.0, RAIN_VOLUME_HEIGHT * 0.9),
    )
    distant = bpy.context.active_object
    distant.name = "Rain_DistantEmitter"
    link_object(distant, col)
    distant.hide_render = True
    set_active(distant)
    distant.modifiers.new(name="RainDistant", type="PARTICLE_SYSTEM")
    psys2 = distant.particle_systems[-1]
    psys2.name = "Rain_Distant"
    s2 = psys2.settings
    s2.name = "STORM_RainDistantSettings"
    s2.type = "EMITTER"
    s2.count = int(40_000 * RAIN_INTENSITY)
    s2.frame_start = FRAME_START
    s2.frame_end = FRAME_END
    s2.lifetime = 40
    s2.lifetime_random = 0.5
    s2.factor_gravity = 1.2
    s2.particle_size = DROP_SIZE_MIN * 0.8
    s2.size_random = 0.6
    s2.render_type = "OBJECT"
    s2.instance_object = drop
    s2.use_scale_instance = True
    s2.use_rotations = True
    s2.rotation_mode = "VEL"
    s2.effector_weights.wind = 1.0
    s2.effector_weights.turbulence = 1.0

    _log(f"Rain system ready — GN instances≈{count:,} + particle layers.")
    return {
        "rain_object": rain_obj,
        "drop_prototype": drop,
        "modifier": mod,
        "node_group": ng,
        "streak_emitter": streak_emitter,
        "distant_emitter": distant,
    }


# =============================================================================
# 4. SPLASH SYSTEM
# =============================================================================

def _create_splash_crown_mesh(name: str = "Splash_CrownMesh") -> bpy.types.Object:
    """Low-poly crown / ring mesh for splash instancing."""
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=12,
        radius=1.0,
        depth=0.15,
        location=(0, 0, -2000),
        end_fill_type="NOTHING",
    )
    crown = bpy.context.active_object
    crown.name = name
    # Taper top via proportional scale on upper ring — simple squash
    crown.scale = (1.0, 1.0, 2.5)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    mat = create_splash_material()
    if crown.data.materials:
        crown.data.materials[0] = mat
    else:
        crown.data.materials.append(mat)
    crown.hide_render = True
    crown.hide_viewport = True
    return crown


def _create_splash_droplet_mesh(name: str = "Splash_DropletMesh") -> bpy.types.Object:
    """Tiny sphere for bouncing splash droplets."""
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=1.0, location=(0, 0, -2100))
    drop = bpy.context.active_object
    drop.name = name
    mat = create_splash_material("STORM_SplashDroplet")
    if drop.data.materials:
        drop.data.materials[0] = mat
    else:
        drop.data.materials.append(mat)
    drop.hide_render = True
    drop.hide_viewport = True
    return drop


def create_splash_geometry_nodes(
    splash_scale: float = SPLASH_SCALE,
    splash_density: float = SPLASH_DENSITY,
) -> bpy.types.GeometryNodeTree:
    """
    Procedural splash system: points on ground plane spawn animated crown
    instances and upward droplets, looping with Scene Time.
    """
    ng = new_geometry_node_group("STORM_SplashGN")
    add_group_socket(ng, "Count", "INPUT", "NodeSocketInt",
                     default=int(SPLASH_BASE_COUNT * splash_density), min_value=10, max_value=200_000)
    add_group_socket(ng, "Area", "INPUT", "NodeSocketFloat", default=GROUND_SIZE * 0.9, min_value=1.0)
    add_group_socket(ng, "Scale", "INPUT", "NodeSocketFloat", default=splash_scale, min_value=0.1, max_value=10.0)
    add_group_socket(ng, "Seed", "INPUT", "NodeSocketInt", default=7)

    nodes = ng.nodes
    links = ng.links
    n_in = nodes.new("NodeGroupInput")
    n_in.location = (-1200, 0)
    n_out = nodes.new("NodeGroupOutput")
    n_out.location = (1200, 0)

    # Grid on ground
    grid = nodes.new("GeometryNodeMeshGrid")
    grid.location = (-900, 100)
    grid.inputs["Vertices X"].default_value = 64
    grid.inputs["Vertices Y"].default_value = 64
    links.new(n_in.outputs["Area"], grid.inputs["Size X"])
    links.new(n_in.outputs["Area"], grid.inputs["Size Y"])

    dist = nodes.new("GeometryNodeDistributePointsOnFaces")
    dist.location = (-650, 100)
    dist.distribute_method = "RANDOM"
    links.new(grid.outputs["Mesh"], dist.inputs["Mesh"])
    links.new(n_in.outputs["Seed"], dist.inputs["Seed"])

    dens = nodes.new("ShaderNodeMath")
    dens.operation = "DIVIDE"
    dens.location = (-900, -50)
    links.new(n_in.outputs["Count"], dens.inputs[0])
    area_sq = nodes.new("ShaderNodeMath")
    area_sq.operation = "MULTIPLY"
    area_sq.location = (-1100, -100)
    links.new(n_in.outputs["Area"], area_sq.inputs[0])
    links.new(n_in.outputs["Area"], area_sq.inputs[1])
    links.new(area_sq.outputs["Value"], dens.inputs[1])
    links.new(dens.outputs["Value"], dist.inputs["Density"])

    # Animate splash lifecycle with fraction of time + per-point phase
    scene_time = nodes.new("GeometryNodeInputSceneTime")
    scene_time.location = (-650, -250)
    index = nodes.new("GeometryNodeInputIndex")
    index.location = (-650, -400)

    rand_phase = nodes.new("FunctionNodeRandomValue")
    rand_phase.data_type = "FLOAT"
    rand_phase.location = (-400, -300)
    _set_random_float_range(rand_phase, 0.0, 1.0)
    links.new(n_in.outputs["Seed"], rand_phase.inputs["Seed"])
    links.new(index.outputs["Index"], rand_phase.inputs["ID"])

    # Splash rate: ~6 cycles/sec
    time_scale = nodes.new("ShaderNodeMath")
    time_scale.operation = "MULTIPLY"
    time_scale.location = (-400, -150)
    time_scale.inputs[1].default_value = 6.0
    links.new(scene_time.outputs["Seconds"], time_scale.inputs[0])

    phase = nodes.new("ShaderNodeMath")
    phase.operation = "ADD"
    phase.location = (-200, -200)
    links.new(time_scale.outputs["Value"], phase.inputs[0])
    links.new(rand_phase.outputs["Value"], phase.inputs[1])

    fract = _math_fract(nodes, (0, -200))
    links.new(phase.outputs["Value"], fract.inputs[0])

    # Scale envelope: grow quickly then shrink — 4*f*(1-f)
    one_minus = nodes.new("ShaderNodeMath")
    one_minus.operation = "SUBTRACT"
    one_minus.location = (200, -250)
    one_minus.inputs[0].default_value = 1.0
    links.new(fract.outputs["Value"], one_minus.inputs[1])

    env_mul = nodes.new("ShaderNodeMath")
    env_mul.operation = "MULTIPLY"
    env_mul.location = (400, -200)
    links.new(fract.outputs["Value"], env_mul.inputs[0])
    links.new(one_minus.outputs["Value"], env_mul.inputs[1])

    env = nodes.new("ShaderNodeMath")
    env.operation = "MULTIPLY"
    env.location = (600, -200)
    env.inputs[1].default_value = 4.0
    links.new(env_mul.outputs["Value"], env.inputs[0])

    # Random splash size
    rand_sz = nodes.new("FunctionNodeRandomValue")
    rand_sz.data_type = "FLOAT"
    rand_sz.location = (400, -400)
    _set_random_float_range(rand_sz, 0.4, 1.6)
    seed2 = nodes.new("ShaderNodeMath")
    seed2.operation = "ADD"
    seed2.inputs[1].default_value = 33
    seed2.location = (200, -400)
    links.new(n_in.outputs["Seed"], seed2.inputs[0])
    links.new(seed2.outputs["Value"], rand_sz.inputs["Seed"])
    links.new(index.outputs["Index"], rand_sz.inputs["ID"])

    final_scale = nodes.new("ShaderNodeMath")
    final_scale.operation = "MULTIPLY"
    final_scale.location = (800, -200)
    links.new(env.outputs["Value"], final_scale.inputs[0])
    links.new(n_in.outputs["Scale"], final_scale.inputs[1])

    final_scale2 = nodes.new("ShaderNodeMath")
    final_scale2.operation = "MULTIPLY"
    final_scale2.location = (1000, -200)
    links.new(final_scale.outputs["Value"], final_scale2.inputs[0])
    links.new(rand_sz.outputs["Value"], final_scale2.inputs[1])

    # Crown object
    crown_info = nodes.new("GeometryNodeObjectInfo")
    crown_info.name = "SplashCrownInfo"
    crown_info.location = (600, 100)

    inst_crown = nodes.new("GeometryNodeInstanceOnPoints")
    inst_crown.location = (900, 100)
    links.new(dist.outputs["Points"], inst_crown.inputs["Points"])
    links.new(crown_info.outputs["Geometry"], inst_crown.inputs["Instance"])
    links.new(final_scale2.outputs["Value"], inst_crown.inputs["Scale"])

    # Droplet layer — offset upward by envelope
    droplet_info = nodes.new("GeometryNodeObjectInfo")
    droplet_info.name = "SplashDropletInfo"
    droplet_info.location = (600, -50)

    # Duplicate points with upward offset for droplets
    z_up = nodes.new("ShaderNodeMath")
    z_up.operation = "MULTIPLY"
    z_up.location = (600, -350)
    z_up.inputs[1].default_value = 0.35
    links.new(env.outputs["Value"], z_up.inputs[0])

    up_vec = nodes.new("ShaderNodeCombineXYZ")
    up_vec.location = (800, -350)
    links.new(z_up.outputs["Value"], up_vec.inputs["Z"])

    set_up = nodes.new("GeometryNodeSetPosition")
    set_up.location = (700, 0)
    links.new(dist.outputs["Points"], set_up.inputs["Geometry"])
    links.new(up_vec.outputs["Vector"], set_up.inputs["Offset"])

    drop_scale = nodes.new("ShaderNodeMath")
    drop_scale.operation = "MULTIPLY"
    drop_scale.location = (1000, -50)
    drop_scale.inputs[1].default_value = 0.15
    links.new(final_scale2.outputs["Value"], drop_scale.inputs[0])

    inst_drop = nodes.new("GeometryNodeInstanceOnPoints")
    inst_drop.location = (1000, 0)
    links.new(set_up.outputs["Geometry"], inst_drop.inputs["Points"])
    links.new(droplet_info.outputs["Geometry"], inst_drop.inputs["Instance"])
    links.new(drop_scale.outputs["Value"], inst_drop.inputs["Scale"])

    join = nodes.new("GeometryNodeJoinGeometry")
    join.location = (1100, 80)
    links.new(inst_crown.outputs["Instances"], join.inputs["Geometry"])
    # Join Geometry in newer Blender takes multi-input
    links.new(inst_drop.outputs["Instances"], join.inputs["Geometry"])
    links.new(join.outputs["Geometry"], n_out.inputs["Geometry"])

    return ng


def create_splash_system(collections: dict) -> dict[str, Any]:
    """Create secondary splash particle / GN systems on the ground plane."""
    _log("Creating splash system…")
    col = collections["splash"]

    crown = _create_splash_crown_mesh()
    droplet = _create_splash_droplet_mesh()
    link_object(crown, col)
    link_object(droplet, col)
    crown.hide_set(True)
    droplet.hide_set(True)

    bpy.ops.mesh.primitive_plane_add(size=1.0, location=(0.0, 0.0, 0.02))
    splash_obj = bpy.context.active_object
    splash_obj.name = "Splash_System"
    splash_obj.scale = (GROUND_SIZE * 0.5, GROUND_SIZE * 0.5, 1.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    link_object(splash_obj, col)

    ng = create_splash_geometry_nodes(SPLASH_SCALE, SPLASH_DENSITY)
    mod = splash_obj.modifiers.new(name="STORM_SplashNodes", type="NODES")
    mod.node_group = ng

    crown_info = ng.nodes.get("SplashCrownInfo")
    drop_info = ng.nodes.get("SplashDropletInfo")
    if crown_info:
        crown_info.inputs["Object"].default_value = crown
    if drop_info:
        drop_info.inputs["Object"].default_value = droplet

    count = int(SPLASH_BASE_COUNT * max(0.05, SPLASH_DENSITY))
    set_gn_modifier_input(mod, find_socket_identifier(ng, "Count"), count)
    set_gn_modifier_input(mod, find_socket_identifier(ng, "Scale"), SPLASH_SCALE)

    # Secondary physics particle splash for bouncing droplets near camera
    bpy.ops.mesh.primitive_plane_add(
        size=GROUND_SIZE * 0.5,
        location=(8.0, -12.0, 0.05),
    )
    splash_phys = bpy.context.active_object
    splash_phys.name = "Splash_PhysicsEmitter"
    link_object(splash_phys, col)
    splash_phys.hide_render = True
    set_active(splash_phys)
    splash_phys.modifiers.new(name="SplashParticles", type="PARTICLE_SYSTEM")
    psys = splash_phys.particle_systems[-1]
    psys.name = "Splash_Bounce"
    st = psys.settings
    st.name = "STORM_SplashBounceSettings"
    st.type = "EMITTER"
    st.count = int(5_000 * SPLASH_DENSITY)
    st.frame_start = FRAME_START
    st.frame_end = FRAME_END
    st.lifetime = 12
    st.lifetime_random = 0.5
    st.emit_from = "FACE"
    st.normal_factor = 1.8 * SPLASH_SCALE
    st.factor_random = 0.6
    st.factor_gravity = 1.0
    st.particle_size = 0.02 * SPLASH_SCALE
    st.size_random = 0.7
    st.render_type = "OBJECT"
    st.instance_object = droplet
    st.use_scale_instance = True
    st.effector_weights.wind = 0.4
    st.effector_weights.turbulence = 0.6

    _log(f"Splash system ready — {count:,} procedural hits + physics bounce layer.")
    return {
        "splash_object": splash_obj,
        "crown": crown,
        "droplet": droplet,
        "modifier": mod,
        "physics_emitter": splash_phys,
    }


# =============================================================================
# 5. PUDDLE / GROUND SYSTEM
# =============================================================================

def create_puddle_system(collections: dict) -> dict[str, Any]:
    """
    Create the ground plane with wet material, procedural puddle masks,
    and subtle geometric ripples via a displacement-friendly subdivision.
    """
    _log("Creating puddle / wet ground system…")
    col = collections["ground"]

    # High-res ground for reflections & subtle displacement
    bpy.ops.mesh.primitive_plane_add(size=GROUND_SIZE, location=(0.0, 0.0, 0.0))
    ground = bpy.context.active_object
    ground.name = "Ground_WetTerrain"
    link_object(ground, col)

    set_active(ground)
    # Subdivide for smooth reflections / future displacement
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.subdivide(number_cuts=6)
    bpy.ops.object.mode_set(mode="OBJECT")

    # Subdivision surface for cinematic smoothness
    sub = ground.modifiers.new(name="GroundSubdiv", type="SUBSURF")
    sub.levels = 2
    sub.render_levels = 3

    mat = create_wet_ground_material(
        puddle_coverage=PUDDLE_COVERAGE,
        puddle_depth=PUDDLE_DEPTH,
    )
    if ground.data.materials:
        ground.data.materials[0] = mat
    else:
        ground.data.materials.append(mat)

    # Slight uneven terrain via displace (low areas collect visual puddles)
    tex = bpy.data.textures.new("STORM_GroundHeight", type="CLOUDS")
    tex.noise_scale = 1.2
    tex.noise_depth = 4
    disp = ground.modifiers.new(name="GroundHeight", type="DISPLACE")
    disp.texture = tex
    disp.strength = 0.35
    disp.mid_level = 0.5

    # Collision for particle rain / splash interaction
    try:
        set_active(ground)
        bpy.ops.object.modifier_add(type="COLLISION")
        if hasattr(ground, "collision") and ground.collision is not None:
            ground.collision.damping_factor = 0.4
            ground.collision.damping_random = 0.2
            ground.collision.friction_factor = 0.3
            ground.collision.permeability = 0.05
    except Exception as exc:
        _log(f"Collision setup skipped: {exc}")

    # Thin water plane overlay in deepest visual sense — optional second plane
    # slightly above ground using pure water material for strong reflections
    bpy.ops.mesh.primitive_plane_add(size=GROUND_SIZE * 0.55, location=(3.0, -2.0, 0.04))
    water_sheet = bpy.context.active_object
    water_sheet.name = "Puddle_WaterSheet"
    link_object(water_sheet, col)

    water_mat = bpy.data.materials.new("STORM_PuddleWaterSheet")
    water_mat.use_nodes = True
    nt = water_mat.node_tree
    nodes = nt.nodes
    links = nt.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (400, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (100, 0)
    bsdf.inputs["Base Color"].default_value = (0.01, 0.02, 0.03, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.015
    if "Transmission Weight" in bsdf.inputs:
        bsdf.inputs["Transmission Weight"].default_value = 0.95
    elif "Transmission" in bsdf.inputs:
        bsdf.inputs["Transmission"].default_value = 0.95
    bsdf.inputs["IOR"].default_value = 1.333
    if "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = 0.85
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    # Mask water sheet with noise so it only covers irregular puddle regions
    tex_coord = nodes.new("ShaderNodeTexCoord")
    tex_coord.location = (-600, 200)
    noise = nodes.new("ShaderNodeTexNoise")
    noise.location = (-400, 200)
    noise.inputs["Scale"].default_value = 2.5
    noise.inputs["Detail"].default_value = 8.0
    links.new(tex_coord.outputs["Object"], noise.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.location = (-150, 200)
    # Coverage-driven threshold
    t = 1.0 - PUDDLE_COVERAGE
    ramp.color_ramp.elements[0].position = max(0.01, t - 0.05)
    ramp.color_ramp.elements[0].color = (0, 0, 0, 0)
    ramp.color_ramp.elements[1].position = min(0.99, t + 0.1)
    ramp.color_ramp.elements[1].color = (1, 1, 1, 1)
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Alpha"], bsdf.inputs["Alpha"])

    # Transparent blend
    if hasattr(water_mat, "blend_method"):
        try:
            water_mat.blend_method = "BLEND"
        except TypeError:
            water_mat.blend_method = "HASHED"
    if hasattr(water_mat, "shadow_method"):
        try:
            water_mat.shadow_method = "NONE"
        except TypeError:
            pass

    water_sheet.data.materials.append(water_mat)

    _log("Puddle / wet ground system complete.")
    return {
        "ground": ground,
        "water_sheet": water_sheet,
        "material": mat,
        "water_material": water_mat,
    }


# =============================================================================
# 6. LIGHTING SYSTEM
# =============================================================================

def create_lighting_system(collections: dict) -> dict[str, Any]:
    """
    Overcast storm lighting: low sun, cool fill, volumetric-friendly lamps,
    and optional animated lightning strikes.
    """
    _log("Creating storm lighting system…")
    col = collections["lighting"]
    create_world_storm_shader()

    lights: dict[str, Any] = {}

    # Key — dim, low-angle storm sun / break in clouds
    sun_data = bpy.data.lights.new("Light_StormSun_Data", type="SUN")
    sun_data.energy = 2.2
    sun_data.color = (0.55, 0.62, 0.75)
    if hasattr(sun_data, "angle"):
        sun_data.angle = math.radians(5.5)  # soft overcast sun disc
    sun = new_object("Light_StormSun", sun_data, col)
    sun.rotation_euler = Euler((math.radians(25), math.radians(10), math.radians(40)), "XYZ")
    lights["sun"] = sun

    # Cool fill — broad overcast bounce
    fill_data = bpy.data.lights.new("Light_OvercastFill_Data", type="AREA")
    fill_data.energy = 350.0
    fill_data.color = (0.45, 0.52, 0.65)
    fill_data.shape = "RECTANGLE"
    fill_data.size = 40.0
    fill_data.size_y = 30.0
    fill = new_object("Light_OvercastFill", fill_data, col)
    fill.location = (0.0, -15.0, 28.0)
    fill.rotation_euler = Euler((math.radians(50), 0.0, 0.0), "XYZ")
    lights["fill"] = fill

    # Rim / edge light for rain streak catchlights
    rim_data = bpy.data.lights.new("Light_RainRim_Data", type="AREA")
    rim_data.energy = 200.0
    rim_data.color = (0.6, 0.7, 0.85)
    rim_data.size = 20.0
    rim = new_object("Light_RainRim", rim_data, col)
    rim.location = (-20.0, 10.0, 12.0)
    rim.rotation_euler = Euler((math.radians(70), math.radians(20), math.radians(-50)), "XYZ")
    lights["rim"] = rim

    # Ground bounce (very dim)
    bounce_data = bpy.data.lights.new("Light_GroundBounce_Data", type="AREA")
    bounce_data.energy = 40.0
    bounce_data.color = (0.3, 0.32, 0.35)
    bounce_data.size = 50.0
    bounce = new_object("Light_GroundBounce", bounce_data, col)
    bounce.location = (0.0, 0.0, 0.5)
    bounce.rotation_euler = Euler((math.radians(180), 0.0, 0.0), "XYZ")
    lights["bounce"] = bounce

    # Atmospheric fog domain
    fog_mat = create_atmosphere_material()
    fog_mesh = bpy.data.meshes.new("Atmos_FogDomain_Mesh")
    fog_mesh.from_pydata(
        [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
         (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)],
        [],
        [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
         (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)],
    )
    fog_mesh.update()
    fog = new_object("Atmos_FogDomain", fog_mesh, collections["atmosphere"])
    fog.location = (0.0, 0.0, 12.0)
    fog.scale = (GROUND_SIZE * 0.7, GROUND_SIZE * 0.7, 22.0)
    fog.display_type = "WIRE"
    fog.data.materials.append(fog_mat)
    lights["fog"] = fog

    # Lightning lights (animated later if enabled)
    lightning_lights = []
    if ENABLE_LIGHTNING:
        strike_positions = [
            (-25.0, 30.0, 35.0),
            (20.0, 40.0, 42.0),
            (5.0, -5.0, 38.0),
            (-10.0, 50.0, 48.0),
        ]
        for i, loc in enumerate(strike_positions):
            ld = bpy.data.lights.new(f"Lightning_Flash_{i}_Data", type="POINT")
            ld.energy = 0.0  # keyed during animation
            ld.color = (0.75, 0.85, 1.0)
            ld.shadow_soft_size = 3.0
            lo = new_object(f"Lightning_Flash_{i}", ld, col)
            lo.location = loc
            lightning_lights.append(lo)

            # Secondary fill flash for broader illumination
            ld2 = bpy.data.lights.new(f"Lightning_Fill_{i}_Data", type="POINT")
            ld2.energy = 0.0
            ld2.color = (0.55, 0.65, 0.9)
            ld2.shadow_soft_size = 12.0
            lo2 = new_object(f"Lightning_Fill_{i}", ld2, col)
            lo2.location = (loc[0] * 0.5, loc[1] * 0.5, loc[2] * 0.7)
            lightning_lights.append(lo2)

    lights["lightning"] = lightning_lights
    _log(f"Lighting ready — lightning={'ON' if ENABLE_LIGHTNING else 'OFF'}.")
    return lights


# =============================================================================
# 7. WIND SYSTEM
# =============================================================================

def create_wind_system(collections: dict) -> dict[str, Any]:
    """
    Storm wind: primary Wind force + Turbulence for gusts.
    Affects rain particle systems and storm ambience.
    """
    _log("Creating wind system…")
    col = collections["wind"]

    # Primary wind via effector_add (Blender 5.x API)
    bpy.ops.object.effector_add(
        type="WIND",
        location=(0.0, 0.0, 15.0),
        rotation=(math.radians(90), 0.0, math.radians(15)),
    )
    wind_empty = bpy.context.active_object
    wind_empty.name = "Wind_Primary"
    wind_empty.empty_display_type = "SINGLE_ARROW"
    wind_empty.empty_display_size = 3.0
    link_object(wind_empty, col)

    field = wind_empty.field
    field.strength = WIND_SPEED
    field.flow = 0.3
    field.noise = 0.4 * GUST_FACTOR
    field.seed = 3

    # Turbulence
    bpy.ops.object.effector_add(type="TURBULENCE", location=(10.0, 5.0, 12.0))
    turb_empty = bpy.context.active_object
    turb_empty.name = "Wind_Turbulence"
    turb_empty.empty_display_type = "SPHERE"
    turb_empty.empty_display_size = 2.0
    link_object(turb_empty, col)

    tfield = turb_empty.field
    tfield.strength = WIND_TURBULENCE * GUST_FACTOR
    tfield.size = 4.0
    tfield.flow = 0.5
    tfield.seed = 11
    if hasattr(tfield, "use_global_coords"):
        tfield.use_global_coords = True

    # Secondary gust vortex
    bpy.ops.object.effector_add(type="VORTEX", location=(-15.0, 0.0, 8.0))
    gust = bpy.context.active_object
    gust.name = "Wind_GustVortex"
    gust.empty_display_type = "CIRCLE"
    gust.empty_display_size = 4.0
    link_object(gust, col)

    gfield = gust.field
    gfield.strength = 1.2 * GUST_FACTOR
    gfield.flow = 0.2

    _log("Wind force fields created.")
    return {
        "wind": wind_empty,
        "turbulence": turb_empty,
        "gust": gust,
    }


# =============================================================================
# ANIMATION SYSTEM
# =============================================================================

def animate_storm(
    clouds: list[bpy.types.Object],
    rain_data: dict,
    splash_data: dict,
    puddle_data: dict,
    lights: dict,
    wind_data: dict,
) -> None:
    """
    Keyframe the full 300-frame storm sequence:
    cloud drift, wind gusts, puddle ripple phase, optional lightning flashes.
    """
    _log("Animating storm sequence…")
    scene = bpy.context.scene
    scene.frame_start = FRAME_START
    scene.frame_end = FRAME_END

    rng = random.Random(2026)

    # --- Cloud drift ---
    for i, cloud in enumerate(clouds):
        base_loc = cloud.location.copy()
        drift_x = 4.0 + i * 0.7
        drift_y = 2.0 + (i % 3) * 0.5
        # Slow turbulent rotation
        base_rot = cloud.rotation_euler.copy()

        for f, t in ((FRAME_START, 0.0), (FRAME_END // 2, 0.5), (FRAME_END, 1.0)):
            cloud.location = (
                base_loc.x + drift_x * t + math.sin(t * math.pi * 2 + i) * 1.5,
                base_loc.y + drift_y * t + math.cos(t * math.pi * 2 + i * 0.7) * 1.0,
                base_loc.z + math.sin(t * math.pi + i) * 0.8,
            )
            cloud.keyframe_insert(data_path="location", frame=f)
            cloud.rotation_euler = (
                base_rot.x,
                base_rot.y,
                base_rot.z + math.radians(3.0 + i) * t,
            )
            cloud.keyframe_insert(data_path="rotation_euler", frame=f)

        # Smooth interpolation
        if cloud.animation_data and cloud.animation_data.action:
            _set_action_interpolation(cloud, "BEZIER")

    # --- Wind gust strength pulsing ---
    wind = wind_data["wind"]
    turb = wind_data["turbulence"]
    for f in range(FRAME_START, FRAME_END + 1, 8):
        gust = 0.65 + 0.35 * math.sin(f * 0.07) + 0.2 * math.sin(f * 0.023)
        gust *= GUST_FACTOR
        wind.field.strength = WIND_SPEED * gust
        wind.keyframe_insert(data_path="field.strength", frame=f)
        turb.field.strength = WIND_TURBULENCE * (0.7 + 0.5 * math.sin(f * 0.05 + 1.2))
        turb.keyframe_insert(data_path="field.strength", frame=f)
        # Sway wind direction slightly
        wind.rotation_euler = Euler(
            (
                math.radians(90),
                math.radians(math.sin(f * 0.03) * 8),
                math.radians(15 + math.sin(f * 0.02) * 12),
            ),
            "XYZ",
        )
        wind.keyframe_insert(data_path="rotation_euler", frame=f)

    # --- Puddle ripple animation (shader mapping offset) ---
    mat = puddle_data.get("material")
    if mat and mat.use_nodes:
        mapping = None
        for n in mat.node_tree.nodes:
            if n.type == "MAPPING":
                mapping = n
                break
        if mapping is not None:
            for f in range(FRAME_START, FRAME_END + 1, 4):
                t = (f - FRAME_START) / max(1, FRAME_END - FRAME_START)
                mapping.inputs["Location"].default_value[0] = t * 2.5
                mapping.inputs["Location"].default_value[1] = t * 1.2
                mapping.inputs["Location"].keyframe_insert(data_path="default_value", frame=f)

    # --- Camera subtle drift ---
    cam = bpy.data.objects.get("Cam_Storm")
    if cam is not None:
        base = cam.location.copy()
        base_rot = cam.rotation_euler.copy()
        for f, t in ((FRAME_START, 0.0), (150, 0.5), (FRAME_END, 1.0)):
            cam.location = (
                base.x + math.sin(t * math.pi * 2) * 0.4,
                base.y + t * 1.5,
                base.z + math.sin(t * math.pi) * 0.15,
            )
            cam.keyframe_insert(data_path="location", frame=f)
            cam.rotation_euler = (
                base_rot.x + math.radians(math.sin(t * math.pi) * 1.5),
                base_rot.y,
                base_rot.z + math.radians(t * 3.0),
            )
            cam.keyframe_insert(data_path="rotation_euler", frame=f)

    # --- Lightning flashes ---
    if ENABLE_LIGHTNING and lights.get("lightning"):
        _animate_lightning(lights["lightning"], rng)
        # Briefly boost sun/fill on big strikes for sky illumination
        sun = lights.get("sun")
        if sun is not None:
            # Baseline keyframes
            sun.data.energy = 2.2
            sun.data.keyframe_insert(data_path="energy", frame=FRAME_START)
            sun.data.keyframe_insert(data_path="energy", frame=FRAME_END)

    # --- Rain intensity subtle breathing (modifier count not easily animated;
    #     animate particle lifetime / emission via settings) ---
    for emitter_name, settings_name in (
        ("Rain_StreakEmitter", "STORM_RainStreakSettings"),
        ("Rain_DistantEmitter", "STORM_RainDistantSettings"),
    ):
        st = bpy.data.particles.get(settings_name)
        if st is None:
            continue
        base_count = st.count
        for f in (FRAME_START, 100, 200, FRAME_END):
            pulse = 0.85 + 0.15 * math.sin(f * 0.04)
            st.count = int(base_count * pulse)
            try:
                st.keyframe_insert(data_path="count", frame=f)
            except TypeError:
                # Some particle properties may not be animatable in all builds
                pass
        st.count = base_count

    # Fog density subtle pulse via material value
    fog = lights.get("fog")
    if fog and fog.data.materials:
        fog_mat = fog.data.materials[0]
        vol_nodes = [n for n in fog_mat.node_tree.nodes if n.type == "PRINCIPLED_VOLUME"]
        if vol_nodes:
            dens_in = vol_nodes[0].inputs["Density"]
            for f in range(FRAME_START, FRAME_END + 1, 10):
                dens_in.default_value = 0.01 + 0.006 * (0.5 + 0.5 * math.sin(f * 0.05))
                dens_in.keyframe_insert(data_path="default_value", frame=f)

    _log(f"Animation set for frames {FRAME_START}–{FRAME_END}.")


def _animate_lightning(lightning_lights: list[bpy.types.Object], rng: random.Random) -> None:
    """
    Frame-based natural lightning: irregular intervals, multi-frame flicker,
    and intensity spikes on paired flash/fill lights.
    """
    # Pair lights as (flash, fill)
    pairs = []
    flashes = [o for o in lightning_lights if "Flash" in o.name]
    fills = [o for o in lightning_lights if "Fill" in o.name]
    for i, flash in enumerate(flashes):
        fill = fills[i] if i < len(fills) else None
        pairs.append((flash, fill))

    # Generate strike times
    t = FRAME_START + 20
    strikes = []
    while t < FRAME_END - 10:
        strikes.append(t)
        t += rng.randint(28, 70)

    for strike_frame in strikes:
        pair = rng.choice(pairs)
        flash, fill = pair
        peak = rng.uniform(3500, 9000)
        fill_peak = peak * rng.uniform(0.25, 0.45)

        # Pre-strike darkness
        for obj, base_peak in ((flash, peak), (fill, fill_peak)):
            if obj is None:
                continue
            obj.data.energy = 0.0
            obj.data.keyframe_insert(data_path="energy", frame=strike_frame - 1)

        # Flicker pattern: main bolt + 1–3 re-strikes
        flicker_frames = [0]
        n_flickers = rng.randint(1, 3)
        cursor = 0
        for _ in range(n_flickers):
            cursor += rng.randint(1, 3)
            flicker_frames.append(cursor)

        for fi, offset in enumerate(flicker_frames):
            f = strike_frame + offset
            # Decay subsequent flickers
            decay = 1.0 if fi == 0 else rng.uniform(0.35, 0.75)
            flash.data.energy = peak * decay * rng.uniform(0.85, 1.0)
            flash.data.keyframe_insert(data_path="energy", frame=f)
            if fill is not None:
                fill.data.energy = fill_peak * decay * rng.uniform(0.7, 1.0)
                fill.data.keyframe_insert(data_path="energy", frame=f)
            # Off between flickers
            if fi < len(flicker_frames) - 1:
                gap = strike_frame + offset + 1
                flash.data.energy = rng.uniform(0, peak * 0.05)
                flash.data.keyframe_insert(data_path="energy", frame=gap)
                if fill is not None:
                    fill.data.energy = 0.0
                    fill.data.keyframe_insert(data_path="energy", frame=gap)

        # Return to zero
        end_f = strike_frame + flicker_frames[-1] + 2
        flash.data.energy = 0.0
        flash.data.keyframe_insert(data_path="energy", frame=end_f)
        if fill is not None:
            fill.data.energy = 0.0
            fill.data.keyframe_insert(data_path="energy", frame=end_f)

        # Constant interpolation for snappy flashes
        for obj in (flash, fill):
            if obj is None or not obj.data.animation_data:
                continue
            _set_action_interpolation(obj.data, "CONSTANT")


def _set_action_interpolation(id_data: Any, mode: str = "BEZIER") -> None:
    """Set keyframe interpolation on all fcurves of an ID's action."""
    ad = getattr(id_data, "animation_data", None)
    if not ad or not ad.action:
        return
    action = ad.action
    # Blender 4.4+ layered actions vs classic fcurves
    try:
        fcurves = action.fcurves
    except AttributeError:
        fcurves = []
        if hasattr(action, "layers"):
            for layer in action.layers:
                for strip in getattr(layer, "strips", []):
                    channelbag = getattr(strip, "channelbag", None)
                    if channelbag and hasattr(channelbag, "fcurves"):
                        fcurves.extend(channelbag.fcurves)
    for fc in fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = mode


# =============================================================================
# MAIN
# =============================================================================

def main() -> None:
    """Orchestrate full storm environment construction."""
    _log("=" * 60)
    _log("Ultra-Realistic Rainstorm Generator — Blender 5.2.0")
    _log("=" * 60)

    # Version check (warn only — allow close versions)
    version = bpy.app.version
    if version < (4, 0, 0):
        _log(f"WARNING: Detected Blender {bpy.app.version_string}; script targets 5.2.0.")
    else:
        _log(f"Running on Blender {bpy.app.version_string}")

    try:
        collections = setup_scene()
        clouds = create_cloud_system(collections)
        rain_data = create_rain_system(collections)
        splash_data = create_splash_system(collections)
        puddle_data = create_puddle_system(collections)
        lights = create_lighting_system(collections)
        wind_data = create_wind_system(collections)
        animate_storm(clouds, rain_data, splash_data, puddle_data, lights, wind_data)

        # Frame to start
        bpy.context.scene.frame_set(FRAME_START)

        # Deselect all for clean viewport
        bpy.ops.object.select_all(action="DESELECT")

        _log("-" * 60)
        _log("Storm environment created successfully.")
        _log(f"  Frames: {FRAME_START}–{FRAME_END} @ {FPS} fps")
        _log(f"  Rain intensity: {RAIN_INTENSITY}")
        _log(f"  Puddle coverage: {PUDDLE_COVERAGE}")
        _log(f"  Wind speed: {WIND_SPEED} | Turbulence: {WIND_TURBULENCE}")
        _log(f"  Lightning: {ENABLE_LIGHTNING}")
        _log(f"  Engine: {bpy.context.scene.render.engine}")
        _log("Adjust CONFIGURATION constants at the top of this script and re-run.")
        _log("=" * 60)

    except Exception as exc:
        _log(f"ERROR: {exc}")
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
