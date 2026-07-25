"""
Procedural Rainy Coffee Shop Environment for Blender 5.2+
==========================================================

Run this file once from Blender's Text Editor.  It creates a complete, organized
coffee-shop level, a rain-soaked street facade, materials, physics, cameras,
animation, LOD collections, and Unity exports.

The generator deliberately uses only Blender's bundled Python API.  Discovered
texture sets are connected automatically; when no bitmap exists, procedural PBR
detail is used so the scene remains renderable and never shows missing textures.

Coordinate convention: metres, Z-up.  Unity export converts to Y-up.
"""

from __future__ import annotations

import math
import random
import re
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import bpy
from mathutils import Vector


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class CoffeeShopConfig:
    """All artist-facing controls in one place."""

    seed: int = 12581
    shop_width: float = 18.0
    shop_depth: float = 14.0
    wall_height: float = 4.4
    wall_thickness: float = 0.24
    street_depth: float = 24.0
    rain_intensity: float = 1.0
    rain_streak_count: int = 3200
    texture_root: str = "//Textures"
    export_root: str = "//UnityExport"
    texture_resolution: str = "4K"  # 2K, 4K, or 8K
    build_lods: bool = True
    auto_export: bool = True
    render_samples: int = 256
    cinematic_seconds: int = 30
    fps: int = 24


CFG = CoffeeShopConfig()
RNG = random.Random(CFG.seed)


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def ensure_collection(name: str, parent: Optional[bpy.types.Collection] = None) -> bpy.types.Collection:
    """Return a named collection and link it exactly once."""
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
    parent = parent or bpy.context.scene.collection
    if collection.name not in {c.name for c in parent.children}:
        parent.children.link(collection)
    return collection


def move_to_collection(obj: bpy.types.Object, collection: bpy.types.Collection) -> None:
    """Unlink an object from current collections and place it in `collection`."""
    for current in list(obj.users_collection):
        current.objects.unlink(obj)
    collection.objects.link(obj)


def set_active(obj: bpy.types.Object) -> None:
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)


def animation_fcurves(animated_id) -> Iterable[bpy.types.FCurve]:
    """Return F-curves through Blender 5's slotted Action API, with 4.x fallback."""
    animation_data = getattr(animated_id, "animation_data", None)
    action = getattr(animation_data, "action", None)
    if not action:
        return ()
    # Blender 4.4 exposes this compatibility proxy; Blender 5 removes it.
    if hasattr(action, "fcurves"):
        return action.fcurves
    try:
        from bpy_extras import anim_utils
        slot = animation_data.action_slot
        channelbag = anim_utils.action_get_channelbag_for_slot(action, slot)
        return channelbag.fcurves if channelbag else ()
    except (AttributeError, RuntimeError):
        return ()


def deselect_all() -> None:
    for obj in bpy.context.selected_objects:
        obj.select_set(False)


def apply_transform(obj: bpy.types.Object, location: bool = False,
                    rotation: bool = False, scale: bool = True) -> None:
    deselect_all()
    set_active(obj)
    bpy.ops.object.transform_apply(location=location, rotation=rotation, scale=scale)


def assign_material(obj: bpy.types.Object, material: Optional[bpy.types.Material]) -> None:
    if material and hasattr(obj.data, "materials"):
        obj.data.materials.clear()
        obj.data.materials.append(material)


def bevel(obj: bpy.types.Object, width: float = 0.04, segments: int = 3) -> None:
    """Add a non-destructive bevel; tiny highlights make generated forms believable."""
    if obj.type != "MESH":
        return
    mod = obj.modifiers.new("Edge highlights", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.limit_method = "ANGLE"


def smooth(obj: bpy.types.Object) -> None:
    if obj.type == "MESH":
        for polygon in obj.data.polygons:
            polygon.use_smooth = True


def cube(name: str, location: Sequence[float], scale: Sequence[float],
         collection: bpy.types.Collection, material=None, bevel_width: float = 0.0,
         rotation: Sequence[float] = (0, 0, 0)) -> bpy.types.Object:
    """Create a cube where scale is the desired full size, not Blender half-extents."""
    bpy.ops.mesh.primitive_cube_add(location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.scale = Vector(scale) * 0.5
    apply_transform(obj)
    move_to_collection(obj, collection)
    assign_material(obj, material)
    if bevel_width:
        bevel(obj, bevel_width)
    return obj


def cylinder(name: str, location: Sequence[float], radius: float, depth: float,
             collection: bpy.types.Collection, material=None, vertices: int = 32,
             rotation: Sequence[float] = (0, 0, 0), bevel_width: float = 0.0) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices, radius=radius, depth=depth, location=location, rotation=rotation
    )
    obj = bpy.context.object
    obj.name = name
    move_to_collection(obj, collection)
    assign_material(obj, material)
    if bevel_width:
        bevel(obj, bevel_width)
    smooth(obj)
    return obj


def uv_sphere(name: str, location: Sequence[float], scale: Sequence[float],
              collection: bpy.types.Collection, material=None,
              segments: int = 24, rings: int = 12) -> bpy.types.Object:
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments, ring_count=rings, location=location
    )
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    apply_transform(obj)
    move_to_collection(obj, collection)
    assign_material(obj, material)
    smooth(obj)
    return obj


def torus(name: str, location: Sequence[float], major_radius: float, minor_radius: float,
          collection: bpy.types.Collection, material=None,
          rotation: Sequence[float] = (0, 0, 0)) -> bpy.types.Object:
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major_radius, minor_radius=minor_radius,
        major_segments=32, minor_segments=10, location=location, rotation=rotation
    )
    obj = bpy.context.object
    obj.name = name
    move_to_collection(obj, collection)
    assign_material(obj, material)
    smooth(obj)
    return obj


def text_object(name: str, body: str, location: Sequence[float],
                rotation: Sequence[float], size: float,
                collection: bpy.types.Collection, material=None,
                extrude: float = 0.008, align: str = "CENTER") -> bpy.types.Object:
    curve = bpy.data.curves.new(name + "_Curve", "FONT")
    curve.body = body
    curve.align_x = align
    curve.size = size
    curve.extrude = extrude
    curve.bevel_depth = 0.002
    obj = bpy.data.objects.new(name, curve)
    collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = rotation
    assign_material(obj, material)
    return obj


def add_area_light(name: str, location: Sequence[float], energy: float,
                   color: Sequence[float], size: float,
                   collection: bpy.types.Collection,
                   rotation: Sequence[float] = (0, 0, 0)) -> bpy.types.Object:
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.color = color
    data.shape = "DISK"
    data.size = size
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = rotation
    return obj


def track_to(obj: bpy.types.Object, target: bpy.types.Object) -> None:
    constraint = obj.constraints.new("TRACK_TO")
    constraint.target = target
    constraint.track_axis = "TRACK_NEGATIVE_Z"
    constraint.up_axis = "UP_Y"


def add_collision(obj: bpy.types.Object) -> None:
    """Add collision where supported, without making generation version-fragile."""
    try:
        if not any(m.type == "COLLISION" for m in obj.modifiers):
            obj.modifiers.new("Weather Collision", "COLLISION")
    except Exception as exc:
        print(f"[CoffeeShop] Collision unavailable for {obj.name}: {exc}")


def add_rigid_body(obj: bpy.types.Object, kinematic: bool = True) -> None:
    """Configure close-up props for rigid-body preview while keeping layout stable."""
    try:
        deselect_all()
        set_active(obj)
        bpy.ops.rigidbody.object_add()
        obj.rigid_body.type = "ACTIVE"
        obj.rigid_body.kinematic = kinematic
        obj.rigid_body.collision_shape = "CONVEX_HULL"
        obj.rigid_body.mass = 4.0
        obj["unity_rigidbody"] = True
    except Exception as exc:
        obj["unity_rigidbody"] = True
        print(f"[CoffeeShop] Rigid body fallback for {obj.name}: {exc}")


def add_soft_body(obj: bpy.types.Object) -> None:
    """Add a conservative soft-body setup suitable for cushion preview and baking."""
    try:
        modifier = obj.modifiers.new("Cushion Soft Body", "SOFT_BODY")
        modifier.show_render = False  # Keep the authored shape until an artist bakes it.
        if hasattr(obj, "soft_body") and obj.soft_body:
            obj.soft_body.friction = 8.0
            obj.soft_body.mass = 1.5
        obj["unity_softbody"] = True
    except Exception as exc:
        obj["unity_softbody"] = True
        print(f"[CoffeeShop] Soft body fallback for {obj.name}: {exc}")


def set_custom_asset_data(obj: bpy.types.Object, category: str, lod: int = 0) -> None:
    """Metadata consumed by Unity editor importers or custom asset pipelines."""
    obj["unity_category"] = category
    obj["unity_lod"] = lod
    obj["units"] = "meters"
    obj["generated_by"] = "ProceduralCoffeeShop_5_2"


# ---------------------------------------------------------------------------
# PBR material and texture management
# ---------------------------------------------------------------------------

class MaterialManager:
    """Creates PBR materials and resolves common AI/library texture naming schemes."""

    CHANNEL_ALIASES = {
        "base_color": ("basecolor", "base_color", "albedo", "diffuse", "color"),
        "roughness": ("roughness", "rough"),
        "metallic": ("metallic", "metalness", "metal"),
        "normal": ("normal", "nor", "nrm"),
        "height": ("height", "displacement", "disp"),
    }
    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".exr", ".webp"}

    def __init__(self, config: CoffeeShopConfig):
        self.config = config
        self.materials: Dict[str, bpy.types.Material] = {}
        self.texture_root = Path(bpy.path.abspath(config.texture_root))
        self._create_texture_tree()

    def _create_texture_tree(self) -> None:
        """Create folders expected from SD, Flux, Midjourney, and local libraries."""
        categories = ("wood", "leather", "fabric", "concrete", "metal", "food",
                      "decals", "weather", "glass", "paper", "ceramic")
        generators = ("stable_diffusion", "flux", "midjourney", "local")
        try:
            for category in categories:
                for generator in generators:
                    (self.texture_root / category / generator).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print(f"[CoffeeShop] Texture folders could not be created: {exc}")

    def _discover_texture(self, category: str, asset: str, channel: str) -> Optional[Path]:
        root = self.texture_root / category
        if not root.exists():
            return None
        aliases = self.CHANNEL_ALIASES[channel]
        wanted = re.sub(r"[^a-z0-9]", "", asset.lower())
        candidates = []
        try:
            for path in root.rglob("*"):
                stem = re.sub(r"[^a-z0-9]", "", path.stem.lower())
                if path.suffix.lower() in self.IMAGE_EXTENSIONS and any(a in stem for a in aliases):
                    score = (2 if wanted and wanted in stem else 0)
                    score += (1 if self.config.texture_resolution.lower() in stem else 0)
                    candidates.append((score, path))
        except OSError:
            return None
        return max(candidates, default=(0, None), key=lambda item: item[0])[1]

    def load_texture_source(self, generator: str, category: str, asset: str,
                            channel: str = "base_color") -> Optional[bpy.types.Image]:
        """Load one map from stable_diffusion, flux, midjourney, or local sources."""
        if generator not in {"stable_diffusion", "flux", "midjourney", "local"}:
            raise ValueError(f"Unsupported texture source: {generator}")
        folder = self.texture_root / category / generator
        if not folder.exists():
            return None
        aliases = self.CHANNEL_ALIASES[channel]
        wanted = re.sub(r"[^a-z0-9]", "", asset.lower())
        for path in sorted(folder.iterdir()):
            stem = re.sub(r"[^a-z0-9]", "", path.stem.lower())
            if (path.suffix.lower() in self.IMAGE_EXTENSIONS
                    and wanted in stem and any(alias in stem for alias in aliases)):
                colorspace = "sRGB" if channel == "base_color" else "Non-Color"
                return self._load_image(path, colorspace)
        return None

    def load_stable_diffusion_texture(self, category: str, asset: str,
                                      channel: str = "base_color"):
        return self.load_texture_source("stable_diffusion", category, asset, channel)

    def load_flux_texture(self, category: str, asset: str, channel: str = "base_color"):
        return self.load_texture_source("flux", category, asset, channel)

    def load_midjourney_texture(self, category: str, asset: str,
                                channel: str = "base_color"):
        return self.load_texture_source("midjourney", category, asset, channel)

    def load_local_texture(self, category: str, asset: str, channel: str = "base_color"):
        return self.load_texture_source("local", category, asset, channel)

    @staticmethod
    def _load_image(path: Path, colorspace: str) -> Optional[bpy.types.Image]:
        try:
            image = bpy.data.images.load(str(path), check_existing=True)
            image.colorspace_settings.name = colorspace
            return image
        except Exception as exc:
            print(f"[CoffeeShop] Failed to load {path}: {exc}")
            return None

    def create_pbr(self, name: str, category: str, color: Tuple[float, float, float, float],
                   roughness: float = 0.5, metallic: float = 0.0,
                   normal_strength: float = 0.22, transmission: float = 0.0,
                   ior: float = 1.45, emission=None, emission_strength: float = 0.0,
                   alpha: float = 1.0) -> bpy.types.Material:
        """Build a map-ready Principled material with a procedural fallback."""
        if name in self.materials:
            return self.materials[name]
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        mat.diffuse_color = color
        mat["texture_category"] = category
        mat["texture_resolution"] = self.config.texture_resolution
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()
        output = nodes.new("ShaderNodeOutputMaterial")
        output.location = (650, 0)
        shader = nodes.new("ShaderNodeBsdfPrincipled")
        shader.name = "PBR Principled"
        shader.location = (330, 0)
        shader.inputs["Base Color"].default_value = color
        shader.inputs["Roughness"].default_value = roughness
        shader.inputs["Metallic"].default_value = metallic
        shader.inputs["IOR"].default_value = ior
        if "Transmission Weight" in shader.inputs:
            shader.inputs["Transmission Weight"].default_value = transmission
        shader.inputs["Alpha"].default_value = alpha
        if emission and "Emission Color" in shader.inputs:
            shader.inputs["Emission Color"].default_value = emission
            shader.inputs["Emission Strength"].default_value = emission_strength
        links.new(shader.outputs["BSDF"], output.inputs["Surface"])

        texcoord = nodes.new("ShaderNodeTexCoord")
        texcoord.location = (-900, -100)
        mapping = nodes.new("ShaderNodeMapping")
        mapping.location = (-720, -100)
        links.new(texcoord.outputs["Generated"], mapping.inputs["Vector"])

        # Fine procedural normal remains under loaded normal maps.
        noise = nodes.new("ShaderNodeTexNoise")
        noise.name = "Procedural micro-surface fallback"
        noise.location = (-490, -420)
        noise.inputs["Scale"].default_value = 65.0 if category != "concrete" else 12.0
        noise.inputs["Detail"].default_value = 4.0
        noise.inputs["Roughness"].default_value = 0.65
        bump = nodes.new("ShaderNodeBump")
        bump.location = (80, -260)
        bump.inputs["Strength"].default_value = normal_strength
        bump.inputs["Distance"].default_value = 0.035
        links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
        links.new(noise.outputs["Fac"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], shader.inputs["Normal"])

        channel_inputs = {
            "base_color": (shader.inputs["Base Color"], "sRGB", (-480, 250)),
            "roughness": (shader.inputs["Roughness"], "Non-Color", (-240, 400)),
            "metallic": (shader.inputs["Metallic"], "Non-Color", (-240, 520)),
        }
        for channel, (socket, colorspace, location) in channel_inputs.items():
            path = self._discover_texture(category, name, channel)
            if path:
                tex = nodes.new("ShaderNodeTexImage")
                tex.name = f"{channel}: {path.name}"
                tex.image = self._load_image(path, colorspace)
                tex.location = location
                links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
                links.new(tex.outputs["Color"], socket)

        normal_path = self._discover_texture(category, name, "normal")
        if normal_path:
            tex = nodes.new("ShaderNodeTexImage")
            tex.name = f"normal: {normal_path.name}"
            tex.image = self._load_image(normal_path, "Non-Color")
            tex.location = (-240, -250)
            normal = nodes.new("ShaderNodeNormalMap")
            normal.location = (70, -150)
            normal.inputs["Strength"].default_value = 1.0
            links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
            links.new(tex.outputs["Color"], normal.inputs["Color"])
            links.new(normal.outputs["Normal"], shader.inputs["Normal"])

        height_path = self._discover_texture(category, name, "height")
        if height_path:
            tex = nodes.new("ShaderNodeTexImage")
            tex.name = f"height: {height_path.name}"
            tex.image = self._load_image(height_path, "Non-Color")
            tex.location = (-240, -560)
            links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
            links.new(tex.outputs["Color"], bump.inputs["Height"])
            mat.surface_render_method = "DITHERED"

        self.materials[name] = mat
        return mat

    def create_library(self) -> Dict[str, bpy.types.Material]:
        p = self.create_pbr
        p("Oak_Wood", "wood", (0.28, 0.105, 0.035, 1), .32, normal_strength=.35)
        p("Dark_Walnut", "wood", (0.065, 0.023, 0.012, 1), .28, normal_strength=.3)
        p("Wood_Panel", "wood", (0.19, 0.055, 0.018, 1), .38, normal_strength=.25)
        p("Blackened_Steel", "metal", (.012, .014, .017, 1), .22, .92)
        p("Brushed_Steel", "metal", (.32, .35, .37, 1), .2, .95)
        p("Copper", "metal", (.46, .13, .045, 1), .2, .88)
        p("Concrete", "concrete", (.19, .205, .215, 1), .62, normal_strength=.4)
        p("Wet_Asphalt", "concrete", (.018, .023, .03, 1), .12, normal_strength=.18)
        p("Cream_Fabric", "fabric", (.51, .44, .34, 1), .74, normal_strength=.42)
        p("Rust_Fabric", "fabric", (.34, .065, .025, 1), .7, normal_strength=.4)
        p("Green_Velvet", "fabric", (.025, .16, .095, 1), .58, normal_strength=.42)
        p("Brown_Leather", "leather", (.13, .035, .014, 1), .35, normal_strength=.33)
        p("Ceramic_White", "ceramic", (.82, .8, .72, 1), .2)
        p("Ceramic_Black", "ceramic", (.012, .013, .015, 1), .18)
        p("Paper", "paper", (.72, .63, .48, 1), .76, normal_strength=.12)
        p("Leaf", "fabric", (.022, .19, .035, 1), .55, normal_strength=.25)
        p("Soil", "concrete", (.025, .012, .006, 1), .9, normal_strength=.5)
        p("Pastry", "food", (.63, .25, .055, 1), .42, normal_strength=.25)
        p("Coffee", "food", (.018, .005, .002, 1), .12)
        p("Water", "weather", (.12, .23, .32, .35), .04, transmission=.96, ior=1.333, alpha=.35)
        p("Glass", "glass", (.68, .82, .9, .12), .045, transmission=.98, ior=1.45, alpha=.12)
        p("Condensation", "weather", (.72, .84, .92, .22), .08, transmission=.82, ior=1.333, alpha=.22)
        p("Warm_Emission", "metal", (1, .28, .055, 1), .25,
          emission=(1, .19, .035, 1), emission_strength=7)
        p("Cool_Emission", "metal", (.05, .2, .55, 1), .3,
          emission=(.03, .14, .65, 1), emission_strength=3)
        return self.materials

    def __getitem__(self, key: str) -> bpy.types.Material:
        return self.materials[key]


# ---------------------------------------------------------------------------
# Architecture and exterior environment
# ---------------------------------------------------------------------------

class EnvironmentBuilder:
    """Builds the shell, glazing, and low-cost city visible through the windows."""

    def __init__(self, config: CoffeeShopConfig, materials: MaterialManager):
        self.c = config
        self.m = materials
        self.root = ensure_collection("ENVIRONMENT")
        self.arch = ensure_collection("Architecture", self.root)
        self.street = ensure_collection("Exterior_City_LOD", self.root)
        self.weather_glass = ensure_collection("Window_Weather", self.root)

    def build_architecture(self) -> None:
        c, m = self.c, self.m
        # Floor, roof, rear and side walls.  The front is a framed glass curtain wall.
        floor = cube("Cafe_Floor", (0, 0, .05), (c.shop_width, c.shop_depth, .1),
                     self.arch, m["Concrete"], .025)
        roof = cube("Cafe_Roof", (0, 0, c.wall_height + .14),
                    (c.shop_width + .4, c.shop_depth + .4, .28),
                    self.arch, m["Concrete"], .04)
        cube("Rear_Wall", (0, c.shop_depth / 2, c.wall_height / 2),
             (c.shop_width, c.wall_thickness, c.wall_height), self.arch, m["Concrete"], .025)
        for x in (-c.shop_width / 2, c.shop_width / 2):
            cube("Side_Wall", (x, 0, c.wall_height / 2),
                 (c.wall_thickness, c.shop_depth, c.wall_height), self.arch, m["Concrete"], .025)
        # Scandinavian wood-panel feature wall.
        cube("Wood_Feature_Wall", (-5.5, 6.82, 2.15), (6.2, .08, 3.7),
             self.arch, m["Wood_Panel"], .015)
        for x in [i * .18 - 8.35 for i in range(33)]:
            cube("Panel_Shadow_Gap", (x, 6.765, 2.15), (.018, .014, 3.65),
                 self.arch, m["Blackened_Steel"])
        # Baseboards and crown-like ceiling trim.
        for y in (-6.87, 6.87):
            cube("Baseboard", (0, y, .11), (17.6, .08, .22), self.arch, m["Dark_Walnut"], .018)
        for x in (-8.87, 8.87):
            cube("Baseboard", (x, 0, .11), (.08, 13.7, .22), self.arch, m["Dark_Walnut"], .018)
        # Exposed beams and structural columns.
        for x in (-6, 0, 6):
            cube("Ceiling_Beam", (x, 0, 4.08), (.16, 13.5, .3),
                 self.arch, m["Blackened_Steel"], .015)
        for x in (-8.55, 8.55):
            column = cylinder("Structural_Column", (x, -4.8, 2.15), .18, 4.3,
                              self.arch, m["Blackened_Steel"], 24, bevel_width=.02)
            set_custom_asset_data(column, "architecture")
        add_collision(floor)
        add_collision(roof)

    def build_windows(self) -> None:
        c, m = self.c, self.m
        front_y = -c.shop_depth / 2 + .03
        # Eight floor-to-ceiling panes, steel mullions, and a central glass door.
        pane_width = c.shop_width / 8
        for i in range(8):
            x = -c.shop_width / 2 + pane_width * (i + .5)
            pane = cube(f"Window_Pane_{i+1:02d}", (x, front_y, 2.18),
                        (pane_width - .09, .025, 4.16), self.arch, m["Glass"], .006)
            pane["glass_ior"] = 1.45
            pane["physical_thickness_m"] = .025
            cube("Window_Mullion", (x - pane_width / 2, front_y - .015, 2.2),
                 (.07, .09, 4.4), self.arch, m["Blackened_Steel"], .01)
        cube("Window_Header", (0, front_y, 4.28), (c.shop_width, .12, .16),
             self.arch, m["Blackened_Steel"], .015)
        # Condensation layer on the warm interior side.
        cube("Interior_Condensation", (0, front_y + .022, 2.25),
             (17.7, .006, 4.0), self.weather_glass, m["Condensation"])
        # Droplets are instanced-looking low geometry spheres, merged conceptually by collection.
        for i in range(260):
            x = RNG.uniform(-8.7, 8.7)
            z = RNG.uniform(.35, 4.12)
            radius = RNG.uniform(.004, .018)
            drop = uv_sphere(f"Glass_Droplet_{i:03d}", (x, front_y - .02, z),
                             (radius * .7, radius * .3, radius * RNG.uniform(1.0, 2.8)),
                             self.weather_glass, m["Water"], 8, 4)
            drop["weather_decal"] = True
        # Long streaks communicate rainfall much better than droplets alone.
        for i in range(55):
            x = RNG.uniform(-8.6, 8.6)
            z = RNG.uniform(1.0, 4.0)
            cube(f"Water_Streak_{i:02d}", (x, front_y - .028, z),
                 (RNG.uniform(.004, .012), .006, RNG.uniform(.12, .8)),
                 self.weather_glass, m["Water"], .003,
                 rotation=(0, 0, RNG.uniform(-.035, .035)))

    def build_street(self) -> None:
        m = self.m
        sidewalk = cube("Sidewalk", (0, -8.55, .03), (32, 3, .16),
                        self.street, m["Concrete"], .03)
        road = cube("Wet_Road", (0, -16, -.04), (42, 12, .12),
                    self.street, m["Wet_Asphalt"], .02)
        add_collision(sidewalk)
        add_collision(road)
        # Reflective, thin irregular puddles (flattened ellipsoids).
        for i in range(24):
            puddle = uv_sphere(f"Puddle_{i:02d}",
                               (RNG.uniform(-16, 16), RNG.uniform(-20.5, -8.4), .035),
                               (RNG.uniform(.25, 1.5), RNG.uniform(.15, .7), .006),
                               self.street, m["Water"], 20, 8)
            puddle["reflection_probe_candidate"] = True
        # Opposite buildings are intentionally low detail and window-driven.
        facade_colors = [(.025, .035, .055, 1), (.06, .045, .05, 1), (.035, .055, .065, 1)]
        for block in range(5):
            x = (block - 2) * 8.0
            height = RNG.uniform(8, 15)
            facade_mat = self.m.create_pbr(
                f"Facade_{block}", "concrete", facade_colors[block % 3], .68
            )
            cube(f"City_Block_{block}", (x, -25.0, height / 2),
                 (7.5, 3.5, height), self.street, facade_mat, .08)
            for floor in range(1, int(height / 2.1)):
                for col in range(3):
                    wx = x + (col - 1) * 1.8
                    wz = floor * 2.05
                    chosen = m["Warm_Emission"] if RNG.random() < .36 else m["Cool_Emission"]
                    cube("Distant_Window", (wx, -23.23, wz), (1.1, .035, 1.15),
                         self.street, chosen, .015)
            cube("Storefront_Awning", (x, -23.0, 2.8), (6.2, 1.0, .18),
                 self.street, m["Blackened_Steel"], .04,
                 rotation=(math.radians(-8), 0, 0))
        self._build_street_furniture()
        self._build_vehicles()

    def _build_street_furniture(self) -> None:
        m = self.m
        for x in (-10, -3.2, 4.4, 11.5):
            cylinder("Streetlight_Pole", (x, -10.3, 2.2), .07, 4.4,
                     self.street, m["Blackened_Steel"], 12)
            lamp = add_area_light("Streetlight_Cold", (x, -10.3, 4.25), 360,
                                  (.28, .45, 1.0), .5, self.street,
                                  rotation=(0, 0, 0))
            lamp.data.use_shadow = True
            cylinder("Lamp_Hood", (x, -10.3, 4.31), .29, .12,
                     self.street, m["Blackened_Steel"], 16)
        # Bench, bins, traffic light, and utility poles.
        for x in (-6.5, 7.0):
            cube("Street_Bench_Seat", (x, -9.4, .56), (2.0, .5, .12),
                 self.street, m["Oak_Wood"], .04)
            for dx in (-.75, .75):
                cube("Bench_Leg", (x + dx, -9.4, .3), (.08, .42, .55),
                     self.street, m["Blackened_Steel"], .02)
        for x in (-13, 13):
            cylinder("Trash_Can", (x, -9.2, .5), .31, 1,
                     self.street, m["Blackened_Steel"], 16, bevel_width=.03)
        pole = cylinder("Traffic_Signal_Pole", (15, -11.2, 2.2), .09, 4.4,
                        self.street, m["Blackened_Steel"], 12)
        cube("Traffic_Signal_Box", (15, -11.2, 4.0), (.42, .35, 1.15),
             self.street, m["Blackened_Steel"], .06)
        for z, color in zip((4.35, 4.0, 3.65),
                            ((.5, .01, .005, 1), (.5, .18, .005, 1), (.01, .5, .06, 1))):
            signal = self.m.create_pbr(f"Signal_{z}", "glass", color, .15,
                                       emission=color, emission_strength=2)
            uv_sphere("Traffic_Light", (15, -11.0, z), (.11, .045, .11),
                      self.street, signal, 12, 6)
        for x in (-17, 18):
            cylinder("Utility_Pole", (x, -19, 3.5), .13, 7,
                     self.street, m["Dark_Walnut"], 12)
        set_custom_asset_data(pole, "street_prop", 2)

    def _build_vehicles(self) -> None:
        m = self.m
        car_mats = [
            self.m.create_pbr("Car_Maroon", "metal", (.18, .012, .018, 1), .16, .75),
            self.m.create_pbr("Car_Navy", "metal", (.008, .03, .09, 1), .14, .8),
            self.m.create_pbr("Car_Silver", "metal", (.28, .3, .32, 1), .18, .82),
        ]
        for i, x in enumerate((-10, -2, 7.5)):
            y = -14.0 if i % 2 == 0 else -18.2
            body = cube(f"Parked_Car_{i}_Body", (x, y, .62), (4.1, 1.75, .72),
                        self.street, car_mats[i], .2)
            cube(f"Parked_Car_{i}_Cabin", (x + .15, y, 1.18), (2.15, 1.58, .72),
                 self.street, m["Glass"], .18)
            for dx in (-1.25, 1.25):
                for dy in (-.84, .84):
                    cylinder("Car_Wheel", (x + dx, y + dy, .42), .34, .18,
                             self.street, m["Blackened_Steel"], 16,
                             rotation=(math.pi / 2, 0, 0))
            set_custom_asset_data(body, "vehicle", 2)

    def build(self) -> None:
        self.build_architecture()
        self.build_windows()
        self.build_street()


# ---------------------------------------------------------------------------
# Furniture, bar, decor, and close-up props
# ---------------------------------------------------------------------------

class CoffeeShopBuilder:
    """Creates game-scale furniture and coffee service assets."""

    def __init__(self, config: CoffeeShopConfig, materials: MaterialManager):
        self.c = config
        self.m = materials
        self.root = ensure_collection("COFFEE_SHOP")
        self.furniture = ensure_collection("Furniture", self.root)
        self.bar = ensure_collection("Coffee_Bar", self.root)
        self.props = ensure_collection("Props_Closeup", self.root)
        self.decor = ensure_collection("Decor", self.root)
        self.physics = ensure_collection("Physics_Assets", self.root)

    def build_table(self, name: str, location: Tuple[float, float, float],
                    style: str = "round") -> bpy.types.Object:
        x, y, _ = location
        if style == "round":
            top = cylinder(name + "_Top", (x, y, .76), .62, .065,
                           self.furniture, self.m["Oak_Wood"], 40, bevel_width=.025)
            cylinder(name + "_Pedestal", (x, y, .39), .075, .7,
                     self.furniture, self.m["Blackened_Steel"], 20)
            cylinder(name + "_Foot", (x, y, .05), .36, .045,
                     self.furniture, self.m["Blackened_Steel"], 24)
        else:
            top = cube(name + "_Top", (x, y, .76), (1.35, .75, .07),
                       self.furniture, self.m["Dark_Walnut"], .035)
            for dx in (-.53, .53):
                for dy in (-.23, .23):
                    cube(name + "_Leg", (x + dx, y + dy, .38), (.055, .055, .72),
                         self.furniture, self.m["Blackened_Steel"], .012)
        set_custom_asset_data(top, "table")
        return top

    def build_chair(self, name: str, location: Tuple[float, float, float],
                    rotation_z: float = 0, material_name: str = "Green_Velvet") -> bpy.types.Object:
        x, y, _ = location
        rot = (0, 0, rotation_z)
        seat = cube(name + "_Seat", (x, y, .48), (.58, .58, .14),
                    self.furniture, self.m[material_name], .075, rot)
        # Back location follows local Y.
        offset = Vector((0, .255, 0))
        offset.rotate(seat.rotation_euler)
        back = cube(name + "_Back", (x + offset.x, y + offset.y, .82),
                    (.58, .12, .65), self.furniture, self.m[material_name], .08, rot)
        for dx in (-.21, .21):
            for dy in (-.21, .21):
                local = Vector((dx, dy, 0))
                local.rotate(seat.rotation_euler)
                cube(name + "_Leg", (x + local.x, y + local.y, .23), (.045, .045, .47),
                     self.furniture, self.m["Blackened_Steel"], .01, rot)
        seat["rigid_body_ready"] = True
        add_rigid_body(seat)
        set_custom_asset_data(seat, "chair")
        return seat

    def build_armchair(self, name: str, location: Tuple[float, float, float],
                       rotation_z: float = 0) -> bpy.types.Object:
        x, y, _ = location
        rot = (0, 0, rotation_z)
        base = cube(name + "_Base", (x, y, .33), (.92, .9, .35),
                    self.furniture, self.m["Brown_Leather"], .15, rot)
        cushion = cube(name + "_Cushion", (x, y - .03, .57), (.67, .67, .18),
                       self.physics, self.m["Rust_Fabric"], .09, rot)
        cushion["soft_body_ready"] = True
        add_soft_body(cushion)
        offset = Vector((0, .34, 0))
        offset.rotate(base.rotation_euler)
        cube(name + "_Back", (x + offset.x, y + offset.y, .93), (.88, .22, .85),
             self.furniture, self.m["Brown_Leather"], .14, rot)
        for sx in (-1, 1):
            arm_offset = Vector((sx * .39, 0, 0))
            arm_offset.rotate(base.rotation_euler)
            cube(name + "_Arm", (x + arm_offset.x, y + arm_offset.y, .68),
                 (.18, .75, .28), self.furniture, self.m["Brown_Leather"], .1, rot)
        set_custom_asset_data(base, "armchair")
        return base

    def build_sofa_and_booth(self) -> None:
        # Reading-corner sofa.
        cube("Reading_Sofa_Base", (-5.8, 4.85, .34), (3.2, .95, .42),
             self.furniture, self.m["Green_Velvet"], .16)
        cube("Reading_Sofa_Back", (-5.8, 5.23, 1.0), (3.2, .24, 1.05),
             self.furniture, self.m["Green_Velvet"], .15)
        for x in (-6.75, -5.8, -4.85):
            cushion = cube("Sofa_Cushion", (x, 4.77, .62), (.86, .68, .18),
                            self.physics, self.m["Cream_Fabric"], .1,
                            rotation=(RNG.uniform(-.025, .025), 0, RNG.uniform(-.025, .025)))
            cushion["soft_body_ready"] = True
            add_soft_body(cushion)
        # Long booth along the right wall.
        cube("Booth_Base", (7.75, 1.4, .35), (1.35, 6.2, .48),
             self.furniture, self.m["Rust_Fabric"], .13)
        cube("Booth_Back", (8.32, 1.4, 1.08), (.24, 6.2, 1.25),
             self.furniture, self.m["Rust_Fabric"], .12)
        for y in (-.9, 1.3, 3.5):
            self.build_table("Booth_Table", (6.65, y, 0), "square")
            self.build_chair("Booth_Chair", (5.7, y, 0), -math.pi / 2, "Cream_Fabric")

    def build_counter(self) -> None:
        m = self.m
        cube("Bar_Carcass", (1.5, 4.8, .57), (8.8, 1.35, 1.14),
             self.bar, m["Wood_Panel"], .045)
        cube("Bar_Countertop", (1.5, 4.73, 1.18), (9.1, 1.58, .11),
             self.bar, m["Concrete"], .045)
        for x in (-2.1, -.3, 1.5, 3.3, 5.1):
            cube("Counter_Fluting", (x, 4.085, .58), (.07, .025, 1.0),
                 self.bar, m["Dark_Walnut"], .012)
        # Back counter, shelving, sink.
        cube("Back_Counter", (1.4, 6.25, .55), (8.7, .85, 1.05),
             self.bar, m["Dark_Walnut"], .04)
        for z in (2.05, 2.85, 3.65):
            cube("Floating_Shelf", (1.4, 6.55, z), (8.2, .35, .08),
                 self.bar, m["Oak_Wood"], .025)
        sink = cube("Sink_Basin", (3.65, 6.03, 1.09), (1.15, .55, .12),
                    self.bar, m["Brushed_Steel"], .06)
        cylinder("Sink_Drain", (3.65, 6.03, 1.17), .065, .006,
                 self.bar, m["Blackened_Steel"], 20)
        torus("Faucet_Arc", (3.65, 6.25, 1.55), .26, .035,
              self.bar, m["Brushed_Steel"], rotation=(math.pi / 2, 0, 0))
        add_collision(sink)
        self._build_espresso_machine()
        self._build_display_case()
        self._build_register_and_menu()
        self._populate_bar_props()

    def _build_espresso_machine(self) -> None:
        m = self.m
        cube("Espresso_Base", (.2, 4.58, 1.38), (2.15, .72, .38),
             self.bar, m["Brushed_Steel"], .09)
        cube("Espresso_Body", (.2, 4.75, 1.77), (1.95, .62, .62),
             self.bar, m["Blackened_Steel"], .1)
        cube("Espresso_Top", (.2, 4.76, 2.12), (2.02, .66, .11),
             self.bar, m["Copper"], .045)
        for x in (-.36, .36):
            cylinder("Group_Head", (x, 4.37, 1.72), .15, .12,
                     self.bar, m["Brushed_Steel"], 24,
                     rotation=(math.pi / 2, 0, 0), bevel_width=.02)
            cylinder("Portafilter", (x + .3, 4.25, 1.69), .035, .58,
                     self.bar, m["Blackened_Steel"], 12,
                     rotation=(0, math.pi / 2, 0))
            cylinder("Espresso_Nozzle", (x, 4.28, 1.42), .018, .42,
                     self.bar, m["Brushed_Steel"], 10)
        for x in (-.65, 0, .65):
            cylinder("Machine_Gauge", (x, 4.42, 1.93), .075, .03,
                     self.bar, m["Ceramic_White"], 20,
                     rotation=(math.pi / 2, 0, 0))
        # Twin detailed grinders.
        for x in (1.8, 2.55):
            cube("Grinder_Base", (x, 4.67, 1.35), (.5, .48, .23),
                 self.bar, m["Blackened_Steel"], .06)
            cylinder("Grinder_Motor", (x, 4.67, 1.68), .2, .55,
                     self.bar, m["Brushed_Steel"], 24)
            bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=.28, radius2=.18,
                                            depth=.62, location=(x, 4.67, 2.22))
            hopper = bpy.context.object
            hopper.name = "Coffee_Grinder_Hopper"
            move_to_collection(hopper, self.bar)
            assign_material(hopper, m["Glass"])
            cylinder("Hopper_Beans", (x, 4.67, 2.08), .18, .2,
                     self.bar, m["Coffee"], 20)

    def _build_display_case(self) -> None:
        m = self.m
        x = -2.3
        cube("Display_Base", (x, 4.58, 1.38), (1.8, .92, .25),
             self.bar, m["Blackened_Steel"], .035)
        for z in (1.58, 1.92, 2.26):
            cube("Display_Glass_Shelf", (x, 4.58, z), (1.7, .82, .025),
                 self.bar, m["Glass"], .008)
        for dx in (-.82, .82):
            cube("Display_Frame", (x + dx, 4.58, 1.93), (.035, .9, 1.1),
                 self.bar, m["Blackened_Steel"], .008)
        cube("Display_Front_Glass", (x, 4.13, 1.93), (1.65, .025, 1.1),
             self.bar, m["Glass"], .008)
        for row, z in enumerate((1.65, 2.0, 2.33)):
            for col in range(4):
                px = x - .6 + col * .4 + RNG.uniform(-.035, .035)
                pastry = torus("Glazed_Pastry", (px, 4.54, z), .12, .05,
                               self.props, m["Pastry"],
                               rotation=(math.pi / 2, 0, RNG.uniform(0, math.pi)))
                pastry.scale.x = RNG.uniform(.85, 1.15)

    def _build_register_and_menu(self) -> None:
        m = self.m
        cube("Register_Base", (4.65, 4.43, 1.36), (.65, .48, .15),
             self.bar, m["Blackened_Steel"], .04)
        screen = cube("Register_Screen", (4.65, 4.47, 1.68), (.7, .08, .48),
                      self.bar, m["Cool_Emission"], .045,
                      rotation=(math.radians(-12), 0, 0))
        screen["interactive_prop"] = True
        # Three overhead menu boards.
        menu_text = (
            "ESPRESSO\n3.20\nCAPPUCCINO\n4.50\nFLAT WHITE\n4.70",
            "POUR OVER\n5.20\nCOLD BREW\n4.80\nCHAI\n4.40",
            "CROISSANT\n3.80\nCARDAMOM BUN\n4.20\nTART\n5.10",
        )
        for i, body in enumerate(menu_text):
            x = -.9 + i * 2.25
            cube("Menu_Backboard", (x, 6.73, 3.25), (2.0, .06, 1.35),
                 self.decor, m["Blackened_Steel"], .025)
            text_object("Menu_Lettering", body, (x, 6.69, 3.68),
                        (math.pi / 2, 0, 0), .13, self.decor,
                        m["Ceramic_White"], .003)

    def _populate_bar_props(self) -> None:
        m = self.m
        # Cups, mugs, napkins, brewers, bean bags, syrup bottles.
        for shelf_z in (2.12, 2.92):
            for i in range(12):
                x = -2.2 + i * .58 + RNG.uniform(-.035, .035)
                cylinder("Stacked_Cup", (x, 6.45, shelf_z), .09, .16,
                         self.props, m["Ceramic_White"], 20, bevel_width=.012)
        for i in range(8):
            x = -1.6 + i * .43
            mug = cylinder("Coffee_Mug", (x, 5.08, 1.32), .105, .18,
                           self.props, m["Ceramic_Black"] if i % 2 else m["Ceramic_White"],
                           24, bevel_width=.012)
            torus("Mug_Handle", (x + .11, 5.08, 1.34), .075, .018,
                  self.props, mug.data.materials[0], rotation=(math.pi / 2, 0, 0))
        cube("Napkin_Holder", (3.8, 4.3, 1.35), (.3, .18, .28),
             self.props, m["Brushed_Steel"], .025)
        for i in range(5):
            cube("Coffee_Bean_Bag", (-2.7 + i * .65, 6.35, 3.15),
                 (.46, .18, .68), self.props, m["Paper"], .06,
                 rotation=(0, RNG.uniform(-.05, .05), RNG.uniform(-.08, .08)))
        for i in range(6):
            cylinder("Syrup_Bottle", (2.4 + i * .35, 6.25, 1.45),
                     .075, .48, self.props, m["Glass"], 16)
            cylinder("Bottle_Pump", (2.4 + i * .35, 6.25, 1.72),
                     .025, .12, self.props, m["Blackened_Steel"], 10)
        # Pour-over stand.
        cube("Brewer_Stand", (-1.5, 6.1, 1.5), (1.3, .12, .08),
             self.props, m["Blackened_Steel"], .018)
        for x in (-1.9, -1.5, -1.1):
            bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=.14, radius2=.24,
                                            depth=.25, location=(x, 6.02, 1.72))
            brewer = bpy.context.object
            brewer.name = "Pour_Over_Brewer"
            move_to_collection(brewer, self.props)
            assign_material(brewer, m["Ceramic_White"])

    def build_bookshelf(self) -> None:
        m = self.m
        x, y = -7.65, 2.25
        cube("Bookshelf_Frame", (x, y, 1.5), (1.8, .42, 3.0),
             self.decor, m["Dark_Walnut"], .045)
        cube("Bookshelf_Inner", (x, y - .22, 1.5), (1.55, .06, 2.7),
             self.decor, m["Blackened_Steel"])
        cover_colors = [
            (.3, .02, .015, 1), (.025, .11, .18, 1), (.18, .1, .015, 1),
            (.05, .18, .08, 1), (.27, .2, .07, 1),
        ]
        for row, z in enumerate((.35, .98, 1.61, 2.24, 2.78)):
            cube("Shelf", (x, y - .02, z), (1.65, .4, .07),
                 self.decor, m["Oak_Wood"], .015)
            cursor = x - .68
            while cursor < x + .62:
                width = RNG.uniform(.055, .12)
                height = RNG.uniform(.32, .5)
                color = RNG.choice(cover_colors)
                book_mat = self.m.create_pbr(
                    f"Book_{round(color[0],2)}_{round(color[1],2)}", "paper", color, .66
                )
                cube("Book", (cursor, y - .07, z + height / 2 + .04),
                     (width, .25, height), self.props, book_mat, .006,
                     rotation=(0, RNG.uniform(-.025, .025), RNG.uniform(-.05, .05)))
                cursor += width + RNG.uniform(.006, .02)

    def build_plant(self, name: str, location: Tuple[float, float, float],
                    hanging: bool = False, scale: float = 1.0) -> None:
        x, y, z = location
        pot_mat = self.m["Ceramic_Black"] if RNG.random() < .5 else self.m["Ceramic_White"]
        cylinder(name + "_Pot", (x, y, z + .22 * scale), .25 * scale,
                 .44 * scale, self.decor, pot_mat, 20, bevel_width=.025)
        cylinder(name + "_Soil", (x, y, z + .44 * scale), .21 * scale,
                 .025, self.decor, self.m["Soil"], 20)
        for i in range(int(13 * scale) + 5):
            angle = i * 2.399 + RNG.uniform(-.2, .2)
            radial = RNG.uniform(.08, .32) * scale
            leaf_z = z + RNG.uniform(.55, 1.25) * scale
            leaf = uv_sphere(name + "_Leaf", (x + math.cos(angle) * radial,
                                              y + math.sin(angle) * radial, leaf_z),
                             (.1 * scale, .035 * scale, RNG.uniform(.2, .38) * scale),
                             self.decor, self.m["Leaf"], 12, 6)
            leaf.rotation_euler = (RNG.uniform(-.5, .5), RNG.uniform(-.5, .5), angle)
            leaf["wind_response"] = RNG.uniform(.2, 1.0)
        if hanging:
            for dx in (-.18, .18):
                cube(name + "_Rope", (x + dx, y, z + 1.35), (.012, .012, 1.9),
                     self.physics, self.m["Cream_Fabric"])

    def build_decor(self) -> None:
        m = self.m
        self.build_bookshelf()
        for args in [
            ("Plant_Fiddle", (-7.5, -4.9, 0), False, 1.25),
            ("Plant_Counter", (5.3, 6.0, 1.1), False, .62),
            ("Plant_Hanging_A", (-4.2, 1.0, 2.9), True, .7),
            ("Plant_Hanging_B", (4.6, -.8, 2.9), True, .75),
        ]:
            self.build_plant(*args)
        # Rugs.
        cube("Reading_Rug", (-5.4, 4.3, .085), (4.9, 3.3, .025),
             self.decor, m["Rust_Fabric"], .08)
        cube("Center_Rug", (1.0, -.1, .085), (5.5, 3.7, .025),
             self.decor, m["Cream_Fabric"], .08)
        # Artwork with varied proportions and abstract inserts.
        for i, x in enumerate((-5.8, -3.1, -.4, 2.3, 5.0)):
            cube("Artwork_Frame", (x, 6.70, 2.45), (1.35, .09, 1.45),
                 self.decor, m["Blackened_Steel"], .035)
            art_mat = self.m.create_pbr(
                f"Artwork_{i}", "paper",
                (RNG.uniform(.08, .5), RNG.uniform(.025, .22), RNG.uniform(.01, .14), 1), .62
            )
            cube("Artwork_Print", (x, 6.642, 2.45), (1.18, .012, 1.28),
                 self.decor, art_mat)
        # Curtains at the side reading window; cloth-ready subdivided planes.
        for x in (-8.55, 8.55):
            bpy.ops.mesh.primitive_grid_add(x_subdivisions=18, y_subdivisions=24,
                                            size=2, location=(x, -3.7, 2.65))
            curtain = bpy.context.object
            curtain.name = "Cloth_Curtain"
            curtain.scale = (.02, 1.15, 1.55)
            curtain.rotation_euler = (math.pi / 2, 0, math.pi / 2)
            apply_transform(curtain)
            move_to_collection(curtain, self.physics)
            assign_material(curtain, m["Cream_Fabric"])
            curtain["cloth_ready"] = True
            try:
                curtain.modifiers.new("Curtain Cloth", "CLOTH")
            except Exception as exc:
                print(f"[CoffeeShop] Cloth modifier unavailable: {exc}")
        # Candles and wall sign.
        for i in range(7):
            x, y = RNG.uniform(-5, 6), RNG.uniform(-4.5, 3.5)
            cylinder("Candle", (x, y, .86), .035, .16, self.props, m["Ceramic_White"], 12)
            uv_sphere("Candle_Flame", (x, y, .97), (.018, .018, .05),
                      self.props, m["Warm_Emission"], 10, 5)
        text_object("Cafe_Sign", "NORTH & PINE", (-5.6, 6.55, 3.72),
                    (math.pi / 2, 0, 0), .36, self.decor, m["Warm_Emission"], .012)

    def build_seating(self) -> None:
        layouts = [
            ((-4.8, -3.2, 0), "round"),
            ((-1.9, -3.4, 0), "square"),
            ((1.2, -3.25, 0), "round"),
            ((4.2, -3.45, 0), "square"),
            ((4.3, -.5, 0), "round"),
            ((1.0, 1.1, 0), "square"),
        ]
        for index, (loc, style) in enumerate(layouts):
            self.build_table(f"Cafe_Table_{index}", loc, style)
            count = 3 if style == "round" else 2
            for j in range(count):
                angle = (math.tau / count) * j + .2
                radius = 1.02
                self.build_chair(
                    f"Cafe_Chair_{index}_{j}",
                    (loc[0] + math.cos(angle) * radius,
                     loc[1] + math.sin(angle) * radius, 0),
                    angle + math.pi,
                    "Cream_Fabric" if (index + j) % 2 else "Green_Velvet",
                )
        self.build_armchair("Reading_Armchair_A", (-3.5, 4.8, 0), math.pi / 2)
        self.build_armchair("Reading_Armchair_B", (-6.8, 3.45, 0), -.2)
        self.build_sofa_and_booth()

    def build(self) -> None:
        self.build_seating()
        self.build_counter()
        self.build_decor()


# ---------------------------------------------------------------------------
# Weather, particles, steam, wind, and lightning
# ---------------------------------------------------------------------------

class WeatherSystem:
    """Efficient single-mesh weather effects plus collision and wind metadata."""

    def __init__(self, config: CoffeeShopConfig, materials: MaterialManager):
        self.c = config
        self.m = materials
        self.collection = ensure_collection("WEATHER")
        self.lightning: Optional[bpy.types.Object] = None

    def create_rain(self) -> bpy.types.Object:
        """Create thousands of camera-readable streak particles in one draw call."""
        count = max(200, int(self.c.rain_streak_count * self.c.rain_intensity))
        vertices: List[Tuple[float, float, float]] = []
        faces: List[Tuple[int, int, int, int]] = []
        for i in range(count):
            x = RNG.uniform(-21, 21)
            y = RNG.uniform(-30, -6.7)
            z = RNG.uniform(.1, 14)
            length = RNG.uniform(.22, .8)
            wind = RNG.uniform(.025, .11)
            width = RNG.uniform(.0025, .007)
            idx = len(vertices)
            # Camera-facing-ish crossed ribbons render reliably in Cycles without
            # thousands of curve objects or a legacy particle-system dependency.
            vertices.extend((
                (x - width, y, z),
                (x + width, y, z),
                (x + wind + width, y + .015, z - length),
                (x + wind - width, y + .015, z - length),
            ))
            faces.append((idx, idx + 1, idx + 2, idx + 3))
        mesh = bpy.data.meshes.new("Rain_Particles_Mesh")
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        rain = bpy.data.objects.new("Rain_Particle_Field", mesh)
        self.collection.objects.link(rain)
        assign_material(rain, self.m["Water"])
        rain["particle_count"] = count
        rain["particle_implementation"] = "batched billboard streaks"
        rain["collision_enabled_surfaces"] = "Cafe_Roof,Sidewalk,Wet_Road"
        rain["adjustable_intensity"] = self.c.rain_intensity
        # Loop the field every two seconds for continuous rainfall.
        rain.location.z = 0
        rain.keyframe_insert("location", frame=1)
        rain.location.z = -12
        rain.keyframe_insert("location", frame=self.c.fps * 2)
        for curve in animation_fcurves(rain):
            for point in curve.keyframe_points:
                point.interpolation = "LINEAR"
            modifier = curve.modifiers.new("CYCLES")
            modifier.mode_before = "REPEAT"
            modifier.mode_after = "REPEAT"
        return rain

    def create_dust(self) -> bpy.types.Object:
        """Create warm interior dust motes as a lightweight animated particle cloud."""
        vertices = []
        faces = []
        size = .006
        for _ in range(420):
            x, y, z = RNG.uniform(-8.5, 8.5), RNG.uniform(-6.5, 6.5), RNG.uniform(.2, 4)
            index = len(vertices)
            vertices.extend(((x - size, y, z), (x + size, y, z), (x, y, z + size * 2)))
            faces.append((index, index + 1, index + 2))
        mesh = bpy.data.meshes.new("Dust_Particles_Mesh")
        mesh.from_pydata(vertices, [], faces)
        dust = bpy.data.objects.new("Interior_Dust_Particles", mesh)
        self.collection.objects.link(dust)
        assign_material(dust, self.m["Warm_Emission"])
        dust.location = (0, 0, 0)
        dust.keyframe_insert("location", frame=1)
        dust.location = (.18, .08, .35)
        dust.keyframe_insert("location", frame=120)
        for curve in animation_fcurves(dust):
            curve.modifiers.new("CYCLES")
        dust["particle_count"] = 420
        return dust

    def create_steam(self) -> None:
        """Volumetric steam wisps made from animated metaballs and volume material."""
        steam_mat = bpy.data.materials.new("Steam_Volume")
        steam_mat.use_nodes = True
        nodes = steam_mat.node_tree.nodes
        links = steam_mat.node_tree.links
        nodes.clear()
        out = nodes.new("ShaderNodeOutputMaterial")
        volume = nodes.new("ShaderNodeVolumePrincipled")
        volume.inputs["Density"].default_value = .75
        volume.inputs["Color"].default_value = (.72, .76, .8, 1)
        volume.inputs["Temperature"].default_value = 370
        links.new(volume.outputs["Volume"], out.inputs["Volume"])
        sources = [(-1.6, 5.08, 1.5), (-.36, 4.28, 1.48), (.36, 4.28, 1.48)]
        for source_index, source in enumerate(sources):
            for i in range(6):
                data = bpy.data.metaballs.new(f"Steam_{source_index}_{i}_Data")
                data.resolution = .08
                data.render_resolution = .04
                element = data.elements.new()
                element.radius = .09 + i * .018
                obj = bpy.data.objects.new(f"Steam_Wisp_{source_index}_{i}", data)
                self.collection.objects.link(obj)
                obj.data.materials.append(steam_mat)
                obj.location = (source[0] + math.sin(i) * .04,
                                source[1] + math.cos(i) * .025,
                                source[2] + i * .12)
                start = 1 + i * 5
                obj.scale = (.45, .45, .55)
                obj.keyframe_insert("location", frame=start)
                obj.keyframe_insert("scale", frame=start)
                obj.location.z += .85
                obj.location.x += math.sin(i * 1.7) * .18
                obj.scale = (1.4, 1.4, 1.8)
                obj.keyframe_insert("location", frame=start + 55)
                obj.keyframe_insert("scale", frame=start + 55)
                for fc in animation_fcurves(obj):
                    fc.modifiers.new("CYCLES")

    def create_wind(self) -> None:
        bpy.ops.object.effector_add(type="WIND", location=(0, -12, 2.5),
                                    rotation=(math.pi / 2, 0, 0))
        wind = bpy.context.object
        wind.name = "Storm_Wind"
        move_to_collection(wind, self.collection)
        wind.field.strength = 320
        wind.field.noise = 2.2
        wind["affects"] = "cloth, hanging plants, hanging decor"
        wind.field.strength = 250
        wind.field.keyframe_insert("strength", frame=1)
        wind.field.strength = 420
        wind.field.keyframe_insert("strength", frame=48)
        wind.field.strength = 280
        wind.field.keyframe_insert("strength", frame=96)
        for fc in animation_fcurves(wind):
            fc.modifiers.new("CYCLES")

    def create_lightning(self) -> None:
        light_data = bpy.data.lights.new("Lightning_Flash", "AREA")
        light_data.energy = 0
        light_data.color = (.35, .52, 1.0)
        light_data.shape = "DISK"
        light_data.size = 25
        light = bpy.data.objects.new("Lightning_Flash", light_data)
        self.collection.objects.link(light)
        light.location = (0, -19, 11)
        light.rotation_euler = (0, 0, 0)
        # Seeded irregular flashes; two-frame impulses and occasional after-flash.
        flash_frames = [143, 319, 487, 641]
        for frame in flash_frames:
            for f, energy in ((frame - 1, 0), (frame, 85000),
                              (frame + 2, 9000), (frame + 4, 36000), (frame + 6, 0)):
                light_data.energy = energy
                light_data.keyframe_insert("energy", frame=f)
            marker = bpy.context.scene.timeline_markers.new(f"THUNDER_SYNC_{frame}", frame=frame + 34)
            marker["delay_seconds"] = 34 / self.c.fps
        for fc in animation_fcurves(light_data):
            for point in fc.keyframe_points:
                point.interpolation = "CONSTANT"
        self.lightning = light

    def build(self) -> None:
        self.create_rain()
        self.create_dust()
        self.create_steam()
        self.create_wind()
        self.create_lightning()


# ---------------------------------------------------------------------------
# Lighting and color management
# ---------------------------------------------------------------------------

class LightingSystem:
    """Warm practical interior lighting against a cold, overcast exterior."""

    def __init__(self, config: CoffeeShopConfig, materials: MaterialManager):
        self.c = config
        self.m = materials
        self.collection = ensure_collection("LIGHTING")

    def build(self) -> None:
        # World: blue-gray storm fill.
        world = bpy.data.worlds.new("Storm_Evening_World") if not bpy.data.worlds.get(
            "Storm_Evening_World") else bpy.data.worlds["Storm_Evening_World"]
        bpy.context.scene.world = world
        world.use_nodes = True
        background = world.node_tree.nodes.get("Background")
        background.inputs["Color"].default_value = (.012, .025, .055, 1)
        background.inputs["Strength"].default_value = .12
        # Large cold exterior source.
        add_area_light("Overcast_Sky_Fill", (0, -13, 12), 1900,
                       (.23, .37, .62), 18, self.collection,
                       rotation=(0, 0, 0))
        # 2900K-looking warm pendant lights (RGB approximation).
        for x, y in [(-4.7, -3.2), (-1.8, -3.4), (1.2, -3.2), (4.2, -3.4),
                     (4.3, -.5), (1, 1.1), (6.6, 2.1), (-5.6, 4.2)]:
            cylinder("Pendant_Cord", (x, y, 3.55), .009, 1.05,
                     self.collection, self.m["Blackened_Steel"], 8)
            bpy.ops.mesh.primitive_cone_add(vertices=32, radius1=.34, radius2=.09,
                                            depth=.32, location=(x, y, 3.05))
            shade = bpy.context.object
            shade.name = "Pendant_Shade"
            move_to_collection(shade, self.collection)
            assign_material(shade, self.m["Copper"])
            add_area_light("Pendant_2900K", (x, y, 2.88), 470,
                           (1.0, .39, .13), .38, self.collection)
        # Counter work lights and gentle bounce cards.
        for x in (-2.5, 0, 2.5, 5):
            add_area_light("Bar_Task_3100K", (x, 5.25, 3.75), 560,
                           (1.0, .48, .2), .7, self.collection)
        add_area_light("Interior_Bounce_Warm", (0, 2, 2.7), 900,
                       (1.0, .24, .08), 7.0, self.collection,
                       rotation=(0, math.pi / 2, 0))


# ---------------------------------------------------------------------------
# Cameras and cinematic animation
# ---------------------------------------------------------------------------

class CameraSystem:
    """Creates shot cameras and a 30-second smooth master dolly."""

    SHOTS = {
        "CAM_Wide_Interior": ((0, -5.8, 2.25), (0, 1.6, 1.55), 28),
        "CAM_Coffee_Counter": ((-1.7, 1.8, 1.75), (1.0, 4.9, 1.55), 44),
        "CAM_Reading_Corner": ((-1.8, 1.8, 1.65), (-5.6, 4.8, .85), 50),
        "CAM_Window_Seating": ((6.8, 1.2, 1.65), (2.0, -3.1, .8), 42),
        "CAM_Street_Rain": ((11, -17.5, 1.8), (0, -7.0, 1.7), 52),
        "CAM_Exterior_Establishing": ((-12, -19, 4.0), (0, -5.2, 2.0), 35),
    }

    def __init__(self, config: CoffeeShopConfig):
        self.c = config
        self.collection = ensure_collection("CAMERAS")
        self.cameras: Dict[str, bpy.types.Object] = {}

    def create_camera(self, name: str, location, target_location, lens) -> bpy.types.Object:
        data = bpy.data.cameras.new(name)
        data.lens = lens
        data.sensor_width = 36
        data.dof.use_dof = True
        data.dof.aperture_fstop = 2.4
        data.dof.aperture_blades = 9
        camera = bpy.data.objects.new(name, data)
        self.collection.objects.link(camera)
        camera.location = location
        target = bpy.data.objects.new(name + "_Focus", None)
        self.collection.objects.link(target)
        target.location = target_location
        data.dof.focus_object = target
        track_to(camera, target)
        self.cameras[name] = camera
        return camera

    def build(self) -> None:
        for name, (loc, target, lens) in self.SHOTS.items():
            self.create_camera(name, loc, target, lens)
        master = self.cameras["CAM_Wide_Interior"]
        target = master.data.dof.focus_object
        keyframes = [
            (1, (-.8, -5.9, 2.2), (0, .8, 1.5), 30),
            (180, (4.8, -3.7, 1.72), (1.2, 4.8, 1.55), 42),
            (360, (-1.5, .8, 1.65), (-5.6, 4.6, .9), 50),
            (540, (-6.8, -2.8, 1.62), (0, -3.2, .85), 38),
            (720, (2.6, -5.7, 2.15), (1.4, 4.6, 1.4), 30),
        ]
        for frame, location, focus, lens in keyframes:
            master.location = location
            target.location = focus
            master.data.lens = lens
            master.keyframe_insert("location", frame=frame)
            target.keyframe_insert("location", frame=frame)
            master.data.keyframe_insert("lens", frame=frame)
        for owner in (master, target, master.data):
            for curve in animation_fcurves(owner):
                for point in curve.keyframe_points:
                    point.interpolation = "BEZIER"
                    point.handle_left_type = "AUTO_CLAMPED"
                    point.handle_right_type = "AUTO_CLAMPED"
        bpy.context.scene.camera = master


class AnimationSystem:
    """Scene timing, ambient motion, and optional game-engine metadata."""

    def __init__(self, config: CoffeeShopConfig):
        self.c = config

    def configure(self) -> None:
        scene = bpy.context.scene
        scene.render.fps = self.c.fps
        scene.frame_start = 1
        scene.frame_end = self.c.cinematic_seconds * self.c.fps
        # Animate plant leaves subtly without expensive per-object simulations.
        leaves = [o for o in bpy.data.objects if "wind_response" in o]
        for index, leaf in enumerate(leaves):
            base = leaf.rotation_euler.copy()
            amplitude = .015 + float(leaf["wind_response"]) * .035
            for frame, sign in ((1, -1), (48 + index % 17, 1), (96 + index % 11, -1)):
                leaf.rotation_euler = base
                leaf.rotation_euler.x += amplitude * sign
                leaf.rotation_euler.y += amplitude * .6 * -sign
                leaf.keyframe_insert("rotation_euler", frame=frame)
            for fc in animation_fcurves(leaf):
                fc.modifiers.new("CYCLES")
        scene["cinematic_duration_seconds"] = self.c.cinematic_seconds
        scene["thunder_markers_are_audio_sync_points"] = True


# ---------------------------------------------------------------------------
# LOD generation, rendering, and Unity export
# ---------------------------------------------------------------------------

class ExportManager:
    """Creates LOD collections and exports clean Unity-oriented FBX/GLB packages."""

    def __init__(self, config: CoffeeShopConfig):
        self.c = config
        self.export_root = Path(bpy.path.abspath(config.export_root))

    def generate_lods(self) -> None:
        """Generate linked LOD1-3 meshes for marked game assets."""
        if not self.c.build_lods:
            return
        lod_root = ensure_collection("UNITY_LODS")
        source_objects = [
            o for o in bpy.data.objects
            if o.type == "MESH" and "unity_category" in o and int(o.get("unity_lod", 0)) == 0
        ]
        ratios = {1: .55, 2: .28, 3: .12}
        for source in source_objects:
            source.name = re.sub(r"_LOD\d+$", "", source.name) + "_LOD0"
            source["unity_lod"] = 0
            for level, ratio in ratios.items():
                lod_collection = ensure_collection(f"LOD{level}", lod_root)
                duplicate = source.copy()
                duplicate.data = source.data.copy()
                duplicate.name = re.sub(r"_LOD0$", f"_LOD{level}", source.name)
                lod_collection.objects.link(duplicate)
                duplicate["unity_lod"] = level
                decimate = duplicate.modifiers.new(f"LOD{level}_Decimate", "DECIMATE")
                decimate.ratio = ratio
                decimate.use_collapse_triangulate = True
                duplicate.hide_render = True
                duplicate.hide_viewport = True
        # Preserve explicit nomenclature even if a scene category had no candidates.
        for level in range(4):
            ensure_collection(f"LOD{level}", lod_root)

    def configure_render(self) -> None:
        scene = bpy.context.scene
        try:
            scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in {
                item.identifier for item in scene.bl_rna.properties["render"].fixed_type.properties[
                    "engine"].enum_items
            } else scene.render.engine
        except Exception:
            pass
        # Prefer Cycles as requested, but remain executable in builds compiled without it.
        try:
            scene.render.engine = "CYCLES"
            scene.cycles.samples = self.c.render_samples
            scene.cycles.use_denoising = True
            scene.cycles.max_bounces = 12
            scene.cycles.diffuse_bounces = 4
            scene.cycles.glossy_bounces = 6
            scene.cycles.transmission_bounces = 8
            scene.cycles.volume_bounces = 3
            if hasattr(scene.cycles, "use_fast_gi"):
                scene.cycles.use_fast_gi = False
            if hasattr(scene.cycles, "caustics_reflective"):
                scene.cycles.caustics_reflective = True
            if hasattr(scene.cycles, "caustics_refractive"):
                scene.cycles.caustics_refractive = True
        except Exception as exc:
            print(f"[CoffeeShop] Cycles configuration fallback: {exc}")
        scene.render.resolution_x = 2560
        scene.render.resolution_y = 1440
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = "OPEN_EXR"
        scene.render.image_settings.color_mode = "RGBA"
        scene.render.film_transparent = False
        scene.view_settings.look = "AgX - Medium High Contrast"
        scene.view_settings.exposure = .25
        scene.render.use_file_extension = True
        scene["render_profile"] = "Cycles_Photoreal_Production"
        scene["texture_profiles"] = "2K,4K,8K"

    def export(self) -> None:
        self.export_root.mkdir(parents=True, exist_ok=True)
        scene = bpy.context.scene
        original_frame = scene.frame_current
        scene.frame_set(1)
        # Exporters can be absent in custom Blender builds; each format is independent.
        try:
            bpy.ops.export_scene.fbx(
                filepath=str(self.export_root / "RainyCoffeeShop_Unity.fbx"),
                use_selection=False,
                object_types={"MESH", "ARMATURE", "EMPTY", "CAMERA", "LIGHT"},
                apply_unit_scale=True,
                apply_scale_options="FBX_SCALE_UNITS",
                use_space_transform=True,
                axis_forward="-Z",
                axis_up="Y",
                bake_anim=True,
                bake_anim_use_all_actions=True,
                bake_anim_simplify_factor=0.0,
                path_mode="COPY",
                embed_textures=False,
                add_leaf_bones=False,
            )
            print("[CoffeeShop] FBX export complete.")
        except Exception as exc:
            print(f"[CoffeeShop] FBX exporter unavailable or failed: {exc}")
        try:
            bpy.ops.export_scene.gltf(
                filepath=str(self.export_root / "RainyCoffeeShop_Unity.glb"),
                export_format="GLB",
                export_apply=True,
                export_yup=True,
                export_animations=True,
                export_materials="EXPORT",
                export_cameras=True,
                export_lights=True,
            )
            print("[CoffeeShop] GLB export complete.")
        except Exception as exc:
            print(f"[CoffeeShop] glTF exporter unavailable or failed: {exc}")
        # Save a source blend and copy discovered images beside the exports.
        try:
            bpy.ops.wm.save_as_mainfile(filepath=str(self.export_root / "RainyCoffeeShop_Source.blend"),
                                       copy=True)
        except Exception as exc:
            print(f"[CoffeeShop] Source blend copy failed: {exc}")
        scene.frame_set(original_frame)


def export_for_unity() -> None:
    """Public one-call Unity exporter requested by the production brief."""
    ExportManager(CFG).export()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def clear_generated_scene() -> None:
    """Make repeated one-click runs deterministic without touching external files."""
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.collections, bpy.data.meshes, bpy.data.curves,
                  bpy.data.metaballs, bpy.data.materials, bpy.data.cameras,
                  bpy.data.lights):
        for item in list(block):
            if item.users == 0:
                block.remove(item)


def main() -> None:
    """Build, animate, optimize, configure, and export the complete scene."""
    print("[CoffeeShop] Starting procedural rainy coffee-shop build...")
    try:
        clear_generated_scene()
        random.seed(CFG.seed)
        global RNG
        RNG = random.Random(CFG.seed)

        scene = bpy.context.scene
        scene.unit_settings.system = "METRIC"
        scene.unit_settings.scale_length = 1.0
        scene.unit_settings.length_unit = "METERS"

        materials = MaterialManager(CFG)
        materials.create_library()

        EnvironmentBuilder(CFG, materials).build()
        CoffeeShopBuilder(CFG, materials).build()
        WeatherSystem(CFG, materials).build()
        LightingSystem(CFG, materials).build()
        CameraSystem(CFG).build()
        AnimationSystem(CFG).configure()

        exporter = ExportManager(CFG)
        exporter.generate_lods()
        exporter.configure_render()

        scene.frame_set(1)
        scene["generator_status"] = "COMPLETE"
        scene["unity_scale"] = 1.0
        scene["level_dimensions_m"] = (
            CFG.shop_width, CFG.shop_depth + CFG.street_depth, CFG.wall_height
        )

        if CFG.auto_export:
            export_for_unity()
        print("[CoffeeShop] Build complete. Scene is ready for lighting review and Unity import.")
    except Exception:
        print("[CoffeeShop] BUILD FAILED\n" + traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
