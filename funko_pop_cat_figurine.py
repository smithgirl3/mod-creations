# ============================================================================
#  FUNKO POP–STYLE CAT FIGURINE — PROCEDURAL GENERATOR
#  Blender 5.2.0  |  bpy Python API  |  3D-Print Ready
# ============================================================================
#
#  Builds a stylized collectible cat figurine inspired by a fluffy long-haired
#  tabby (dark brown / black / white) with wide golden-amber eyes, a white
#  muzzle bib, thick chest fluff, and a slightly open mouth showing two small
#  lower snaggle-teeth.
#
#  Design language: Funko Pop! proportions
#    - Oversized rounded head
#    - Simplified facial features
#    - Small squat body + short stubby limbs
#    - Exaggerated cute chibi silhouette
#
#  Technical approach
#    - Primitive meshes (UV spheres, cubes, cylinders, cones)
#    - Subdivision Surface + Bevel for soft stylized forms
#    - Geometric fur volumes (overlapping spheres / clumps — NO particles)
#    - Voxel Remesh to produce a single manifold, watertight print mesh
#    - Circular base for stability
#    - Principled materials + studio lighting + camera
#    - Preview PNG render + STL export for 3D printing
#
#  USAGE
#  -----
#    Blender GUI:
#      1. Open Blender 5.2.0 → Scripting workspace → New text block
#      2. Open / paste this file → Run Script
#      3. Outputs land in OUTPUT_DIR (default: next to this script, or /tmp)
#
#    Command line:
#      blender --background --python funko_pop_cat_figurine.py
#
#  Tunables live in the CONFIG dict near the top — adjust proportions there
#  before re-running.
#
#  License: MIT
# ============================================================================

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Euler, Vector


# ============================================================================
#  CONFIGURATION — tweak proportions / colors / export here
# ============================================================================
#  Units are Blender meters. The figurine is intentionally ~80–100 mm tall
#  (0.08–0.10 m) so the STL is print-ready at 1:1 without rescaling.
# ============================================================================

CONFIG = {
    # --- output -------------------------------------------------------------
    # Directory for the preview PNG, STL, and optional .blend save.
    # Set to None to auto-pick (script folder if known, else /tmp).
    "output_dir": None,
    "render_filename": "funko_pop_cat_preview.png",
    "stl_filename": "funko_pop_cat_figurine.stl",
    "save_blend": True,
    "blend_filename": "funko_pop_cat_figurine.blend",

    # --- overall scale ------------------------------------------------------
    # Master scale multiplier. 1.0 ≈ 95 mm tall including base.
    "global_scale": 1.0,

    # --- head (Funko oversized) ---------------------------------------------
    "head": {
        "radius": 0.028,          # base UV-sphere radius before non-uniform scale
        "scale": (1.05, 0.95, 1.00),  # (X width, Y depth, Z height)
        "location_z": 0.072,      # center height of the head
        "subdiv": 2,              # Subdivision Surface levels (viewport+render)
    },

    # --- body (small / squat) -----------------------------------------------
    "body": {
        "radius": 0.016,
        "scale": (1.15, 0.95, 1.35),
        "location_z": 0.038,
        "subdiv": 2,
    },

    # --- limbs --------------------------------------------------------------
    "arm": {
        "radius": 0.0065,
        "scale": (0.85, 0.85, 1.35),
        "z": 0.040,
        "x_offset": 0.018,
        "y": 0.002,
    },
    "leg": {
        "radius": 0.0075,
        "scale": (1.0, 1.05, 0.85),
        "z": 0.016,
        "x_offset": 0.010,
        "y": 0.004,
    },

    # --- ears ---------------------------------------------------------------
    "ear": {
        "radius": 0.014,          # larger soft ears (Funko + fluffy cat)
        "scale": (0.90, 0.55, 1.35),
        "z_offset": 0.026,        # relative to head center
        "x_offset": 0.016,
        "y_offset": -0.001,
        "tilt_deg": 24.0,         # tip outward
        "inner_scale": 0.55,      # pink inner ear size factor
    },

    # --- face ---------------------------------------------------------------
    "eye": {
        "radius": 0.0090,         # wide expressive golden eyes
        "x_offset": 0.0110,
        "y_offset": -0.023,       # push forward on the face (−Y in Blender)
        "z_offset": 0.004,        # relative to head center
        "pupil_scale": 0.48,
    },
    "muzzle": {
        # White snout patch — elongated sphere on the face
        "radius": 0.011,
        "scale": (0.95, 0.55, 0.85),
        "y_offset": -0.024,
        "z_offset": -0.008,
    },
    "nose": {
        "radius": 0.0026,
        "scale": (1.1, 0.7, 0.75),
        "y_offset": -0.0285,
        "z_offset": -0.0055,
    },
    "mouth": {
        # Soft cavity suggestion (dark oval) + two lower snaggle-teeth
        "radius": 0.0042,
        "scale": (1.35, 0.45, 0.55),
        "y_offset": -0.0275,
        "z_offset": -0.0135,
    },
    "tooth": {
        "radius": 0.00135,
        "depth": 0.0024,
        "x_offset": 0.0018,
        "y_offset": -0.0288,
        "z_offset": -0.0148,
    },

    # --- geometric fur (printable clumps) -----------------------------------
    # Overlapping spheres around neck / chest to read as a thick white bib,
    # plus darker shoulder / cheek fluff. No particle systems.
    "fur": {
        "chest_clump_radius": 0.010,
        "neck_clump_radius": 0.0085,
        "cheek_clump_radius": 0.007,
        "subdiv": 1,
    },

    # --- tail ---------------------------------------------------------------
    "tail": {
        "radius": 0.0055,
        "scale": (0.85, 2.4, 0.85),
        "location": (-0.002, 0.018, 0.028),
        "rotation_deg": (55.0, 0.0, 25.0),
    },

    # --- base ---------------------------------------------------------------
    "base": {
        "radius": 0.032,
        "height": 0.0035,
        "location_z": 0.00175,
    },

    # --- print / remesh -----------------------------------------------------
    # Voxel remesh converts overlapping closed meshes into one manifold solid.
    "print": {
        "voxel_size": 0.00055,    # smaller = finer detail, denser mesh
        "adaptivity": 0.0,        # 0 keeps uniform voxels (safer for print)
        "smooth_iterations": 4,   # Laplacian-ish smooth via Corrective Smooth
        "merge_distance": 0.0002,
    },

    # --- materials (RGBA 0–1 linear-ish display colors) ---------------------
    "colors": {
        # Dark chocolate / near-black tabby (reference cat). Kept above pure
        # black so Filmic still shows a brown cast under studio lights.
        "tabby_dark": (0.045, 0.022, 0.012, 1.0),
        "tabby_mid": (0.11, 0.055, 0.025, 1.0),
        "white": (0.94, 0.92, 0.89, 1.0),         # muzzle + chest bib
        "amber": (0.90, 0.52, 0.06, 1.0),         # golden-brown iris
        "pupil": (0.01, 0.01, 0.01, 1.0),
        "nose": (0.05, 0.03, 0.03, 1.0),
        "mouth": (0.05, 0.015, 0.015, 1.0),
        "tooth": (0.97, 0.95, 0.90, 1.0),
        "ear_inner": (0.75, 0.48, 0.42, 1.0),
        "base": (0.015, 0.015, 0.015, 1.0),
    },

    # --- render / camera ----------------------------------------------------
    "render": {
        "engine": "CYCLES",       # "CYCLES" or "BLENDER_EEVEE"
        "samples": 64,            # raise for final quality (128–256)
        "resolution": (1280, 1280),
        "transparent_bg": False,
        "use_denoising": True,
    },
    "camera": {
        "location": (0.14, -0.18, 0.11),
        "look_at": (0.0, 0.0, 0.055),
        "focal_mm": 70.0,
        "clip_start": 0.01,
        "clip_end": 10.0,
    },
}


# ============================================================================
#  UTILITIES
# ============================================================================

def _script_dir() -> Path:
    """Best-effort directory of this script (works in GUI and CLI)."""
    try:
        return Path(bpy.path.abspath("//")) if bpy.data.filepath else Path(__file__).resolve().parent
    except Exception:
        pass
    try:
        return Path(__file__).resolve().parent
    except Exception:
        return Path(tempfile_fallback())


def tempfile_fallback() -> str:
    return "/tmp"


def get_output_dir() -> Path:
    """Resolve OUTPUT_DIR and ensure it exists."""
    configured = CONFIG["output_dir"]
    if configured:
        out = Path(configured).expanduser().resolve()
    else:
        out = _script_dir() / "output_funko_cat"
    out.mkdir(parents=True, exist_ok=True)
    return out


def log(msg: str) -> None:
    print(f"[FunkoCat] {msg}")


def set_active(obj: bpy.types.Object) -> None:
    """Make `obj` the active selected object (OBJECT mode)."""
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    if obj.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")


def ensure_object_mode() -> None:
    obj = bpy.context.view_layer.objects.active
    if obj is not None and obj.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")


def apply_transforms(obj: bpy.types.Object) -> None:
    set_active(obj)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)


def shade_smooth(obj: bpy.types.Object, auto_smooth_angle_deg: float = 40.0) -> None:
    """Enable smooth shading; use auto-smooth when available (Blender 4.1+)."""
    set_active(obj)
    bpy.ops.object.shade_smooth()
    mesh = obj.data
    # Blender 4.1+ stores auto-smooth as a modifier / attribute; keep best-effort.
    if hasattr(mesh, "use_auto_smooth"):
        mesh.use_auto_smooth = True
        mesh.auto_smooth_angle = math.radians(auto_smooth_angle_deg)
    else:
        try:
            bpy.ops.object.shade_auto_smooth(angle=math.radians(auto_smooth_angle_deg))
        except Exception:
            pass


def add_subsurf(obj: bpy.types.Object, levels: int) -> None:
    if levels <= 0:
        return
    mod = obj.modifiers.new(name="Subdivision", type="SUBSURF")
    mod.levels = levels
    mod.render_levels = levels
    mod.uv_smooth = "PRESERVE_CORNERS"
    mod.boundary_smooth = "ALL"


def add_bevel(obj: bpy.types.Object, width: float = 0.0008, segments: int = 2) -> None:
    mod = obj.modifiers.new(name="Bevel", type="BEVEL")
    mod.width = width
    mod.segments = segments
    mod.limit_method = "ANGLE"
    mod.angle_limit = math.radians(30.0)


def move_to_collection(obj: bpy.types.Object, coll: bpy.types.Collection) -> None:
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    coll.objects.link(obj)


def get_or_create_collection(name: str, parent: bpy.types.Collection | None = None) -> bpy.types.Collection:
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        if parent is None:
            bpy.context.scene.collection.children.link(coll)
        else:
            parent.children.link(coll)
    return coll


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    """Point object's -Z axis (camera forward) toward target."""
    direction = target - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def gs(value: float) -> float:
    """Apply global scale to a scalar."""
    return value * CONFIG["global_scale"]


def gs_vec(v) -> tuple[float, float, float]:
    s = CONFIG["global_scale"]
    return (v[0] * s, v[1] * s, v[2] * s)


# ============================================================================
#  SCENE SETUP
# ============================================================================

def clear_scene() -> None:
    """Remove objects / orphaned data so re-runs are clean."""
    ensure_object_mode()
    # Delete all objects
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    # Purge unused datablocks
    for block_coll in (
        bpy.data.meshes,
        bpy.data.materials,
        bpy.data.lights,
        bpy.data.cameras,
        bpy.data.images,
    ):
        for block in list(block_coll):
            if block.users == 0:
                block_coll.remove(block)

    # Remove non-master collections
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)

    log("Scene cleared.")


def configure_units() -> None:
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = "MILLIMETERS"


# ============================================================================
#  MATERIALS
# ============================================================================

def _set_principled(mat: bpy.types.Material, *, color, roughness: float, specular: float = 0.35) -> None:
    """Configure Principled BSDF with Blender 4/5 input-name safety.

    Note: ``Material.use_nodes`` is deprecated in Blender 5.x (always on) and
    will be removed in 6.0 — do not set it.
    """
    # bpy.data.materials.new() already creates a default node tree in 5.x.
    tree = mat.node_tree
    if tree is None:
        raise RuntimeError(f"Material {mat.name!r} has no node_tree (unexpected in Blender 5.x).")

    nodes = tree.nodes
    links = tree.links
    principled = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)
    out = next((n for n in nodes if n.type == "OUTPUT_MATERIAL"), None)

    if principled is None or out is None:
        nodes.clear()
        principled = nodes.new("ShaderNodeBsdfPrincipled")
        principled.location = (0, 0)
        out = nodes.new("ShaderNodeOutputMaterial")
        out.location = (300, 0)
        links.new(principled.outputs["BSDF"], out.inputs["Surface"])
    else:
        # Ensure the surface link exists (re-runs / odd defaults).
        if not out.inputs["Surface"].is_linked:
            links.new(principled.outputs["BSDF"], out.inputs["Surface"])

    principled.inputs["Base Color"].default_value = color
    principled.inputs["Roughness"].default_value = roughness

    # Specular renamed in Blender 4.0+
    if "Specular IOR Level" in principled.inputs:
        principled.inputs["Specular IOR Level"].default_value = specular
    elif "Specular" in principled.inputs:
        principled.inputs["Specular"].default_value = specular

    if "Metallic" in principled.inputs:
        principled.inputs["Metallic"].default_value = 0.0


def make_material(name: str, color, roughness: float = 0.55) -> bpy.types.Material:
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name=name)
    _set_principled(mat, color=color, roughness=roughness)
    return mat


def create_materials() -> dict[str, bpy.types.Material]:
    c = CONFIG["colors"]
    mats = {
        "tabby_dark": make_material("MAT_TabbyDark", c["tabby_dark"], 0.62),
        "tabby_mid": make_material("MAT_TabbyMid", c["tabby_mid"], 0.60),
        "white": make_material("MAT_WhiteFur", c["white"], 0.58),
        "amber": make_material("MAT_AmberEye", c["amber"], 0.22),
        "pupil": make_material("MAT_Pupil", c["pupil"], 0.35),
        "nose": make_material("MAT_Nose", c["nose"], 0.40),
        "mouth": make_material("MAT_Mouth", c["mouth"], 0.55),
        "tooth": make_material("MAT_Tooth", c["tooth"], 0.30),
        "ear_inner": make_material("MAT_EarInner", c["ear_inner"], 0.50),
        "base": make_material("MAT_Base", c["base"], 0.45),
    }

    # Slight clearcoat on eyes for a glossy collectible look (if available).
    eye = mats["amber"]
    principled = next(
        (n for n in eye.node_tree.nodes if n.type == "BSDF_PRINCIPLED"),
        None,
    )
    if principled is not None:
        if "Coat Weight" in principled.inputs:
            principled.inputs["Coat Weight"].default_value = 0.45
            principled.inputs["Coat Roughness"].default_value = 0.06
        elif "Clearcoat" in principled.inputs:
            principled.inputs["Clearcoat"].default_value = 0.45
            principled.inputs["Clearcoat Roughness"].default_value = 0.06

    log(f"Created {len(mats)} materials.")
    return mats


def assign_material(obj: bpy.types.Object, mat: bpy.types.Material) -> None:
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)


# ============================================================================
#  PRIMITIVE BUILDERS
# ============================================================================

def create_sphere(
    name: str,
    radius: float,
    location,
    scale=(1.0, 1.0, 1.0),
    segments: int = 32,
    rings: int = 16,
    material: bpy.types.Material | None = None,
    collection: bpy.types.Collection | None = None,
    subdiv: int = 0,
) -> bpy.types.Object:
    """UV sphere helper with optional non-uniform scale + subdiv."""
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=gs(radius),
        location=gs_vec(location),
        segments=segments,
        ring_count=rings,
    )
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = scale  # non-uniform stylization before apply
    apply_transforms(obj)
    if subdiv:
        add_subsurf(obj, subdiv)
    shade_smooth(obj)
    if material:
        assign_material(obj, material)
    if collection:
        move_to_collection(obj, collection)
    return obj


def create_cylinder(
    name: str,
    radius: float,
    depth: float,
    location,
    rotation_euler=(0.0, 0.0, 0.0),
    vertices: int = 48,
    material: bpy.types.Material | None = None,
    collection: bpy.types.Collection | None = None,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(
        radius=gs(radius),
        depth=gs(depth),
        location=gs_vec(location),
        vertices=vertices,
    )
    obj = bpy.context.active_object
    obj.name = name
    obj.rotation_euler = Euler(rotation_euler)
    apply_transforms(obj)
    shade_smooth(obj)
    if material:
        assign_material(obj, material)
    if collection:
        move_to_collection(obj, collection)
    return obj


def create_cone(
    name: str,
    radius1: float,
    depth: float,
    location,
    rotation_euler=(0.0, 0.0, 0.0),
    scale=(1.0, 1.0, 1.0),
    vertices: int = 20,
    material: bpy.types.Material | None = None,
    collection: bpy.types.Collection | None = None,
) -> bpy.types.Object:
    """Cone primitive — used for ears and snaggle-teeth."""
    bpy.ops.mesh.primitive_cone_add(
        radius1=gs(radius1),
        radius2=0.0,
        depth=gs(depth),
        location=gs_vec(location),
        vertices=vertices,
    )
    obj = bpy.context.active_object
    obj.name = name
    obj.rotation_euler = Euler(rotation_euler)
    obj.scale = scale
    apply_transforms(obj)
    shade_smooth(obj)
    if material:
        assign_material(obj, material)
    if collection:
        move_to_collection(obj, collection)
    return obj


def create_cube(
    name: str,
    size: float,
    location,
    scale=(1.0, 1.0, 1.0),
    material: bpy.types.Material | None = None,
    collection: bpy.types.Collection | None = None,
    bevel: bool = True,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=gs(size), location=gs_vec(location))
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = scale
    apply_transforms(obj)
    if bevel:
        add_bevel(obj, width=gs(0.0012), segments=3)
    shade_smooth(obj)
    if material:
        assign_material(obj, material)
    if collection:
        move_to_collection(obj, collection)
    return obj


# ============================================================================
#  FIGURINE CONSTRUCTION
# ============================================================================

def build_base(mats, coll) -> bpy.types.Object:
    """Thin black circular disc for print stability."""
    cfg = CONFIG["base"]
    base = create_cylinder(
        name="Base",
        radius=cfg["radius"],
        depth=cfg["height"],
        location=(0.0, 0.0, cfg["location_z"]),
        material=mats["base"],
        collection=coll,
        vertices=64,
    )
    add_bevel(base, width=gs(0.0006), segments=2)
    return base


def build_body(mats, coll) -> list[bpy.types.Object]:
    """Small squat torso + stubby limbs + curled-ish tail."""
    parts: list[bpy.types.Object] = []
    bcfg = CONFIG["body"]
    body = create_sphere(
        "Body",
        radius=bcfg["radius"],
        location=(0.0, 0.0, bcfg["location_z"]),
        scale=bcfg["scale"],
        material=mats["tabby_dark"],
        collection=coll,
        subdiv=bcfg["subdiv"],
    )
    parts.append(body)

    # Arms (short, slightly forward)
    acfg = CONFIG["arm"]
    for side, sign in (("L", -1.0), ("R", 1.0)):
        arm = create_sphere(
            f"Arm_{side}",
            radius=acfg["radius"],
            location=(sign * acfg["x_offset"], acfg["y"], acfg["z"]),
            scale=acfg["scale"],
            material=mats["tabby_dark"],
            collection=coll,
            subdiv=1,
        )
        parts.append(arm)

    # Legs / feet stubs
    lcfg = CONFIG["leg"]
    for side, sign in (("L", -1.0), ("R", 1.0)):
        leg = create_sphere(
            f"Leg_{side}",
            radius=lcfg["radius"],
            location=(sign * lcfg["x_offset"], lcfg["y"], lcfg["z"]),
            scale=lcfg["scale"],
            material=mats["tabby_dark"],
            collection=coll,
            subdiv=1,
        )
        parts.append(leg)

    # Tail — elongated sphere, angled upward behind the body
    tcfg = CONFIG["tail"]
    tail = create_sphere(
        "Tail",
        radius=tcfg["radius"],
        location=tcfg["location"],
        scale=tcfg["scale"],
        material=mats["tabby_mid"],
        collection=coll,
        subdiv=1,
    )
    tail.rotation_euler = Euler(tuple(math.radians(a) for a in tcfg["rotation_deg"]))
    apply_transforms(tail)
    parts.append(tail)

    return parts


def build_head(mats, coll) -> list[bpy.types.Object]:
    """Oversized rounded head + ears + facial features."""
    parts: list[bpy.types.Object] = []
    hcfg = CONFIG["head"]
    head_z = hcfg["location_z"]

    head = create_sphere(
        "Head",
        radius=hcfg["radius"],
        location=(0.0, 0.0, head_z),
        scale=hcfg["scale"],
        material=mats["tabby_dark"],
        collection=coll,
        subdiv=hcfg["subdiv"],
        segments=40,
        rings=20,
    )
    parts.append(head)

    # Mid-brown forehead / cheek patches (subtle tabby read)
    for side, sign in (("L", -1.0), ("R", 1.0)):
        patch = create_sphere(
            f"TabbyPatch_{side}",
            radius=hcfg["radius"] * 0.42,
            location=(sign * 0.014, -0.010, head_z + 0.006),
            scale=(0.9, 0.55, 0.75),
            material=mats["tabby_mid"],
            collection=coll,
            subdiv=1,
            segments=24,
            rings=12,
        )
        parts.append(patch)

    # Ears — cones scaled into soft triangles, with inner ear pads
    ecfg = CONFIG["ear"]
    for side, sign in (("L", -1.0), ("R", 1.0)):
        ear_loc = (
            sign * ecfg["x_offset"],
            ecfg["y_offset"],
            head_z + ecfg["z_offset"],
        )
        # Tip upward; tilt outward left/right
        tilt = math.radians(ecfg["tilt_deg"])
        rot = (math.radians(8.0), sign * tilt, sign * math.radians(8.0))
        ear = create_cone(
            f"Ear_{side}",
            radius1=ecfg["radius"],
            depth=ecfg["radius"] * 1.6,
            location=ear_loc,
            rotation_euler=rot,
            scale=ecfg["scale"],
            material=mats["tabby_dark"],
            collection=coll,
        )
        add_subsurf(ear, 1)
        parts.append(ear)

        inner = create_cone(
            f"EarInner_{side}",
            radius1=ecfg["radius"] * ecfg["inner_scale"],
            depth=ecfg["radius"] * 1.05,
            location=(
                ear_loc[0],
                ear_loc[1] - 0.0015,
                ear_loc[2] - 0.001,
            ),
            rotation_euler=rot,
            scale=ecfg["scale"],
            material=mats["ear_inner"],
            collection=coll,
        )
        add_subsurf(inner, 1)
        parts.append(inner)

    # White muzzle / snout patch
    mcfg = CONFIG["muzzle"]
    muzzle = create_sphere(
        "MuzzleWhite",
        radius=mcfg["radius"],
        location=(0.0, mcfg["y_offset"], head_z + mcfg["z_offset"]),
        scale=mcfg["scale"],
        material=mats["white"],
        collection=coll,
        subdiv=1,
    )
    parts.append(muzzle)

    # Nose
    ncfg = CONFIG["nose"]
    nose = create_sphere(
        "Nose",
        radius=ncfg["radius"],
        location=(0.0, ncfg["y_offset"], head_z + ncfg["z_offset"]),
        scale=ncfg["scale"],
        material=mats["nose"],
        collection=coll,
        subdiv=1,
        segments=16,
        rings=8,
    )
    parts.append(nose)

    # Mouth cavity (dark oval) — reads as a slightly open mouth
    ocfg = CONFIG["mouth"]
    mouth = create_sphere(
        "Mouth",
        radius=ocfg["radius"],
        location=(0.0, ocfg["y_offset"], head_z + ocfg["z_offset"]),
        scale=ocfg["scale"],
        material=mats["mouth"],
        collection=coll,
        subdiv=1,
        segments=16,
        rings=8,
    )
    parts.append(mouth)

    # Two small lower snaggle-teeth (cones pointing up)
    tcfg = CONFIG["tooth"]
    for side, sign in (("L", -1.0), ("R", 1.0)):
        tooth = create_cone(
            f"Tooth_{side}",
            radius1=tcfg["radius"],
            depth=tcfg["depth"],
            location=(
                sign * tcfg["x_offset"],
                tcfg["y_offset"],
                head_z + tcfg["z_offset"],
            ),
            # Cone default tip is +Z; rotate 180° so tip points up into the smile
            rotation_euler=(0.0, 0.0, 0.0),
            scale=(0.7, 0.7, 1.0),
            material=mats["tooth"],
            collection=coll,
            vertices=10,
        )
        parts.append(tooth)

    # Eyes + pupils (wide, expressive, golden-amber)
    ec = CONFIG["eye"]
    for side, sign in (("L", -1.0), ("R", 1.0)):
        eye = create_sphere(
            f"Eye_{side}",
            radius=ec["radius"],
            location=(
                sign * ec["x_offset"],
                ec["y_offset"],
                head_z + ec["z_offset"],
            ),
            scale=(1.0, 0.55, 1.05),
            material=mats["amber"],
            collection=coll,
            subdiv=1,
            segments=28,
            rings=14,
        )
        parts.append(eye)

        pupil = create_sphere(
            f"Pupil_{side}",
            radius=ec["radius"] * ec["pupil_scale"],
            location=(
                sign * ec["x_offset"],
                ec["y_offset"] - 0.0018,
                head_z + ec["z_offset"],
            ),
            scale=(0.85, 0.45, 1.05),
            material=mats["pupil"],
            collection=coll,
            subdiv=0,
            segments=16,
            rings=8,
        )
        parts.append(pupil)

        # Tiny eye highlight for the collectible gloss (render only — still solid)
        highlight = create_sphere(
            f"EyeHighlight_{side}",
            radius=ec["radius"] * 0.18,
            location=(
                sign * (ec["x_offset"] - 0.002),
                ec["y_offset"] - 0.0026,
                head_z + ec["z_offset"] + 0.0025,
            ),
            scale=(1.0, 0.5, 1.0),
            material=mats["white"],
            collection=coll,
            segments=12,
            rings=6,
        )
        parts.append(highlight)

    return parts


def build_fur_volumes(mats, coll) -> list[bpy.types.Object]:
    """
    Stylized printable fur using overlapping sphere clumps.

    White bib / chest / neck mane + darker cheek / shoulder fluff.
    Particle systems are intentionally avoided so the model remains manifold
    after voxel remesh.
    """
    parts: list[bpy.types.Object] = []
    fcfg = CONFIG["fur"]
    head_z = CONFIG["head"]["location_z"]
    body_z = CONFIG["body"]["location_z"]

    # --- thick white chest bib (tiered clumps) -----------------------------
    chest_layout = [
        # (name, x, y, z, radius_scale, scale_xyz)
        ("FurChest_C", 0.0, -0.012, body_z + 0.006, 1.15, (1.25, 0.85, 1.15)),
        ("FurChest_L", -0.010, -0.010, body_z + 0.004, 0.95, (1.1, 0.8, 1.0)),
        ("FurChest_R", 0.010, -0.010, body_z + 0.004, 0.95, (1.1, 0.8, 1.0)),
        ("FurChest_Low", 0.0, -0.011, body_z - 0.004, 1.05, (1.35, 0.75, 0.9)),
        ("FurBib_Upper", 0.0, -0.013, body_z + 0.014, 1.0, (1.2, 0.7, 0.95)),
    ]
    for name, x, y, z, r_mul, scale in chest_layout:
        clump = create_sphere(
            name,
            radius=fcfg["chest_clump_radius"] * r_mul,
            location=(x, y, z),
            scale=scale,
            material=mats["white"],
            collection=coll,
            subdiv=fcfg["subdiv"],
            segments=24,
            rings=12,
        )
        parts.append(clump)

    # --- neck ruff (bridges head and body) ---------------------------------
    neck_layout = [
        ("FurNeck_C", 0.0, -0.008, (head_z + body_z) * 0.52, 1.0, (1.3, 0.9, 0.85)),
        ("FurNeck_L", -0.012, -0.004, (head_z + body_z) * 0.55, 0.9, (1.0, 0.85, 0.85)),
        ("FurNeck_R", 0.012, -0.004, (head_z + body_z) * 0.55, 0.9, (1.0, 0.85, 0.85)),
        ("FurNeck_Back", 0.0, 0.010, (head_z + body_z) * 0.50, 0.95, (1.25, 0.9, 0.8)),
    ]
    for name, x, y, z, r_mul, scale in neck_layout:
        clump = create_sphere(
            name,
            radius=fcfg["neck_clump_radius"] * r_mul,
            location=(x, y, z),
            scale=scale,
            material=mats["white"],
            collection=coll,
            subdiv=fcfg["subdiv"],
            segments=20,
            rings=10,
        )
        parts.append(clump)

    # --- darker cheek / shoulder fluff (tabby) -----------------------------
    fluff_layout = [
        ("FurCheek_L", -0.020, -0.012, head_z - 0.010, 1.0, (1.2, 0.85, 0.9), "tabby_mid"),
        ("FurCheek_R", 0.020, -0.012, head_z - 0.010, 1.0, (1.2, 0.85, 0.9), "tabby_mid"),
        ("FurShoulder_L", -0.016, 0.002, body_z + 0.010, 1.05, (1.1, 1.0, 0.9), "tabby_dark"),
        ("FurShoulder_R", 0.016, 0.002, body_z + 0.010, 1.05, (1.1, 1.0, 0.9), "tabby_dark"),
        ("FurCrown", 0.0, -0.006, head_z + 0.018, 0.85, (1.4, 0.8, 0.7), "tabby_mid"),
    ]
    for name, x, y, z, r_mul, scale, mat_key in fluff_layout:
        clump = create_sphere(
            name,
            radius=fcfg["cheek_clump_radius"] * r_mul,
            location=(x, y, z),
            scale=scale,
            material=mats[mat_key],
            collection=coll,
            subdiv=fcfg["subdiv"],
            segments=20,
            rings=10,
        )
        parts.append(clump)

    # Optional print-safe whiskers: short thick tapered cylinders.
    # Radius stays ≥ ~0.9 mm after global_scale=1 so a 0.4 mm nozzle can print
    # them; set include_whiskers=False below (or delete Whisker_* objects) for
    # a cleaner FDM figure.
    include_whiskers = True
    if include_whiskers:
        for side, sign in (("L", -1.0), ("R", 1.0)):
            for i, (z_off, y_rot_deg) in enumerate(
                ((-0.006, 12.0), (-0.009, 0.0), (-0.012, -12.0))
            ):
                whisk = create_cylinder(
                    name=f"Whisker_{side}_{i}",
                    radius=0.00095,
                    depth=0.016,
                    location=(sign * 0.022, -0.026, head_z + z_off),
                    rotation_euler=(
                        0.0,
                        math.radians(sign * (70.0 + y_rot_deg * 0.15)),
                        0.0,
                    ),
                    material=mats["white"],
                    collection=coll,
                    vertices=10,
                )
                # Taper via non-uniform scale on X/Z after creation
                whisk.scale = (0.75, 1.0, 0.60)
                apply_transforms(whisk)
                parts.append(whisk)

    log(f"Built {len(parts)} geometric fur / whisker parts.")
    return parts


def build_figurine(mats) -> list[bpy.types.Object]:
    """Assemble the full display figurine (separate meshes + materials)."""
    root = get_or_create_collection("FunkoPop_Cat")
    coll_body = get_or_create_collection("Cat_Body", parent=root)
    coll_head = get_or_create_collection("Cat_Head", parent=root)
    coll_fur = get_or_create_collection("Cat_Fur", parent=root)
    coll_base = get_or_create_collection("Cat_Base", parent=root)

    parts: list[bpy.types.Object] = []
    parts.append(build_base(mats, coll_base))
    parts.extend(build_body(mats, coll_body))
    parts.extend(build_head(mats, coll_head))
    parts.extend(build_fur_volumes(mats, coll_fur))

    log(f"Figurine assembled: {len(parts)} mesh objects.")
    return parts


# ============================================================================
#  PRINT MESH — manifold / watertight via Voxel Remesh
# ============================================================================

def apply_all_modifiers(obj: bpy.types.Object) -> None:
    set_active(obj)
    for mod in list(obj.modifiers):
        try:
            bpy.ops.object.modifier_apply(modifier=mod.name)
        except RuntimeError as exc:
            log(f"  Could not apply modifier {mod.name} on {obj.name}: {exc}")


def create_print_mesh(source_objects: list[bpy.types.Object]) -> bpy.types.Object:
    """
    Duplicate display parts, apply modifiers, join, and Voxel Remesh into
    a single manifold solid suitable for STL / FDM or resin printing.
    """
    ensure_object_mode()
    print_coll = get_or_create_collection("Cat_PrintMesh")

    # Duplicate every source mesh
    duplicates: list[bpy.types.Object] = []
    for src in source_objects:
        if src.type != "MESH":
            continue
        set_active(src)
        bpy.ops.object.duplicate()
        dup = bpy.context.active_object
        dup.name = f"Print_{src.name}"
        move_to_collection(dup, print_coll)
        apply_all_modifiers(dup)
        duplicates.append(dup)

    if not duplicates:
        raise RuntimeError("No mesh objects available to build a print mesh.")

    # Join into one object
    bpy.ops.object.select_all(action="DESELECT")
    for obj in duplicates:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = duplicates[0]
    bpy.ops.object.join()
    joined = bpy.context.active_object
    joined.name = "FunkoPop_Cat_Printable"

    # Merge nearby vertices (helps remesh input cleanliness)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    merge_dist = gs(CONFIG["print"]["merge_distance"])
    bpy.ops.mesh.remove_doubles(threshold=merge_dist)
    bpy.ops.object.mode_set(mode="OBJECT")

    # Voxel Remesh → closed manifold volume from overlapping spheres/cones
    remesh = joined.modifiers.new(name="VoxelRemesh", type="REMESH")
    remesh.mode = "VOXEL"
    remesh.voxel_size = gs(CONFIG["print"]["voxel_size"])
    remesh.adaptivity = CONFIG["print"]["adaptivity"]
    remesh.use_smooth_shade = True
    apply_all_modifiers(joined)

    # Light smoothing for softer Funko silhouette without destroying volume
    smooth = joined.modifiers.new(name="PrintSmooth", type="SMOOTH")
    smooth.factor = 0.35
    smooth.iterations = CONFIG["print"]["smooth_iterations"]
    apply_all_modifiers(joined)

    # Final cleanup: normals + doubles
    set_active(joined)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.mesh.remove_doubles(threshold=merge_dist)
    bpy.ops.object.mode_set(mode="OBJECT")
    shade_smooth(joined)

    # Hide print mesh from the beauty render (display parts stay visible)
    joined.hide_render = True
    joined.display_type = "WIRE"

    log(
        f"Print mesh ready: {len(joined.data.vertices)} verts, "
        f"{len(joined.data.polygons)} faces (manifold via voxel remesh)."
    )
    return joined


# ============================================================================
#  LIGHTING + CAMERA + RENDER
# ============================================================================

def setup_world() -> None:
    world = bpy.data.worlds.get("World")
    if world is None:
        world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    # World.use_nodes is deprecated in Blender 5.x (always enabled).
    nodes = world.node_tree.nodes if world.node_tree else None
    if nodes:
        bg = next((n for n in nodes if n.type == "BACKGROUND"), nodes.get("Background"))
        if bg:
            # Soft neutral studio fill — keep strength low so mesh colors read.
            bg.inputs["Color"].default_value = (0.55, 0.52, 0.50, 1.0)
            bg.inputs["Strength"].default_value = 0.15


def setup_lights(coll: bpy.types.Collection) -> None:
    """Simple three-point studio lighting around the figurine.

    Energies are tuned for a ~100 mm subject. Oversized wattages clip Filmic
    to pure white and hide the tabby / amber materials.
    """
    ensure_object_mode()

    def add_light(name, type_, energy, location, color=(1.0, 1.0, 1.0), size=0.18):
        light_data = bpy.data.lights.new(name=name, type=type_)
        light_data.energy = energy
        light_data.color = color
        if type_ == "AREA":
            light_data.size = gs(size)
        obj = bpy.data.objects.new(name=name, object_data=light_data)
        obj.location = gs_vec(location)
        coll.objects.link(obj)
        return obj

    key = add_light(
        "Light_Key",
        "AREA",
        energy=10.0,
        location=(0.16, -0.20, 0.18),
        color=(1.0, 0.97, 0.92),
        size=0.22,
    )
    look_at(key, Vector(gs_vec((0.0, 0.0, 0.055))))

    fill = add_light(
        "Light_Fill",
        "AREA",
        energy=3.2,
        location=(-0.18, -0.12, 0.12),
        color=(0.80, 0.88, 1.0),
        size=0.25,
    )
    look_at(fill, Vector(gs_vec((0.0, 0.0, 0.055))))

    rim = add_light(
        "Light_Rim",
        "AREA",
        energy=5.5,
        location=(0.04, 0.20, 0.16),
        color=(1.0, 0.93, 0.86),
        size=0.18,
    )
    look_at(rim, Vector(gs_vec((0.0, 0.0, 0.06))))

    log("Studio lights created (key / fill / rim).")


def setup_camera(coll: bpy.types.Collection) -> bpy.types.Object:
    cfg = CONFIG["camera"]
    cam_data = bpy.data.cameras.new("Camera_Preview")
    cam_data.lens = cfg["focal_mm"]
    cam_data.clip_start = cfg["clip_start"]
    cam_data.clip_end = cfg["clip_end"]

    cam = bpy.data.objects.new("Camera_Preview", cam_data)
    cam.location = gs_vec(cfg["location"])
    look_at(cam, Vector(gs_vec(cfg["look_at"])))
    coll.objects.link(cam)
    bpy.context.scene.camera = cam
    log(f"Camera set at {tuple(round(c, 3) for c in cam.location)}.")
    return cam


def configure_render(output_path: Path) -> None:
    scene = bpy.context.scene
    rcfg = CONFIG["render"]

    engine = rcfg["engine"]
    # Blender 5.x Eevee identifier
    if engine in {"BLENDER_EEVEE", "EEVEE", "BLENDER_EEVEE_NEXT"}:
        # Prefer EEVEE_NEXT when present; fall back gracefully.
        try:
            scene.render.engine = "BLENDER_EEVEE"
        except Exception:
            scene.render.engine = "BLENDER_EEVEE_NEXT"
    else:
        scene.render.engine = "CYCLES"
        scene.cycles.samples = rcfg["samples"]
        if hasattr(scene.cycles, "use_denoising"):
            scene.cycles.use_denoising = rcfg["use_denoising"]
        # Prefer GPU if available; ignore failures in headless CPU boxes.
        try:
            cycles_prefs = bpy.context.preferences.addons["cycles"].preferences
            cycles_prefs.compute_device_type = "CUDA"
            for device in cycles_prefs.devices:
                device.use = True
            scene.cycles.device = "GPU"
        except Exception:
            scene.cycles.device = "CPU"

    scene.render.resolution_x = rcfg["resolution"][0]
    scene.render.resolution_y = rcfg["resolution"][1]
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = rcfg["transparent_bg"]
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA" if rcfg["transparent_bg"] else "RGB"
    scene.render.filepath = str(output_path)

    # Mild exposure / view transform for a clean product shot
    # Standard keeps dark tabby browns closer to the authored albedo;
    # Filmic tends to lift small studio-lit subjects into a washed tan.
    if "Standard" in {
        item.identifier
        for item in scene.view_settings.bl_rna.properties["view_transform"].enum_items
    }:
        scene.view_settings.view_transform = "Standard"
    else:
        scene.view_settings.view_transform = "Filmic"
        scene.view_settings.look = "Medium Contrast"
    scene.view_settings.exposure = 0.0

    log(f"Render configured → {output_path} ({scene.render.engine}).")


def render_preview(output_dir: Path) -> Path:
    path = output_dir / CONFIG["render_filename"]
    configure_render(path)
    log("Rendering preview...")
    bpy.ops.render.render(write_still=True)
    log(f"Preview written: {path}")
    return path


# ============================================================================
#  EXPORT
# ============================================================================

def export_stl(print_obj: bpy.types.Object, output_dir: Path) -> Path:
    """
    Export the manifold print mesh as STL using Blender 5.2's ``wm.stl_export``.

    Important: with ``export_selected_objects=True``, Blender 5.2 skips objects
    that have ``hide_render=True`` (exports an empty 84-byte STL). We either
    export by collection name, or temporarily clear ``hide_render``.
    """
    path = output_dir / CONFIG["stl_filename"]
    ensure_object_mode()

    print_obj.hide_set(False)
    was_hidden_render = print_obj.hide_render
    print_obj.hide_render = False

    # Prefer collection-scoped export so display meshes are not merged in.
    try:
        bpy.ops.wm.stl_export(
            filepath=str(path),
            export_selected_objects=False,
            collection="Cat_PrintMesh",
            apply_modifiers=True,
            ascii_format=False,
            global_scale=1.0,
            forward_axis="Y",
            up_axis="Z",
        )
    except TypeError:
        # Fallback if an older build lacks the collection argument.
        bpy.ops.object.select_all(action="DESELECT")
        print_obj.select_set(True)
        bpy.context.view_layer.objects.active = print_obj
        bpy.ops.wm.stl_export(
            filepath=str(path),
            export_selected_objects=True,
            apply_modifiers=True,
            ascii_format=False,
            global_scale=1.0,
            forward_axis="Y",
            up_axis="Z",
        )
    finally:
        print_obj.hide_render = was_hidden_render

    size = path.stat().st_size if path.exists() else 0
    if size < 1024:
        raise RuntimeError(
            f"STL export looks empty ({size} bytes). "
            "Check that Cat_PrintMesh / FunkoPop_Cat_Printable exists."
        )

    log(f"STL exported: {path} ({size / 1_000_000:.2f} MB)")
    return path


def save_blend(output_dir: Path) -> Path | None:
    if not CONFIG["save_blend"]:
        return None
    path = output_dir / CONFIG["blend_filename"]
    bpy.ops.wm.save_as_mainfile(filepath=str(path))
    log(f"Blend saved: {path}")
    return path


# ============================================================================
#  MAIN
# ============================================================================

def main() -> None:
    log("=" * 60)
    log("Funko Pop Cat Figurine — Blender 5.2 procedural build")
    log("=" * 60)

    # Version soft-check (warn only; do not abort on minor mismatches)
    version = bpy.app.version
    log(f"Blender version: {bpy.app.version_string}")
    if version[0] < 5:
        log("WARNING: Script targets Blender 5.2.x; older versions may differ.")

    output_dir = get_output_dir()
    log(f"Output directory: {output_dir}")

    clear_scene()
    configure_units()

    mats = create_materials()
    parts = build_figurine(mats)

    scene_coll = get_or_create_collection("Studio")
    setup_world()
    setup_lights(scene_coll)
    setup_camera(scene_coll)

    # Beauty render uses the colored display meshes
    render_path = render_preview(output_dir)

    # Manifold print solid (hidden from render)
    print_obj = create_print_mesh(parts)
    stl_path = export_stl(print_obj, output_dir)

    blend_path = save_blend(output_dir)

    log("-" * 60)
    log("BUILD COMPLETE")
    log(f"  Preview : {render_path}")
    log(f"  STL     : {stl_path}")
    if blend_path:
        log(f"  Blend   : {blend_path}")
    log("Tips:")
    log("  • Tweak CONFIG['head'], CONFIG['body'], CONFIG['fur'] for proportions.")
    log("  • Lower CONFIG['print']['voxel_size'] for sharper STL detail.")
    log("  • Delete Whisker_* objects before print if too thin for your nozzle.")
    log("=" * 60)


# Run automatically when executed from Blender (Scripting or --python).
if __name__ == "__main__":
    main()
