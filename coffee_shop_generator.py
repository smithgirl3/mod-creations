# ============================================================================
#  HYPERREALISTIC COZY COFFEE SHOP — PROCEDURAL ENVIRONMENT GENERATOR
#  Blender 5.2.0 Python Script  |  Unity Game-Ready Export Pipeline
# ============================================================================
#
#  A complete, production-quality procedural environment generator that
#  builds a warm, cinematic independent coffee shop on a rainy city evening:
#
#    * Full architecture  (walls, floor-to-ceiling windows, roof, columns,
#      trim, baseboards, wood paneling, realistic flooring)
#    * Complete coffee bar (espresso machine, grinders, brewers, sink,
#      display case with pastries, register, menus, shelving, cups, mugs)
#    * Seating area        (tables, booths, armchairs, couches, reading corner)
#    * Decor               (bookshelves, plants, artwork, rugs, curtains,
#                           lamps, signs, candles, string lights)
#    * Exterior city street (road, sidewalks, buildings, storefronts,
#                            street lights, traffic signals, parked cars,
#                            benches, trash cans, utility poles + wires)
#    * Weather FX          (particle rain with collisions, wind, puddles,
#                           lightning flashes, thunder sync markers,
#                           rain droplets / streaks / condensation on glass)
#    * Physics             (cloth curtains, rigid bodies, soft-body cushions,
#                           dust and steam particles/volumes)
#    * Cinematic lighting  (2700-3200K warm interior vs. cold storm exterior)
#    * Camera system       (6 cameras, 30 s animated dolly sequence, DOF,
#                           rack-focus transitions, marker-bound cuts)
#    * Cycles render setup (path tracing, denoising, GI, volumetrics, caustics)
#    * Unity export        (FBX + GLB + textures, LOD0-LOD3 generation,
#                           texture size optimization: 2K / 4K / 8K)
#
#  USAGE
#  -----
#    1. Open Blender 5.2.0  ->  Scripting workspace  ->  New text block.
#    2. Paste this entire script and press "Run Script".
#    3. main() executes automatically and builds everything.
#    4. Call export_for_unity() at any time to (re)export the scene.
#
#  All geometry, materials, physics, lighting and animation are generated
#  procedurally — no external assets are required.  If AI-generated textures
#  (Stable Diffusion / Flux / Midjourney / local libraries) are dropped into
#  the auto-created  Textures/  folder tree, they are discovered and wired
#  into the PBR materials automatically on the next run.
#
#  Author : Procedural Environments Team
#  License: MIT
# ============================================================================

import bpy
import bmesh
import math
import os
import sys
import json
import time
import random
import tempfile
import traceback
from mathutils import Vector, Matrix, Euler

# ============================================================================
#  GLOBAL CONFIGURATION
# ============================================================================
#  Every tunable of the generator lives here so the whole environment can be
#  re-dressed (bigger shop, heavier rain, different seed...) without touching
#  the builder code.
# ============================================================================

CONFIG = {
    # -- determinism -------------------------------------------------------
    "seed": 42,                       # master random seed (reproducible builds)

    # -- animation / timeline ----------------------------------------------
    "fps": 24,
    "duration_seconds": 30,           # cinematic sequence length

    # -- shop architecture (meters) ------------------------------------------
    "shop": {
        "width": 16.0,                # X extent of the interior
        "depth": 12.0,                # Y extent of the interior
        "height": 4.2,                # floor-to-ceiling
        "wall_thickness": 0.30,
        "window_mullion_spacing": 2.0,
        "door_x": 6.0,                # entrance door position on front wall
    },

    # -- exterior street ------------------------------------------------------
    "street": {
        "sidewalk_near": (6.30, 8.60),    # Y range of near sidewalk
        "road": (8.60, 16.60),            # Y range of the road
        "sidewalk_far": (16.60, 18.80),   # Y range of far sidewalk
        "building_row_y": 20.0,           # far buildings front face
        "extent_x": 34.0,                 # how far the street runs in X
    },

    # -- weather ---------------------------------------------------------------
    "rain": {
        "intensity": 1.0,             # 0.0 .. 2.0  (scales particle count)
        "base_count": 9000,           # particles at intensity 1.0
        "emitter_height": 17.0,
        "lifetime": 45,
    },
    "wind": {
        "strength": 700.0,            # wind force field strength
        "turbulence": 250.0,
    },
    "lightning": {
        "flash_count": 5,             # flashes across the 30 s sequence
        "min_gap_frames": 70,
        "thunder_delay_frames": (10, 42),   # random delay flash -> thunder
    },

    # -- lighting -----------------------------------------------------------
    "interior_kelvin": (2700, 3200),  # warm practical range
    "exterior_kelvin": 9500,          # cold storm light

    # -- textures / AI texture system -----------------------------------------
    "texture_root": "Textures",       # relative to the .blend (or temp dir)
    "texture_categories": [
        "wood", "leather", "fabric", "concrete",
        "metal", "food", "decals", "weather",
        "ceramic", "glass", "paper",
    ],
    "ai_sources": ["stable_diffusion", "flux", "midjourney", "local"],
    "texture_max_size": 4096,         # 2048 / 4096 / 8192 supported

    # -- optimization / export ------------------------------------------------
    "lod_ratios": [1.0, 0.55, 0.28, 0.10],   # LOD0..LOD3 decimate ratios
    "export_dir": "UnityExport",
    "export_fbx": True,
    "export_glb": True,

    # -- render ----------------------------------------------------------------
    "render": {
        "samples": 512,
        "resolution": (1920, 1080),
        "max_bounces": 12,
        "volume_bounces": 2,
        "use_caustics": True,
    },
}

# Master RNG — every stochastic decision flows through this for repeatability.
RNG = random.Random(CONFIG["seed"])

# Frame range derived from config.
FRAME_START = 1
FRAME_END = CONFIG["fps"] * CONFIG["duration_seconds"]   # 720 @ 24 fps

# Collected build statistics for the final report.
BUILD_REPORT = {"stages": [], "warnings": [], "objects": 0}


# ============================================================================
#  LOGGING + ERROR HANDLING
# ============================================================================

def log(msg, level="INFO"):
    """Uniform console logger so build progress is easy to follow."""
    print(f"[CoffeeShopGen][{level}] {msg}")


def warn(msg):
    """Log a non-fatal problem and remember it for the build report."""
    BUILD_REPORT["warnings"].append(msg)
    log(msg, level="WARN")


def run_stage(stage_name, func, *args, **kwargs):
    """
    Execute one build stage with full error isolation.

    A failure in a single stage (e.g. an exporter add-on that is disabled)
    must never abort the whole environment build, so every stage is wrapped
    in its own try/except and timed for the report.
    """
    t0 = time.time()
    log(f"--- stage: {stage_name} ...")
    try:
        result = func(*args, **kwargs)
        dt = time.time() - t0
        BUILD_REPORT["stages"].append((stage_name, "OK", round(dt, 2)))
        log(f"--- stage: {stage_name} done ({dt:.2f}s)")
        return result
    except Exception as exc:
        dt = time.time() - t0
        BUILD_REPORT["stages"].append((stage_name, f"FAILED: {exc}", round(dt, 2)))
        log(f"--- stage: {stage_name} FAILED: {exc}", level="ERROR")
        traceback.print_exc()
        return None


# ============================================================================
#  SCENE / COLLECTION HELPERS
# ============================================================================

def get_or_create_collection(name, parent=None):
    """Return the collection `name`, creating and linking it if necessary."""
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
    parent = parent or bpy.context.scene.collection
    if coll.name not in [c.name for c in parent.children]:
        try:
            parent.children.link(coll)
        except RuntimeError:
            pass   # already linked somewhere else in the hierarchy
    return coll


def link_to_collection(obj, coll):
    """Move `obj` so it lives ONLY in `coll` (unlink from all others)."""
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    coll.objects.link(obj)


def set_active(obj):
    """Make `obj` the active + only selected object (needed by operators)."""
    try:
        bpy.ops.object.select_all(action='DESELECT')
    except RuntimeError:
        pass
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def clear_scene():
    """
    Wipe the current scene back to an empty state so the generator always
    starts from scratch (safe to re-run the script repeatedly).
    """
    # Leave edit mode if the user happened to be in it.
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    # Remove every object.
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    # Remove all collections except scene roots.
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)

    # Remove timeline markers from previous runs.
    scene = bpy.context.scene
    for marker in list(scene.timeline_markers):
        scene.timeline_markers.remove(marker)

    # Purge orphaned datablocks (meshes, materials, images, ...).
    for block_list in (bpy.data.meshes, bpy.data.materials, bpy.data.images,
                       bpy.data.lights, bpy.data.cameras, bpy.data.curves,
                       bpy.data.particles, bpy.data.node_groups,
                       bpy.data.texts if False else []):
        for block in list(block_list):
            if block.users == 0:
                try:
                    block_list.remove(block)
                except Exception:
                    pass

    # Reset animation.
    scene.frame_start = FRAME_START
    scene.frame_end = FRAME_END
    scene.frame_set(FRAME_START)
    log("Scene cleared.")


def project_root():
    """
    Directory used for Textures/ and UnityExport/.
    Prefers the folder of the saved .blend; falls back to the system temp
    dir so the script also works in an unsaved file.
    """
    blend_dir = bpy.path.abspath("//")
    if blend_dir and os.path.isdir(blend_dir):
        return blend_dir
    return os.path.join(tempfile.gettempdir(), "coffee_shop_project")


# ============================================================================
#  PRIMITIVE / MESH HELPERS
# ============================================================================
#  All geometry passes through these wrappers so objects get consistent
#  naming, collection linking, materials and clean (applied) scales — which
#  is essential for a clean Unity import (correct pivots + transforms).
# ============================================================================

def _post_create(name, collection, material):
    """Shared bookkeeping after a bpy.ops primitive call."""
    obj = bpy.context.active_object
    obj.name = name
    if collection is not None:
        link_to_collection(obj, collection)
    if material is not None:
        assign_material(obj, material)
    BUILD_REPORT["objects"] += 1
    return obj


def add_cube(name, size=(1.0, 1.0, 1.0), location=(0, 0, 0), rotation=(0, 0, 0),
             collection=None, material=None):
    """Create a box with explicit dimensions and an applied (1,1,1) scale."""
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location,
                                    rotation=rotation)
    obj = _post_create(name, collection, material)
    obj.scale = (size[0], size[1], size[2])
    apply_scale(obj)
    return obj


def add_plane(name, size=(1.0, 1.0), location=(0, 0, 0), rotation=(0, 0, 0),
              collection=None, material=None):
    """Create a rectangular plane (size = X,Y extents)."""
    bpy.ops.mesh.primitive_plane_add(size=1.0, location=location,
                                     rotation=rotation)
    obj = _post_create(name, collection, material)
    obj.scale = (size[0], size[1], 1.0)
    apply_scale(obj)
    return obj


def add_grid(name, size=(1.0, 1.0), subdivisions=(10, 10), location=(0, 0, 0),
             rotation=(0, 0, 0), collection=None, material=None):
    """Create a subdivided plane — used for cloth and displaced surfaces."""
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=subdivisions[0],
                                    y_subdivisions=subdivisions[1],
                                    size=1.0, location=location,
                                    rotation=rotation)
    obj = _post_create(name, collection, material)
    obj.scale = (size[0], size[1], 1.0)
    apply_scale(obj)
    return obj


def add_cylinder(name, radius=0.5, depth=1.0, location=(0, 0, 0),
                 rotation=(0, 0, 0), vertices=24, collection=None,
                 material=None):
    """Create a cylinder (Z axis = depth)."""
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius,
                                        depth=depth, location=location,
                                        rotation=rotation)
    return _post_create(name, collection, material)


def add_cone(name, radius1=0.5, radius2=0.0, depth=1.0, location=(0, 0, 0),
             rotation=(0, 0, 0), vertices=24, collection=None, material=None):
    """Create a cone / truncated cone."""
    bpy.ops.mesh.primitive_cone_add(vertices=vertices, radius1=radius1,
                                    radius2=radius2, depth=depth,
                                    location=location, rotation=rotation)
    return _post_create(name, collection, material)


def add_sphere(name, radius=0.5, location=(0, 0, 0), segments=24, rings=16,
               collection=None, material=None):
    """Create a UV sphere."""
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings,
                                         radius=radius, location=location)
    return _post_create(name, collection, material)


def add_ico_sphere(name, radius=0.5, location=(0, 0, 0), subdivisions=2,
                   collection=None, material=None):
    """Create an icosphere (cheap organic blobs: leaves, pastries...)."""
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=subdivisions,
                                          radius=radius, location=location)
    return _post_create(name, collection, material)


def add_torus(name, major_radius=0.5, minor_radius=0.1, location=(0, 0, 0),
              rotation=(0, 0, 0), major_segments=32, minor_segments=16,
              collection=None, material=None):
    """Create a torus (mug handles, donuts, rings)."""
    bpy.ops.mesh.primitive_torus_add(major_radius=major_radius,
                                     minor_radius=minor_radius,
                                     major_segments=major_segments,
                                     minor_segments=minor_segments,
                                     location=location, rotation=rotation)
    return _post_create(name, collection, material)


def add_empty(name, location=(0, 0, 0), collection=None):
    """Create an empty (camera targets, group pivots)."""
    empty = bpy.data.objects.new(name, None)
    empty.location = location
    (collection or bpy.context.scene.collection).objects.link(empty)
    return empty


def add_text_mesh(name, body, location=(0, 0, 0), rotation=(0, 0, 0),
                  size=0.3, extrude=0.02, collection=None, material=None):
    """Create 3D text and immediately convert it to a mesh (FBX friendly)."""
    bpy.ops.object.text_add(location=location, rotation=rotation)
    obj = bpy.context.active_object
    obj.data.body = body
    obj.data.size = size
    obj.data.extrude = extrude
    obj.data.align_x = 'CENTER'
    set_active(obj)
    bpy.ops.object.convert(target='MESH')
    obj = bpy.context.active_object
    obj.name = name
    if collection is not None:
        link_to_collection(obj, collection)
    if material is not None:
        assign_material(obj, material)
    BUILD_REPORT["objects"] += 1
    return obj


def apply_scale(obj):
    """
    Bake the object scale into the mesh WITHOUT relying on operator context.
    Clean unit scales are mandatory for well-behaved Unity imports.
    """
    if obj.type != 'MESH':
        return
    sx, sy, sz = obj.scale
    if (sx, sy, sz) == (1.0, 1.0, 1.0):
        return
    mat = Matrix.Diagonal(Vector((sx, sy, sz))).to_4x4()
    obj.data.transform(mat)
    obj.scale = (1.0, 1.0, 1.0)


def assign_material(obj, mat):
    """Assign `mat` as the object's (only) material slot 0."""
    if obj.type not in {'MESH', 'CURVE', 'FONT'}:
        return
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)


def shade_smooth(obj, auto_angle=math.radians(35)):
    """Context-free smooth shading with an angle-based sharp split."""
    if obj.type != 'MESH':
        return
    for poly in obj.data.polygons:
        poly.use_smooth = True
    try:
        # Blender 4/5: smooth-by-angle is a geometry-nodes based operator;
        # falling back to plain smooth shading is fine for stylized props.
        set_active(obj)
        bpy.ops.object.shade_smooth_by_angle(angle=auto_angle)
    except Exception:
        pass


def add_bevel(obj, width=0.012, segments=2, angle_limit=math.radians(45)):
    """Add a bevel modifier — the single cheapest realism win on hard props."""
    mod = obj.modifiers.new("Bevel", 'BEVEL')
    mod.width = width
    mod.segments = segments
    mod.limit_method = 'ANGLE'
    mod.angle_limit = angle_limit
    mod.miter_outer = 'MITER_ARC'
    return mod


def add_subsurf(obj, levels=1, render_levels=2):
    """Add a subdivision surface modifier (soft furniture, cushions...)."""
    mod = obj.modifiers.new("Subsurf", 'SUBSURF')
    mod.levels = levels
    mod.render_levels = render_levels
    return mod


def add_solidify(obj, thickness=0.02):
    """Give thickness to planes (lamp shades, awnings, menus...)."""
    mod = obj.modifiers.new("Solidify", 'SOLIDIFY')
    mod.thickness = thickness
    return mod


def add_displace_noise(obj, strength=0.02, noise_scale=1.5):
    """Organic surface break-up via a procedural displace modifier."""
    tex = bpy.data.textures.new(obj.name + "_DispTex", type='CLOUDS')
    tex.noise_scale = noise_scale
    mod = obj.modifiers.new("Displace", 'DISPLACE')
    mod.texture = tex
    mod.strength = strength
    mod.texture_coords = 'LOCAL'
    return mod


def join_objects(objects, name):
    """Join a list of objects into one mesh (prop consolidation for LODs)."""
    meshes = [o for o in objects if o.type == 'MESH']
    if not meshes:
        return None
    bpy.ops.object.select_all(action='DESELECT')
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.join()
    joined = bpy.context.active_object
    joined.name = name
    return joined


def rebase_origin_to_world(obj):
    """
    Move the object's origin to the world origin by baking its current
    location into the mesh data.  Essential after join_objects() for props
    that are assembled around (0,0,0) and then placed with `.location = ...`
    — the join keeps the FIRST part's origin, which would otherwise offset
    the whole prop when relocated.
    """
    if obj.type != 'MESH':
        return
    offset = Vector(obj.location)
    if offset.length == 0.0:
        return
    obj.data.transform(Matrix.Translation(offset))
    obj.location = (0.0, 0.0, 0.0)


def set_parent_keep_transform(child, parent):
    """Parent while preserving world transform (clean hierarchies in Unity)."""
    child.parent = parent
    child.matrix_parent_inverse = parent.matrix_world.inverted()


def randomize_transform(obj, loc_jitter=0.02, rot_jitter_deg=4.0,
                        scale_jitter=0.04):
    """
    Tiny random nudges so repeated props (chairs, cups, books) never read
    as perfect duplicates — a hallmark of believable set dressing.
    """
    obj.location.x += RNG.uniform(-loc_jitter, loc_jitter)
    obj.location.y += RNG.uniform(-loc_jitter, loc_jitter)
    obj.rotation_euler.z += math.radians(RNG.uniform(-rot_jitter_deg,
                                                     rot_jitter_deg))
    s = 1.0 + RNG.uniform(-scale_jitter, scale_jitter)
    obj.scale = (obj.scale.x * s, obj.scale.y * s, obj.scale.z * s)


# ============================================================================
#  NODE / SHADER HELPERS
# ============================================================================

def new_node(node_tree, node_type, location=(0, 0)):
    """Create a shader node at a layout position (keeps trees readable)."""
    node = node_tree.nodes.new(node_type)
    node.location = location
    return node


def set_input(node, names, value):
    """
    Set a node input by trying several socket names.

    Principled BSDF socket names have shifted across Blender versions
    (e.g. 'Transmission' -> 'Transmission Weight'), so all material code
    goes through this version-tolerant setter.
    """
    if isinstance(names, str):
        names = [names]
    for name in names:
        sock = node.inputs.get(name)
        if sock is not None:
            try:
                sock.default_value = value
                return True
            except (TypeError, ValueError):
                continue
    return False


def kelvin_to_rgb(kelvin):
    """
    Approximate blackbody color for a temperature in Kelvin (Tanner Helland
    fit).  Returns linear-ish (r, g, b) in 0..1 — good enough for lamps.
    """
    temp = max(1000.0, min(40000.0, float(kelvin))) / 100.0
    # Red
    if temp <= 66:
        r = 255.0
    else:
        r = 329.698727446 * ((temp - 60.0) ** -0.1332047592)
    # Green
    if temp <= 66:
        g = 99.4708025861 * math.log(temp) - 161.1195681661
    else:
        g = 288.1221695283 * ((temp - 60.0) ** -0.0755148492)
    # Blue
    if temp >= 66:
        b = 255.0
    elif temp <= 19:
        b = 0.0
    else:
        b = 138.5177312231 * math.log(temp - 10.0) - 305.0447927307
    clamp = lambda v: max(0.0, min(255.0, v)) / 255.0
    return (clamp(r), clamp(g), clamp(b))


def get_action_fcurves(id_data):
    """
    Return all f-curves animating `id_data`, tolerant of both the legacy
    flat Action API (`action.fcurves`) and the layered/slotted Actions
    introduced in modern Blender (layers -> strips -> channelbags).
    """
    anim = getattr(id_data, "animation_data", None)
    if anim is None or anim.action is None:
        return []
    action = anim.action
    if hasattr(action, "fcurves"):          # legacy flat actions
        return list(action.fcurves)
    fcurves = []
    for layer in action.layers:             # slotted actions (Blender 5.x)
        for strip in layer.strips:
            try:
                bag = strip.channelbag(anim.action_slot)
            except (TypeError, RuntimeError):
                bag = None
            if bag is not None:
                fcurves.extend(bag.fcurves)
    return fcurves


def add_fcurve_noise(id_data, data_path, index=-1, strength=0.3, scale=20.0,
                     offset=0.0):
    """
    Attach a NOISE modifier to an f-curve (organic flicker / sway).
    The f-curve must already exist — insert a keyframe first.
    """
    for fcu in get_action_fcurves(id_data):
        if fcu.data_path == data_path and (index < 0 or fcu.array_index == index):
            mod = fcu.modifiers.new('NOISE')
            mod.strength = strength
            mod.scale = scale
            mod.offset = offset
            return mod
    return None


def keyframe(obj, data_path, frame, value=None, index=-1):
    """
    Set a value (optional) and insert a keyframe.

    Dotted paths such as "data.energy" are resolved to the OWNING datablock
    first (modern Blender rejects keyframe paths that span ID blocks), so
    the key lands on e.g. the Light datablock rather than the object.
    """
    target = obj
    parts = data_path.split(".")
    for part in parts[:-1]:
        target = getattr(target, part)
    attr = parts[-1]
    if value is not None:
        if index >= 0:
            getattr(target, attr)[index] = value
        else:
            setattr(target, attr, value)
    target.keyframe_insert(data_path=attr, frame=frame, index=index)


# ============================================================================
#  MATERIAL MANAGER  +  AI TEXTURE SYSTEM
# ============================================================================
#  Every material is a Principled-BSDF PBR setup built procedurally, with
#  automatic hookup of any AI-generated texture maps (albedo / roughness /
#  metallic / normal / displacement) discovered in the Textures/ folder tree:
#
#      Textures/
#      ├── wood/        ├── leather/    ├── fabric/    ├── concrete/
#      ├── metal/       ├── food/       ├── decals/    └── weather/
#
#  Each category also gets AI-source subfolders (stable_diffusion/, flux/,
#  midjourney/, local/) that are scanned in priority order.
# ============================================================================

# Filename keywords used to classify texture maps.
MAP_KEYWORDS = {
    "albedo":       ["albedo", "basecolor", "base_color", "diffuse", "color", "col"],
    "roughness":    ["roughness", "rough", "rgh"],
    "metallic":     ["metallic", "metalness", "metal", "mtl"],
    "normal":       ["normal", "nrm", "nor", "normalgl"],
    "displacement": ["displacement", "height", "disp", "bump"],
}

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".tga", ".tif", ".tiff", ".exr", ".webp")


class MaterialManager:
    """
    Central factory + cache for every PBR material in the environment.

    * Builds fully procedural Principled BSDF node trees (no dependencies).
    * Creates the AI texture folder structure + a JSON manifest of expected
      placeholder paths on first run.
    * Discovers AI-generated / library textures and connects them on top of
      the procedural base (image maps override procedural values).
    """

    def __init__(self):
        self.cache = {}
        self.texture_root = os.path.join(project_root(), CONFIG["texture_root"])
        self.texture_index = {}      # {category: {map_type: filepath}}
        self.ensure_texture_folders()
        self.discover_textures()

    # ------------------------------------------------------------------ #
    #  AI TEXTURE SYSTEM
    # ------------------------------------------------------------------ #

    def ensure_texture_folders(self):
        """Create the placeholder folder tree + manifest for AI textures."""
        try:
            manifest = {}
            for category in CONFIG["texture_categories"]:
                cat_dir = os.path.join(self.texture_root, category)
                os.makedirs(cat_dir, exist_ok=True)
                for source in CONFIG["ai_sources"]:
                    os.makedirs(os.path.join(cat_dir, source), exist_ok=True)
                # Advertise the exact filenames the loader will pick up.
                manifest[category] = {
                    map_type: f"{category}/<source>/{category}_{map_type}.png"
                    for map_type in MAP_KEYWORDS
                }
            manifest_path = os.path.join(self.texture_root,
                                         "texture_manifest.json")
            with open(manifest_path, "w") as fh:
                json.dump({
                    "info": "Drop AI-generated textures into these folders; "
                            "they are wired into materials automatically.",
                    "sources": CONFIG["ai_sources"],
                    "expected": manifest,
                }, fh, indent=2)
            log(f"Texture tree ready at: {self.texture_root}")
        except OSError as exc:
            warn(f"Could not create texture folders: {exc}")

    def discover_textures(self):
        """
        Scan every category folder (AI-source subfolders first, then the
        category root) and index the best candidate file per map type.
        """
        self.texture_index = {}
        if not os.path.isdir(self.texture_root):
            return
        for category in CONFIG["texture_categories"]:
            cat_dir = os.path.join(self.texture_root, category)
            if not os.path.isdir(cat_dir):
                continue
            found = {}
            search_dirs = [os.path.join(cat_dir, s) for s in CONFIG["ai_sources"]]
            search_dirs.append(cat_dir)
            for directory in search_dirs:
                if not os.path.isdir(directory):
                    continue
                for fname in sorted(os.listdir(directory)):
                    if not fname.lower().endswith(IMAGE_EXTENSIONS):
                        continue
                    lower = fname.lower()
                    for map_type, keywords in MAP_KEYWORDS.items():
                        if map_type in found:
                            continue
                        if any(kw in lower for kw in keywords):
                            found[map_type] = os.path.join(directory, fname)
            if found:
                self.texture_index[category] = found
                log(f"Discovered {len(found)} texture map(s) for '{category}'")

    # Dedicated loader entry points per AI source (identical mechanics —
    # they only constrain which subfolder is searched).
    def load_stable_diffusion_texture(self, category, map_type):
        return self._load_from_source(category, map_type, "stable_diffusion")

    def load_flux_texture(self, category, map_type):
        return self._load_from_source(category, map_type, "flux")

    def load_midjourney_texture(self, category, map_type):
        return self._load_from_source(category, map_type, "midjourney")

    def load_local_texture(self, category, map_type):
        return self._load_from_source(category, map_type, "local")

    def _load_from_source(self, category, map_type, source):
        """Find + load an image for (category, map_type) from one AI source."""
        directory = os.path.join(self.texture_root, category, source)
        if not os.path.isdir(directory):
            return None
        keywords = MAP_KEYWORDS.get(map_type, [map_type])
        for fname in sorted(os.listdir(directory)):
            lower = fname.lower()
            if lower.endswith(IMAGE_EXTENSIONS) and any(k in lower for k in keywords):
                return self._load_image(os.path.join(directory, fname))
        return None

    def _load_image(self, path):
        """Load an image datablock once (re-using it on repeat calls)."""
        for img in bpy.data.images:
            if bpy.path.abspath(img.filepath) == os.path.abspath(path):
                return img
        try:
            return bpy.data.images.load(path)
        except RuntimeError as exc:
            warn(f"Failed to load texture {path}: {exc}")
            return None

    def attach_texture_maps(self, mat, category, uv_scale=1.0):
        """
        Wire any discovered texture maps of `category` into the material's
        Principled BSDF, overriding the procedural inputs.
        """
        maps = self.texture_index.get(category)
        if not maps:
            return False
        nt = mat.node_tree
        bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        out = next((n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'), None)
        if bsdf is None or out is None:
            return False

        tex_coord = new_node(nt, 'ShaderNodeTexCoord', (-1400, 0))
        mapping = new_node(nt, 'ShaderNodeMapping', (-1200, 0))
        mapping.inputs['Scale'].default_value = (uv_scale, uv_scale, uv_scale)
        nt.links.new(tex_coord.outputs['UV'], mapping.inputs['Vector'])

        y = 400
        for map_type, path in maps.items():
            img = self._load_image(path)
            if img is None:
                continue
            tex = new_node(nt, 'ShaderNodeTexImage', (-950, y))
            tex.image = img
            tex.label = f"{category}_{map_type}"
            nt.links.new(mapping.outputs['Vector'], tex.inputs['Vector'])
            y -= 320

            if map_type == "albedo":
                nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
            elif map_type == "roughness":
                img.colorspace_settings.name = 'Non-Color'
                nt.links.new(tex.outputs['Color'], bsdf.inputs['Roughness'])
            elif map_type == "metallic":
                img.colorspace_settings.name = 'Non-Color'
                nt.links.new(tex.outputs['Color'], bsdf.inputs['Metallic'])
            elif map_type == "normal":
                img.colorspace_settings.name = 'Non-Color'
                nmap = new_node(nt, 'ShaderNodeNormalMap', (-650, y + 160))
                nt.links.new(tex.outputs['Color'], nmap.inputs['Color'])
                nt.links.new(nmap.outputs['Normal'], bsdf.inputs['Normal'])
            elif map_type == "displacement":
                img.colorspace_settings.name = 'Non-Color'
                disp = new_node(nt, 'ShaderNodeDisplacement', (-350, -500))
                disp.inputs['Scale'].default_value = 0.03
                nt.links.new(tex.outputs['Color'], disp.inputs['Height'])
                nt.links.new(disp.outputs['Displacement'],
                             out.inputs['Displacement'])
        log(f"Connected AI textures ({category}) -> {mat.name}")
        return True

    # ------------------------------------------------------------------ #
    #  CORE PBR FACTORY
    # ------------------------------------------------------------------ #

    def _base(self, name):
        """
        Create (or fetch from cache) a material with a fresh Principled BSDF
        node tree.  Returns (mat, node_tree, bsdf, output) — or the cached
        material with Nones when it already exists.
        """
        if name in self.cache:
            return self.cache[name], None, None, None
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        out = new_node(nt, 'ShaderNodeOutputMaterial', (300, 0))
        bsdf = new_node(nt, 'ShaderNodeBsdfPrincipled', (0, 0))
        nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
        self.cache[name] = mat
        return mat, nt, bsdf, out

    def create_pbr(self, name, base_color=(0.8, 0.8, 0.8, 1.0), roughness=0.5,
                   metallic=0.0, texture_category=None, uv_scale=1.0):
        """Generic flat PBR material with optional AI texture hookup."""
        mat, nt, bsdf, out = self._base(name)
        if nt is None:
            return mat
        set_input(bsdf, 'Base Color', base_color)
        set_input(bsdf, 'Roughness', roughness)
        set_input(bsdf, 'Metallic', metallic)
        if texture_category:
            self.attach_texture_maps(mat, texture_category, uv_scale)
        return mat

    def _add_bump_from(self, nt, bsdf, source_socket, strength=0.15):
        """Convenience: pipe a scalar texture output into a bump node."""
        bump = new_node(nt, 'ShaderNodeBump', (-250, -350))
        bump.inputs['Strength'].default_value = strength
        nt.links.new(source_socket, bump.inputs['Height'])
        nt.links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
        return bump

    # ------------------------------------------------------------------ #
    #  WOOD
    # ------------------------------------------------------------------ #

    def wood(self, name, color_light=(0.42, 0.26, 0.14, 1.0),
             color_dark=(0.18, 0.09, 0.045, 1.0), roughness=0.35,
             grain_scale=4.0, plank=False):
        """Procedural wood: wave grain + noise breakup + bump, PBR clearcoat."""
        mat, nt, bsdf, out = self._base(name)
        if nt is None:
            return mat

        coord = new_node(nt, 'ShaderNodeTexCoord', (-1300, 0))
        mapping = new_node(nt, 'ShaderNodeMapping', (-1100, 0))
        # Stretch the grain strongly along one axis for a planked look.
        mapping.inputs['Scale'].default_value = (1.0, 8.0 if plank else 3.0, 1.0)
        nt.links.new(coord.outputs['Object'], mapping.inputs['Vector'])

        wave = new_node(nt, 'ShaderNodeTexWave', (-900, 150))
        wave.inputs['Scale'].default_value = grain_scale
        wave.inputs['Distortion'].default_value = 6.0
        wave.inputs['Detail'].default_value = 3.0
        nt.links.new(mapping.outputs['Vector'], wave.inputs['Vector'])

        noise = new_node(nt, 'ShaderNodeTexNoise', (-900, -150))
        noise.inputs['Scale'].default_value = grain_scale * 6.0
        noise.inputs['Detail'].default_value = 8.0
        nt.links.new(mapping.outputs['Vector'], noise.inputs['Vector'])

        mix_grain = new_node(nt, 'ShaderNodeMix', (-650, 100))
        mix_grain.data_type = 'RGBA'
        mix_grain.inputs['Factor'].default_value = 0.35
        nt.links.new(wave.outputs['Color'], mix_grain.inputs[6])   # A
        nt.links.new(noise.outputs['Fac'], mix_grain.inputs[7])    # B

        ramp = new_node(nt, 'ShaderNodeValToRGB', (-450, 100))
        ramp.color_ramp.elements[0].color = color_dark
        ramp.color_ramp.elements[1].color = color_light
        nt.links.new(mix_grain.outputs[2], ramp.inputs['Fac'])
        nt.links.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])

        # Roughness variation follows the grain (worn varnish feel).
        rough_ramp = new_node(nt, 'ShaderNodeMapRange', (-450, -200))
        rough_ramp.inputs['To Min'].default_value = max(0.05, roughness - 0.12)
        rough_ramp.inputs['To Max'].default_value = min(1.0, roughness + 0.15)
        nt.links.new(noise.outputs['Fac'], rough_ramp.inputs['Value'])
        nt.links.new(rough_ramp.outputs['Result'], bsdf.inputs['Roughness'])

        self._add_bump_from(nt, bsdf, wave.outputs['Color'], strength=0.10)
        set_input(bsdf, ['Coat Weight', 'Clearcoat'], 0.15)
        self.attach_texture_maps(mat, "wood")
        return mat

    def wood_floor(self):
        """Warm oak plank flooring (hero surface — close-up ready)."""
        return self.wood("MAT_Wood_Oak_Floor",
                         color_light=(0.46, 0.29, 0.16, 1.0),
                         color_dark=(0.22, 0.12, 0.06, 1.0),
                         roughness=0.28, grain_scale=3.0, plank=True)

    def wood_walnut(self):
        """Dark walnut for table tops and the bar counter face."""
        return self.wood("MAT_Wood_Walnut",
                         color_light=(0.20, 0.11, 0.06, 1.0),
                         color_dark=(0.08, 0.045, 0.025, 1.0),
                         roughness=0.30, grain_scale=5.0)

    def wood_paneling(self):
        """Mid-tone vertical slat paneling for feature walls."""
        return self.wood("MAT_Wood_Paneling",
                         color_light=(0.36, 0.22, 0.12, 1.0),
                         color_dark=(0.16, 0.09, 0.05, 1.0),
                         roughness=0.4, grain_scale=2.0, plank=True)

    # ------------------------------------------------------------------ #
    #  METALS
    # ------------------------------------------------------------------ #

    def metal(self, name, color=(0.85, 0.85, 0.87, 1.0), roughness=0.3,
              anisotropic=0.0):
        """Generic metal with subtle procedural roughness variation."""
        mat, nt, bsdf, out = self._base(name)
        if nt is None:
            return mat
        set_input(bsdf, 'Base Color', color)
        set_input(bsdf, 'Metallic', 1.0)
        set_input(bsdf, 'Roughness', roughness)
        set_input(bsdf, ['Anisotropic'], anisotropic)

        noise = new_node(nt, 'ShaderNodeTexNoise', (-700, -200))
        noise.inputs['Scale'].default_value = 40.0
        rng = new_node(nt, 'ShaderNodeMapRange', (-450, -200))
        rng.inputs['To Min'].default_value = max(0.02, roughness - 0.08)
        rng.inputs['To Max'].default_value = min(1.0, roughness + 0.10)
        nt.links.new(noise.outputs['Fac'], rng.inputs['Value'])
        nt.links.new(rng.outputs['Result'], bsdf.inputs['Roughness'])
        self.attach_texture_maps(mat, "metal")
        return mat

    def metal_brushed(self):
        """Brushed stainless — espresso machine, sink, kitchen gear."""
        return self.metal("MAT_Metal_Brushed", (0.82, 0.82, 0.84, 1.0),
                          roughness=0.32, anisotropic=0.7)

    def metal_black(self):
        """Powder-coated black steel — chair frames, lamp arms, grinders."""
        return self.metal("MAT_Metal_Black", (0.03, 0.03, 0.03, 1.0),
                          roughness=0.45)

    def chrome(self):
        """Polished chrome — faucet, portafilter, trim details."""
        return self.metal("MAT_Chrome", (0.95, 0.95, 0.97, 1.0), roughness=0.06)

    def copper(self):
        """Warm copper accents — pendant shades, kettles."""
        return self.metal("MAT_Copper", (0.90, 0.44, 0.25, 1.0), roughness=0.22)

    # ------------------------------------------------------------------ #
    #  LEATHER / FABRIC
    # ------------------------------------------------------------------ #

    def leather(self, name="MAT_Leather_Brown", color=(0.23, 0.10, 0.05, 1.0)):
        """Worn leather: voronoi cell grain + noise sheen variation."""
        mat, nt, bsdf, out = self._base(name)
        if nt is None:
            return mat
        set_input(bsdf, 'Base Color', color)
        set_input(bsdf, 'Roughness', 0.5)
        set_input(bsdf, ['Sheen Weight', 'Sheen'], 0.15)

        voro = new_node(nt, 'ShaderNodeTexVoronoi', (-800, -250))
        voro.inputs['Scale'].default_value = 120.0
        self._add_bump_from(nt, bsdf, voro.outputs['Distance'], strength=0.06)

        noise = new_node(nt, 'ShaderNodeTexNoise', (-800, 150))
        noise.inputs['Scale'].default_value = 8.0
        rng = new_node(nt, 'ShaderNodeMapRange', (-550, 150))
        rng.inputs['To Min'].default_value = 0.35
        rng.inputs['To Max'].default_value = 0.62
        nt.links.new(noise.outputs['Fac'], rng.inputs['Value'])
        nt.links.new(rng.outputs['Result'], bsdf.inputs['Roughness'])
        self.attach_texture_maps(mat, "leather")
        return mat

    def fabric(self, name, color=(0.35, 0.30, 0.25, 1.0), roughness=0.85):
        """Soft woven fabric: fine wave weave bump + sheen (upholstery)."""
        mat, nt, bsdf, out = self._base(name)
        if nt is None:
            return mat
        set_input(bsdf, 'Base Color', color)
        set_input(bsdf, 'Roughness', roughness)
        set_input(bsdf, ['Sheen Weight', 'Sheen'], 0.6)

        wave = new_node(nt, 'ShaderNodeTexWave', (-800, -250))
        wave.inputs['Scale'].default_value = 300.0
        wave.inputs['Distortion'].default_value = 1.5
        self._add_bump_from(nt, bsdf, wave.outputs['Color'], strength=0.04)
        self.attach_texture_maps(mat, "fabric")
        return mat

    # ------------------------------------------------------------------ #
    #  CERAMIC / STONE / MASONRY
    # ------------------------------------------------------------------ #

    def ceramic(self, name="MAT_Ceramic_White", color=(0.92, 0.90, 0.87, 1.0)):
        """Glazed ceramic for cups, mugs and plates."""
        mat, nt, bsdf, out = self._base(name)
        if nt is None:
            return mat
        set_input(bsdf, 'Base Color', color)
        set_input(bsdf, 'Roughness', 0.12)
        set_input(bsdf, ['Coat Weight', 'Clearcoat'], 0.4)
        set_input(bsdf, ['Subsurface Weight', 'Subsurface'], 0.03)
        self.attach_texture_maps(mat, "ceramic")
        return mat

    def concrete(self, name="MAT_Concrete", color=(0.42, 0.42, 0.41, 1.0)):
        """Concrete with noise mottling, bump and true displacement output."""
        mat, nt, bsdf, out = self._base(name)
        if nt is None:
            return mat
        set_input(bsdf, 'Roughness', 0.8)

        noise = new_node(nt, 'ShaderNodeTexNoise', (-900, 100))
        noise.inputs['Scale'].default_value = 9.0
        noise.inputs['Detail'].default_value = 10.0

        ramp = new_node(nt, 'ShaderNodeValToRGB', (-650, 100))
        ramp.color_ramp.elements[0].color = (color[0] * 0.7, color[1] * 0.7,
                                             color[2] * 0.7, 1.0)
        ramp.color_ramp.elements[1].color = color
        nt.links.new(noise.outputs['Fac'], ramp.inputs['Fac'])
        nt.links.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])

        self._add_bump_from(nt, bsdf, noise.outputs['Fac'], strength=0.12)

        # Real displacement channel (Cycles 'displacement + bump' capable).
        disp = new_node(nt, 'ShaderNodeDisplacement', (0, -400))
        disp.inputs['Scale'].default_value = 0.012
        nt.links.new(noise.outputs['Fac'], disp.inputs['Height'])
        nt.links.new(disp.outputs['Displacement'], out.inputs['Displacement'])
        self.attach_texture_maps(mat, "concrete")
        return mat

    def plaster(self):
        """Warm off-white interior plaster walls."""
        return self.create_pbr("MAT_Plaster_Warm",
                               base_color=(0.82, 0.76, 0.68, 1.0),
                               roughness=0.9, texture_category=None)

    def brick(self, name="MAT_Brick_Red", color=(0.40, 0.16, 0.10, 1.0)):
        """Brick facade: brick-texture pattern with mortar lines + bump."""
        mat, nt, bsdf, out = self._base(name)
        if nt is None:
            return mat
        coord = new_node(nt, 'ShaderNodeTexCoord', (-1200, 0))
        brick = new_node(nt, 'ShaderNodeTexBrick', (-900, 0))
        brick.inputs['Scale'].default_value = 6.0
        brick.inputs['Color1'].default_value = color
        brick.inputs['Color2'].default_value = (color[0] * 0.75, color[1] * 0.75,
                                                color[2] * 0.75, 1.0)
        brick.inputs['Mortar'].default_value = (0.55, 0.52, 0.48, 1.0)
        brick.inputs['Mortar Size'].default_value = 0.012
        nt.links.new(coord.outputs['Object'], brick.inputs['Vector'])
        nt.links.new(brick.outputs['Color'], bsdf.inputs['Base Color'])
        set_input(bsdf, 'Roughness', 0.85)
        self._add_bump_from(nt, bsdf, brick.outputs['Fac'], strength=0.25)
        return mat

    def marble(self):
        """Marble bar counter top (veined noise)."""
        mat, nt, bsdf, out = self._base("MAT_Marble_Counter")
        if nt is None:
            return mat
        noise = new_node(nt, 'ShaderNodeTexNoise', (-900, 0))
        noise.inputs['Scale'].default_value = 2.5
        noise.inputs['Detail'].default_value = 12.0
        noise.inputs['Distortion'].default_value = 1.2
        ramp = new_node(nt, 'ShaderNodeValToRGB', (-650, 0))
        ramp.color_ramp.elements[0].position = 0.42
        ramp.color_ramp.elements[0].color = (0.35, 0.35, 0.37, 1.0)
        ramp.color_ramp.elements[1].position = 0.55
        ramp.color_ramp.elements[1].color = (0.90, 0.89, 0.87, 1.0)
        nt.links.new(noise.outputs['Fac'], ramp.inputs['Fac'])
        nt.links.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])
        set_input(bsdf, 'Roughness', 0.1)
        set_input(bsdf, ['Coat Weight', 'Clearcoat'], 0.5)
        return mat

    # ------------------------------------------------------------------ #
    #  GLASS  (including the hero rainy window glass)
    # ------------------------------------------------------------------ #

    def glass_clear(self):
        """Simple architectural glass for the pastry display case."""
        mat, nt, bsdf, out = self._base("MAT_Glass_Clear")
        if nt is None:
            return mat
        set_input(bsdf, 'Base Color', (1.0, 1.0, 1.0, 1.0))
        set_input(bsdf, 'Roughness', 0.02)
        set_input(bsdf, ['Transmission Weight', 'Transmission'], 1.0)
        set_input(bsdf, 'IOR', 1.45)
        return mat

    def glass_rainy(self):
        """
        Physically-based storm window glass:
          * full transmission + accurate IOR (real refraction / reflections)
          * droplet bump   -> voronoi cells masked by noise
          * water streaks  -> heavily Y-stretched wave bands
          * condensation   -> roughness rises toward the bottom of the pane
        """
        mat, nt, bsdf, out = self._base("MAT_Glass_Window_Rainy")
        if nt is None:
            return mat
        set_input(bsdf, 'Base Color', (1.0, 1.0, 1.0, 1.0))
        set_input(bsdf, ['Transmission Weight', 'Transmission'], 1.0)
        set_input(bsdf, 'IOR', 1.45)

        coord = new_node(nt, 'ShaderNodeTexCoord', (-1600, 0))

        # --- droplets: sparse voronoi bumps ------------------------------
        voro = new_node(nt, 'ShaderNodeTexVoronoi', (-1300, 300))
        voro.inputs['Scale'].default_value = 90.0
        nt.links.new(coord.outputs['Object'], voro.inputs['Vector'])
        drop_ramp = new_node(nt, 'ShaderNodeValToRGB', (-1050, 300))
        drop_ramp.color_ramp.elements[0].position = 0.0
        drop_ramp.color_ramp.elements[1].position = 0.12   # tight round dots
        nt.links.new(voro.outputs['Distance'], drop_ramp.inputs['Fac'])
        drop_invert = new_node(nt, 'ShaderNodeInvert', (-850, 300))
        nt.links.new(drop_ramp.outputs['Color'], drop_invert.inputs['Color'])

        # --- streaks: vertical stretched wave bands ----------------------
        streak_map = new_node(nt, 'ShaderNodeMapping', (-1300, 0))
        streak_map.inputs['Scale'].default_value = (25.0, 0.4, 1.0)
        nt.links.new(coord.outputs['Object'], streak_map.inputs['Vector'])
        streaks = new_node(nt, 'ShaderNodeTexNoise', (-1050, 0))
        streaks.inputs['Scale'].default_value = 2.0
        streaks.inputs['Detail'].default_value = 6.0
        nt.links.new(streak_map.outputs['Vector'], streaks.inputs['Vector'])
        streak_ramp = new_node(nt, 'ShaderNodeValToRGB', (-850, 0))
        streak_ramp.color_ramp.elements[0].position = 0.55
        streak_ramp.color_ramp.elements[1].position = 0.62
        nt.links.new(streaks.outputs['Fac'], streak_ramp.inputs['Fac'])

        # --- combine droplet + streak height field -----------------------
        water_mix = new_node(nt, 'ShaderNodeMath', (-650, 150))
        water_mix.operation = 'MAXIMUM'
        nt.links.new(drop_invert.outputs['Color'], water_mix.inputs[0])
        nt.links.new(streak_ramp.outputs['Color'], water_mix.inputs[1])

        bump = new_node(nt, 'ShaderNodeBump', (-400, 100))
        bump.inputs['Strength'].default_value = 0.55
        nt.links.new(water_mix.outputs['Value'], bump.inputs['Height'])
        nt.links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])

        # --- condensation: hazy roughness toward the pane bottom ---------
        sep = new_node(nt, 'ShaderNodeSeparateXYZ', (-1300, -350))
        nt.links.new(coord.outputs['Object'], sep.inputs['Vector'])
        cond_rng = new_node(nt, 'ShaderNodeMapRange', (-1050, -350))
        cond_rng.inputs['From Min'].default_value = -0.5   # object bottom
        cond_rng.inputs['From Max'].default_value = 0.3
        cond_rng.inputs['To Min'].default_value = 0.32     # hazy
        cond_rng.inputs['To Max'].default_value = 0.02     # clear
        nt.links.new(sep.outputs['Z'], cond_rng.inputs['Value'])

        cond_noise = new_node(nt, 'ShaderNodeTexNoise', (-1050, -600))
        cond_noise.inputs['Scale'].default_value = 6.0
        cond_mix = new_node(nt, 'ShaderNodeMath', (-800, -420))
        cond_mix.operation = 'MULTIPLY'
        nt.links.new(cond_rng.outputs['Result'], cond_mix.inputs[0])
        nt.links.new(cond_noise.outputs['Fac'], cond_mix.inputs[1])
        nt.links.new(cond_mix.outputs['Value'], bsdf.inputs['Roughness'])
        return mat

    def rain_droplet(self):
        """Material for individual rain drop / streak meshes on the glass."""
        mat, nt, bsdf, out = self._base("MAT_Rain_Droplet")
        if nt is None:
            return mat
        set_input(bsdf, 'Base Color', (0.9, 0.95, 1.0, 1.0))
        set_input(bsdf, 'Roughness', 0.02)
        set_input(bsdf, ['Transmission Weight', 'Transmission'], 1.0)
        set_input(bsdf, 'IOR', 1.33)
        return mat

    def puddle(self):
        """Mirror-like puddle water with gentle animated ripple normals."""
        mat, nt, bsdf, out = self._base("MAT_Puddle")
        if nt is None:
            return mat
        set_input(bsdf, 'Base Color', (0.02, 0.025, 0.03, 1.0))
        set_input(bsdf, 'Roughness', 0.02)
        set_input(bsdf, 'Metallic', 0.0)
        set_input(bsdf, 'IOR', 1.33)

        noise = new_node(nt, 'ShaderNodeTexNoise', (-700, -250))
        noise.noise_dimensions = '4D'
        noise.inputs['Scale'].default_value = 14.0
        # Animate the 4th dimension => rippling water surface.
        w_input = noise.inputs['W']
        w_input.default_value = 0.0
        w_input.keyframe_insert('default_value', frame=FRAME_START)
        w_input.default_value = 8.0
        w_input.keyframe_insert('default_value', frame=FRAME_END)
        self._add_bump_from(nt, bsdf, noise.outputs['Fac'], strength=0.08)
        return mat

    # ------------------------------------------------------------------ #
    #  WET STREET SURFACES
    # ------------------------------------------------------------------ #

    def asphalt_wet(self):
        """Rain-soaked asphalt: dark, noisy, with glossy wet patches."""
        mat, nt, bsdf, out = self._base("MAT_Asphalt_Wet")
        if nt is None:
            return mat
        noise = new_node(nt, 'ShaderNodeTexNoise', (-900, 100))
        noise.inputs['Scale'].default_value = 60.0
        noise.inputs['Detail'].default_value = 10.0
        ramp = new_node(nt, 'ShaderNodeValToRGB', (-650, 100))
        ramp.color_ramp.elements[0].color = (0.010, 0.010, 0.012, 1.0)
        ramp.color_ramp.elements[1].color = (0.045, 0.045, 0.05, 1.0)
        nt.links.new(noise.outputs['Fac'], ramp.inputs['Fac'])
        nt.links.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])

        # Large-scale wetness mask drives glossy pooling between rough spots.
        wet = new_node(nt, 'ShaderNodeTexNoise', (-900, -200))
        wet.inputs['Scale'].default_value = 1.4
        wet_rng = new_node(nt, 'ShaderNodeMapRange', (-650, -200))
        wet_rng.inputs['To Min'].default_value = 0.05   # wet & reflective
        wet_rng.inputs['To Max'].default_value = 0.55   # merely damp
        nt.links.new(wet.outputs['Fac'], wet_rng.inputs['Value'])
        nt.links.new(wet_rng.outputs['Result'], bsdf.inputs['Roughness'])
        self._add_bump_from(nt, bsdf, noise.outputs['Fac'], strength=0.10)
        self.attach_texture_maps(mat, "weather")
        return mat

    def pavement_wet(self):
        """Wet concrete sidewalk with slab-line brick pattern."""
        mat, nt, bsdf, out = self._base("MAT_Pavement_Wet")
        if nt is None:
            return mat
        coord = new_node(nt, 'ShaderNodeTexCoord', (-1200, 0))
        slabs = new_node(nt, 'ShaderNodeTexBrick', (-900, 0))
        slabs.inputs['Scale'].default_value = 0.7
        slabs.inputs['Color1'].default_value = (0.16, 0.16, 0.165, 1.0)
        slabs.inputs['Color2'].default_value = (0.13, 0.13, 0.135, 1.0)
        slabs.inputs['Mortar'].default_value = (0.05, 0.05, 0.055, 1.0)
        slabs.inputs['Mortar Size'].default_value = 0.01
        nt.links.new(coord.outputs['Object'], slabs.inputs['Vector'])
        nt.links.new(slabs.outputs['Color'], bsdf.inputs['Base Color'])
        set_input(bsdf, 'Roughness', 0.22)   # rain-glazed
        self._add_bump_from(nt, bsdf, slabs.outputs['Fac'], strength=0.15)
        return mat

    # ------------------------------------------------------------------ #
    #  PAPER / FOOD / MISC
    # ------------------------------------------------------------------ #

    def paper(self, name="MAT_Paper", color=(0.85, 0.80, 0.72, 1.0)):
        """Kraft paper: menus, napkins, coffee bags, book pages."""
        return self.create_pbr(name, base_color=color, roughness=0.95)

    def chalkboard(self):
        """Dark matte chalkboard for the menu boards."""
        return self.create_pbr("MAT_Chalkboard",
                               base_color=(0.035, 0.04, 0.038, 1.0),
                               roughness=0.9)

    def food(self, name, color, roughness=0.55, subsurface=0.15):
        """Baked-goods material with subsurface scattering for realism."""
        mat, nt, bsdf, out = self._base(name)
        if nt is None:
            return mat
        set_input(bsdf, 'Base Color', color)
        set_input(bsdf, 'Roughness', roughness)
        set_input(bsdf, ['Subsurface Weight', 'Subsurface'], subsurface)
        set_input(bsdf, ['Subsurface Radius'], (0.02, 0.012, 0.006))
        noise = new_node(nt, 'ShaderNodeTexNoise', (-700, -250))
        noise.inputs['Scale'].default_value = 90.0
        self._add_bump_from(nt, bsdf, noise.outputs['Fac'], strength=0.10)
        self.attach_texture_maps(mat, "food")
        return mat

    def coffee_liquid(self):
        """Dark reflective coffee surface inside cups."""
        mat, nt, bsdf, out = self._base("MAT_Coffee_Liquid")
        if nt is None:
            return mat
        set_input(bsdf, 'Base Color', (0.04, 0.02, 0.01, 1.0))
        set_input(bsdf, 'Roughness', 0.05)
        set_input(bsdf, 'IOR', 1.34)
        return mat

    def candle_wax(self):
        """Translucent warm candle wax."""
        mat, nt, bsdf, out = self._base("MAT_Candle_Wax")
        if nt is None:
            return mat
        set_input(bsdf, 'Base Color', (0.93, 0.88, 0.78, 1.0))
        set_input(bsdf, 'Roughness', 0.35)
        set_input(bsdf, ['Subsurface Weight', 'Subsurface'], 0.3)
        return mat

    def emission(self, name, color=(1.0, 0.7, 0.4), strength=5.0):
        """Pure emitter (bulbs, signs, lit windows, flames)."""
        if name in self.cache:
            return self.cache[name]
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        out = new_node(nt, 'ShaderNodeOutputMaterial', (300, 0))
        emit = new_node(nt, 'ShaderNodeEmission', (0, 0))
        emit.inputs['Color'].default_value = (*color, 1.0)
        emit.inputs['Strength'].default_value = strength
        nt.links.new(emit.outputs['Emission'], out.inputs['Surface'])
        self.cache[name] = mat
        return mat

    def steam_volume(self):
        """
        Animated volumetric steam: noise-modulated density drifting upward
        (mapping location is keyframed by the AnimationSystem).
        """
        if "MAT_Steam_Volume" in self.cache:
            return self.cache["MAT_Steam_Volume"]
        mat = bpy.data.materials.new("MAT_Steam_Volume")
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        out = new_node(nt, 'ShaderNodeOutputMaterial', (500, 0))
        vol = new_node(nt, 'ShaderNodeVolumePrincipled', (200, 0))
        set_input(vol, 'Color', (0.9, 0.9, 0.92, 1.0))
        set_input(vol, 'Density', 0.0)   # driven by the noise below

        coord = new_node(nt, 'ShaderNodeTexCoord', (-900, 0))
        mapping = new_node(nt, 'ShaderNodeMapping', (-700, 0))
        mapping.name = "SteamDrift"      # AnimationSystem keyframes this node
        nt.links.new(coord.outputs['Object'], mapping.inputs['Vector'])

        noise = new_node(nt, 'ShaderNodeTexNoise', (-500, 0))
        noise.inputs['Scale'].default_value = 4.0
        noise.inputs['Detail'].default_value = 6.0
        nt.links.new(mapping.outputs['Vector'], noise.inputs['Vector'])

        # Fade density toward the top of the (unit) steam volume.
        sep = new_node(nt, 'ShaderNodeSeparateXYZ', (-700, -300))
        nt.links.new(coord.outputs['Object'], sep.inputs['Vector'])
        fade = new_node(nt, 'ShaderNodeMapRange', (-500, -300))
        fade.inputs['From Min'].default_value = -0.5
        fade.inputs['From Max'].default_value = 0.5
        fade.inputs['To Min'].default_value = 1.0
        fade.inputs['To Max'].default_value = 0.0
        nt.links.new(sep.outputs['Z'], fade.inputs['Value'])

        dens = new_node(nt, 'ShaderNodeMath', (-250, -100))
        dens.operation = 'MULTIPLY'
        nt.links.new(noise.outputs['Fac'], dens.inputs[0])
        nt.links.new(fade.outputs['Result'], dens.inputs[1])
        scale = new_node(nt, 'ShaderNodeMath', (-50, -100))
        scale.operation = 'MULTIPLY'
        scale.inputs[1].default_value = 1.4   # overall steam density
        nt.links.new(dens.outputs['Value'], scale.inputs[0])
        nt.links.new(scale.outputs['Value'], vol.inputs['Density'])
        nt.links.new(vol.outputs['Volume'], out.inputs['Volume'])
        self.cache["MAT_Steam_Volume"] = mat
        return mat

    def atmosphere_volume(self):
        """Ultra-thin scatter volume for the exterior storm atmosphere."""
        if "MAT_Atmosphere" in self.cache:
            return self.cache["MAT_Atmosphere"]
        mat = bpy.data.materials.new("MAT_Atmosphere")
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        out = new_node(nt, 'ShaderNodeOutputMaterial', (300, 0))
        vol = new_node(nt, 'ShaderNodeVolumeScatter', (0, 0))
        vol.inputs['Color'].default_value = (0.65, 0.72, 0.8, 1.0)
        vol.inputs['Density'].default_value = 0.006
        nt.links.new(vol.outputs['Volume'], out.inputs['Volume'])
        self.cache["MAT_Atmosphere"] = mat
        return mat

    # ------------------------------------------------------------------ #
    #  EXTERIOR / VEHICLES / VEGETATION
    # ------------------------------------------------------------------ #

    def facade(self, index):
        """Randomized building facade material (brick or painted concrete)."""
        name = f"MAT_Facade_{index:02d}"
        if name in self.cache:
            return self.cache[name]
        if RNG.random() < 0.5:
            hue = RNG.uniform(0.3, 0.5)
            return self.brick(name, color=(hue, hue * 0.42, hue * 0.28, 1.0))
        v = RNG.uniform(0.18, 0.45)
        tint = (v * RNG.uniform(0.9, 1.1), v * RNG.uniform(0.9, 1.05), v, 1.0)
        return self.concrete(name, color=tint)

    def window_lit(self):
        """Warm glowing apartment window (seen across the street)."""
        return self.emission("MAT_Window_Lit", color=(1.0, 0.62, 0.28),
                             strength=9.0)

    def window_dark(self):
        """Unlit reflective building window."""
        return self.create_pbr("MAT_Window_Dark",
                               base_color=(0.02, 0.03, 0.045, 1.0),
                               roughness=0.06, metallic=0.4)

    def car_paint(self, name, color):
        """Wet car paint with strong clearcoat."""
        mat, nt, bsdf, out = self._base(name)
        if nt is None:
            return mat
        set_input(bsdf, 'Base Color', color)
        set_input(bsdf, 'Metallic', 0.85)
        set_input(bsdf, 'Roughness', 0.18)
        set_input(bsdf, ['Coat Weight', 'Clearcoat'], 1.0)
        set_input(bsdf, ['Coat Roughness', 'Clearcoat Roughness'], 0.03)
        return mat

    def rubber(self):
        """Matte black tire rubber."""
        return self.create_pbr("MAT_Rubber", base_color=(0.015, 0.015, 0.015, 1.0),
                               roughness=0.9)

    def plant_leaf(self):
        """Plant foliage with translucent subsurface."""
        mat, nt, bsdf, out = self._base("MAT_Plant_Leaf")
        if nt is None:
            return mat
        set_input(bsdf, 'Base Color', (0.05, 0.22, 0.06, 1.0))
        set_input(bsdf, 'Roughness', 0.45)
        set_input(bsdf, ['Subsurface Weight', 'Subsurface'], 0.1)
        noise = new_node(nt, 'ShaderNodeTexNoise', (-700, -250))
        noise.inputs['Scale'].default_value = 15.0
        self._add_bump_from(nt, bsdf, noise.outputs['Fac'], strength=0.05)
        return mat

    def terracotta(self):
        """Terracotta plant pots."""
        return self.create_pbr("MAT_Terracotta",
                               base_color=(0.53, 0.26, 0.15, 1.0),
                               roughness=0.75)

    def book_covers(self, count=8):
        """A small palette of randomized cloth book-cover materials."""
        mats = []
        palette = [(0.45, 0.12, 0.10), (0.10, 0.22, 0.35), (0.13, 0.30, 0.16),
                   (0.55, 0.42, 0.16), (0.30, 0.15, 0.35), (0.60, 0.55, 0.48),
                   (0.15, 0.15, 0.18), (0.50, 0.28, 0.12)]
        for i in range(count):
            base = palette[i % len(palette)]
            jit = lambda v: max(0.02, min(1.0, v * RNG.uniform(0.8, 1.2)))
            mats.append(self.fabric(f"MAT_Book_Cover_{i:02d}",
                                    color=(jit(base[0]), jit(base[1]),
                                           jit(base[2]), 1.0),
                                    roughness=0.8))
        return mats

    def curtain(self):
        """Heavy linen curtain fabric."""
        return self.fabric("MAT_Curtain_Linen",
                           color=(0.55, 0.47, 0.38, 1.0), roughness=0.9)

    def rug(self):
        """Deep patterned area rug (checker weave tint)."""
        mat, nt, bsdf, out = self._base("MAT_Rug")
        if nt is None:
            return mat
        coord = new_node(nt, 'ShaderNodeTexCoord', (-1100, 0))
        checker = new_node(nt, 'ShaderNodeTexChecker', (-850, 0))
        checker.inputs['Scale'].default_value = 14.0
        checker.inputs['Color1'].default_value = (0.30, 0.10, 0.08, 1.0)
        checker.inputs['Color2'].default_value = (0.16, 0.13, 0.20, 1.0)
        nt.links.new(coord.outputs['Object'], checker.inputs['Vector'])
        nt.links.new(checker.outputs['Color'], bsdf.inputs['Base Color'])
        set_input(bsdf, 'Roughness', 0.95)
        set_input(bsdf, ['Sheen Weight', 'Sheen'], 0.8)
        noise = new_node(nt, 'ShaderNodeTexNoise', (-850, -300))
        noise.inputs['Scale'].default_value = 220.0
        self._add_bump_from(nt, bsdf, noise.outputs['Fac'], strength=0.15)
        return mat

    def dust_mote(self):
        """Barely-there translucent dust particle material."""
        mat, nt, bsdf, out = self._base("MAT_Dust_Mote")
        if nt is None:
            return mat
        set_input(bsdf, 'Base Color', (0.9, 0.85, 0.75, 1.0))
        set_input(bsdf, 'Roughness', 1.0)
        set_input(bsdf, ['Emission Color'], (0.9, 0.85, 0.75, 1.0))
        set_input(bsdf, ['Emission Strength'], 0.4)
        return mat


# ============================================================================
#  ENVIRONMENT BUILDER  (architecture + exterior street)
# ============================================================================
#  Scene layout (meters, Z-up):
#    * Shop interior:  x ∈ [-8, 8],  y ∈ [-6, 6],  floor at z = 0.
#    * Front wall (floor-to-ceiling glass + door) at y = +6, facing street.
#    * Near sidewalk / road / far sidewalk / building row extend in +Y.
#  Exterior props are prefixed EXT_ so the optimizer can treat them as
#  background geometry (aggressive LODs — only seen through the windows).
# ============================================================================

class EnvironmentBuilder:
    """Builds all architecture and the exterior city street."""

    def __init__(self, materials):
        self.mat = materials
        s = CONFIG["shop"]
        self.W = s["width"]          # 16
        self.D = s["depth"]          # 12
        self.H = s["height"]         # 4.2
        self.T = s["wall_thickness"]

        root = get_or_create_collection("CoffeeShop_Environment")
        self.arch_coll = get_or_create_collection("Architecture", root)
        self.ext_coll = get_or_create_collection("Exterior", root)

        # Shared with other systems:
        self.window_panes = []        # glass panes (rain droplet targets)
        self.collision_surfaces = []  # meshes that should stop rain particles
        self.street_light_heads = []  # (x, y, z) for LightingSystem
        self.lit_sign_positions = []  # emissive sign glow points

    # ------------------------------------------------------------------ #
    #  MASTER BUILD
    # ------------------------------------------------------------------ #

    def build(self):
        """Construct all architecture, then the exterior street."""
        self.build_floor()
        self.build_ceiling_and_roof()
        self.build_walls()
        self.build_window_wall()
        self.build_columns()
        self.build_trim_and_baseboards()
        self.build_wood_paneling()
        self.build_exterior_street()
        log("EnvironmentBuilder complete.")

    # ------------------------------------------------------------------ #
    #  INTERIOR ARCHITECTURE
    # ------------------------------------------------------------------ #

    def build_floor(self):
        """Oak plank floor slab + concrete sub-slab under the shop."""
        floor = add_cube("ARCH_Floor_Wood",
                         size=(self.W, self.D, 0.08),
                         location=(0, 0, -0.04),
                         collection=self.arch_coll,
                         material=self.mat.wood_floor())
        self.collision_surfaces.append(floor)

        add_cube("ARCH_Floor_Slab",
                 size=(self.W + 1.0, self.D + 1.0, 0.30),
                 location=(0, 0, -0.25),
                 collection=self.arch_coll,
                 material=self.mat.concrete())

    def build_ceiling_and_roof(self):
        """Ceiling slab, exposed wooden beams, and the exterior roof."""
        add_cube("ARCH_Ceiling",
                 size=(self.W, self.D, 0.12),
                 location=(0, 0, self.H + 0.06),
                 collection=self.arch_coll,
                 material=self.mat.plaster())

        # Exposed structural beams give the ceiling depth and warmth.
        beam_mat = self.mat.wood_walnut()
        for i in range(5):
            x = -self.W / 2 + (i + 0.5) * (self.W / 5)
            beam = add_cube(f"ARCH_Beam_{i:02d}",
                            size=(0.22, self.D - 0.2, 0.30),
                            location=(x, 0, self.H - 0.15),
                            collection=self.arch_coll, material=beam_mat)
            add_bevel(beam, width=0.015)

        # Exterior roof slab + parapet (also a rain collision surface).
        roof = add_cube("ARCH_Roof",
                        size=(self.W + 0.8, self.D + 0.8, 0.25),
                        location=(0, 0, self.H + 0.25),
                        collection=self.arch_coll,
                        material=self.mat.concrete())
        self.collision_surfaces.append(roof)
        for sign_y, rot in ((self.D / 2 + 0.3, 0),):
            add_cube("ARCH_Roof_Parapet",
                     size=(self.W + 0.8, 0.2, 0.5),
                     location=(0, sign_y, self.H + 0.55),
                     collection=self.arch_coll,
                     material=self.mat.brick("MAT_Brick_Shop",
                                             color=(0.30, 0.14, 0.10, 1.0)))

        # Upper facade above the shop front (the cafe sits under apartments —
        # visible when exterior cameras tilt up).
        upper = add_cube("EXT_Upper_Facade",
                         size=(self.W + 0.8, 0.5, 6.0),
                         location=(0, self.D / 2 + 0.05, self.H + 3.4),
                         collection=self.ext_coll,
                         material=self.mat.brick("MAT_Brick_Shop"))
        self._add_window_grid(upper, face_y=self.D / 2 - 0.19, rows=2, cols=6,
                              z_base=self.H + 1.2, z_step=2.4,
                              x_base=-self.W / 2 + 1.6, x_step=2.6,
                              w=1.2, h=1.6, lit_chance=0.3, facing=-1)

    def build_walls(self):
        """Back wall, two side walls (with brick exterior faces)."""
        wall_mat = self.mat.plaster()
        # Back wall (behind the coffee bar).
        add_cube("ARCH_Wall_Back",
                 size=(self.W + 2 * self.T, self.T, self.H),
                 location=(0, -self.D / 2 - self.T / 2, self.H / 2),
                 collection=self.arch_coll, material=wall_mat)
        # Side walls.
        for sign, tag in ((-1, "West"), (1, "East")):
            add_cube(f"ARCH_Wall_{tag}",
                     size=(self.T, self.D, self.H),
                     location=(sign * (self.W / 2 + self.T / 2), 0, self.H / 2),
                     collection=self.arch_coll, material=wall_mat)
        # Exterior brick shells on the visible outer faces.
        add_cube("EXT_Wall_Back_Brick",
                 size=(self.W + 2 * self.T, 0.06, self.H + 0.5),
                 location=(0, -self.D / 2 - self.T - 0.03, (self.H + 0.5) / 2),
                 collection=self.ext_coll,
                 material=self.mat.brick("MAT_Brick_Shop"))

    def build_window_wall(self):
        """
        Floor-to-ceiling storefront glazing along the front wall:
        header beam, sill, vertical mullions, physically-based rainy glass
        panes, and a glass entrance door on the east side.
        """
        y = self.D / 2 + self.T / 2          # wall centerline (y = 6.15)
        frame_mat = self.mat.metal_black()
        glass_mat = self.mat.glass_rainy()
        door_x = CONFIG["shop"]["door_x"]

        # Header beam + low sill.
        add_cube("ARCH_Window_Header",
                 size=(self.W + 2 * self.T, self.T, 0.35),
                 location=(0, y, self.H - 0.175),
                 collection=self.arch_coll, material=frame_mat)
        add_cube("ARCH_Window_Sill",
                 size=(self.W + 2 * self.T, self.T, 0.12),
                 location=(0, y, 0.06),
                 collection=self.arch_coll, material=frame_mat)

        glass_bottom, glass_top = 0.12, self.H - 0.35
        glass_h = glass_top - glass_bottom
        spacing = CONFIG["shop"]["window_mullion_spacing"]

        # Vertical mullions every `spacing` meters (skipping the door bay).
        xs = []
        x = -self.W / 2
        while x <= self.W / 2 + 0.01:
            xs.append(round(x, 3))
            x += spacing
        door_min, door_max = door_x - 1.0, door_x + 1.0

        for mx in xs:
            add_cube(f"ARCH_Mullion_{mx:+.1f}",
                     size=(0.10, self.T, glass_h),
                     location=(mx, y, glass_bottom + glass_h / 2),
                     collection=self.arch_coll, material=frame_mat)

        # Glass panes between mullions (the door bay gets a door instead).
        for i in range(len(xs) - 1):
            cx = (xs[i] + xs[i + 1]) / 2
            if door_min - 0.1 < cx < door_max + 0.1:
                continue
            pane = add_cube(f"ARCH_Glass_Pane_{i:02d}",
                            size=(spacing - 0.10, 0.02, glass_h),
                            location=(cx, y, glass_bottom + glass_h / 2),
                            collection=self.arch_coll, material=glass_mat)
            self.window_panes.append(pane)

        # --- entrance door (glass door + frame + long pull handle) --------
        add_cube("ARCH_Door_Frame_Top",
                 size=(2.0, self.T, 0.9),
                 location=(door_x, y, glass_top - 0.45),
                 collection=self.arch_coll, material=frame_mat)
        door = add_cube("ARCH_Door_Glass",
                        size=(1.8, 0.03, glass_h - 0.9),
                        location=(door_x, y, glass_bottom + (glass_h - 0.9) / 2),
                        collection=self.arch_coll, material=glass_mat)
        self.window_panes.append(door)
        add_cylinder("ARCH_Door_Handle",
                     radius=0.02, depth=1.1,
                     location=(door_x - 0.7, y - self.T / 2 - 0.05,
                               glass_bottom + 1.1),
                     collection=self.arch_coll, material=self.mat.chrome())

        # Fill the wall stubs left/right of the glazing run.
        add_cube("ARCH_Wall_Front_StubW",
                 size=(self.T, self.T, self.H),
                 location=(-self.W / 2 - self.T / 2, y, self.H / 2),
                 collection=self.arch_coll, material=self.mat.plaster())
        add_cube("ARCH_Wall_Front_StubE",
                 size=(self.T, self.T, self.H),
                 location=(self.W / 2 + self.T / 2, y, self.H / 2),
                 collection=self.arch_coll, material=self.mat.plaster())

    def build_columns(self):
        """Two interior structural columns wrapped in walnut cladding."""
        for i, cx in enumerate((-3.0, 3.0)):
            col = add_cube(f"ARCH_Column_{i:02d}",
                           size=(0.40, 0.40, self.H),
                           location=(cx, 0.5, self.H / 2),
                           collection=self.arch_coll,
                           material=self.mat.wood_walnut())
            add_bevel(col, width=0.02, segments=3)
            # Steel base plate detail.
            add_cube(f"ARCH_Column_Base_{i:02d}",
                     size=(0.5, 0.5, 0.10),
                     location=(cx, 0.5, 0.05),
                     collection=self.arch_coll,
                     material=self.mat.metal_black())

    def build_trim_and_baseboards(self):
        """Baseboards + crown trim on the three solid interior walls."""
        base_mat = self.mat.wood_walnut()
        walls = [
            # (size, location) for back, west, east baseboards
            ((self.W, 0.04, 0.14), (0, -self.D / 2 + 0.02, 0.07)),
            ((0.04, self.D, 0.14), (-self.W / 2 + 0.02, 0, 0.07)),
            ((0.04, self.D, 0.14), (self.W / 2 - 0.02, 0, 0.07)),
        ]
        for i, (size, loc) in enumerate(walls):
            add_cube(f"ARCH_Baseboard_{i:02d}", size=size, location=loc,
                     collection=self.arch_coll, material=base_mat)
            # Matching crown trim at the ceiling line.
            crown_loc = (loc[0], loc[1], self.H - 0.05)
            add_cube(f"ARCH_CrownTrim_{i:02d}", size=(size[0], size[1], 0.10),
                     location=crown_loc, collection=self.arch_coll,
                     material=base_mat)

    def build_wood_paneling(self):
        """Vertical slat feature wall behind the coffee bar (joined mesh)."""
        slat_mat = self.mat.wood_paneling()
        slats = []
        x = -6.0
        while x <= 4.0:
            slat = add_cube("ARCH_Slat",
                            size=(0.06, 0.05, self.H - 0.3),
                            location=(x, -self.D / 2 + 0.05, (self.H - 0.3) / 2 + 0.15),
                            collection=self.arch_coll, material=slat_mat)
            slats.append(slat)
            x += 0.14
        joined = join_objects(slats, "ARCH_Wood_Paneling")
        if joined:
            link_to_collection(joined, self.arch_coll)

    # ------------------------------------------------------------------ #
    #  EXTERIOR STREET
    # ------------------------------------------------------------------ #

    def build_exterior_street(self):
        """Assemble the whole rainy city street visible through the glass."""
        self._build_ground()
        self._build_buildings()
        self._build_street_furniture()
        self._build_vehicles()
        self._build_utility_poles()
        self._build_shop_signage()

    def _build_ground(self):
        """Sidewalks, curbs, wet road and center-line markings."""
        st = CONFIG["street"]
        ex = st["extent_x"]

        def strip(name, y_range, z, height, material):
            y0, y1 = y_range
            obj = add_cube(name, size=(2 * ex, y1 - y0, height),
                           location=(0, (y0 + y1) / 2, z),
                           collection=self.ext_coll, material=material)
            self.collision_surfaces.append(obj)
            return obj

        strip("EXT_Sidewalk_Near", st["sidewalk_near"], 0.05, 0.14,
              self.mat.pavement_wet())
        strip("EXT_Road", st["road"], -0.02, 0.10, self.mat.asphalt_wet())
        strip("EXT_Sidewalk_Far", st["sidewalk_far"], 0.05, 0.14,
              self.mat.pavement_wet())

        # Curbs.
        curb_mat = self.mat.concrete("MAT_Concrete_Curb")
        add_cube("EXT_Curb_Near", size=(2 * ex, 0.15, 0.16),
                 location=(0, st["road"][0] - 0.075, 0.05),
                 collection=self.ext_coll, material=curb_mat)
        add_cube("EXT_Curb_Far", size=(2 * ex, 0.15, 0.16),
                 location=(0, st["road"][1] + 0.075, 0.05),
                 collection=self.ext_coll, material=curb_mat)

        # Dashed center line.
        line_mat = self.mat.create_pbr("MAT_Road_Line",
                                       base_color=(0.75, 0.72, 0.60, 1.0),
                                       roughness=0.35)
        road_mid = (st["road"][0] + st["road"][1]) / 2
        x = -ex + 1.0
        i = 0
        while x < ex:
            add_plane(f"EXT_RoadLine_{i:02d}", size=(1.8, 0.14),
                      location=(x, road_mid, 0.035),
                      collection=self.ext_coll, material=line_mat)
            x += 4.0
            i += 1

    def _add_window_grid(self, building, face_y, rows, cols, z_base, z_step,
                         x_base, x_step, w, h, lit_chance=0.35, facing=-1,
                         x_center=0.0):
        """
        Add a grid of window planes onto a building face at world Y=face_y.
        `facing` = -1 for faces looking toward the shop (-Y normal).
        Randomly mixes warm-lit and dark windows for a lived-in skyline.
        """
        lit = self.mat.window_lit()
        dark = self.mat.window_dark()
        for r in range(rows):
            for c in range(cols):
                x = x_center + x_base + c * x_step
                z = z_base + r * z_step
                mat = lit if RNG.random() < lit_chance else dark
                add_plane(f"EXT_Win_{building.name}_{r}{c}",
                          size=(w, h),
                          location=(x, face_y, z),
                          rotation=(math.radians(90) * facing, 0, 0),
                          collection=self.ext_coll, material=mat)

    def _build_buildings(self):
        """
        Background city blocks:
          * a row of tall buildings across the street (facing the shop)
          * flanking buildings left/right of the cafe on the near side
          * ground-floor storefronts with awnings on the far row
        Simple massing + emissive window grids = convincing through glass.
        """
        st = CONFIG["street"]
        row_y = st["building_row_y"]
        x = -st["extent_x"]
        idx = 0
        while x < st["extent_x"] - 4.0:
            w = RNG.uniform(6.0, 10.0)
            h = RNG.uniform(10.0, 22.0)
            d = RNG.uniform(6.0, 10.0)
            cx = x + w / 2
            b = add_cube(f"EXT_Building_{idx:02d}",
                         size=(w, d, h),
                         location=(cx, row_y + d / 2, h / 2),
                         collection=self.ext_coll,
                         material=self.mat.facade(idx))
            # Window grid on the face looking at the cafe.
            cols = max(2, int(w / 2.2))
            rows = max(2, int((h - 4.0) / 2.6))
            self._add_window_grid(
                b, face_y=row_y - 0.02, rows=rows, cols=cols,
                z_base=4.0, z_step=2.6,
                x_base=-(cols - 1) * 2.2 / 2, x_step=2.2,
                w=1.3, h=1.7, lit_chance=0.35, facing=-1, x_center=cx)
            # Ground-floor storefront: recessed dark glazing + awning + sign.
            self._build_storefront(cx, row_y, w)
            x += w + RNG.uniform(0.4, 1.2)
            idx += 1

        # Flanking buildings beside the cafe (near side of the street).
        for sign, tag in ((-1, "W"), (1, "E")):
            fx = sign * (self.W / 2 + 8.0)
            fb = add_cube(f"EXT_Building_Flank_{tag}",
                          size=(14.0, 12.0, RNG.uniform(9.0, 14.0)),
                          location=(fx, 0.0, 6.0),
                          collection=self.ext_coll,
                          material=self.mat.facade(20 + (0 if sign < 0 else 1)))
            self._add_window_grid(
                fb, face_y=self.D / 2 + 0.01, rows=2, cols=4,
                z_base=5.0, z_step=2.6,
                x_base=-4.5, x_step=3.0, w=1.3, h=1.7,
                lit_chance=0.3, facing=-1, x_center=fx)

    def _build_storefront(self, cx, row_y, width):
        """Ground-floor storefront: glazing, awning and a glowing sign."""
        glaze_w = min(width - 1.5, 6.0)
        add_plane(f"EXT_Storefront_Glass_{cx:.0f}",
                  size=(glaze_w, 2.6),
                  location=(cx, row_y - 0.03, 1.5),
                  rotation=(math.radians(-90), 0, 0),
                  collection=self.ext_coll, material=self.mat.window_dark())
        # Awning (slanted solidified plane).
        awn_col = (RNG.uniform(0.2, 0.6), RNG.uniform(0.05, 0.3),
                   RNG.uniform(0.05, 0.3), 1.0)
        awning = add_plane(f"EXT_Awning_{cx:.0f}",
                           size=(glaze_w + 0.4, 1.2),
                           location=(cx, row_y - 0.7, 3.0),
                           rotation=(math.radians(-25), 0, 0),
                           collection=self.ext_coll,
                           material=self.mat.fabric(
                               f"MAT_Awning_{cx:.0f}", color=awn_col,
                               roughness=0.7))
        add_solidify(awning, thickness=0.03)
        self.collision_surfaces.append(awning)
        # Sign glow above the storefront.
        hue = RNG.choice([(1.0, 0.5, 0.2), (0.3, 0.8, 1.0), (1.0, 0.2, 0.4),
                          (0.6, 1.0, 0.5)])
        add_plane(f"EXT_StoreSign_{cx:.0f}",
                  size=(glaze_w * 0.6, 0.5),
                  location=(cx, row_y - 0.06, 3.6),
                  rotation=(math.radians(-90), 0, 0),
                  collection=self.ext_coll,
                  material=self.mat.emission(f"MAT_StoreSign_{cx:.0f}",
                                             color=hue, strength=14.0))
        self.lit_sign_positions.append((cx, row_y - 0.4, 3.6))

    def _build_street_furniture(self):
        """Street lights, traffic signal, benches and trash cans."""
        st = CONFIG["street"]
        pole_mat = self.mat.metal_black()

        # --- street lights (near + far sidewalks) --------------------------
        light_xs = [(-12.0, st["sidewalk_near"][1] - 0.5),
                    (-2.0, st["sidewalk_near"][1] - 0.5),
                    (8.5, st["sidewalk_near"][1] - 0.5),
                    (-7.0, st["sidewalk_far"][0] + 0.5),
                    (4.0, st["sidewalk_far"][0] + 0.5),
                    (14.0, st["sidewalk_far"][0] + 0.5)]
        for i, (lx, ly) in enumerate(light_xs):
            arm_dir = -1 if ly > 12 else 1   # arms lean over the road
            add_cylinder(f"EXT_StreetLight_Pole_{i:02d}",
                         radius=0.07, depth=5.4,
                         location=(lx, ly, 2.7),
                         collection=self.ext_coll, material=pole_mat)
            add_cylinder(f"EXT_StreetLight_Arm_{i:02d}",
                         radius=0.045, depth=1.6,
                         location=(lx, ly + arm_dir * 0.7, 5.3),
                         rotation=(math.radians(90), 0, 0),
                         collection=self.ext_coll, material=pole_mat)
            head = add_cube(f"EXT_StreetLight_Head_{i:02d}",
                            size=(0.30, 0.75, 0.14),
                            location=(lx, ly + arm_dir * 1.45, 5.28),
                            collection=self.ext_coll, material=pole_mat)
            add_bevel(head, width=0.02)
            add_plane(f"EXT_StreetLight_Lens_{i:02d}",
                      size=(0.24, 0.65),
                      location=(lx, ly + arm_dir * 1.45, 5.2),
                      collection=self.ext_coll,
                      material=self.mat.emission("MAT_StreetLamp_Glow",
                                                 color=(1.0, 0.75, 0.45),
                                                 strength=25.0))
            self.street_light_heads.append((lx, ly + arm_dir * 1.45, 5.1))

        # --- traffic signal at the east corner -----------------------------
        tx, ty = 15.5, st["road"][1] + 0.6
        add_cylinder("EXT_Signal_Pole", radius=0.09, depth=6.0,
                     location=(tx, ty, 3.0),
                     collection=self.ext_coll, material=pole_mat)
        add_cylinder("EXT_Signal_Arm", radius=0.055, depth=4.5,
                     location=(tx, ty - 2.25, 5.8),
                     rotation=(math.radians(90), 0, 0),
                     collection=self.ext_coll, material=pole_mat)
        head = add_cube("EXT_Signal_Head", size=(0.35, 0.28, 1.0),
                        location=(tx, ty - 4.3, 5.35),
                        collection=self.ext_coll, material=pole_mat)
        add_bevel(head, width=0.02)
        lamp_specs = [("Red", (1.0, 0.05, 0.02), 30.0, 0.30),
                      ("Amber", (0.25, 0.12, 0.01), 0.0, 0.0),
                      ("Green", (0.02, 0.2, 0.05), 0.0, 0.0)]
        for j, (cname, col, strength, _s) in enumerate(lamp_specs):
            mat = (self.mat.emission(f"MAT_Signal_{cname}", color=col,
                                     strength=strength) if strength > 0
                   else self.mat.create_pbr(f"MAT_Signal_{cname}_Off",
                                            base_color=(*col, 1.0),
                                            roughness=0.4))
            add_sphere(f"EXT_Signal_Lamp_{cname}", radius=0.10,
                       location=(tx, ty - 4.3 - 0.15, 5.65 - j * 0.3),
                       segments=16, rings=12,
                       collection=self.ext_coll, material=mat)

        # --- benches ---------------------------------------------------------
        bench_wood = self.mat.wood("MAT_Wood_Bench",
                                   color_light=(0.30, 0.18, 0.10, 1.0),
                                   color_dark=(0.14, 0.08, 0.04, 1.0),
                                   roughness=0.6)
        for i, (bx, by) in enumerate([(-9.0, st["sidewalk_near"][1] - 0.9),
                                      (1.5, st["sidewalk_far"][0] + 1.0)]):
            for k in range(5):   # slats
                add_cube(f"EXT_Bench_{i}_Slat_{k}",
                         size=(1.6, 0.09, 0.03),
                         location=(bx, by - 0.25 + k * 0.11, 0.55),
                         collection=self.ext_coll, material=bench_wood)
            for sx in (-0.7, 0.7):   # legs
                add_cube(f"EXT_Bench_{i}_Leg_{sx:+.0f}",
                         size=(0.06, 0.5, 0.55),
                         location=(bx + sx, by, 0.275),
                         collection=self.ext_coll, material=pole_mat)

        # --- trash cans -------------------------------------------------------
        for i, (cx2, cy2) in enumerate([(-5.5, st["sidewalk_near"][1] - 0.6),
                                        (11.0, st["sidewalk_far"][0] + 0.7)]):
            can = add_cylinder(f"EXT_TrashCan_{i:02d}",
                               radius=0.32, depth=0.9,
                               location=(cx2, cy2, 0.55), vertices=20,
                               collection=self.ext_coll,
                               material=self.mat.metal(
                                   "MAT_Metal_Galvanized",
                                   color=(0.35, 0.36, 0.38, 1.0),
                                   roughness=0.55))
            add_bevel(can, width=0.02)
            add_cylinder(f"EXT_TrashCan_Lid_{i:02d}",
                         radius=0.34, depth=0.06,
                         location=(cx2, cy2, 1.03), vertices=20,
                         collection=self.ext_coll,
                         material=self.mat.metal_black())

    def _build_vehicles(self):
        """Low-detail parked cars along both curbs (wet paint, LOD-friendly)."""
        st = CONFIG["street"]
        colors = [("MAT_Car_Blue", (0.02, 0.08, 0.25, 1.0)),
                  ("MAT_Car_Red", (0.30, 0.02, 0.03, 1.0)),
                  ("MAT_Car_Silver", (0.45, 0.46, 0.48, 1.0)),
                  ("MAT_Car_Black", (0.01, 0.01, 0.012, 1.0))]
        spots = [(-11.0, st["road"][0] + 1.2, 0),
                 (-1.0, st["road"][0] + 1.2, 0),
                 (9.5, st["road"][0] + 1.2, 0),
                 (3.0, st["road"][1] - 1.2, math.pi)]
        for i, (cx, cy, rz) in enumerate(spots):
            name, col = colors[i % len(colors)]
            self._build_car(f"EXT_Car_{i:02d}", (cx, cy, 0.0), rz,
                            self.mat.car_paint(name, col))

    def _build_car(self, name, location, z_rot, paint):
        """One simple sedan: body + cabin + 4 wheels + glass + light bar."""
        cx, cy, cz = location
        body = add_cube(name + "_Body", size=(4.4, 1.85, 0.62),
                        location=(cx, cy, cz + 0.62),
                        rotation=(0, 0, z_rot),
                        collection=self.ext_coll, material=paint)
        add_bevel(body, width=0.10, segments=3)
        self.collision_surfaces.append(body)
        cabin = add_cube(name + "_Cabin", size=(2.3, 1.7, 0.55),
                         location=(cx - 0.2 * math.cos(z_rot),
                                   cy - 0.2 * math.sin(z_rot), cz + 1.18),
                         rotation=(0, 0, z_rot),
                         collection=self.ext_coll,
                         material=self.mat.window_dark())
        add_bevel(cabin, width=0.14, segments=3)
        # Wheels.
        rubber = self.mat.rubber()
        for dx in (-1.45, 1.45):
            for dy in (-0.95, 0.95):
                wx = cx + dx * math.cos(z_rot) - dy * math.sin(z_rot)
                wy = cy + dx * math.sin(z_rot) + dy * math.cos(z_rot)
                add_cylinder(name + f"_Wheel_{dx:+.0f}{dy:+.0f}",
                             radius=0.33, depth=0.24,
                             location=(wx, wy, cz + 0.33),
                             rotation=(math.radians(90), 0, z_rot),
                             vertices=18,
                             collection=self.ext_coll, material=rubber)
        # Tail-light glow (adds color into the wet street reflections).
        add_plane(name + "_TailGlow", size=(0.35, 0.12),
                  location=(cx + 2.21 * math.cos(z_rot),
                            cy + 2.21 * math.sin(z_rot), cz + 0.75),
                  rotation=(math.radians(90), 0, z_rot + math.pi / 2),
                  collection=self.ext_coll,
                  material=self.mat.emission("MAT_TailLight",
                                             color=(1.0, 0.03, 0.01),
                                             strength=8.0))

    def _build_utility_poles(self):
        """Wooden utility poles + sagging cables (converted to meshes)."""
        st = CONFIG["street"]
        pole_mat = self.mat.wood("MAT_Wood_UtilityPole",
                                 color_light=(0.20, 0.14, 0.09, 1.0),
                                 color_dark=(0.10, 0.07, 0.04, 1.0),
                                 roughness=0.85)
        wire_mat = self.mat.metal_black()
        pole_y = st["sidewalk_far"][1] - 0.4
        pole_xs = [-14.0, 0.0, 14.0]
        tops = []
        for i, px in enumerate(pole_xs):
            add_cylinder(f"EXT_UtilityPole_{i:02d}", radius=0.14, depth=8.0,
                         location=(px, pole_y, 4.0), vertices=12,
                         collection=self.ext_coll, material=pole_mat)
            add_cube(f"EXT_UtilityCrossarm_{i:02d}",
                     size=(1.6, 0.10, 0.10),
                     location=(px, pole_y, 7.4),
                     collection=self.ext_coll, material=pole_mat)
            tops.append((px, pole_y, 7.4))

        # Sagging wires between consecutive crossarms (bezier -> mesh).
        for i in range(len(tops) - 1):
            for dx in (-0.6, 0.6):
                p0 = Vector((tops[i][0] + dx, tops[i][1], tops[i][2]))
                p1 = Vector((tops[i + 1][0] + dx, tops[i + 1][1], tops[i + 1][2]))
                mid = (p0 + p1) / 2 + Vector((0, 0, -0.6))   # cable sag
                curve = bpy.data.curves.new(f"EXT_Wire_{i}_{dx:+.1f}", 'CURVE')
                curve.dimensions = '3D'
                curve.bevel_depth = 0.012
                spline = curve.splines.new('BEZIER')
                spline.bezier_points.add(2)
                for bp, pt in zip(spline.bezier_points, (p0, mid, p1)):
                    bp.co = pt
                    bp.handle_left_type = bp.handle_right_type = 'AUTO'
                wire = bpy.data.objects.new(f"EXT_Wire_{i}_{dx:+.1f}", curve)
                self.ext_coll.objects.link(wire)
                assign_material(wire, wire_mat)
                set_active(wire)
                bpy.ops.object.convert(target='MESH')

    def _build_shop_signage(self):
        """The cafe's own exterior signage: fascia text + hanging blade sign."""
        y_face = self.D / 2 + self.T + 0.02
        # Fascia sign: warm backlit 3D lettering over the entrance.
        add_cube("EXT_Sign_Fascia",
                 size=(6.5, 0.12, 0.7),
                 location=(0, y_face + 0.06, self.H - 0.55),
                 collection=self.ext_coll, material=self.mat.metal_black())
        # Rotated 180° in Z so the lettering faces (and reads from) the
        # street side rather than the interior.
        add_text_mesh("EXT_Sign_Text", "NIMBUS  COFFEE",
                      location=(0, y_face + 0.14, self.H - 0.75),
                      rotation=(math.radians(90), 0, math.pi),
                      size=0.42, extrude=0.03,
                      collection=self.ext_coll,
                      material=self.mat.emission("MAT_Sign_Warm",
                                                 color=(1.0, 0.68, 0.32),
                                                 strength=12.0))
        self.lit_sign_positions.append((0, y_face + 0.3, self.H - 0.6))

        # Hanging blade sign (a coffee-cup silhouette on a bracket).
        bx = -6.5
        add_cylinder("EXT_Blade_Bracket", radius=0.025, depth=0.9,
                     location=(bx, y_face + 0.45, 3.4),
                     rotation=(math.radians(90), 0, 0),
                     collection=self.ext_coll, material=self.mat.metal_black())
        blade = add_cube("EXT_Blade_Sign", size=(0.03, 0.75, 0.55),
                         location=(bx, y_face + 0.65, 3.0),
                         collection=self.ext_coll,
                         material=self.mat.emission("MAT_Blade_Sign",
                                                    color=(0.95, 0.55, 0.25),
                                                    strength=6.0))
        add_bevel(blade, width=0.015)


# ============================================================================
#  COFFEE SHOP BUILDER  (furniture, coffee bar, decor)
# ============================================================================
#  Interior dressing.  Every prop is parametric + slightly randomized so
#  repeated furniture never reads as duplicated.  The builder records shared
#  data for the other systems:
#      steam_sources        -> AnimationSystem (volumetric steam)
#      lamp_light_positions -> LightingSystem  (warm practical lights)
#      candle_positions     -> LightingSystem  (flickering candle lights)
#      cloth_targets        -> AnimationSystem (cloth sim curtains)
#      soft_body_targets    -> AnimationSystem (couch / cushion soft bodies)
#      rigid_active         -> AnimationSystem (rigid-body chairs & props)
#      sway_objects         -> AnimationSystem (wind sway on hanging decor)
# ============================================================================

class CoffeeShopBuilder:
    """Builds the full interior: seating area, coffee bar and decor."""

    def __init__(self, materials):
        self.mat = materials
        root = get_or_create_collection("CoffeeShop_Environment")
        self.furn_coll = get_or_create_collection("Furniture", root)
        self.bar_coll = get_or_create_collection("CoffeeBar", root)
        self.decor_coll = get_or_create_collection("Decor", root)

        # Cross-system registries.
        self.steam_sources = []
        self.lamp_light_positions = []
        self.candle_positions = []
        self.cloth_targets = []
        self.soft_body_targets = []
        self.rigid_active = []
        self.sway_objects = []

        # Frequently used materials.
        self.wood_dark = self.mat.wood_walnut()
        self.metal_blk = self.mat.metal_black()
        self.leather = self.mat.leather()

    # ------------------------------------------------------------------ #
    #  MASTER BUILD
    # ------------------------------------------------------------------ #

    def build(self):
        """Assemble the complete interior."""
        self.build_seating_area()
        self.build_coffee_bar()
        self.build_decor()
        log("CoffeeShopBuilder complete.")

    # ==================================================================== #
    #  SEATING AREA
    # ==================================================================== #

    def build_seating_area(self):
        """Tables, chairs, booths, lounge couch, window bar and stools."""
        # --- round dining tables with chairs -------------------------------
        table_spots = [((-0.5, 1.2, 0), 2), ((2.8, 2.2, 0), 3),
                       ((0.9, 4.0, 0), 2)]
        for t_idx, (loc, chair_count) in enumerate(table_spots):
            table = self.create_round_table(f"FURN_Table_{t_idx:02d}", loc)
            for c in range(chair_count):
                ang = c * (2 * math.pi / chair_count) + RNG.uniform(-0.3, 0.3)
                cx = loc[0] + 0.75 * math.cos(ang)
                cy = loc[1] + 0.75 * math.sin(ang)
                chair = self.create_chair(
                    f"FURN_Chair_{t_idx:02d}_{c}", (cx, cy, 0),
                    z_rot=ang + math.pi)   # face the table
                randomize_transform(chair, loc_jitter=0.04, rot_jitter_deg=8)
                self.rigid_active.append(chair)
            # A coffee cup (with steam) + candle on each table.
            top_z = 0.76
            self.create_coffee_cup(f"PROP_Cup_Table_{t_idx:02d}",
                                   (loc[0] + RNG.uniform(-0.15, 0.15),
                                    loc[1] + RNG.uniform(-0.15, 0.15), top_z),
                                   with_steam=(t_idx < 2))
            self.create_candle(f"DECOR_Candle_{t_idx:02d}",
                               (loc[0] - 0.18, loc[1] + 0.1, top_z))

        # --- booth seating along the west wall ------------------------------
        for b_idx, by in enumerate((0.2, 3.2)):
            self.create_booth(f"FURN_Booth_{b_idx:02d}", by)

        # --- window bar + stools (rain-watching seats) ----------------------
        win_bar = add_cube("FURN_WindowBar",
                           size=(6.0, 0.35, 0.05),
                           location=(-3.0, 5.35, 1.04),
                           collection=self.furn_coll, material=self.wood_dark)
        add_bevel(win_bar, width=0.015)
        for k in range(4):
            add_cube(f"FURN_WindowBar_Bracket_{k}",
                     size=(0.05, 0.28, 0.10),
                     location=(-5.5 + k * 1.7, 5.35, 0.96),
                     collection=self.furn_coll, material=self.metal_blk)
        for k in range(4):
            stool = self.create_stool(f"FURN_Stool_{k:02d}",
                                      (-5.4 + k * 1.65, 4.75, 0))
            randomize_transform(stool, loc_jitter=0.05, rot_jitter_deg=15)
        # A cup left on the window bar — hero prop for the window camera.
        self.create_coffee_cup("PROP_Cup_Window", (-3.6, 5.32, 1.07),
                               with_steam=True)

        # --- lounge: couch + armchairs + coffee table -----------------------
        self.create_couch("FURN_Couch", (5.3, 0.2, 0), z_rot=math.pi / 2)
        self.create_coffee_table("FURN_CoffeeTable", (4.2, 0.2, 0))
        self.create_armchair("FURN_Armchair_Lounge_A", (4.2, 1.9, 0),
                             z_rot=-math.pi / 2 - 0.4)
        self.create_armchair("FURN_Armchair_Lounge_B", (4.2, -1.5, 0),
                             z_rot=-math.pi / 2 + 2.6)

        # --- reading corner (back-west): armchair + side table + rug -------
        self.create_armchair("FURN_Armchair_Reading", (-6.3, -4.3, 0),
                             z_rot=math.radians(40))
        self.create_side_table("FURN_SideTable_Reading", (-5.4, -4.8, 0))
        self.create_coffee_cup("PROP_Cup_Reading", (-5.4, -4.8, 0.56),
                               with_steam=True)

    # ------------------------------------------------------------------ #
    #  FURNITURE FACTORIES
    # ------------------------------------------------------------------ #

    def create_round_table(self, name, location):
        """Round pedestal cafe table (walnut top, steel column + base)."""
        x, y, _ = location
        parts = []
        top = add_cylinder(name + "_Top", radius=0.42, depth=0.04,
                           location=(x, y, 0.74), vertices=36,
                           collection=self.furn_coll, material=self.wood_dark)
        add_bevel(top, width=0.01, segments=2)
        shade_smooth(top)
        parts.append(top)
        parts.append(add_cylinder(name + "_Column", radius=0.04, depth=0.68,
                                  location=(x, y, 0.38),
                                  collection=self.furn_coll,
                                  material=self.metal_blk))
        base = add_cylinder(name + "_Base", radius=0.25, depth=0.03,
                            location=(x, y, 0.015), vertices=28,
                            collection=self.furn_coll,
                            material=self.metal_blk)
        parts.append(base)
        return join_objects(parts, name)

    def create_side_table(self, name, location):
        """Small three-leg side table for the reading corner."""
        x, y, _ = location
        parts = [add_cylinder(name + "_Top", radius=0.28, depth=0.03,
                              location=(x, y, 0.54), vertices=28,
                              collection=self.furn_coll,
                              material=self.wood_dark)]
        for i in range(3):
            ang = i * 2 * math.pi / 3
            parts.append(add_cylinder(
                name + f"_Leg_{i}", radius=0.015, depth=0.54,
                location=(x + 0.18 * math.cos(ang),
                          y + 0.18 * math.sin(ang), 0.27),
                rotation=(math.radians(6) * math.cos(ang),
                          math.radians(6) * math.sin(ang), 0),
                collection=self.furn_coll, material=self.metal_blk))
        return join_objects(parts, name)

    def create_coffee_table(self, name, location):
        """Low rectangular lounge coffee table."""
        x, y, _ = location
        parts = []
        top = add_cube(name + "_Top", size=(1.1, 0.6, 0.04),
                       location=(x, y, 0.42),
                       collection=self.furn_coll, material=self.wood_dark)
        add_bevel(top, width=0.012)
        parts.append(top)
        for dx in (-0.48, 0.48):
            for dy in (-0.22, 0.22):
                parts.append(add_cube(name + f"_Leg{dx:+.1f}{dy:+.1f}",
                                      size=(0.05, 0.05, 0.40),
                                      location=(x + dx, y + dy, 0.20),
                                      collection=self.furn_coll,
                                      material=self.metal_blk))
        table = join_objects(parts, name)
        # Dress it with a small book stack.
        self._book_stack(name + "_Books", (x - 0.25, y + 0.1, 0.44), count=3)
        return table

    def create_chair(self, name, location, z_rot=0.0):
        """Scandinavian wooden cafe chair (joined into one rigid mesh)."""
        x, y, _ = location
        wood = self.mat.wood("MAT_Wood_Chair",
                             color_light=(0.50, 0.33, 0.18, 1.0),
                             color_dark=(0.26, 0.15, 0.08, 1.0),
                             roughness=0.4)
        parts = []
        seat = add_cube(name + "_Seat", size=(0.42, 0.42, 0.035),
                        location=(0, 0, 0.45),
                        collection=self.furn_coll, material=wood)
        add_bevel(seat, width=0.015, segments=3)
        parts.append(seat)
        back = add_cube(name + "_Back", size=(0.42, 0.03, 0.42),
                        location=(0, 0.20, 0.85),
                        rotation=(math.radians(-8), 0, 0),
                        collection=self.furn_coll, material=wood)
        add_bevel(back, width=0.012, segments=3)
        parts.append(back)
        for dx in (-0.18, 0.18):
            for dy, height, tilt in ((-0.18, 0.45, 4), (0.18, 1.0, -4)):
                parts.append(add_cube(
                    name + f"_Leg{dx:+.1f}{dy:+.1f}",
                    size=(0.035, 0.035, height),
                    location=(dx, dy, height / 2),
                    rotation=(math.radians(tilt), 0, 0),
                    collection=self.furn_coll, material=wood))
        chair = join_objects(parts, name)
        rebase_origin_to_world(chair)
        chair.location = (x, y, 0)
        chair.rotation_euler = (0, 0, z_rot)
        return chair

    def create_stool(self, name, location):
        """Industrial bar stool with a round wooden seat."""
        x, y, _ = location
        parts = []
        seat = add_cylinder(name + "_Seat", radius=0.17, depth=0.05,
                            location=(0, 0, 0.72), vertices=24,
                            collection=self.furn_coll, material=self.wood_dark)
        add_bevel(seat, width=0.015)
        shade_smooth(seat)
        parts.append(seat)
        for i in range(4):
            ang = i * math.pi / 2 + math.pi / 4
            parts.append(add_cylinder(
                name + f"_Leg_{i}", radius=0.014, depth=0.72,
                location=(0.13 * math.cos(ang), 0.13 * math.sin(ang), 0.36),
                rotation=(math.radians(7) * math.sin(ang),
                          -math.radians(7) * math.cos(ang), 0),
                collection=self.furn_coll, material=self.metal_blk))
        parts.append(add_torus(name + "_Footring",
                               major_radius=0.16, minor_radius=0.010,
                               location=(0, 0, 0.24),
                               collection=self.furn_coll,
                               material=self.metal_blk))
        stool = join_objects(parts, name)
        rebase_origin_to_world(stool)
        stool.location = (x, y, 0)
        return stool

    def create_armchair(self, name, location, z_rot=0.0):
        """
        Upholstered leather armchair with a separate seat cushion that is
        registered for the soft-body simulation.
        """
        x, y, _ = location
        leather = self.leather
        parts = []
        base = add_cube(name + "_Base", size=(0.80, 0.75, 0.30),
                        location=(0, 0, 0.22),
                        collection=self.furn_coll, material=leather)
        add_bevel(base, width=0.05, segments=4)
        parts.append(base)
        back = add_cube(name + "_BackRest", size=(0.80, 0.22, 0.55),
                        location=(0, 0.33, 0.62),
                        rotation=(math.radians(-10), 0, 0),
                        collection=self.furn_coll, material=leather)
        add_bevel(back, width=0.06, segments=4)
        parts.append(back)
        for dx in (-0.35, 0.35):
            arm = add_cube(name + f"_Arm{dx:+.1f}",
                           size=(0.12, 0.70, 0.28),
                           location=(dx, 0.02, 0.50),
                           collection=self.furn_coll, material=leather)
            add_bevel(arm, width=0.045, segments=4)
            parts.append(arm)
        for dx in (-0.32, 0.32):
            for dy in (-0.30, 0.30):
                parts.append(add_cube(name + f"_Foot{dx:+.1f}{dy:+.1f}",
                                      size=(0.05, 0.05, 0.09),
                                      location=(dx, dy, 0.045),
                                      collection=self.furn_coll,
                                      material=self.wood_dark))
        chair = join_objects(parts, name)
        rebase_origin_to_world(chair)
        chair.location = (x, y, 0)
        chair.rotation_euler = (0, 0, z_rot)

        # Separate soft-body seat cushion (fabric, slightly randomized tint).
        tint = (RNG.uniform(0.25, 0.5), RNG.uniform(0.18, 0.32),
                RNG.uniform(0.12, 0.22), 1.0)
        cushion = add_cube(name + "_Cushion", size=(0.62, 0.58, 0.14),
                           location=(x, y, 0.46),
                           rotation=(0, 0, z_rot),
                           collection=self.furn_coll,
                           material=self.mat.fabric(
                               f"MAT_Fabric_{name}", color=tint))
        add_bevel(cushion, width=0.05, segments=3)
        add_subsurf(cushion, levels=1, render_levels=1)
        self.soft_body_targets.append(cushion)
        return chair

    def create_couch(self, name, location, z_rot=0.0):
        """Three-seat fabric couch; seat cushions get soft-body physics."""
        x, y, _ = location
        col = (0.16, 0.20, 0.24, 1.0)   # storm-blue fabric
        fabric = self.mat.fabric("MAT_Fabric_Couch", color=col)
        parts = []
        base = add_cube(name + "_Base", size=(2.1, 0.85, 0.32),
                        location=(0, 0, 0.24),
                        collection=self.furn_coll, material=fabric)
        add_bevel(base, width=0.06, segments=4)
        parts.append(base)
        back = add_cube(name + "_Back", size=(2.1, 0.24, 0.55),
                        location=(0, 0.36, 0.66),
                        rotation=(math.radians(-8), 0, 0),
                        collection=self.furn_coll, material=fabric)
        add_bevel(back, width=0.07, segments=4)
        parts.append(back)
        for dx in (-1.0, 1.0):
            arm = add_cube(name + f"_Arm{dx:+.0f}", size=(0.18, 0.85, 0.30),
                           location=(dx, 0, 0.55),
                           collection=self.furn_coll, material=fabric)
            add_bevel(arm, width=0.06, segments=4)
            parts.append(arm)
        for dx in (-0.95, 0.95):
            for dy in (-0.35, 0.35):
                parts.append(add_cube(name + f"_Foot{dx:+.1f}{dy:+.1f}",
                                      size=(0.05, 0.05, 0.08),
                                      location=(dx, dy, 0.04),
                                      collection=self.furn_coll,
                                      material=self.wood_dark))
        couch = join_objects(parts, name)
        rebase_origin_to_world(couch)
        couch.location = (x, y, 0)
        couch.rotation_euler = (0, 0, z_rot)

        # Three separate soft-body seat cushions.
        for i, dx in enumerate((-0.66, 0.0, 0.66)):
            lx = x + dx * math.cos(z_rot)
            ly = y + dx * math.sin(z_rot)
            cushion = add_cube(f"{name}_Cushion_{i}",
                               size=(0.62, 0.62, 0.16),
                               location=(lx, ly, 0.48),
                               rotation=(0, 0, z_rot),
                               collection=self.furn_coll, material=fabric)
            add_bevel(cushion, width=0.055, segments=3)
            add_subsurf(cushion, levels=1, render_levels=1)
            self.soft_body_targets.append(cushion)
        return couch

    def create_booth(self, name, by):
        """Booth unit against the west wall: two benches + table."""
        wall_x = -7.3
        leather = self.mat.leather("MAT_Leather_Booth",
                                   color=(0.16, 0.28, 0.20, 1.0))
        for i, dy in enumerate((-0.85, 0.85)):
            bench_parts = []
            seat = add_cube(f"{name}_Seat_{i}", size=(1.0, 0.60, 0.42),
                            location=(0, 0, 0.24),
                            collection=self.furn_coll, material=leather)
            add_bevel(seat, width=0.05, segments=3)
            bench_parts.append(seat)
            back = add_cube(f"{name}_Back_{i}", size=(1.0, 0.14, 0.75),
                            location=(0, (0.28 if dy > 0 else -0.28), 0.72),
                            collection=self.furn_coll, material=leather)
            add_bevel(back, width=0.05, segments=3)
            bench_parts.append(back)
            bench = join_objects(bench_parts, f"{name}_Bench_{i}")
            rebase_origin_to_world(bench)
            bench.location = (wall_x + 0.55, by + dy, 0)
        # Wall-mounted booth table.
        table = add_cube(f"{name}_Table", size=(0.9, 0.75, 0.045),
                         location=(wall_x + 0.6, by, 0.73),
                         collection=self.furn_coll, material=self.wood_dark)
        add_bevel(table, width=0.012)
        add_cylinder(f"{name}_TableLeg", radius=0.035, depth=0.71,
                     location=(wall_x + 0.85, by, 0.355),
                     collection=self.furn_coll, material=self.metal_blk)
        self.create_candle(f"DECOR_Candle_{name}",
                           (wall_x + 0.55, by + 0.15, 0.755))
        return table

    # ==================================================================== #
    #  COFFEE BAR
    # ==================================================================== #

    def build_coffee_bar(self):
        """The complete working coffee station."""
        self.build_counter()
        self.build_espresso_machine((-2.0, -2.95, 1.02))
        self.build_grinder("BAR_Grinder_A", (-3.3, -2.95, 1.02))
        self.build_grinder("BAR_Grinder_B", (-3.8, -2.95, 1.02), scale=0.85)
        self.build_brewer((-4.4, -5.35, 0.92))
        self.build_sink((0.6, -5.35, 0.92))
        self.build_display_case((2.2, -2.9, 1.02))
        self.build_register((0.2, -2.85, 1.02))
        self.build_menu_boards()
        self.build_shelving_and_cups()
        self.build_napkin_holder((-0.7, -2.8, 1.02))
        self.build_bean_bags()

    def build_counter(self):
        """Front service counter + back work counter (walnut + marble)."""
        marble = self.mat.marble()
        # Main counter: walnut slat face, marble top, kickboard.
        add_cube("BAR_Counter_Body", size=(8.2, 0.8, 0.96),
                 location=(-1.0, -2.9, 0.48),
                 collection=self.bar_coll,
                 material=self.mat.wood_paneling())
        top = add_cube("BAR_Counter_Top", size=(8.5, 0.95, 0.06),
                       location=(-1.0, -2.9, 0.99),
                       collection=self.bar_coll, material=marble)
        add_bevel(top, width=0.015, segments=3)
        add_cube("BAR_Counter_Kick", size=(8.2, 0.06, 0.10),
                 location=(-1.0, -2.53, 0.05),
                 collection=self.bar_coll, material=self.metal_blk)

        # Back counter along the paneled wall.
        add_cube("BAR_BackCounter_Body", size=(8.0, 0.7, 0.86),
                 location=(-1.0, -5.55, 0.43),
                 collection=self.bar_coll, material=self.wood_dark)
        btop = add_cube("BAR_BackCounter_Top", size=(8.2, 0.8, 0.05),
                        location=(-1.0, -5.55, 0.885),
                        collection=self.bar_coll, material=marble)
        add_bevel(btop, width=0.012, segments=3)

    def build_espresso_machine(self, location):
        """
        Two-group espresso machine: body, group heads, portafilters,
        steam wand, cup warmer tray with cups, and a steam source.
        """
        x, y, z = location
        steel = self.mat.metal_brushed()
        chrome = self.mat.chrome()
        parts = []
        body = add_cube("BAR_Espresso_Body", size=(0.78, 0.55, 0.42),
                        location=(0, 0, 0.24),
                        collection=self.bar_coll, material=steel)
        add_bevel(body, width=0.03, segments=3)
        parts.append(body)
        # Brand plate glow on the customer-facing side (the working side
        # with the group heads faces the barista aisle at -Y).
        add_plane("BAR_Espresso_Logo", size=(0.28, 0.10),
                  location=(x, y + 0.281, z + 0.30),
                  rotation=(math.radians(90), 0, math.pi),
                  collection=self.bar_coll,
                  material=self.mat.emission("MAT_Espresso_Logo",
                                             color=(1.0, 0.55, 0.2),
                                             strength=4.0))
        # Group heads + portafilters.
        for i, dx in enumerate((-0.18, 0.18)):
            parts.append(add_cylinder(f"BAR_Espresso_Group_{i}",
                                      radius=0.05, depth=0.10,
                                      location=(dx, -0.20, 0.06),
                                      collection=self.bar_coll,
                                      material=chrome))
            parts.append(add_cylinder(f"BAR_Espresso_PF_{i}",
                                      radius=0.045, depth=0.03,
                                      location=(dx, -0.20, -0.005),
                                      collection=self.bar_coll,
                                      material=chrome))
            parts.append(add_cylinder(f"BAR_Espresso_PFHandle_{i}",
                                      radius=0.012, depth=0.16,
                                      location=(dx, -0.30, -0.005),
                                      rotation=(math.radians(90), 0, 0),
                                      collection=self.bar_coll,
                                      material=self.metal_blk))
        # Steam wand (angled chrome pipe) — registered as a steam source.
        wand = add_cylinder("BAR_Espresso_Wand", radius=0.010, depth=0.26,
                            location=(0.33, -0.16, 0.02),
                            rotation=(math.radians(30), 0, 0),
                            collection=self.bar_coll, material=chrome)
        parts.append(wand)
        # Drip tray.
        parts.append(add_cube("BAR_Espresso_Tray", size=(0.72, 0.28, 0.02),
                              location=(0, -0.18, -0.10),
                              collection=self.bar_coll, material=steel))
        machine = join_objects(parts, "BAR_EspressoMachine")
        rebase_origin_to_world(machine)
        machine.location = (x, y, z + 0.10)
        # Warming cups on top of the machine.
        for i in range(4):
            self.create_coffee_cup(
                f"PROP_Cup_Warmer_{i}",
                (x - 0.24 + i * 0.16, y + 0.08, z + 0.56), small=True)
        # Steam rises from the wand tip and the group area.
        self.steam_sources.append((x + 0.33, y - 0.16, z + 0.12, 0.9))

    def build_grinder(self, name, location, scale=1.0):
        """Burr coffee grinder: hopper cone + body + spout."""
        x, y, z = location
        s = scale
        parts = []
        body = add_cube(name + "_Body", size=(0.16 * s, 0.20 * s, 0.34 * s),
                        location=(0, 0, 0.17 * s),
                        collection=self.bar_coll, material=self.metal_blk)
        add_bevel(body, width=0.02, segments=3)
        parts.append(body)
        parts.append(add_cylinder(name + "_Throat", radius=0.045 * s,
                                  depth=0.08 * s,
                                  location=(0, 0, 0.38 * s),
                                  collection=self.bar_coll,
                                  material=self.metal_blk))
        hopper = add_cone(name + "_Hopper", radius1=0.055 * s,
                          radius2=0.10 * s, depth=0.18 * s,
                          location=(0, 0, 0.51 * s),
                          collection=self.bar_coll,
                          material=self.mat.glass_clear())
        shade_smooth(hopper)
        parts.append(hopper)
        parts.append(add_cylinder(name + "_Spout", radius=0.015 * s,
                                  depth=0.07 * s,
                                  location=(0, -0.09 * s, 0.16 * s),
                                  rotation=(math.radians(60), 0, 0),
                                  collection=self.bar_coll,
                                  material=self.metal_blk))
        grinder = join_objects(parts, name)
        rebase_origin_to_world(grinder)
        grinder.location = (x, y, z)
        randomize_transform(grinder, loc_jitter=0.01, rot_jitter_deg=6,
                            scale_jitter=0.0)
        return grinder

    def build_brewer(self, location):
        """Batch filter-coffee brewer + glass carafe on the back counter."""
        x, y, z = location
        steel = self.mat.metal_brushed()
        parts = []
        tower = add_cube("BAR_Brewer_Tower", size=(0.24, 0.30, 0.55),
                         location=(0, 0.04, 0.275),
                         collection=self.bar_coll, material=steel)
        add_bevel(tower, width=0.02)
        parts.append(tower)
        parts.append(add_cube("BAR_Brewer_Base", size=(0.24, 0.34, 0.03),
                              location=(0, -0.02, 0.015),
                              collection=self.bar_coll, material=steel))
        brewer = join_objects(parts, "BAR_Brewer")
        rebase_origin_to_world(brewer)
        brewer.location = (x, y, z)
        # Glass carafe with coffee inside.
        carafe = add_cylinder("BAR_Carafe", radius=0.075, depth=0.18,
                              location=(x, y - 0.06, z + 0.10),
                              collection=self.bar_coll,
                              material=self.mat.glass_clear())
        shade_smooth(carafe)
        add_cylinder("BAR_Carafe_Coffee", radius=0.065, depth=0.10,
                     location=(x, y - 0.06, z + 0.065),
                     collection=self.bar_coll,
                     material=self.mat.coffee_liquid())
        self.steam_sources.append((x, y - 0.06, z + 0.22, 0.5))

    def build_sink(self, location):
        """Under-mount sink basin + gooseneck faucet in the back counter."""
        x, y, z = location
        steel = self.mat.metal_brushed()
        # Basin: outer shell with an inner dark cavity (fake depth).
        add_cube("BAR_Sink_Rim", size=(0.55, 0.45, 0.03),
                 location=(x, y, z + 0.005),
                 collection=self.bar_coll, material=steel)
        add_cube("BAR_Sink_Basin", size=(0.47, 0.37, 0.20),
                 location=(x, y, z - 0.09),
                 collection=self.bar_coll,
                 material=self.mat.metal("MAT_Metal_SinkInner",
                                         color=(0.35, 0.36, 0.38, 1.0),
                                         roughness=0.4))
        # Gooseneck faucet (vertical riser + curved spout approximation).
        chrome = self.mat.chrome()
        add_cylinder("BAR_Faucet_Riser", radius=0.015, depth=0.30,
                     location=(x, y + 0.19, z + 0.15),
                     collection=self.bar_coll, material=chrome)
        add_cylinder("BAR_Faucet_Spout", radius=0.012, depth=0.22,
                     location=(x, y + 0.08, z + 0.295),
                     rotation=(math.radians(90), 0, 0),
                     collection=self.bar_coll, material=chrome)
        add_cylinder("BAR_Faucet_Drop", radius=0.012, depth=0.06,
                     location=(x, y - 0.02, z + 0.27),
                     collection=self.bar_coll, material=chrome)

    def build_display_case(self, location):
        """Curved glass pastry display case, fully stocked."""
        x, y, z = location
        # Glass shell.
        shell = add_cube("BAR_Display_Glass", size=(1.5, 0.75, 0.62),
                         location=(x, y, z + 0.31),
                         collection=self.bar_coll,
                         material=self.mat.glass_clear())
        add_bevel(shell, width=0.03, segments=3)
        # Interior shelves.
        for i, sz in enumerate((0.08, 0.34)):
            add_cube(f"BAR_Display_Shelf_{i}", size=(1.42, 0.66, 0.02),
                     location=(x, y, z + sz),
                     collection=self.bar_coll,
                     material=self.mat.metal_brushed())
        # Warm display strip light (emissive).
        add_plane("BAR_Display_Light", size=(1.38, 0.04),
                  location=(x, y - 0.30, z + 0.58),
                  rotation=(math.radians(180), 0, 0),
                  collection=self.bar_coll,
                  material=self.mat.emission("MAT_Display_Strip",
                                             color=(1.0, 0.75, 0.45),
                                             strength=18.0))
        self.lamp_light_positions.append(((x, y, z + 0.5), 3000, 12.0))
        self.populate_pastries(x, y, z)

    def populate_pastries(self, x, y, z):
        """Fill the display case with randomized croissants/donuts/muffins."""
        croissant_mat = self.mat.food("MAT_Food_Croissant",
                                      (0.55, 0.30, 0.10, 1.0))
        donut_mat = self.mat.food("MAT_Food_Donut", (0.42, 0.20, 0.08, 1.0))
        glaze_mat = self.mat.food("MAT_Food_Glaze", (0.75, 0.35, 0.45, 1.0),
                                  roughness=0.15, subsurface=0.05)
        muffin_mat = self.mat.food("MAT_Food_Muffin", (0.45, 0.26, 0.12, 1.0))
        paper_mat = self.mat.paper("MAT_Paper_Doily",
                                   color=(0.92, 0.90, 0.86, 1.0))

        for shelf_z in (z + 0.10, z + 0.36):
            # Doily tray.
            add_plane(f"BAR_Doily_{shelf_z:.2f}", size=(1.35, 0.6),
                      location=(x, y, shelf_z + 0.002),
                      collection=self.bar_coll, material=paper_mat)
            for i in range(5):
                px = x - 0.58 + i * 0.29 + RNG.uniform(-0.02, 0.02)
                py = y + RNG.uniform(-0.16, 0.16)
                kind = RNG.choice(("croissant", "donut", "muffin"))
                rot_z = RNG.uniform(0, math.pi * 2)
                if kind == "croissant":
                    # Croissant = 3 shrinking lobes in an arc.
                    for j, (off, r) in enumerate(((-0.05, 0.045), (0.0, 0.055),
                                                  (0.05, 0.045))):
                        blob = add_ico_sphere(
                            f"PROP_Croissant_{i}_{shelf_z:.1f}_{j}",
                            radius=r,
                            location=(px + off * math.cos(rot_z),
                                      py + off * math.sin(rot_z),
                                      shelf_z + 0.04),
                            subdivisions=2,
                            collection=self.bar_coll, material=croissant_mat)
                        blob.scale = (1.0, 0.7, 0.62)
                        apply_scale(blob)
                        shade_smooth(blob)
                elif kind == "donut":
                    d = add_torus(f"PROP_Donut_{i}_{shelf_z:.1f}",
                                  major_radius=0.05, minor_radius=0.024,
                                  location=(px, py, shelf_z + 0.028),
                                  collection=self.bar_coll,
                                  material=donut_mat)
                    shade_smooth(d)
                    g = add_torus(f"PROP_DonutGlaze_{i}_{shelf_z:.1f}",
                                  major_radius=0.05, minor_radius=0.020,
                                  location=(px, py, shelf_z + 0.038),
                                  collection=self.bar_coll,
                                  material=glaze_mat)
                    g.scale = (1.0, 1.0, 0.55)
                    apply_scale(g)
                    shade_smooth(g)
                else:
                    base = add_cone(f"PROP_MuffinBase_{i}_{shelf_z:.1f}",
                                    radius1=0.035, radius2=0.045, depth=0.05,
                                    location=(px, py, shelf_z + 0.028),
                                    collection=self.bar_coll,
                                    material=paper_mat)
                    shade_smooth(base)
                    top = add_ico_sphere(f"PROP_MuffinTop_{i}_{shelf_z:.1f}",
                                         radius=0.05,
                                         location=(px, py, shelf_z + 0.062),
                                         subdivisions=2,
                                         collection=self.bar_coll,
                                         material=muffin_mat)
                    top.scale = (1.0, 1.0, 0.62)
                    apply_scale(top)
                    shade_smooth(top)

    def build_register(self, location):
        """Modern POS: tablet on a stand + card reader + tip jar."""
        x, y, z = location
        add_cube("BAR_Register_Stand", size=(0.16, 0.12, 0.10),
                 location=(x, y, z + 0.05),
                 collection=self.bar_coll, material=self.metal_blk)
        screen = add_cube("BAR_Register_Tablet", size=(0.24, 0.02, 0.17),
                          location=(x, y - 0.03, z + 0.17),
                          rotation=(math.radians(-20), 0, 0),
                          collection=self.bar_coll, material=self.metal_blk)
        add_bevel(screen, width=0.008, segments=2)
        add_plane("BAR_Register_Screen", size=(0.21, 0.14),
                  location=(x, y - 0.045, z + 0.172),
                  rotation=(math.radians(70), 0, math.pi),
                  collection=self.bar_coll,
                  material=self.mat.emission("MAT_Screen_Glow",
                                             color=(0.85, 0.9, 1.0),
                                             strength=3.0))
        # Tip jar (glass cylinder).
        add_cylinder("BAR_TipJar", radius=0.05, depth=0.13,
                     location=(x + 0.25, y, z + 0.065),
                     collection=self.bar_coll,
                     material=self.mat.glass_clear())

    def build_menu_boards(self):
        """Three framed chalkboard menus on the paneled wall, up-lit."""
        for i in range(3):
            mx = -2.2 + i * 1.5
            frame = add_cube(f"BAR_Menu_Frame_{i}", size=(1.3, 0.05, 0.95),
                             location=(mx, -5.9, 2.75),
                             collection=self.bar_coll,
                             material=self.wood_dark)
            add_bevel(frame, width=0.015)
            add_plane(f"BAR_Menu_Board_{i}", size=(1.18, 0.83),
                      location=(mx, -5.86, 2.75),
                      rotation=(math.radians(90), 0, 0),
                      collection=self.bar_coll,
                      material=self.mat.chalkboard())
            # Chalk "text" lines (thin light planes with jitter).
            chalk = self.mat.create_pbr("MAT_Chalk",
                                        base_color=(0.85, 0.85, 0.8, 1.0),
                                        roughness=1.0)
            for line in range(6):
                w = RNG.uniform(0.4, 0.95)
                add_plane(f"BAR_Menu_Line_{i}_{line}",
                          size=(w, 0.035),
                          location=(mx + RNG.uniform(-0.08, 0.08), -5.855,
                                    3.05 - line * 0.115),
                          rotation=(math.radians(90), 0, 0),
                          collection=self.bar_coll, material=chalk)
        # Paper takeaway menus on the counter.
        for i in range(3):
            menu = add_cube(f"BAR_PaperMenu_{i}", size=(0.10, 0.21, 0.002),
                            location=(1.15 + i * 0.015, -2.7 + i * 0.01,
                                      1.023 + i * 0.002),
                            rotation=(0, 0, RNG.uniform(-0.3, 0.3)),
                            collection=self.bar_coll,
                            material=self.mat.paper())

    def build_shelving_and_cups(self):
        """Open wall shelves stocked with cups, mugs and jars."""
        shelf_mat = self.wood_dark
        ceramic_tints = [(0.92, 0.90, 0.87, 1.0), (0.75, 0.45, 0.35, 1.0),
                         (0.45, 0.55, 0.60, 1.0), (0.30, 0.35, 0.30, 1.0)]
        for s in range(2):
            sz = 1.7 + s * 0.55
            shelf = add_cube(f"BAR_Shelf_{s}", size=(3.4, 0.28, 0.04),
                             location=(-4.0, -5.82, sz),
                             collection=self.bar_coll, material=shelf_mat)
            add_bevel(shelf, width=0.01)
            for b in (-1.5, 0.0, 1.5):   # brackets
                add_cube(f"BAR_ShelfBracket_{s}_{b:+.0f}",
                         size=(0.04, 0.24, 0.05),
                         location=(-4.0 + b, -5.82, sz - 0.045),
                         collection=self.bar_coll, material=self.metal_blk)
            # Rows of mugs with slight variation.
            n = 8
            for i in range(n):
                cx = -5.5 + i * 0.42 + RNG.uniform(-0.02, 0.02)
                tint = RNG.choice(ceramic_tints)
                self.create_mug(f"PROP_Mug_{s}_{i}",
                                (cx, -5.82 + RNG.uniform(-0.04, 0.04),
                                 sz + 0.02),
                                tint=tint)
        # Stacks of takeaway cups on the back counter.
        for i in range(3):
            for j in range(4):
                add_cone(f"PROP_PaperCup_{i}_{j}",
                         radius1=0.035, radius2=0.042, depth=0.045,
                         location=(2.3 + i * 0.12, -5.5, 0.93 + j * 0.038),
                         collection=self.bar_coll,
                         material=self.mat.paper("MAT_Paper_Cup",
                                                 color=(0.9, 0.87, 0.82, 1.0)))

    def create_mug(self, name, location, tint=(0.92, 0.90, 0.87, 1.0)):
        """Ceramic mug: body cylinder + torus handle."""
        x, y, z = location
        mat = self.mat.ceramic(f"MAT_Ceramic_{tint[0]:.2f}_{tint[1]:.2f}",
                               color=tint)
        body = add_cylinder(name, radius=0.042, depth=0.095,
                            location=(x, y, z + 0.048), vertices=20,
                            collection=self.bar_coll, material=mat)
        shade_smooth(body)
        handle = add_torus(name + "_Handle", major_radius=0.028,
                           minor_radius=0.007,
                           location=(x + 0.045, y, z + 0.05),
                           rotation=(0, math.radians(90), 0),
                           major_segments=20, minor_segments=10,
                           collection=self.bar_coll, material=mat)
        shade_smooth(handle)
        return body

    def create_coffee_cup(self, name, location, with_steam=False, small=False):
        """Cup + saucer + coffee liquid; optionally registers a steam source."""
        x, y, z = location
        s = 0.7 if small else 1.0
        ceramic = self.mat.ceramic()
        if not small:
            saucer = add_cylinder(name + "_Saucer", radius=0.075, depth=0.012,
                                  location=(x, y, z + 0.006), vertices=24,
                                  collection=self.bar_coll, material=ceramic)
            shade_smooth(saucer)
        cup = add_cone(name, radius1=0.032 * s, radius2=0.042 * s,
                       depth=0.07 * s,
                       location=(x, y, z + 0.047 * s), vertices=20,
                       collection=self.bar_coll, material=ceramic)
        shade_smooth(cup)
        add_cylinder(name + "_Coffee", radius=0.036 * s, depth=0.004,
                     location=(x, y, z + 0.068 * s), vertices=20,
                     collection=self.bar_coll,
                     material=self.mat.coffee_liquid())
        if with_steam:
            self.steam_sources.append((x, y, z + 0.10, 0.45))
        return cup

    def build_napkin_holder(self, location):
        """Steel napkin holder with a paper stack + loose napkins."""
        x, y, z = location
        add_cube("BAR_NapkinHolder", size=(0.16, 0.06, 0.11),
                 location=(x, y, z + 0.055),
                 collection=self.bar_coll, material=self.mat.metal_brushed())
        add_cube("BAR_Napkins", size=(0.13, 0.045, 0.09),
                 location=(x, y, z + 0.055),
                 collection=self.bar_coll,
                 material=self.mat.paper("MAT_Paper_Napkin",
                                         color=(0.95, 0.94, 0.92, 1.0)))
        for i in range(2):
            add_plane(f"BAR_LooseNapkin_{i}", size=(0.12, 0.12),
                      location=(x + 0.2 + i * 0.05, y + 0.05, z + 0.001),
                      rotation=(0, 0, RNG.uniform(0, math.pi)),
                      collection=self.bar_coll,
                      material=self.mat.paper("MAT_Paper_Napkin"))

    def build_bean_bags(self):
        """Kraft coffee-bean bags on the back counter + shelf."""
        bag_mat = self.mat.paper("MAT_Paper_BeanBag",
                                 color=(0.45, 0.30, 0.18, 1.0))
        label_mat = self.mat.paper("MAT_Paper_Label",
                                   color=(0.88, 0.84, 0.78, 1.0))
        spots = [(-2.6, -5.5, 0.91), (-2.25, -5.45, 0.91),
                 (-1.9, -5.55, 0.91), (-5.3, -5.8, 2.29)]
        for i, (bx, by, bz) in enumerate(spots):
            bag = add_cube(f"PROP_BeanBag_{i}", size=(0.16, 0.10, 0.30),
                           location=(bx, by, bz + 0.15),
                           rotation=(0, 0, RNG.uniform(-0.25, 0.25)),
                           collection=self.bar_coll, material=bag_mat)
            add_bevel(bag, width=0.03, segments=3)
            add_displace_noise(bag, strength=0.012, noise_scale=0.4)
            add_plane(f"PROP_BeanBag_Label_{i}", size=(0.10, 0.12),
                      location=(bx, by - 0.055, bz + 0.16),
                      rotation=(math.radians(90), 0,
                                bag.rotation_euler.z),
                      collection=self.bar_coll, material=label_mat)
            # Only the counter bags become dynamic (the shelf bag has no
            # passive support surface directly beneath it).
            if bz < 2.0:
                self.rigid_active.append(bag)

    # ==================================================================== #
    #  DECOR
    # ==================================================================== #

    def build_decor(self):
        """All decorative dressing: shelves, plants, art, rugs, lights..."""
        self.build_bookshelves()
        self.build_plants()
        self.build_artwork()
        self.build_rugs()
        self.build_curtains()
        self.build_lamps()
        self.build_signs()
        self.build_string_lights()

    def build_bookshelves(self):
        """Two bookshelves filled with randomized books."""
        covers = self.mat.book_covers()
        specs = [("DECOR_Bookshelf_Reading", (-7.55, -3.0, 0), 0.0),
                 ("DECOR_Bookshelf_East", (7.55, 3.5, 0), math.pi)]
        for name, (x, y, _), rz in specs:
            # Carcass + 4 shelves.
            add_cube(name + "_Side_L", size=(0.30, 0.03, 2.1),
                     location=(x, y - 0.55, 1.05),
                     collection=self.decor_coll, material=self.wood_dark)
            add_cube(name + "_Side_R", size=(0.30, 0.03, 2.1),
                     location=(x, y + 0.55, 1.05),
                     collection=self.decor_coll, material=self.wood_dark)
            add_cube(name + "_BackPanel", size=(0.03, 1.13, 2.1),
                     location=(x + (0.13 if rz == 0 else -0.13), y, 1.05),
                     collection=self.decor_coll, material=self.wood_dark)
            for s in range(5):
                sz = 0.08 + s * 0.48
                add_cube(name + f"_Shelf_{s}", size=(0.30, 1.10, 0.03),
                         location=(x, y, sz),
                         collection=self.decor_coll, material=self.wood_dark)
                if s < 4:
                    self._fill_shelf_with_books(name, x, y, sz + 0.015,
                                                covers, rz)

    def _fill_shelf_with_books(self, name, x, y, z, covers, rz):
        """One shelf row of randomized books (heights/widths/lean)."""
        cy = y - 0.48
        b = 0
        while cy < y + 0.42:
            w = RNG.uniform(0.025, 0.05)
            h = RNG.uniform(0.20, 0.34)
            lean = RNG.uniform(-0.06, 0.06) if RNG.random() < 0.25 else 0.0
            book = add_cube(f"{name}_Book_{z:.1f}_{b}",
                            size=(0.20, w, h),
                            location=(x - (0.02 if rz == 0 else -0.02),
                                      cy + w / 2, z + h / 2),
                            rotation=(lean, 0, 0),
                            collection=self.decor_coll,
                            material=RNG.choice(covers))
            cy += w + RNG.uniform(0.002, 0.015)
            b += 1

    def _book_stack(self, name, location, count=3):
        """A small flat stack of books (coffee-table dressing)."""
        covers = self.mat.book_covers()
        x, y, z = location
        cz = z
        for i in range(count):
            h = RNG.uniform(0.02, 0.035)
            add_cube(f"{name}_{i}",
                     size=(RNG.uniform(0.18, 0.24), RNG.uniform(0.13, 0.17), h),
                     location=(x + RNG.uniform(-0.01, 0.01),
                               y + RNG.uniform(-0.01, 0.01), cz + h / 2),
                     rotation=(0, 0, RNG.uniform(-0.3, 0.3)),
                     collection=self.decor_coll,
                     material=RNG.choice(covers))
            cz += h

    def build_plants(self):
        """Potted floor plants + hanging plants (wind-swayed)."""
        leaf = self.mat.plant_leaf()
        pot_mat = self.mat.terracotta()
        # Floor plants in the quiet corners.
        for i, (px, py) in enumerate([(-7.2, 5.1), (7.2, 5.1), (7.3, -5.0)]):
            scale = RNG.uniform(0.85, 1.25)
            pot = add_cone(f"DECOR_Plant_{i}_Pot", radius1=0.16 * scale,
                           radius2=0.20 * scale, depth=0.30 * scale,
                           location=(px, py, 0.15 * scale),
                           collection=self.decor_coll, material=pot_mat)
            shade_smooth(pot)
            add_cylinder(f"DECOR_Plant_{i}_Soil", radius=0.17 * scale,
                         depth=0.02,
                         location=(px, py, 0.285 * scale),
                         collection=self.decor_coll,
                         material=self.mat.create_pbr(
                             "MAT_Soil", base_color=(0.06, 0.04, 0.025, 1.0),
                             roughness=1.0))
            trunk = add_cylinder(f"DECOR_Plant_{i}_Trunk",
                                 radius=0.020 * scale, depth=0.7 * scale,
                                 location=(px, py, 0.6 * scale), vertices=10,
                                 collection=self.decor_coll,
                                 material=self.mat.wood("MAT_Wood_Trunk"))
            self.sway_objects.append(trunk)
            for L in range(7):
                ang = L * 2.4 + RNG.uniform(-0.3, 0.3)
                r = RNG.uniform(0.16, 0.30) * scale
                blob = add_ico_sphere(
                    f"DECOR_Plant_{i}_Leaf_{L}", radius=r,
                    location=(px + 0.55 * r * math.cos(ang),
                              py + 0.55 * r * math.sin(ang),
                              scale * (0.85 + L * 0.06)),
                    subdivisions=2,
                    collection=self.decor_coll, material=leaf)
                blob.scale = (1.0, 1.0, RNG.uniform(0.5, 0.75))
                apply_scale(blob)
                add_displace_noise(blob, strength=0.05, noise_scale=0.25)
                shade_smooth(blob)
                self.sway_objects.append(blob)

        # Hanging plants near the windows (rope + pot + trailing vines).
        for i, hx in enumerate((-4.5, 1.5)):
            hz = CONFIG["shop"]["height"]
            rope = add_cylinder(f"DECOR_HangPlant_{i}_Rope", radius=0.008,
                                depth=0.9,
                                location=(hx, 5.0, hz - 0.45), vertices=8,
                                collection=self.decor_coll,
                                material=self.mat.fabric(
                                    "MAT_Fabric_Rope",
                                    color=(0.55, 0.45, 0.30, 1.0)))
            pot = add_cone(f"DECOR_HangPlant_{i}_Pot", radius1=0.09,
                           radius2=0.13, depth=0.16,
                           location=(hx, 5.0, hz - 0.98),
                           collection=self.decor_coll, material=pot_mat)
            shade_smooth(pot)
            self.sway_objects.append(pot)
            for v in range(6):
                ang = v * 1.05 + RNG.uniform(-0.2, 0.2)
                vine = add_cone(f"DECOR_HangPlant_{i}_Vine_{v}",
                                radius1=0.030, radius2=0.004,
                                depth=RNG.uniform(0.35, 0.65),
                                location=(hx + 0.11 * math.cos(ang),
                                          5.0 + 0.11 * math.sin(ang),
                                          hz - 1.25),
                                rotation=(RNG.uniform(-0.25, 0.25),
                                          RNG.uniform(-0.25, 0.25), 0),
                                vertices=8,
                                collection=self.decor_coll, material=leaf)
                shade_smooth(vine)
                self.sway_objects.append(vine)

    def build_artwork(self):
        """Framed abstract artwork on the solid walls."""
        specs = [((-7.82, 1.8, 2.2), (0, math.radians(90), 0), (0.7, 0.9)),
                 ((7.82, 0.5, 2.3), (0, math.radians(-90), 0), (0.9, 0.65)),
                 ((7.82, -2.6, 2.15), (0, math.radians(-90), 0), (0.55, 0.75))]
        for i, (loc, rot, (w, h)) in enumerate(specs):
            frame = add_cube(f"DECOR_Art_Frame_{i}", size=(0.04, w + 0.08,
                                                           h + 0.08),
                             location=loc,
                             collection=self.decor_coll,
                             material=self.wood_dark)
            add_bevel(frame, width=0.01)
            # Unique procedural "abstract canvas" per artwork.
            mat, nt, bsdf, out = self.mat._base(f"MAT_Canvas_{i}")
            if nt is not None:
                noise = new_node(nt, 'ShaderNodeTexNoise', (-700, 0))
                noise.inputs['Scale'].default_value = RNG.uniform(2.0, 7.0)
                noise.inputs['Distortion'].default_value = RNG.uniform(0, 3)
                ramp = new_node(nt, 'ShaderNodeValToRGB', (-450, 0))
                c0 = (RNG.uniform(0.05, 0.6), RNG.uniform(0.05, 0.5),
                      RNG.uniform(0.05, 0.55), 1.0)
                c1 = (RNG.uniform(0.4, 0.95), RNG.uniform(0.35, 0.85),
                      RNG.uniform(0.3, 0.8), 1.0)
                ramp.color_ramp.elements[0].color = c0
                ramp.color_ramp.elements[1].color = c1
                nt.links.new(noise.outputs['Fac'], ramp.inputs['Fac'])
                nt.links.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])
                set_input(bsdf, 'Roughness', 0.85)
            add_cube(f"DECOR_Art_Canvas_{i}", size=(0.02, w, h),
                     location=(loc[0] + (0.015 if loc[0] < 0 else -0.015),
                               loc[1], loc[2]),
                     collection=self.decor_coll, material=mat)

    def build_rugs(self):
        """Area rugs under the lounge and the reading corner."""
        rug_mat = self.mat.rug()
        for name, loc, size in (("DECOR_Rug_Lounge", (4.6, 0.2, 0.012),
                                 (2.6, 3.2)),
                                ("DECOR_Rug_Reading", (-6.0, -4.3, 0.012),
                                 (2.0, 2.2))):
            rug = add_plane(name, size=size, location=loc,
                            collection=self.decor_coll, material=rug_mat)
            add_solidify(rug, thickness=0.012)

    def build_curtains(self):
        """
        Linen curtain panels flanking the window wall — subdivided grids
        with a pinned top row, registered for the cloth simulation.
        """
        curtain_mat = self.mat.curtain()
        for i, cx in enumerate((-7.6, 4.2)):
            panel = add_grid(f"DECOR_Curtain_{i}", size=(1.1, 3.4),
                             subdivisions=(14, 40),
                             location=(cx, 5.55, 2.15),
                             rotation=(math.radians(90), 0, 0),
                             collection=self.decor_coll,
                             material=curtain_mat)
            add_solidify(panel, thickness=0.006)
            # Vertex group "PIN": the top edge stays attached to the rail.
            vg = panel.vertex_groups.new(name="PIN")
            top_ids = [v.index for v in panel.data.vertices
                       if v.co.y > 1.62]   # local top edge (pre-rotation Y)
            vg.add(top_ids, 1.0, 'REPLACE')
            self.cloth_targets.append(panel)
            # Curtain rail.
            add_cylinder(f"DECOR_CurtainRail_{i}", radius=0.015, depth=1.3,
                         location=(cx, 5.55, 3.9),
                         rotation=(0, math.radians(90), 0),
                         collection=self.decor_coll,
                         material=self.metal_blk)

    def build_lamps(self):
        """Pendants over the bar + tables, a floor lamp, table candles."""
        # --- copper pendants over the counter -------------------------------
        for i in range(4):
            px = -4.0 + i * 2.0
            self.create_pendant(f"DECOR_Pendant_Bar_{i}", (px, -2.9),
                                drop=1.3)
        # --- small pendants over each dining table ---------------------------
        for i, (tx, ty) in enumerate([(-0.5, 1.2), (2.8, 2.2), (0.9, 4.0)]):
            self.create_pendant(f"DECOR_Pendant_Table_{i}", (tx, ty),
                                drop=1.6, scale=0.75)
        # --- reading-corner floor lamp ---------------------------------------
        self.create_floor_lamp("DECOR_FloorLamp_Reading", (-6.9, -5.0, 0))
        # --- booth wall sconces -----------------------------------------------
        for i, by in enumerate((0.2, 3.2)):
            add_cylinder(f"DECOR_Sconce_{i}", radius=0.055, depth=0.12,
                         location=(-7.75, by, 2.0),
                         rotation=(0, math.radians(90), 0),
                         collection=self.decor_coll,
                         material=self.mat.copper())
            add_sphere(f"DECOR_Sconce_Bulb_{i}", radius=0.035,
                       location=(-7.68, by, 2.0), segments=16, rings=12,
                       collection=self.decor_coll,
                       material=self.mat.emission("MAT_Bulb_Warm",
                                                  color=(1.0, 0.65, 0.32),
                                                  strength=20.0))
            self.lamp_light_positions.append(((-7.6, by, 2.0), 2800, 12.0))

    def create_pendant(self, name, xy, drop=1.4, scale=1.0):
        """Hanging pendant: cord + copper shade + glowing bulb + light."""
        x, y = xy
        top_z = CONFIG["shop"]["height"]
        bulb_z = top_z - drop
        add_cylinder(name + "_Cord", radius=0.006, depth=drop - 0.14,
                     location=(x, y, top_z - (drop - 0.14) / 2), vertices=8,
                     collection=self.decor_coll, material=self.metal_blk)
        shade = add_cone(name + "_Shade", radius1=0.16 * scale,
                         radius2=0.045 * scale, depth=0.16 * scale,
                         location=(x, y, bulb_z + 0.10),
                         collection=self.decor_coll,
                         material=self.mat.copper())
        shade_smooth(shade)
        self.sway_objects.append(shade)
        add_sphere(name + "_Bulb", radius=0.035 * scale,
                   location=(x, y, bulb_z), segments=16, rings=12,
                   collection=self.decor_coll,
                   material=self.mat.emission("MAT_Bulb_Warm",
                                              color=(1.0, 0.65, 0.32),
                                              strength=20.0))
        kelvin = RNG.uniform(*CONFIG["interior_kelvin"])
        self.lamp_light_positions.append(((x, y, bulb_z - 0.05), kelvin,
                                          28.0 * scale))

    def create_floor_lamp(self, name, location):
        """Arced floor lamp with a warm fabric shade."""
        x, y, _ = location
        add_cylinder(name + "_Base", radius=0.16, depth=0.03,
                     location=(x, y, 0.015),
                     collection=self.decor_coll, material=self.metal_blk)
        add_cylinder(name + "_Pole", radius=0.018, depth=1.55,
                     location=(x, y, 0.80),
                     collection=self.decor_coll, material=self.metal_blk)
        add_cylinder(name + "_Arm", radius=0.015, depth=0.5,
                     location=(x + 0.22, y + 0.1, 1.62),
                     rotation=(0, math.radians(60), math.radians(25)),
                     collection=self.decor_coll, material=self.metal_blk)
        shade = add_cone(name + "_Shade", radius1=0.19, radius2=0.13,
                         depth=0.22,
                         location=(x + 0.42, y + 0.19, 1.52),
                         collection=self.decor_coll,
                         material=self.mat.fabric(
                             "MAT_Fabric_LampShade",
                             color=(0.85, 0.70, 0.48, 1.0), roughness=0.9))
        shade_smooth(shade)
        add_sphere(name + "_Bulb", radius=0.04,
                   location=(x + 0.42, y + 0.19, 1.48), segments=16, rings=12,
                   collection=self.decor_coll,
                   material=self.mat.emission("MAT_Bulb_Warm",
                                              color=(1.0, 0.65, 0.32),
                                              strength=20.0))
        self.lamp_light_positions.append(((x + 0.42, y + 0.19, 1.45),
                                          2700, 20.0))

    def create_candle(self, name, location):
        """Tealight candle in a glass holder with an emissive flame."""
        x, y, z = location
        add_cylinder(name + "_Holder", radius=0.035, depth=0.05,
                     location=(x, y, z + 0.025), vertices=16,
                     collection=self.decor_coll,
                     material=self.mat.glass_clear())
        add_cylinder(name + "_Wax", radius=0.028, depth=0.035,
                     location=(x, y, z + 0.022), vertices=16,
                     collection=self.decor_coll,
                     material=self.mat.candle_wax())
        flame = add_cone(name + "_Flame", radius1=0.006, radius2=0.001,
                         depth=0.022,
                         location=(x, y, z + 0.052), vertices=8,
                         collection=self.decor_coll,
                         material=self.mat.emission("MAT_Flame",
                                                    color=(1.0, 0.45, 0.08),
                                                    strength=40.0))
        shade_smooth(flame)
        self.candle_positions.append((x, y, z + 0.06))

    def build_signs(self):
        """Interior signage: neon OPEN sign + wall clock + letter board."""
        # Neon OPEN sign hanging in the window near the door (faces street).
        nx = 4.2
        neon = self.mat.emission("MAT_Neon_Open", color=(1.0, 0.25, 0.35),
                                 strength=30.0)
        add_text_mesh("DECOR_Neon_OPEN", "OPEN",
                      location=(nx, 5.8, 2.7),
                      rotation=(math.radians(90), 0, math.pi),
                      size=0.28, extrude=0.015,
                      collection=self.decor_coll, material=neon)
        add_torus("DECOR_Neon_Ring", major_radius=0.5, minor_radius=0.012,
                  location=(nx, 5.8, 2.78),
                  rotation=(math.radians(90), 0, 0),
                  collection=self.decor_coll, material=neon)
        for cx2 in (nx - 0.5, nx + 0.5):
            add_cylinder(f"DECOR_Neon_Chain_{cx2:+.1f}", radius=0.004,
                         depth=0.6,
                         location=(cx2, 5.8, 3.55), vertices=6,
                         collection=self.decor_coll,
                         material=self.metal_blk)
        self.lamp_light_positions.append(((nx, 5.6, 2.7), 2000, 6.0))

        # Wall clock over the east wall.
        add_cylinder("DECOR_Clock_Body", radius=0.22, depth=0.05,
                     location=(7.8, 1.8, 3.0),
                     rotation=(0, math.radians(90), 0),
                     collection=self.decor_coll, material=self.metal_blk)
        add_cylinder("DECOR_Clock_Face", radius=0.19, depth=0.055,
                     location=(7.79, 1.8, 3.0),
                     rotation=(0, math.radians(90), 0),
                     collection=self.decor_coll,
                     material=self.mat.paper("MAT_Paper_ClockFace",
                                             color=(0.93, 0.91, 0.86, 1.0)))
        add_cube("DECOR_Clock_HandH", size=(0.012, 0.09, 0.008),
                 location=(7.76, 1.8, 3.03),
                 collection=self.decor_coll, material=self.metal_blk)
        add_cube("DECOR_Clock_HandM", size=(0.012, 0.14, 0.008),
                 location=(7.76, 1.83, 3.0),
                 rotation=(0, 0, math.radians(90)),
                 collection=self.decor_coll, material=self.metal_blk)

    def build_string_lights(self):
        """Warm string lights sagging along the window header (interior)."""
        bulb_mat = self.mat.emission("MAT_StringBulb",
                                     color=(1.0, 0.6, 0.28), strength=14.0)
        n = 22
        for i in range(n):
            t = i / (n - 1)
            x = -7.5 + t * 15.0
            # Two sagging spans (catenary-ish via sine).
            sag = 0.28 * abs(math.sin(t * math.pi * 2))
            z = 3.75 - sag
            bulb = add_sphere(f"DECOR_StringBulb_{i:02d}", radius=0.022,
                              location=(x, 5.55, z), segments=12, rings=8,
                              collection=self.decor_coll, material=bulb_mat)
            self.sway_objects.append(bulb)
        # Only a few actual light objects (performance) along the string.
        for x in (-5.5, 0.0, 5.5):
            self.lamp_light_positions.append(((x, 5.5, 3.55), 2400, 5.0))


# ============================================================================
#  WEATHER SYSTEM  (rain, wind, puddles, lightning, thunder markers)
# ============================================================================

class WeatherSystem:
    """
    Heavy-rainstorm FX:
      * collision-enabled particle rain with adjustable intensity
      * wind + turbulence force fields (drives cloth, particles, sway)
      * reflective puddles + wet street shading (materials)
      * rain droplets / streaks meshes on the window glass
      * random lightning flashes + thunder-sync timeline markers
    """

    def __init__(self, materials, environment):
        self.mat = materials
        self.env = environment
        root = get_or_create_collection("CoffeeShop_Environment")
        self.fx_coll = get_or_create_collection("Weather_FX", root)

    def build(self):
        """Create the full storm."""
        self.build_rain()
        self.build_wind()
        self.build_puddles()
        self.build_window_rain()
        self.build_lightning_and_thunder()
        log("WeatherSystem complete.")

    # ------------------------------------------------------------------ #
    #  RAIN
    # ------------------------------------------------------------------ #

    def build_rain(self):
        """
        Particle-based rain over the street:
          * a thin stretched droplet mesh is instanced by the emitter
          * intensity scales the particle count (CONFIG['rain']['intensity'])
          * every roof / road / car / awning surface gets a collision mod
        """
        rain_cfg = CONFIG["rain"]

        # --- droplet instance mesh (parked far below the ground) ----------
        droplet = add_ico_sphere("FX_Rain_Droplet", radius=0.012,
                                 location=(0, 0, -50.0), subdivisions=1,
                                 collection=self.fx_coll,
                                 material=self.mat.rain_droplet())
        droplet.scale = (0.35, 0.35, 5.0)     # motion-stretched raindrop
        apply_scale(droplet)
        shade_smooth(droplet)

        # --- emitter plane above the street --------------------------------
        emitter = add_plane("FX_Rain_Emitter",
                            size=(2 * CONFIG["street"]["extent_x"], 24.0),
                            location=(0, 14.0, rain_cfg["emitter_height"]),
                            collection=self.fx_coll)
        emitter.hide_render = True
        emitter.display_type = 'WIRE'

        psys_mod = emitter.modifiers.new("RainParticles", 'PARTICLE_SYSTEM')
        settings = psys_mod.particle_system.settings
        settings.name = "PS_Rain"
        settings.type = 'EMITTER'
        settings.count = int(rain_cfg["base_count"] * rain_cfg["intensity"])
        settings.frame_start = FRAME_START - 40    # rain already falling
        settings.frame_end = FRAME_END
        settings.lifetime = rain_cfg["lifetime"]
        settings.emit_from = 'FACE'
        settings.distribution = 'RAND'
        settings.normal_factor = -11.0             # fast initial down-speed
        settings.factor_random = 1.5
        settings.mass = 0.001
        settings.particle_size = 1.0
        settings.size_random = 0.4
        settings.render_type = 'OBJECT'
        settings.instance_object = droplet
        settings.use_rotations = True
        try:
            settings.rotation_mode = 'VEL'          # align drops to velocity
        except TypeError:
            pass
        settings.effector_weights.gravity = 1.0
        settings.effector_weights.wind = 0.35       # storm-blown rain angle
        # Kill particles on impact so pudd 1es "absorb" them.
        try:
            settings.use_die_on_collision = True
        except AttributeError:
            pass

        # --- collision surfaces --------------------------------------------
        for surf in self.env.collision_surfaces:
            if surf.modifiers.get("Collision") is None:
                surf.modifiers.new("Collision", 'COLLISION')
                surf.collision.damping_factor = 0.8
                surf.collision.friction_factor = 0.6

    def set_rain_intensity(self, intensity):
        """Runtime intensity control: rescale the rain particle count."""
        settings = bpy.data.particles.get("PS_Rain")
        if settings:
            settings.count = int(CONFIG["rain"]["base_count"] * intensity)
            log(f"Rain intensity set to {intensity} "
                f"({settings.count} particles)")

    # ------------------------------------------------------------------ #
    #  WIND
    # ------------------------------------------------------------------ #

    def build_wind(self):
        """Wind + turbulence fields: angled rain, cloth motion, plant sway."""
        bpy.ops.object.effector_add(type='WIND',
                                    location=(-20.0, 12.0, 6.0),
                                    rotation=(0, math.radians(80), 0))
        wind = bpy.context.active_object
        wind.name = "FX_Wind"
        link_to_collection(wind, self.fx_coll)
        wind.field.strength = CONFIG["wind"]["strength"]
        wind.field.noise = 3.0
        wind.field.flow = 0.6

        bpy.ops.object.effector_add(type='TURBULENCE', location=(0, 10.0, 5.0))
        turb = bpy.context.active_object
        turb.name = "FX_Turbulence"
        link_to_collection(turb, self.fx_coll)
        turb.field.strength = CONFIG["wind"]["turbulence"]
        turb.field.size = 4.0
        turb.field.flow = 0.4

    # ------------------------------------------------------------------ #
    #  PUDDLES
    # ------------------------------------------------------------------ #

    def build_puddles(self):
        """
        Mirror-flat puddle discs with randomized irregular outlines,
        floating a hair above the sidewalk / road so reflections of the
        neon signage and street lights read clearly.
        """
        st = CONFIG["street"]
        puddle_mat = self.mat.puddle()
        spots = []
        # Near-sidewalk puddles (visible right outside the glass).
        for i in range(4):
            spots.append((RNG.uniform(-10, 10),
                          RNG.uniform(*st["sidewalk_near"]) * 0.98, 0.125))
        # Road puddles (catching the traffic-light / car reflections).
        for i in range(4):
            spots.append((RNG.uniform(-14, 14),
                          RNG.uniform(st["road"][0] + 1, st["road"][1] - 1),
                          0.032))
        for i, (px, py, pz) in enumerate(spots):
            puddle = add_cylinder(f"FX_Puddle_{i:02d}",
                                  radius=RNG.uniform(0.5, 1.4), depth=0.003,
                                  location=(px, py, pz), vertices=24,
                                  collection=self.fx_coll,
                                  material=puddle_mat)
            # Irregular outline: jitter the rim vertices.
            for v in puddle.data.vertices:
                r = RNG.uniform(0.75, 1.25)
                v.co.x *= r
                v.co.y *= RNG.uniform(0.6, 1.1)
            shade_smooth(puddle)

    # ------------------------------------------------------------------ #
    #  RAIN ON THE GLASS
    # ------------------------------------------------------------------ #

    def build_window_rain(self):
        """
        Physical droplet + streak meshes on the exterior face of every
        window pane (the pane shader already carries bump droplets and
        condensation — these meshes catch real refraction highlights for
        close-up shots).
        """
        drop_mat = self.mat.rain_droplet()
        for pane in self.env.window_panes:
            dims = pane.dimensions
            w, h = dims.x, dims.z
            px, py, pz = pane.location
            out_y = py + 0.02          # exterior face of the pane
            n_drops = max(10, int(w * h * 6))
            for d in range(n_drops):
                dx = RNG.uniform(-w / 2 * 0.92, w / 2 * 0.92)
                dz = RNG.uniform(-h / 2 * 0.92, h / 2 * 0.92)
                r = RNG.uniform(0.004, 0.012)
                drop = add_sphere(f"FX_GlassDrop_{pane.name}_{d}",
                                  radius=r,
                                  location=(px + dx, out_y, pz + dz),
                                  segments=8, rings=6,
                                  collection=self.fx_coll, material=drop_mat)
                drop.scale = (1.0, 0.45, RNG.uniform(1.0, 1.8))
                apply_scale(drop)
                shade_smooth(drop)
                set_parent_keep_transform(drop, pane)
            # A few long run-down streaks per pane.
            for s in range(4):
                sx = RNG.uniform(-w / 2 * 0.85, w / 2 * 0.85)
                sz = RNG.uniform(-h / 2 * 0.4, h / 2 * 0.8)
                length = RNG.uniform(0.25, 0.8)
                streak = add_cube(f"FX_GlassStreak_{pane.name}_{s}",
                                  size=(0.007, 0.006, length),
                                  location=(px + sx, out_y, pz + sz - length / 2),
                                  collection=self.fx_coll, material=drop_mat)
                add_bevel(streak, width=0.003, segments=2)
                shade_smooth(streak)
                set_parent_keep_transform(streak, pane)

    # ------------------------------------------------------------------ #
    #  LIGHTNING + THUNDER
    # ------------------------------------------------------------------ #

    def build_lightning_and_thunder(self):
        """
        Periodic lightning:
          * one huge cold area light behind the far buildings
          * randomized flash times (double-strike energy envelopes)
          * matching world-background brightness pulses
          * THUNDER_## timeline markers a random sound-travel delay later
        """
        cfg = CONFIG["lightning"]

        # The strike light: enormous, cold, normally off.
        light_data = bpy.data.lights.new("LGT_Lightning", 'AREA')
        light_data.shape = 'RECTANGLE'
        light_data.size = 60.0
        light_data.size_y = 30.0
        light_data.color = (0.72, 0.80, 1.0)
        light_data.energy = 0.0
        strike = bpy.data.objects.new("LGT_Lightning", light_data)
        strike.location = (5.0, 45.0, 32.0)
        strike.rotation_euler = Euler((math.radians(-125), 0, 0))
        self.fx_coll.objects.link(strike)

        # World background reference for the sky pulse.
        world = bpy.context.scene.world
        bg = None
        if world and world.use_nodes:
            bg = next((n for n in world.node_tree.nodes
                       if n.type == 'BACKGROUND'), None)
        base_strength = bg.inputs['Strength'].default_value if bg else 0.0

        # Randomized flash schedule across the sequence.
        scene = bpy.context.scene
        frame = FRAME_START + RNG.randint(30, 80)
        flash_id = 0
        while flash_id < cfg["flash_count"] and frame < FRAME_END - 30:
            peak = RNG.uniform(120000.0, 260000.0)
            # Double-strike envelope: spike, dim, second spike, decay.
            envelope = [(0, 0.0), (1, peak), (3, peak * 0.15),
                        (5, peak * 0.7), (9, peak * 0.05), (14, 0.0)]
            for off, energy in envelope:
                keyframe(strike, "data.energy", frame + off, energy)
            if bg is not None:
                sky = [(0, base_strength), (1, base_strength * 7.0),
                       (3, base_strength * 1.6), (5, base_strength * 4.5),
                       (12, base_strength)]
                for off, strength in sky:
                    bg.inputs['Strength'].default_value = strength
                    bg.inputs['Strength'].keyframe_insert(
                        'default_value', frame=frame + off)

            # Thunder marker: light first, sound later.
            delay = RNG.randint(*cfg["thunder_delay_frames"])
            marker = scene.timeline_markers.new(
                f"THUNDER_{flash_id + 1:02d}", frame=min(FRAME_END,
                                                         frame + delay))
            flash_id += 1
            frame += RNG.randint(cfg["min_gap_frames"], 190)
        log(f"Lightning: {flash_id} flashes + thunder markers placed.")


# ============================================================================
#  LIGHTING SYSTEM
# ============================================================================

class LightingSystem:
    """
    Cinematic storm-evening lighting:
      * world:  dark blue-gray overcast gradient sky
      * exterior: dim cold sun + sodium street lamps + thin scatter volume
      * interior: warm 2700-3200K practicals (pendants, sconces, lamps),
        flickering candle lights, and soft warm bounce fills
      * strong warm-inside / cold-outside contrast by design
    """

    def __init__(self, materials, environment, shop):
        self.mat = materials
        self.env = environment
        self.shop = shop
        root = get_or_create_collection("CoffeeShop_Environment")
        self.light_coll = get_or_create_collection("Lighting", root)

    # ------------------------------------------------------------------ #

    def build(self):
        """Create world + all light objects."""
        self.build_world()
        self.build_exterior_lighting()
        self.build_interior_lighting()
        self.build_candle_lights()
        self.build_atmosphere_volume()
        log("LightingSystem complete.")

    def _make_light(self, name, light_type, location, energy, kelvin=None,
                    color=None, radius=0.1, rotation=(0, 0, 0),
                    spot_size=math.radians(65), area_size=1.0):
        """Factory for light objects with blackbody color support."""
        data = bpy.data.lights.new(name, light_type)
        data.energy = energy
        data.color = color if color else kelvin_to_rgb(kelvin or 4500)
        if light_type == 'POINT':
            data.shadow_soft_size = radius
        elif light_type == 'SPOT':
            data.spot_size = spot_size
            data.spot_blend = 0.6
            data.shadow_soft_size = radius
        elif light_type == 'AREA':
            data.size = area_size
        obj = bpy.data.objects.new(name, data)
        obj.location = location
        obj.rotation_euler = Euler(rotation)
        self.light_coll.objects.link(obj)
        return obj

    # ------------------------------------------------------------------ #
    #  WORLD
    # ------------------------------------------------------------------ #

    def build_world(self):
        """Dark storm sky: vertical blue-gray gradient, low energy."""
        world = bpy.data.worlds.get("World_Storm")
        if world is None:
            world = bpy.data.worlds.new("World_Storm")
        bpy.context.scene.world = world
        world.use_nodes = True
        nt = world.node_tree
        nt.nodes.clear()

        out = new_node(nt, 'ShaderNodeOutputWorld', (400, 0))
        bg = new_node(nt, 'ShaderNodeBackground', (200, 0))
        bg.inputs['Strength'].default_value = 0.22

        coord = new_node(nt, 'ShaderNodeTexCoord', (-600, 0))
        sep = new_node(nt, 'ShaderNodeSeparateXYZ', (-400, 0))
        nt.links.new(coord.outputs['Generated'], sep.inputs['Vector'])
        ramp = new_node(nt, 'ShaderNodeValToRGB', (-200, 0))
        # Horizon: murky gray-blue.  Zenith: near-black storm cloud.
        ramp.color_ramp.elements[0].position = 0.45
        ramp.color_ramp.elements[0].color = (0.13, 0.16, 0.21, 1.0)
        ramp.color_ramp.elements[1].position = 0.75
        ramp.color_ramp.elements[1].color = (0.015, 0.02, 0.035, 1.0)
        nt.links.new(sep.outputs['Z'], ramp.inputs['Fac'])
        nt.links.new(ramp.outputs['Color'], bg.inputs['Color'])
        nt.links.new(bg.outputs['Background'], out.inputs['Surface'])

    # ------------------------------------------------------------------ #
    #  EXTERIOR
    # ------------------------------------------------------------------ #

    def build_exterior_lighting(self):
        """Cold dim sun + sodium street lamps + sign accents."""
        # Overcast "sun": barely-there, very soft, cold.
        sun = self._make_light("LGT_Storm_Sun", 'SUN', (0, 20, 30),
                               energy=1.2, kelvin=CONFIG["exterior_kelvin"],
                               rotation=(math.radians(-35),
                                         math.radians(-15), 0))
        sun.data.angle = math.radians(12)   # heavily diffused by cloud cover

        # Street lamps: warm sodium pools on the wet asphalt.
        for i, (lx, ly, lz) in enumerate(self.env.street_light_heads):
            self._make_light(f"LGT_StreetLamp_{i:02d}", 'SPOT',
                             (lx, ly, lz), energy=900.0, kelvin=2200,
                             radius=0.15,
                             rotation=(0, 0, 0),   # spots point -Z by default
                             spot_size=math.radians(110))

        # Storefront sign glow accents across the street.
        for i, (sx, sy, sz) in enumerate(self.env.lit_sign_positions):
            self._make_light(f"LGT_SignGlow_{i:02d}", 'POINT',
                             (sx, sy, sz), energy=60.0,
                             color=(1.0, 0.6, 0.35), radius=0.4)

        # Cold rim light washing the window wall from the street side.
        self._make_light("LGT_Street_Fill", 'AREA', (0, 12.0, 7.0),
                         energy=350.0, kelvin=CONFIG["exterior_kelvin"],
                         rotation=(math.radians(-115), 0, 0), area_size=18.0)

    # ------------------------------------------------------------------ #
    #  INTERIOR
    # ------------------------------------------------------------------ #

    def build_interior_lighting(self):
        """Warm practicals from the shop registry + soft bounce fills."""
        # Practical lights registered by the CoffeeShopBuilder
        # (pendants, sconces, floor lamp, display case, neon sign).
        for i, ((lx, ly, lz), kelvin, energy) in enumerate(
                self.shop.lamp_light_positions):
            self._make_light(f"LGT_Practical_{i:02d}", 'POINT',
                             (lx, ly, lz), energy=energy, kelvin=kelvin,
                             radius=0.08)

        # Indirect warm bounce fills (simulating GI pooling on the ceiling).
        self._make_light("LGT_Bounce_Ceiling_A", 'AREA', (-3.0, 0.0, 3.95),
                         energy=110.0, kelvin=3000,
                         rotation=(0, 0, 0), area_size=5.0)
        self._make_light("LGT_Bounce_Ceiling_B", 'AREA', (4.0, -1.0, 3.95),
                         energy=90.0, kelvin=2900,
                         rotation=(0, 0, 0), area_size=4.0)
        # Low warm kicker behind the bar (bottle-shelf glow).
        self._make_light("LGT_Bar_Kicker", 'AREA', (-1.0, -5.4, 2.6),
                         energy=60.0, kelvin=2700,
                         rotation=(math.radians(80), 0, 0), area_size=3.0)

    def build_candle_lights(self):
        """Tiny flickering point lights at every candle flame."""
        for i, (cx, cy, cz) in enumerate(self.shop.candle_positions):
            candle = self._make_light(f"LGT_Candle_{i:02d}", 'POINT',
                                      (cx, cy, cz), energy=4.0, kelvin=1900,
                                      radius=0.02)
            # Flicker: keyframe once, then layer f-curve noise on energy.
            keyframe(candle, "data.energy", FRAME_START, 4.0)
            keyframe(candle, "data.energy", FRAME_END, 4.0)
            add_fcurve_noise(candle.data, "energy", strength=2.2,
                             scale=6.0, offset=RNG.uniform(0, 100))

    def build_atmosphere_volume(self):
        """Thin scatter volume over the street: rain haze + light shafts."""
        vol = add_cube("LGT_Atmosphere_Volume",
                       size=(2 * CONFIG["street"]["extent_x"], 26.0, 16.0),
                       location=(0, 13.0, 8.0),
                       collection=self.light_coll,
                       material=self.mat.atmosphere_volume())
        vol.display_type = 'WIRE'
        # Keep it out of camera-ray glass reflections cheaply.
        vol.visible_shadow = False


# ============================================================================
#  ANIMATION SYSTEM  (physics, steam, wind sway)
# ============================================================================

class AnimationSystem:
    """
    All simulation + secondary animation:
      * cloth        -> curtains (pinned top edge, wind-driven)
      * rigid body   -> chairs / bean bags (settled, deactivation-started)
      * soft body    -> couch + armchair cushions (goal-pinned jiggle)
      * particles    -> interior dust motes
      * volumetrics  -> animated coffee / espresso steam
      * f-curve noise-> subtle wind sway on plants + hanging decor
    """

    def __init__(self, materials, environment, shop):
        self.mat = materials
        self.env = environment
        self.shop = shop
        root = get_or_create_collection("CoffeeShop_Environment")
        self.fx_coll = get_or_create_collection("Weather_FX", root)

    def build(self):
        """Configure every physics system and secondary animation."""
        self.setup_rigid_body_world()
        self.setup_cloth()
        self.setup_rigid_bodies()
        self.setup_soft_bodies()
        self.setup_dust()
        self.setup_steam()
        self.setup_wind_sway()
        log("AnimationSystem complete.")

    # ------------------------------------------------------------------ #
    #  PHYSICS WORLDS
    # ------------------------------------------------------------------ #

    def setup_rigid_body_world(self):
        """Ensure a rigid body world exists and spans the sequence."""
        scene = bpy.context.scene
        if scene.rigidbody_world is None:
            bpy.ops.rigidbody.world_add()
        rbw = scene.rigidbody_world
        rbw.point_cache.frame_start = FRAME_START
        rbw.point_cache.frame_end = FRAME_END
        try:
            rbw.substeps_per_frame = 10
            rbw.solver_iterations = 10
        except AttributeError:
            pass

    def setup_cloth(self):
        """Cloth simulation on the curtain panels (uses the PIN group)."""
        for panel in self.shop.cloth_targets:
            cloth = panel.modifiers.new("Cloth", 'CLOTH')
            st = cloth.settings
            st.quality = 6
            st.mass = 0.25                     # light linen
            st.air_damping = 1.2
            st.tension_stiffness = 12.0
            st.compression_stiffness = 12.0
            st.shear_stiffness = 6.0
            st.bending_stiffness = 0.4
            if panel.vertex_groups.get("PIN"):
                st.vertex_group_mass = "PIN"   # pinned top edge
            cloth.point_cache.frame_start = FRAME_START
            cloth.point_cache.frame_end = FRAME_END
            # Keep the Solidify AFTER Cloth so thickness follows the sim.
            solid = panel.modifiers.get("Solidify")
            if solid:
                with bpy.context.temp_override(object=panel):
                    try:
                        bpy.ops.object.modifier_move_to_index(
                            modifier="Solidify",
                            index=len(panel.modifiers) - 1)
                    except Exception:
                        pass

    def setup_rigid_bodies(self):
        """
        Rigid bodies: floor + counters are passive; chairs / bean bags are
        active.  After configuration the actives' settling motion is BAKED
        TO KEYFRAMES so the composition is deterministic at any frame
        (live rigid-body caches misbehave on non-sequential timeline
        evaluation, e.g. when jumping straight to a render frame).
        """
        passive_names = ("ARCH_Floor_Wood", "BAR_Counter_Body",
                         "BAR_Counter_Top", "BAR_BackCounter_Body",
                         "BAR_BackCounter_Top")
        for name in passive_names:
            obj = bpy.data.objects.get(name)
            if obj is None:
                continue
            set_active(obj)
            try:
                bpy.ops.rigidbody.object_add(type='PASSIVE')
                obj.rigid_body.friction = 0.9
            except RuntimeError as exc:
                warn(f"Passive rigid body failed on {name}: {exc}")

        actives = [o for o in self.shop.rigid_active if o is not None]
        for obj in actives:
            set_active(obj)
            try:
                bpy.ops.rigidbody.object_add(type='ACTIVE')
            except RuntimeError as exc:
                warn(f"Rigid body failed on {obj.name}: {exc}")
                continue
            rb = obj.rigid_body
            rb.mass = 4.0
            rb.friction = 0.8
            rb.restitution = 0.05
            rb.linear_damping = 0.6
            rb.angular_damping = 0.7
            rb.collision_shape = 'CONVEX_HULL'
            rb.use_deactivation = True

        # Bake the settle (everything comes to rest well within 60 frames)
        # to plain keyframes: stable renders at ANY frame + clean FBX
        # animation.  Done manually via the evaluated depsgraph because
        # bpy.ops.rigidbody.bake_to_keyframes needs UI context and fails
        # in background/headless runs.
        actives = [o for o in actives if o.rigid_body is not None]
        if actives:
            scene = bpy.context.scene
            settle_end = FRAME_START + 60
            sampled = {obj.name: [] for obj in actives}
            for f in range(FRAME_START, settle_end + 1):
                scene.frame_set(f)   # sequential stepping = valid sim cache
                deps = bpy.context.evaluated_depsgraph_get()
                for obj in actives:
                    ev = obj.evaluated_get(deps)
                    sampled[obj.name].append((f, ev.matrix_world.copy()))
            # Remove the bodies from the sim, then key the sampled motion.
            for obj in actives:
                set_active(obj)
                try:
                    bpy.ops.rigidbody.object_remove()
                except RuntimeError:
                    pass
                for f, mw in sampled[obj.name]:
                    obj.matrix_world = mw
                    obj.keyframe_insert("location", frame=f)
                    obj.keyframe_insert("rotation_euler", frame=f)
            scene.frame_set(FRAME_START)
            log(f"Rigid-body settle baked to keyframes "
                f"({len(actives)} objects, {settle_end - FRAME_START + 1} "
                f"frames).")

    def setup_soft_bodies(self):
        """Goal-pinned soft bodies on every registered cushion."""
        for cushion in self.shop.soft_body_targets:
            sb = cushion.modifiers.new("Softbody", 'SOFT_BODY')
            st = sb.settings
            st.use_goal = True
            st.goal_default = 0.85             # mostly holds its shape
            st.goal_spring = 0.6
            st.goal_friction = 4.0
            st.mass = 0.6
            st.use_edges = True
            st.pull = 0.6
            st.push = 0.6
            st.bend = 4.0
            sb.point_cache.frame_start = FRAME_START
            sb.point_cache.frame_end = FRAME_END

    # ------------------------------------------------------------------ #
    #  PARTICLES: DUST
    # ------------------------------------------------------------------ #

    def setup_dust(self):
        """Slow-drifting dust motes catching the warm practicals."""
        mote = add_sphere("FX_Dust_Mote", radius=0.004,
                          location=(0, 0, -52.0), segments=8, rings=6,
                          collection=self.fx_coll,
                          material=self.mat.dust_mote())

        emitter = add_cube("FX_Dust_Emitter", size=(14.0, 10.0, 3.4),
                           location=(0, 0, 2.0),
                           collection=self.fx_coll)
        emitter.hide_render = True
        emitter.display_type = 'WIRE'

        mod = emitter.modifiers.new("DustParticles", 'PARTICLE_SYSTEM')
        settings = mod.particle_system.settings
        settings.name = "PS_Dust"
        settings.count = 350
        settings.frame_start = FRAME_START - 100   # already drifting
        settings.frame_end = FRAME_END
        settings.lifetime = FRAME_END + 200
        settings.emit_from = 'VOLUME'
        settings.physics_type = 'NEWTON'
        settings.normal_factor = 0.0
        settings.brownian_factor = 0.02            # gentle random drift
        settings.drag_factor = 0.9
        settings.effector_weights.gravity = 0.002  # near-weightless
        settings.effector_weights.wind = 0.0       # indoor air is still
        settings.effector_weights.turbulence = 0.01
        settings.render_type = 'OBJECT'
        settings.instance_object = mote
        settings.particle_size = 1.0
        settings.size_random = 0.6

    # ------------------------------------------------------------------ #
    #  STEAM
    # ------------------------------------------------------------------ #

    def setup_steam(self):
        """
        Volumetric steam columns above every registered source (coffee
        cups, espresso wand, brewer carafe).  The shared volume shader's
        mapping node is animated so the noise field drifts upward.
        """
        steam_mat = self.mat.steam_volume()
        for i, (sx, sy, sz, scale) in enumerate(self.shop.steam_sources):
            column = add_cone(f"FX_Steam_{i:02d}",
                              radius1=0.035 * scale, radius2=0.10 * scale,
                              depth=0.55 * scale,
                              location=(sx, sy, sz + 0.27 * scale),
                              vertices=12,
                              collection=self.fx_coll, material=steam_mat)
            column.display_type = 'WIRE'
            column.visible_shadow = False
            shade_smooth(column)

        # Animate the shared noise-drift mapping (upward motion = -Z shift
        # of the noise space with LINEAR interpolation for constant speed).
        nt = steam_mat.node_tree
        mapping = nt.nodes.get("SteamDrift")
        if mapping is not None:
            loc_in = mapping.inputs['Location']
            loc_in.default_value = (0.0, 0.0, 0.0)
            loc_in.keyframe_insert('default_value', frame=FRAME_START)
            loc_in.default_value = (0.15, 0.0, -8.0)
            loc_in.keyframe_insert('default_value', frame=FRAME_END)
            for fcu in get_action_fcurves(nt):
                for kp in fcu.keyframe_points:
                    kp.interpolation = 'LINEAR'

    # ------------------------------------------------------------------ #
    #  WIND SWAY
    # ------------------------------------------------------------------ #

    def setup_wind_sway(self):
        """
        Subtle storm-draft sway on plants, hanging pots, pendant shades
        and string-light bulbs: static keyframes + f-curve noise.
        """
        for obj in self.shop.sway_objects:
            base = tuple(obj.rotation_euler)
            keyframe(obj, "rotation_euler", FRAME_START, base[0], index=0)
            keyframe(obj, "rotation_euler", FRAME_END, base[0], index=0)
            keyframe(obj, "rotation_euler", FRAME_START, base[1], index=1)
            keyframe(obj, "rotation_euler", FRAME_END, base[1], index=1)
            # Hanging items swing more than potted foliage.
            hanging = ("Pendant" in obj.name or "HangPlant" in obj.name
                       or "StringBulb" in obj.name)
            strength = 0.045 if hanging else 0.02
            add_fcurve_noise(obj, "rotation_euler", index=0,
                             strength=strength, scale=45.0,
                             offset=RNG.uniform(0, 200))
            add_fcurve_noise(obj, "rotation_euler", index=1,
                             strength=strength * 0.7, scale=38.0,
                             offset=RNG.uniform(0, 200))


# ============================================================================
#  CAMERA SYSTEM  (6 cinematic cameras, 30-second bound sequence)
# ============================================================================

class CameraSystem:
    """
    Cinematic coverage:
      Interior: counter dolly, reading-corner push-in, window-seat rack
                focus, high wide room move.
      Exterior: street view of the glowing shop, rain/puddle close-up.
    Cameras are cut together with camera-bound timeline markers, animated
    with eased dolly moves, physical DOF and focus transitions.
    """

    def __init__(self):
        root = get_or_create_collection("CoffeeShop_Environment")
        self.cam_coll = get_or_create_collection("Cameras", root)
        self.cameras = []

    def build(self):
        """Create all cameras and assemble the 30 s sequence."""
        scene = bpy.context.scene
        scene.frame_start = FRAME_START
        scene.frame_end = FRAME_END
        scene.render.fps = CONFIG["fps"]

        shot_len = (FRAME_END - FRAME_START + 1) // 6   # 120 frames per shot

        # ---- shot definitions -------------------------------------------
        # (name, lens_mm, f-stop, cam_start, cam_end, target_start,
        #  target_end, use_focus_object)
        shots = [
            # Behind-the-bar dolly: group heads + portafilters in the
            # foreground, warm seating and rainy glass bokeh beyond.
            ("CAM_01_CounterDolly", 40, 2.2,
             (1.6, -5.0, 1.6), (-4.2, -5.05, 1.4),
             (-1.9, -2.7, 1.25), (-2.1, -2.8, 1.2), True),
            ("CAM_02_ReadingCorner", 35, 2.2,
             (-5.5, -0.6, 1.75), (-5.8, -2.6, 1.2),
             (-6.4, -4.3, 0.9), (-6.5, -4.6, 0.6), True),
            ("CAM_03_WindowRackFocus", 50, 1.8,
             (-2.4, 3.2, 1.45), (-4.0, 3.5, 1.40),
             (-3.6, 5.32, 1.15), (-3.6, 5.32, 1.15), False),
            ("CAM_04_WideRoom", 24, 4.0,
             (6.8, -4.6, 3.1), (4.6, -5.1, 2.7),
             (-0.5, 1.5, 1.1), (-1.5, 2.0, 1.1), True),
            ("CAM_05_StreetExterior", 35, 2.8,
             (-9.0, 14.5, 1.9), (-3.0, 12.8, 1.7),
             (0.0, 6.1, 2.2), (1.5, 6.1, 2.0), True),
            ("CAM_06_RainCloseup", 85, 2.0,
             (7.5, 9.5, 1.1), (6.4, 8.4, 0.9),
             (4.2, 6.2, 2.5), (4.2, 6.2, 2.3), True),
        ]

        for idx, spec in enumerate(shots):
            (name, lens, fstop, cam_a, cam_b,
             tgt_a, tgt_b, use_focus_obj) = spec
            f0 = FRAME_START + idx * shot_len
            f1 = f0 + shot_len - 1 if idx < 5 else FRAME_END
            cam = self._create_camera(name, lens, fstop, cam_a, tgt_a,
                                      use_focus_obj)
            self._animate_dolly(cam, cam_a, cam_b, tgt_a, tgt_b, f0, f1)

            # Bind the shot to the timeline (auto camera switching).
            marker = scene.timeline_markers.new(f"SHOT_{idx + 1:02d}_{name}",
                                                frame=f0)
            marker.camera = cam
            self.cameras.append(cam)

        # Shot 3 rack focus: droplets on the glass -> street bokeh -> back.
        self._rack_focus(self.cameras[2],
                         frames_values=[
                             (FRAME_START + 2 * shot_len, 2.1),
                             (FRAME_START + 2 * shot_len + 45, 2.1),
                             (FRAME_START + 2 * shot_len + 75, 9.0),
                             (FRAME_START + 3 * shot_len - 8, 9.0)])

        scene.camera = self.cameras[0]
        log(f"CameraSystem: {len(self.cameras)} cameras, "
            f"{shot_len} frames per shot.")

    # ------------------------------------------------------------------ #

    def _create_camera(self, name, lens, fstop, location, target,
                       use_focus_obj):
        """Camera + tracked target empty + physical depth of field."""
        data = bpy.data.cameras.new(name)
        data.lens = lens
        data.sensor_width = 36.0
        data.dof.use_dof = True
        data.dof.aperture_fstop = fstop
        data.dof.aperture_blades = 9      # round cinematic bokeh
        cam = bpy.data.objects.new(name, data)
        cam.location = location
        self.cam_coll.objects.link(cam)

        target_empty = add_empty(name + "_Target", location=target,
                                 collection=self.cam_coll)
        track = cam.constraints.new('TRACK_TO')
        track.target = target_empty
        track.track_axis = 'TRACK_NEGATIVE_Z'
        track.up_axis = 'UP_Y'

        if use_focus_obj:
            data.dof.focus_object = target_empty   # focus follows the move
        cam["target_empty"] = target_empty.name
        return cam

    def _animate_dolly(self, cam, cam_a, cam_b, tgt_a, tgt_b, f0, f1):
        """Eased dolly move for the camera + its look/focus target."""
        target = bpy.data.objects.get(cam["target_empty"])

        cam.location = cam_a
        cam.keyframe_insert("location", frame=f0)
        cam.location = cam_b
        cam.keyframe_insert("location", frame=f1)

        if target is not None:
            target.location = tgt_a
            target.keyframe_insert("location", frame=f0)
            target.location = tgt_b
            target.keyframe_insert("location", frame=f1)

        # Smooth ease-in/out on every dolly curve (realistic motion).
        for id_obj in (cam, target):
            if id_obj is None:
                continue
            for fcu in get_action_fcurves(id_obj):
                if fcu.data_path != "location":
                    continue
                for kp in fcu.keyframe_points:
                    kp.interpolation = 'BEZIER'
                    kp.easing = 'EASE_IN_OUT'
                    kp.handle_left_type = 'AUTO_CLAMPED'
                    kp.handle_right_type = 'AUTO_CLAMPED'

    def _rack_focus(self, cam, frames_values):
        """Keyframed focus-distance transition (manual rack focus)."""
        data = cam.data
        data.dof.focus_object = None
        for frame, dist in frames_values:
            data.dof.focus_distance = dist
            data.dof.keyframe_insert("focus_distance", frame=frame)


# ============================================================================
#  RENDER CONFIGURATION  (Cycles, photorealism-optimized)
# ============================================================================

def configure_render():
    """
    Cycles path tracing tuned for photoreal interiors:
    denoised adaptive sampling, deep light bounces for GI, volumetrics
    for steam/atmosphere, caustics for the glass + puddles, filmic AgX
    color management and cinematic motion blur.
    """
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    cyc = scene.cycles
    r = CONFIG["render"]

    # -- sampling + denoising ------------------------------------------------
    cyc.samples = r["samples"]
    cyc.use_adaptive_sampling = True
    cyc.adaptive_threshold = 0.01
    cyc.use_denoising = True
    try:
        cyc.denoiser = 'OPENIMAGEDENOISE'
        cyc.denoising_use_gpu = True
    except (AttributeError, TypeError):
        pass

    # -- light transport (global illumination) --------------------------------
    cyc.max_bounces = r["max_bounces"]
    cyc.diffuse_bounces = 6
    cyc.glossy_bounces = 6
    cyc.transmission_bounces = 12     # storefront glass needs deep bounces
    cyc.volume_bounces = r["volume_bounces"]
    cyc.transparent_max_bounces = 16
    cyc.sample_clamp_indirect = 10.0  # tame lightning fireflies

    # -- caustics (glass + puddle sparkle) -------------------------------------
    cyc.caustics_reflective = r["use_caustics"]
    cyc.caustics_refractive = r["use_caustics"]
    cyc.blur_glossy = 0.5

    # -- volumetrics ------------------------------------------------------------
    try:
        cyc.volume_step_rate = 1.0
        cyc.volume_max_steps = 64
    except AttributeError:
        pass

    # -- motion blur (realistic camera + rain motion) ---------------------------
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = 0.5

    # -- output ------------------------------------------------------------------
    scene.render.resolution_x, scene.render.resolution_y = r["resolution"]
    scene.render.resolution_percentage = 100
    scene.render.fps = CONFIG["fps"]

    # -- color management: AgX for filmic highlight rolloff ----------------------
    try:
        scene.view_settings.view_transform = 'AgX'
        scene.view_settings.look = 'AgX - Base Contrast'
    except TypeError:
        warn("AgX view transform unavailable; using default.")
    scene.view_settings.exposure = 0.0

    # -- metric units (matches Unity's 1 unit = 1 meter) --------------------------
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.0
    log("Cycles render configured for photorealism.")


# ============================================================================
#  EXPORT MANAGER  (LODs, texture optimization, Unity FBX/GLB pipeline)
# ============================================================================

class ExportManager:
    """
    Game-ready optimization + automated Unity export:
      * LOD0-LOD3 generation via non-destructive Decimate modifiers
        (LOD0 = high poly, LOD1 = medium, LOD2/3 = low poly) with
        Unity-convention  _LODn  naming for automatic LOD Group setup
      * texture downscaling to the configured budget (2K / 4K / 8K)
      * FBX + GLB export preserving transforms, pivots, materials and
        animation, with textures copied alongside
    """

    # Collections containing exportable scene geometry.
    GEO_COLLECTIONS = ("Architecture", "Furniture", "CoffeeBar",
                       "Decor", "Exterior")

    def __init__(self):
        self.export_dir = os.path.join(project_root(), CONFIG["export_dir"])
        os.makedirs(self.export_dir, exist_ok=True)
        self.lods_generated = False

    # ------------------------------------------------------------------ #
    #  LOD GENERATION
    # ------------------------------------------------------------------ #

    def generate_lods(self):
        """
        For every exportable mesh, create LOD1-LOD3 duplicates with
        progressively stronger Decimate modifiers.  The original object is
        renamed to *_LOD0 (Unity's LOD Group importer convention).
        Exterior (EXT_) props decimate twice as hard — they are only ever
        seen through the windows.
        """
        lod_coll = get_or_create_collection(
            "LODs", get_or_create_collection("CoffeeShop_Environment"))
        ratios = CONFIG["lod_ratios"]
        made = 0

        for coll_name in self.GEO_COLLECTIONS:
            coll = bpy.data.collections.get(coll_name)
            if coll is None:
                continue
            for obj in list(coll.objects):
                if obj.type != 'MESH' or obj.name.endswith("_LOD0"):
                    continue
                if len(obj.data.polygons) < 8:
                    continue   # trivial meshes gain nothing from LODs
                is_background = obj.name.startswith("EXT_")
                base_name = obj.name
                obj.name = base_name + "_LOD0"

                for lod_i in range(1, len(ratios)):
                    ratio = ratios[lod_i] * (0.5 if is_background else 1.0)
                    dup = obj.copy()
                    dup.data = obj.data.copy()
                    dup.name = f"{base_name}_LOD{lod_i}"
                    dup.animation_data_clear()
                    lod_coll.objects.link(dup)
                    dec = dup.modifiers.new("LOD_Decimate", 'DECIMATE')
                    dec.ratio = max(0.02, ratio)
                    dec.use_collapse_triangulate = True
                    made += 1

        # LOD copies stay out of renders (they exist for the game export).
        layer_coll = self._find_layer_collection(
            bpy.context.view_layer.layer_collection, "LODs")
        if layer_coll:
            layer_coll.exclude = False
        lod_coll.hide_render = True
        self.lods_generated = True
        log(f"Generated {made} LOD meshes (LOD1-LOD3).")

    @staticmethod
    def _find_layer_collection(layer_coll, name):
        """Recursive lookup of a view-layer collection by name."""
        if layer_coll.name == name:
            return layer_coll
        for child in layer_coll.children:
            found = ExportManager._find_layer_collection(child, name)
            if found:
                return found
        return None

    # ------------------------------------------------------------------ #
    #  TEXTURE OPTIMIZATION
    # ------------------------------------------------------------------ #

    def optimize_textures(self, max_size=None):
        """
        Downscale every image over the texture budget.  Supported budgets:
        2048 (2K), 4096 (4K), 8192 (8K) — set CONFIG['texture_max_size'].
        """
        max_size = max_size or CONFIG["texture_max_size"]
        if max_size not in (2048, 4096, 8192):
            warn(f"Unusual texture budget {max_size}; proceeding anyway.")
        scaled = 0
        for img in bpy.data.images:
            w, h = img.size
            if w <= max_size and h <= max_size:
                continue
            factor = max_size / max(w, h)
            img.scale(max(1, int(w * factor)), max(1, int(h * factor)))
            scaled += 1
        log(f"Texture optimization: {scaled} image(s) downscaled to "
            f"<= {max_size}px.")

    def export_textures(self):
        """Copy/save every real texture image into UnityExport/Textures."""
        tex_dir = os.path.join(self.export_dir, "Textures")
        os.makedirs(tex_dir, exist_ok=True)
        exported = 0
        for img in bpy.data.images:
            if img.size[0] == 0 or img.name in ("Render Result",
                                                "Viewer Node"):
                continue
            safe = "".join(c if c.isalnum() or c in "-_." else "_"
                           for c in img.name)
            path = os.path.join(tex_dir, os.path.splitext(safe)[0] + ".png")
            try:
                img.save_render(path)
                exported += 1
            except RuntimeError as exc:
                warn(f"Could not export image {img.name}: {exc}")
        log(f"Exported {exported} texture(s) -> {tex_dir}")

    # ------------------------------------------------------------------ #
    #  SELECTION FOR EXPORT
    # ------------------------------------------------------------------ #

    def _select_exportables(self):
        """
        Select everything Unity should receive: geometry, LODs, lights,
        cameras and empties — excluding simulation helpers (emitters,
        off-screen instance sources, volumes).
        """
        bpy.ops.object.select_all(action='DESELECT')
        count = 0
        for obj in bpy.context.scene.objects:
            if obj.hide_render and obj.type == 'MESH':
                continue                        # particle emitters etc.
            if obj.location.z < -20.0:
                continue                        # parked instance meshes
            if obj.name.startswith(("FX_Steam", "LGT_Atmosphere")):
                continue                        # volumes don't translate
            if obj.type in {'MESH', 'LIGHT', 'CAMERA', 'EMPTY'}:
                obj.select_set(True)
                count += 1
        return count

    # ------------------------------------------------------------------ #
    #  FBX / GLB
    # ------------------------------------------------------------------ #

    def export_fbx(self):
        """FBX export tuned for Unity (Y-up conversion, baked anim, LODs)."""
        path = os.path.join(self.export_dir, "CoffeeShop_Environment.fbx")
        n = self._select_exportables()
        kwargs = dict(
            filepath=path,
            use_selection=True,
            object_types={'MESH', 'LIGHT', 'CAMERA', 'EMPTY'},
            use_mesh_modifiers=True,          # applies Decimate LODs, bevels
            apply_unit_scale=True,
            apply_scale_options='FBX_SCALE_ALL',   # Unity scale factor = 1
            axis_forward='-Z', axis_up='Y',
            bake_space_transform=True,        # clean pivots in Unity
            use_triangles=False,
            bake_anim=True,
            bake_anim_use_all_bones=False,
            # Bake only each object's ASSIGNED action — the all-actions /
            # NLA defaults re-bake every action against every animated
            # object, which is combinatorially slow in a scene with
            # hundreds of flicker/sway actions.
            bake_anim_use_all_actions=False,
            bake_anim_use_nla_strips=False,
            bake_anim_step=2.0,               # 12 keys/s is plenty for sway
            bake_anim_simplify_factor=0.05,
            path_mode='COPY',                 # textures shipped with the FBX
            embed_textures=False,
            mesh_smooth_type='FACE',
        )
        try:
            bpy.ops.export_scene.fbx(**kwargs)
        except TypeError:
            # Exporter signature changed: retry with the safe core args.
            bpy.ops.export_scene.fbx(filepath=path, use_selection=True,
                                     bake_anim=True, path_mode='COPY')
        except AttributeError:
            warn("FBX exporter add-on unavailable; skipped FBX.")
            return None
        log(f"FBX exported ({n} objects) -> {path}")
        return path

    def export_glb(self):
        """GLB export (PBR materials + punctual lights + animation)."""
        path = os.path.join(self.export_dir, "CoffeeShop_Environment.glb")
        self._select_exportables()
        kwargs = dict(
            filepath=path,
            export_format='GLB',
            use_selection=True,
            export_apply=True,                # apply modifiers (LODs etc.)
            export_animations=True,
            export_cameras=True,
            export_lights=True,
            export_yup=True,
        )
        try:
            bpy.ops.export_scene.gltf(**kwargs)
        except TypeError:
            bpy.ops.export_scene.gltf(filepath=path, export_format='GLB',
                                      use_selection=True)
        except AttributeError:
            warn("glTF exporter add-on unavailable; skipped GLB.")
            return None
        log(f"GLB exported -> {path}")
        return path

    def write_unity_readme(self):
        """Drop an import-notes file next to the exports."""
        notes = {
            "scene": "Hyperrealistic rainy coffee shop environment",
            "units": "1 unit = 1 meter (Unity scale factor should be 1.0)",
            "lods": "Meshes use _LOD0.._LOD3 suffixes -> enable "
                    "'Import LODs' / LOD Group generation on import.",
            "materials": "Principled BSDF converts to Unity Standard / URP "
                         "Lit; procedural shading bakes are recommended for "
                         "hero assets (use the exported texture folder).",
            "animation": "720-frame (30 s @ 24 fps) camera sequence + "
                         "flicker/sway actions baked into the FBX.",
            "thunder": "Timeline markers THUNDER_01.. mark thunder SFX sync "
                       "points (frames listed below).",
            "thunder_frames": [m.frame for m in
                               bpy.context.scene.timeline_markers
                               if m.name.startswith("THUNDER")],
        }
        path = os.path.join(self.export_dir, "UNITY_IMPORT_NOTES.json")
        with open(path, "w") as fh:
            json.dump(notes, fh, indent=2)
        log(f"Unity import notes -> {path}")

    # ------------------------------------------------------------------ #
    #  ONE-CLICK PIPELINE
    # ------------------------------------------------------------------ #

    def export_for_unity(self):
        """Full pipeline: LODs -> texture budget -> FBX + GLB + textures."""
        if not self.lods_generated:
            run_stage("LOD generation", self.generate_lods)
        run_stage("Texture optimization", self.optimize_textures)
        if CONFIG["export_fbx"]:
            run_stage("FBX export", self.export_fbx)
        if CONFIG["export_glb"]:
            run_stage("GLB export", self.export_glb)
        run_stage("Texture export", self.export_textures)
        run_stage("Unity notes", self.write_unity_readme)
        log(f"Unity export complete -> {self.export_dir}")
        return self.export_dir


def export_for_unity():
    """
    Public one-call Unity export (as required by the pipeline spec):
    creates an ExportManager and runs the complete export chain.
    """
    return ExportManager().export_for_unity()


# ============================================================================
#  MAIN
# ============================================================================

def print_build_report():
    """Human-readable end-of-build summary."""
    log("=" * 64)
    log("BUILD REPORT")
    for stage, status, seconds in BUILD_REPORT["stages"]:
        log(f"  {stage:<28} {status:<12} {seconds:>7.2f}s")
    log(f"  Objects created: {BUILD_REPORT['objects']}")
    if BUILD_REPORT["warnings"]:
        log(f"  Warnings ({len(BUILD_REPORT['warnings'])}):")
        for w in BUILD_REPORT["warnings"]:
            log(f"    - {w}")
    log("=" * 64)


def main():
    """
    One-click entry point.  Builds the entire hyperrealistic rainy coffee
    shop environment, configures weather / physics / lighting / cameras /
    rendering, generates LODs and exports everything for Unity.
    """
    t_start = time.time()
    log("#" * 64)
    log("#  HYPERREALISTIC COZY COFFEE SHOP — PROCEDURAL GENERATOR")
    log("#" * 64)

    # Deterministic rebuilds no matter how often the script is re-run.
    RNG.seed(CONFIG["seed"])

    # 0. Fresh scene ---------------------------------------------------------
    run_stage("Scene reset", clear_scene)

    # 1. Materials + AI texture system ---------------------------------------
    materials = run_stage("Material system", MaterialManager)
    if materials is None:
        log("Material system failed — aborting build.", level="ERROR")
        return

    # 2. Architecture + exterior street ----------------------------------------
    environment = EnvironmentBuilder(materials)
    run_stage("Environment build", environment.build)

    # 3. Interior: furniture, coffee bar, decor ----------------------------------
    shop = CoffeeShopBuilder(materials)
    run_stage("Coffee shop build", shop.build)

    # 4. Lighting (world first — the weather system pulses it) --------------------
    lighting = LightingSystem(materials, environment, shop)
    run_stage("Lighting", lighting.build)

    # 5. Weather: rain, wind, puddles, lightning, thunder markers -----------------
    weather = WeatherSystem(materials, environment)
    run_stage("Weather system", weather.build)

    # 6. Physics + steam + sway animation ------------------------------------------
    animation = AnimationSystem(materials, environment, shop)
    run_stage("Animation & physics", animation.build)

    # 7. Cinematic cameras + 30 s sequence -------------------------------------------
    cameras = CameraSystem()
    run_stage("Camera system", cameras.build)

    # 8. Cycles photoreal render setup --------------------------------------------------
    run_stage("Render configuration", configure_render)

    # 9. Optimization + Unity export ------------------------------------------------------
    exporter = ExportManager()
    run_stage("Unity export pipeline", exporter.export_for_unity)

    # Done. ---------------------------------------------------------------------
    print_build_report()
    log(f"TOTAL BUILD TIME: {time.time() - t_start:.1f}s")
    log("Ready: press F12 to render, or play the timeline for the "
        "30-second cinematic sequence.")


# Run automatically when executed from Blender's Text Editor ("Run Script")
# or headless via  blender --background --python coffee_shop_generator.py
if __name__ == "__main__":
    main()
