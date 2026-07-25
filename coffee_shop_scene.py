"""
Midcentury Storm Café — procedural Blender 5.2 scene generator.

Run from Blender:
    blender --background --python coffee_shop_scene.py

Or open Blender's Scripting workspace, load this file, and press Run Script.
The script builds the scene, saves coffee_shop_scene.blend beside this file,
and leaves frames 1-240 ready to render as an animation.

All geometry and textures are generated locally from deterministic procedural
rules. No external models, images, add-ons, or network access are required.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

import bpy
from mathutils import Vector


SEED = 27041962
FPS = 24
FRAME_START = 1
FRAME_END = 240
random.seed(SEED)


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (
        bpy.data.materials,
        bpy.data.curves,
        bpy.data.meshes,
        bpy.data.cameras,
        bpy.data.lights,
    ):
        # Only remove orphaned data; this also guarantees one camera.
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)


def collection(name: str, parent=None):
    coll = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    target = parent or bpy.context.scene.collection
    if coll.name not in target.children:
        target.children.link(coll)
    return coll


def move_to_collection(obj, coll):
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    coll.objects.link(obj)
    return obj


def set_input(node, names, value):
    for name in names:
        socket = node.inputs.get(name)
        if socket is not None:
            socket.default_value = value
            return socket
    return None


def add_bevel(obj, width=0.04, segments=3):
    mod = obj.modifiers.new("Soft manufactured edges", "BEVEL")
    mod.width = width
    mod.segments = segments
    return mod


def smooth(obj):
    if obj.type == "MESH":
        for poly in obj.data.polygons:
            poly.use_smooth = True
    return obj


def apply_transform(obj):
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.select_set(False)


def cube(name, loc, scale, mat=None, bevel=0.03, coll=None, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(location=loc, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    apply_transform(obj)
    if bevel:
        add_bevel(obj, bevel)
    if mat:
        obj.data.materials.append(mat)
    if coll:
        move_to_collection(obj, coll)
    return obj


def uv_sphere(name, loc, scale, mat=None, coll=None, segments=32, rings=20):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments, ring_count=rings, location=loc
    )
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    apply_transform(obj)
    smooth(obj)
    if mat:
        obj.data.materials.append(mat)
    if coll:
        move_to_collection(obj, coll)
    return obj


def cylinder(
    name,
    loc,
    radius,
    depth,
    mat=None,
    coll=None,
    vertices=32,
    rotation=(0, 0, 0),
    bevel=0.015,
):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices, radius=radius, depth=depth, location=loc, rotation=rotation
    )
    obj = bpy.context.object
    obj.name = name
    smooth(obj)
    if bevel:
        add_bevel(obj, bevel, 2)
    if mat:
        obj.data.materials.append(mat)
    if coll:
        move_to_collection(obj, coll)
    return obj


def cylinder_between(name, start, end, radius, mat=None, coll=None, vertices=20):
    start, end = Vector(start), Vector(end)
    delta = end - start
    obj = cylinder(
        name,
        (start + end) / 2,
        radius,
        delta.length,
        mat,
        coll,
        vertices,
        bevel=radius * 0.25,
    )
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = delta.to_track_quat("Z", "Y")
    return obj


def torus(name, loc, major, minor, mat=None, coll=None, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major,
        minor_radius=minor,
        major_segments=32,
        minor_segments=10,
        location=loc,
        rotation=rotation,
    )
    obj = bpy.context.object
    obj.name = name
    smooth(obj)
    if mat:
        obj.data.materials.append(mat)
    if coll:
        move_to_collection(obj, coll)
    return obj


def curve_object(name, points, bevel, mat, coll=None, cyclic=False):
    data = bpy.data.curves.new(name, "CURVE")
    data.dimensions = "3D"
    data.resolution_u = 2
    data.bevel_depth = bevel
    data.bevel_resolution = 3
    spline = data.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for bp, co in zip(spline.bezier_points, points):
        bp.co = co
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"
    spline.use_cyclic_u = cyclic
    obj = bpy.data.objects.new(name, data)
    (coll or bpy.context.collection).objects.link(obj)
    obj.data.materials.append(mat)
    return obj


def parent_keep_world(obj, parent):
    matrix = obj.matrix_world.copy()
    obj.parent = parent
    obj.matrix_world = matrix


def empty(name, loc, coll):
    loc = tuple(loc)
    if len(loc) == 2:
        loc = (*loc, 0.0)
    if len(loc) != 3:
        raise ValueError(f"{name} requires a 2D or 3D location, got {len(loc)} values")
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_type = "PLAIN_AXES"
    obj.empty_display_size = 0.12
    obj.location = loc
    coll.objects.link(obj)
    return obj


def look_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def key(obj, frame, data_path="rotation_euler"):
    obj.keyframe_insert(data_path=data_path, frame=frame)


# ---------------------------------------------------------------------------
# Procedural physically based materials
# ---------------------------------------------------------------------------


def material(name, color, roughness=0.45, metallic=0.0, transmission=0.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    set_input(bsdf, ("Base Color",), (*color, 1))
    set_input(bsdf, ("Roughness",), roughness)
    set_input(bsdf, ("Metallic",), metallic)
    set_input(bsdf, ("Transmission Weight", "Transmission"), transmission)
    return mat


def noise_material(
    name,
    color_a,
    color_b,
    scale=5.0,
    roughness=0.5,
    bump=0.15,
    detail=5.0,
    metallic=0.0,
):
    mat = material(name, color_a, roughness, metallic)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    tex = nodes.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value = scale
    tex.inputs["Detail"].default_value = detail
    tex.inputs["Roughness"].default_value = 0.65
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*color_a, 1)
    ramp.color_ramp.elements[1].color = (*color_b, 1)
    bump_node = nodes.new("ShaderNodeBump")
    bump_node.inputs["Strength"].default_value = bump
    bump_node.inputs["Distance"].default_value = 0.12
    links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(tex.outputs["Fac"], bump_node.inputs["Height"])
    links.new(bump_node.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def wood_material(name, dark=False):
    c1 = (0.12, 0.035, 0.012) if dark else (0.34, 0.105, 0.027)
    c2 = (0.035, 0.009, 0.003) if dark else (0.10, 0.022, 0.006)
    mat = material(name, c1, 0.3)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    tex = nodes.new("ShaderNodeTexNoise")
    tex.noise_dimensions = "3D"
    tex.inputs["Scale"].default_value = 3.0
    tex.inputs["Detail"].default_value = 4.5
    tex.inputs["Roughness"].default_value = 0.72
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (0.5, 7.0, 3.0)
    coord = nodes.new("ShaderNodeTexCoord")
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*c2, 1)
    ramp.color_ramp.elements[1].color = (*c1, 1)
    bump_node = nodes.new("ShaderNodeBump")
    bump_node.inputs["Strength"].default_value = 0.18
    bump_node.inputs["Distance"].default_value = 0.08
    links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
    links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(tex.outputs["Fac"], bump_node.inputs["Height"])
    links.new(bump_node.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def ceramic_material(name, color):
    mat = noise_material(name, color, tuple(min(1, x * 1.15) for x in color), 45, 0.2, 0.04, 2)
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    set_input(bsdf, ("Coat Weight", "Clearcoat"), 0.3)
    set_input(bsdf, ("Coat Roughness", "Clearcoat Roughness"), 0.12)
    return mat


def glass_material(name, tint=(0.75, 0.9, 1.0), roughness=0.08):
    mat = material(name, tint, roughness, 0.0, 1.0)
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    set_input(bsdf, ("IOR",), 1.45)
    set_input(bsdf, ("Alpha",), 0.28)
    mat.surface_render_method = "DITHERED"
    return mat


def emission_material(name, color, strength):
    mat = material(name, color, 0.2)
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    set_input(bsdf, ("Emission Color", "Emission"), (*color, 1))
    set_input(bsdf, ("Emission Strength",), strength)
    return mat


def fabric_material(name, color_a, color_b):
    mat = noise_material(name, color_a, color_b, 90, 0.75, 0.18, 3)
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    set_input(bsdf, ("Sheen Weight", "Sheen"), 0.25)
    return mat


def create_materials():
    return {
        "plaster": noise_material("Warm ivory plaster", (0.44, 0.34, 0.23), (0.72, 0.62, 0.44), 7, 0.82, 0.12),
        "teal": fabric_material("Deep teal upholstery", (0.018, 0.09, 0.085), (0.035, 0.18, 0.15)),
        "mustard": fabric_material("Mustard wool", (0.42, 0.19, 0.025), (0.75, 0.45, 0.07)),
        "rust": fabric_material("Rust velvet", (0.32, 0.055, 0.018), (0.62, 0.16, 0.045)),
        "walnut": wood_material("Oiled walnut"),
        "dark_wood": wood_material("Dark walnut", True),
        "floor": noise_material("Terrazzo floor", (0.18, 0.14, 0.10), (0.36, 0.29, 0.19), 38, 0.4, 0.25, 7),
        "brass": noise_material("Aged brushed brass", (0.34, 0.17, 0.025), (0.78, 0.49, 0.12), 16, 0.27, 0.08, 3, 0.8),
        "black": material("Soft black metal", (0.008, 0.009, 0.008), 0.25, 0.75),
        "glass": glass_material("Rainy window glass"),
        "case_glass": glass_material("Display case glass", (0.92, 0.98, 1.0), 0.025),
        "wet": noise_material("Wet asphalt", (0.007, 0.012, 0.018), (0.03, 0.045, 0.055), 5, 0.11, 0.16, 7),
        "white": ceramic_material("Speckled cream ceramic", (0.76, 0.69, 0.53)),
        "green_ceramic": ceramic_material("Sage ceramic", (0.15, 0.29, 0.17)),
        "coffee": material("Fresh espresso", (0.035, 0.009, 0.002), 0.08),
        "foam": noise_material("Microfoam", (0.74, 0.54, 0.31), (0.98, 0.88, 0.66), 18, 0.4, 0.06),
        "leaf": noise_material("Plant leaves", (0.012, 0.10, 0.025), (0.07, 0.30, 0.06), 4, 0.65, 0.1),
        "soil": noise_material("Potting soil", (0.035, 0.012, 0.004), (0.12, 0.045, 0.008), 20, 0.9, 0.3),
        "rain": glass_material("Rainwater", (0.32, 0.55, 0.72), 0.03),
        "warm_glow": emission_material("Warm practical glow", (1.0, 0.36, 0.09), 7),
        "sign_glow": emission_material("Cafe sign glow", (1.0, 0.55, 0.18), 3),
        "pastry": noise_material("Baked pastry", (0.34, 0.10, 0.015), (0.86, 0.48, 0.10), 9, 0.6, 0.25),
        "steel": noise_material("Brushed steel", (0.22, 0.24, 0.25), (0.55, 0.58, 0.59), 30, 0.2, 0.06, 2, 0.85),
        "paper": noise_material("Recycled paper", (0.56, 0.42, 0.25), (0.77, 0.64, 0.42), 20, 0.8, 0.08),
    }


# ---------------------------------------------------------------------------
# Architecture, windows, and exterior storm
# ---------------------------------------------------------------------------


def build_architecture(m, arch, storm):
    cube("Terrazzo floor", (0, 1.0, -0.12), (7.6, 8.5, 0.12), m["floor"], 0.02, arch)
    cube("Ceiling", (0, 1.0, 6.25), (7.6, 8.5, 0.10), m["plaster"], 0.01, arch)
    cube("Left wall", (-7.55, 1.0, 3.05), (0.1, 8.5, 3.2), m["plaster"], 0.02, arch)
    cube("Right wall", (7.55, 1.0, 3.05), (0.1, 8.5, 3.2), m["plaster"], 0.02, arch)

    # Back wall wraps around three broad windows.
    cube("Back wall header", (0, 8.15, 5.72), (7.6, 0.12, 0.55), m["plaster"], 0.02, arch)
    cube("Back wall sill", (0, 8.15, 0.45), (7.6, 0.12, 0.45), m["plaster"], 0.02, arch)
    for x in (-7.15, -2.35, 2.35, 7.15):
        cube("Window wall pier", (x, 8.15, 3.08), (0.42, 0.13, 2.2), m["plaster"], 0.02, arch)

    for i, x in enumerate((-4.75, 0, 4.75), 1):
        cube(f"Window glass {i}", (x, 8.08, 3.1), (1.94, 0.025, 2.2), m["glass"], 0.01, arch)
        for fx in (x - 2.03, x + 2.03):
            cube("Slim walnut window frame", (fx, 8.0, 3.1), (0.07, 0.08, 2.28), m["dark_wood"], 0.018, arch)
        cube("Window top frame", (x, 8.0, 5.35), (2.1, 0.08, 0.07), m["dark_wood"], 0.018, arch)
        cube("Window sill frame", (x, 8.0, 0.84), (2.1, 0.12, 0.09), m["dark_wood"], 0.018, arch)
        cube("Window mullion", (x, 8.0, 3.1), (0.045, 0.08, 2.2), m["dark_wood"], 0.012, arch)

    # Wet exterior: visible city silhouettes and reflected light.
    cube("Wet street", (0, 11.0, 0.0), (11.5, 3.0, 0.04), m["wet"], 0, storm)
    for i in range(13):
        x = -10.5 + i * 1.8 + random.uniform(-0.3, 0.3)
        h = random.uniform(2.2, 7.5)
        cube(
            f"Exterior building {i:02d}",
            (x, 14.5 + random.uniform(-0.8, 1.2), h / 2),
            (random.uniform(0.55, 1.1), 0.8, h / 2),
            m["black"],
            0.02,
            storm,
        )
    # Distant bokeh lights and reflections.
    for i in range(22):
        x = random.uniform(-9, 9)
        y = random.uniform(11.2, 14.0)
        z = random.uniform(0.4, 4.6)
        color = (1.0, random.uniform(0.08, 0.35), 0.015) if i % 3 else (0.08, 0.25, 1.0)
        glow = emission_material(f"Exterior bokeh {i:02d}", color, random.uniform(3, 12))
        uv_sphere(f"Defocused city light {i:02d}", (x, y, z), (0.06, 0.035, 0.06), glow, storm, 16, 10)
        cube(
            f"Wet reflection {i:02d}",
            (x, y - 0.1, 0.055),
            (0.025, random.uniform(0.15, 0.65), 0.008),
            glow,
            0.01,
            storm,
        )

    # Rain curtains, animated in four staggered layers.
    for i in range(160):
        x = random.uniform(-10.5, 10.5)
        y = random.uniform(8.7, 13.7)
        z = random.uniform(0.3, 8.2)
        length = random.uniform(0.18, 0.62)
        drop = cylinder(
            f"Rain streak {i:03d}",
            (x, y, z),
            random.uniform(0.004, 0.012),
            length,
            m["rain"],
            storm,
            8,
            rotation=(math.radians(-8), 0, 0),
            bevel=0,
        )
        start = 1 + (i % 4) * 17
        drop.location.z += 2.0
        key(drop, start, "location")
        drop.location.z -= 7.8
        drop.location.y -= 0.65
        key(drop, start + 48, "location")
        drop.location.z += 7.8
        drop.location.y += 0.65
        key(drop, start + 49, "location")
        drop.location.z -= 7.8
        drop.location.y -= 0.65
        key(drop, start + 97, "location")
        drop.location.z += 7.8
        drop.location.y += 0.65
        key(drop, start + 98, "location")
        drop.location.z -= 7.8
        drop.location.y -= 0.65
        key(drop, start + 146, "location")
        drop.location.z += 7.8
        drop.location.y += 0.65
        key(drop, start + 147, "location")
        drop.location.z -= 7.8
        drop.location.y -= 0.65
        key(drop, min(start + 195, FRAME_END), "location")

    # Beads on the glass provide close, sharp rain detail.
    for i in range(90):
        x = random.choice((-4.75, 0, 4.75)) + random.uniform(-1.8, 1.8)
        z = random.uniform(1.0, 5.15)
        bead = uv_sphere(
            f"Window rain bead {i:02d}",
            (x, 7.91, z),
            (random.uniform(0.009, 0.025), 0.008, random.uniform(0.025, 0.09)),
            m["rain"],
            storm,
            12,
            8,
        )
        bead.rotation_euler.x = random.uniform(-0.2, 0.2)


# ---------------------------------------------------------------------------
# Furniture and café props
# ---------------------------------------------------------------------------


def make_chair(name, loc, angle, upholstery, m, coll):
    root = empty(name, (loc[0], loc[1], 0), coll)
    seat = cube(f"{name} seat", (loc[0], loc[1], 1.03), (0.48, 0.47, 0.09), upholstery, 0.09, coll)
    back = cube(f"{name} curved back", (loc[0], loc[1] + 0.43, 1.52), (0.50, 0.08, 0.47), upholstery, 0.12, coll, (math.radians(-8), 0, 0))
    for obj in (seat, back):
        parent_keep_world(obj, root)
    for dx in (-0.38, 0.38):
        for dy in (-0.36, 0.36):
            leg = cylinder_between(
                f"{name} tapered leg",
                (loc[0] + dx, loc[1] + dy, 0.95),
                (loc[0] + dx * 1.10, loc[1] + dy * 1.10, 0.08),
                0.035,
                m["brass"],
                coll,
                12,
            )
            parent_keep_world(leg, root)
    root.rotation_euler.z = angle
    return root


def coffee_cup(name, loc, color_mat, m, coll, scale=1.0):
    root = empty(name, loc, coll)
    cup = cylinder(name + " ceramic body", loc, 0.115 * scale, 0.18 * scale, color_mat, coll, 32, bevel=0.02)
    rim = torus(name + " rim", (loc[0], loc[1], loc[2] + 0.09 * scale), 0.105 * scale, 0.012 * scale, color_mat, coll)
    coffee = cylinder(name + " coffee surface", (loc[0], loc[1], loc[2] + 0.092 * scale), 0.095 * scale, 0.007, m["coffee"], coll, 32, bevel=0)
    handle = torus(
        name + " handle",
        (loc[0] + 0.115 * scale, loc[1], loc[2]),
        0.065 * scale,
        0.018 * scale,
        color_mat,
        coll,
        (math.radians(90), 0, 0),
    )
    for obj in (cup, rim, coffee, handle):
        parent_keep_world(obj, root)
    return root


def table_setting(name, loc, m, coll, seats=2, angle=0.0):
    x, y = loc
    root = empty(name, (x, y, 0), coll)
    top = cylinder(name + " walnut top", (x, y, 1.40), 0.86, 0.09, m["walnut"], coll, 48, bevel=0.045)
    stem = cylinder(name + " brass pedestal", (x, y, 0.72), 0.075, 1.32, m["brass"], coll, 24)
    foot = cylinder(name + " pedestal foot", (x, y, 0.09), 0.44, 0.06, m["brass"], coll, 32)
    for obj in (top, stem, foot):
        parent_keep_world(obj, root)
    coffee_cup(name + " cup A", (x - 0.27, y - 0.08, 1.55), m["white"], m, coll, 0.82)
    coffee_cup(name + " cup B", (x + 0.26, y + 0.12, 1.55), m["green_ceramic"], m, coll, 0.82)
    cylinder(name + " saucer A", (x - 0.27, y - 0.08, 1.505), 0.15, 0.018, m["white"], coll, 32)
    cylinder(name + " saucer B", (x + 0.26, y + 0.12, 1.505), 0.15, 0.018, m["green_ceramic"], coll, 32)
    cube(name + " menu", (x + 0.04, y - 0.22, 1.51), (0.12, 0.18, 0.012), m["paper"], 0.01, coll, (0, 0, 0.22))
    if seats:
        make_chair(name + " chair near", (x, y - 1.20), 0, m["rust"], m, coll)
        make_chair(name + " chair far", (x, y + 1.20), math.pi, m["teal"], m, coll)
    return root


def build_counter(m, props):
    # Right-side counter keeps the seating area readable.
    cube("Counter walnut body", (5.25, 2.35, 0.83), (1.55, 2.8, 0.83), m["dark_wood"], 0.08, props)
    cube("Counter fluted front", (3.66, 2.35, 0.88), (0.07, 2.75, 0.78), m["walnut"], 0.025, props)
    for y in [i * 0.26 - 0.1 for i in range(20)]:
        cube("Counter vertical flute", (3.57, y, 0.87), (0.035, 0.055, 0.72), m["brass"], 0.018, props)
    cube("Counter stone top", (5.18, 2.35, 1.72), (1.66, 2.92, 0.10), m["white"], 0.07, props)

    # Espresso machine, grinder, cups, and small details.
    cube("Espresso machine", (5.35, 2.65, 2.12), (0.73, 0.48, 0.38), m["steel"], 0.12, props)
    cube("Espresso machine black panel", (4.60, 2.65, 2.13), (0.02, 0.37, 0.24), m["black"], 0.02, props)
    for y in (2.43, 2.84):
        cylinder("Portafilter group", (4.54, y, 2.1), 0.10, 0.10, m["brass"], props, 24, (0, math.pi / 2, 0))
        cylinder_between("Portafilter handle", (4.50, y, 2.04), (4.10, y + 0.15, 1.97), 0.035, m["black"], props)
    cylinder("Coffee grinder base", (5.65, 1.30, 1.87), 0.25, 0.20, m["black"], props)
    cylinder("Coffee grinder body", (5.65, 1.30, 2.18), 0.19, 0.45, m["steel"], props)
    cylinder("Bean hopper", (5.65, 1.30, 2.63), 0.29, 0.48, m["case_glass"], props)
    for i in range(8):
        coffee_cup(f"Stacked cup {i}", (6.08, 3.75, 1.87 + i * 0.055), m["white"], m, props, 0.65)

    # Glass pastry display.
    cube("Pastry case base", (4.15, -0.2, 1.89), (0.50, 0.75, 0.08), m["brass"], 0.03, props)
    for x in (3.68, 4.62):
        for y in (-0.88, 0.48):
            cube("Pastry case post", (x, y, 2.36), (0.025, 0.025, 0.46), m["brass"], 0.01, props)
    cube("Pastry case front", (3.66, -0.2, 2.35), (0.02, 0.72, 0.42), m["case_glass"], 0.01, props)
    cube("Pastry case top", (4.15, -0.2, 2.82), (0.50, 0.75, 0.025), m["case_glass"], 0.01, props)
    for i in range(8):
        x = 3.88 + (i % 2) * 0.47
        y = -0.72 + (i // 2) * 0.33
        torus(f"Croissant {i}", (x, y, 2.04), 0.12, 0.05, m["pastry"], props, (math.pi / 2, 0, 0))


def build_decor(m, props):
    # Long banquette at the back.
    cube("Banquette base", (-3.7, 6.55, 0.62), (3.05, 0.62, 0.62), m["dark_wood"], 0.10, props)
    cube("Banquette seat", (-3.7, 6.28, 1.18), (3.1, 0.74, 0.17), m["teal"], 0.16, props)
    cube("Banquette back", (-3.7, 6.86, 2.05), (3.1, 0.18, 0.76), m["teal"], 0.18, props, (math.radians(-4), 0, 0))
    for i in range(6):
        cube(f"Banquette channel {i}", (-6.20 + i, 6.66, 2.03), (0.015, 0.04, 0.60), m["mustard"], 0.008, props)

    # Floating shelves and café objects.
    for z in (3.55, 4.55):
        cube("Walnut display shelf", (5.85, 6.95, z), (1.05, 0.25, 0.06), m["walnut"], 0.04, props)
    for i in range(10):
        x = 5.05 + (i % 5) * 0.4
        z = 3.75 + (i // 5) * 1.0
        coffee_cup(f"Shelf cup {i}", (x, 6.84, z), m["white"] if i % 2 else m["green_ceramic"], m, props, 0.6)

    # Midcentury abstract wall art.
    cube("Art frame", (-6.95, 1.75, 3.55), (0.08, 1.12, 1.12), m["dark_wood"], 0.02, props)
    cube("Art ground", (-6.85, 1.75, 3.55), (0.025, 1.02, 1.02), m["paper"], 0.005, props)
    for i, (y, z, sy, sz, mat) in enumerate(
        [
            (1.35, 3.75, 0.38, 0.58, m["rust"]),
            (2.05, 3.28, 0.45, 0.28, m["teal"]),
            (1.95, 4.10, 0.18, 0.35, m["mustard"]),
        ]
    ):
        uv_sphere(f"Abstract art shape {i}", (-6.80, y, z), (0.02, sy, sz), mat, props, 24, 16)

    # Plants with individual stems and leaves.
    for p, (x, y, size) in enumerate(((-6.35, 5.6, 1.15), (6.45, 6.35, 0.9), (-6.55, -2.7, 0.85))):
        cylinder(f"Plant pot {p}", (x, y, 0.48 * size), 0.36 * size, 0.75 * size, m["green_ceramic"], props, 32)
        cylinder(f"Plant soil {p}", (x, y, 0.86 * size), 0.31 * size, 0.03, m["soil"], props, 24, bevel=0)
        for j in range(12):
            a = (j / 12) * math.tau + random.uniform(-0.25, 0.25)
            tip = (
                x + math.cos(a) * random.uniform(0.28, 0.65) * size,
                y + math.sin(a) * random.uniform(0.20, 0.52) * size,
                0.82 * size + random.uniform(0.65, 1.42) * size,
            )
            curve_object(f"Plant stem {p}-{j}", [(x, y, 0.84 * size), tip], 0.012 * size, m["leaf"], props)
            leaf = uv_sphere(
                f"Plant leaf {p}-{j}",
                tip,
                (0.10 * size, 0.28 * size, 0.045 * size),
                m["leaf"],
                props,
                20,
                12,
            )
            leaf.rotation_euler = (random.uniform(-0.5, 0.5), random.uniform(-0.5, 0.5), a)

    # Rug and low lounge table in foreground.
    cube("Geometric rug", (-2.75, -2.1, 0.025), (2.45, 1.55, 0.025), m["mustard"], 0.12, props)
    for x in (-4.25, -2.75, -1.25):
        cube("Rug teal stripe", (x, -2.1, 0.056), (0.34, 1.43, 0.008), m["teal"], 0.04, props, (0, 0, 0.12))


# ---------------------------------------------------------------------------
# Stylized-realistic animated patrons
# ---------------------------------------------------------------------------


SKIN_TONES = [
    ((0.42, 0.19, 0.09), (0.24, 0.07, 0.025)),
    ((0.72, 0.42, 0.24), (0.46, 0.20, 0.09)),
    ((0.86, 0.61, 0.39), (0.62, 0.34, 0.18)),
    ((0.56, 0.30, 0.18), (0.35, 0.13, 0.055)),
    ((0.91, 0.69, 0.50), (0.69, 0.42, 0.26)),
]


def person_materials(index):
    skin_a, skin_b = SKIN_TONES[index % len(SKIN_TONES)]
    skin = noise_material(f"Skin {index}", skin_a, skin_b, 18, 0.46, 0.08, 4)
    bsdf = skin.node_tree.nodes["Principled BSDF"]
    set_input(bsdf, ("Subsurface Weight", "Subsurface"), 0.09)
    set_input(bsdf, ("Subsurface Scale", "Subsurface Radius"), 0.12)
    hair_colors = [(0.012, 0.004, 0.002), (0.09, 0.025, 0.008), (0.25, 0.10, 0.025), (0.035, 0.018, 0.012)]
    hair = noise_material(f"Hair {index}", hair_colors[index % 4], (0.005, 0.002, 0.001), 65, 0.55, 0.2, 3)
    return skin, hair


def make_person(
    index,
    loc,
    facing,
    shirt_mat,
    trouser_mat,
    m,
    people,
    action="talk",
    phase=0,
):
    x, y = loc
    root = empty(f"Patron {index:02d} root", (x, y, 0), people)
    skin, hair = person_materials(index)

    # Seated proportions, each slightly varied.
    h = random.uniform(0.94, 1.07)
    torso_z = 1.88
    torso = uv_sphere(
        f"Patron {index:02d} torso",
        (x, y, torso_z),
        (0.34 * h, 0.23 * h, 0.54 * h),
        shirt_mat,
        people,
        32,
        20,
    )
    torso.rotation_euler.x = math.radians(-4)
    neck = cylinder(f"Patron {index:02d} neck", (x, y, 2.40), 0.095, 0.18, skin, people, 20)

    head_pivot = empty(f"Patron {index:02d} head control", (x, y, 2.66), people)
    head = uv_sphere(
        f"Patron {index:02d} head",
        (x, y, 2.68),
        (0.235 * h, 0.205 * h, 0.29 * h),
        skin,
        people,
        32,
        24,
    )
    hair_cap = uv_sphere(
        f"Patron {index:02d} hair",
        (x, y + 0.006, 2.84),
        (0.243 * h, 0.215 * h, 0.17 * h),
        hair,
        people,
        32,
        18,
    )
    # Nose, ears, eyes, brows and mouth make faces read in the wide shot.
    nose = uv_sphere(f"Patron {index:02d} nose", (x, y - 0.195, 2.69), (0.035, 0.055, 0.052), skin, people, 16, 10)
    for side in (-1, 1):
        eye = uv_sphere(
            f"Patron {index:02d} eye {side}",
            (x + side * 0.075, y - 0.190, 2.75),
            (0.024, 0.012, 0.014),
            m["black"],
            people,
            12,
            8,
        )
        brow = curve_object(
            f"Patron {index:02d} brow {side}",
            [(x + side * 0.12, y - 0.198, 2.80), (x + side * 0.035, y - 0.205, 2.81)],
            0.008,
            hair,
            people,
        )
        ear = uv_sphere(
            f"Patron {index:02d} ear {side}",
            (x + side * 0.226, y, 2.70),
            (0.035, 0.025, 0.06),
            skin,
            people,
            14,
            10,
        )
        for part in (eye, brow, ear):
            parent_keep_world(part, head_pivot)
    lips = curve_object(
        f"Patron {index:02d} mouth",
        [(x - 0.055, y - 0.208, 2.60), (x, y - 0.218, 2.585), (x + 0.055, y - 0.208, 2.60)],
        0.009,
        m["rust"],
        people,
    )
    for part in (head, hair_cap, nose, lips):
        parent_keep_world(part, head_pivot)

    # Seated legs, angled naturally under chair.
    hip_l, hip_r = (x - 0.17, y, 1.65), (x + 0.17, y, 1.65)
    knee_l, knee_r = (x - 0.20, y - 0.42, 1.02), (x + 0.20, y - 0.38, 1.03)
    ankle_l, ankle_r = (x - 0.23, y - 0.55, 0.22), (x + 0.24, y - 0.48, 0.22)
    for side, hip, knee, ankle in (("L", hip_l, knee_l, ankle_l), ("R", hip_r, knee_r, ankle_r)):
        cylinder_between(f"Patron {index:02d} {side} thigh", hip, knee, 0.12, trouser_mat, people)
        cylinder_between(f"Patron {index:02d} {side} shin", knee, ankle, 0.10, trouser_mat, people)
        shoe = uv_sphere(
            f"Patron {index:02d} {side} shoe",
            (ankle[0], ankle[1] - 0.11, ankle[2] - 0.02),
            (0.13, 0.24, 0.09),
            m["black"],
            people,
            20,
            12,
        )
        shoe.rotation_euler.z = random.uniform(-0.1, 0.1)

    # Shoulder controls rotate complete arm gestures.
    shoulder_l = empty(f"Patron {index:02d} left arm control", (x - 0.30, y - 0.01, 2.18), people)
    shoulder_r = empty(f"Patron {index:02d} right arm control", (x + 0.30, y - 0.01, 2.18), people)
    elbow_l = (x - 0.43, y - 0.28, 1.82)
    elbow_r = (x + 0.43, y - 0.28, 1.84)
    hand_l = (x - 0.28, y - 0.62, 1.61)
    hand_r = (x + 0.27, y - 0.62, 1.62)
    arm_parts = []
    for side, shoulder, elbow, hand, control in (
        ("L", tuple(shoulder_l.location), elbow_l, hand_l, shoulder_l),
        ("R", tuple(shoulder_r.location), elbow_r, hand_r, shoulder_r),
    ):
        upper = cylinder_between(f"Patron {index:02d} {side} upper arm", shoulder, elbow, 0.09, shirt_mat, people)
        fore = cylinder_between(f"Patron {index:02d} {side} forearm", elbow, hand, 0.073, skin, people)
        palm = uv_sphere(f"Patron {index:02d} {side} hand", hand, (0.075, 0.065, 0.095), skin, people, 18, 12)
        for part in (upper, fore, palm):
            parent_keep_world(part, control)
            arm_parts.append(part)

    if action == "sip":
        held_cup = coffee_cup(
            f"Patron {index:02d} held cup",
            (hand_r[0], hand_r[1] - 0.035, hand_r[2] + 0.11),
            m["white"] if index % 2 else m["green_ceramic"],
            m,
            people,
            0.58,
        )
        parent_keep_world(held_cup, shoulder_r)

    for part in (torso, neck, head_pivot, shoulder_l, shoulder_r):
        parent_keep_world(part, root)

    # Natural conversation loops: head listening, speech gestures, and sipping.
    root.rotation_euler.z = facing
    head_pivot.rotation_mode = "XYZ"
    shoulder_l.rotation_mode = "XYZ"
    shoulder_r.rotation_mode = "XYZ"
    frames = [1, 38, 76, 114, 152, 190, 228, 240]
    for n, frame in enumerate(frames):
        wave = math.sin((n + phase) * 1.7)
        head_pivot.rotation_euler = (
            math.radians(1.5 * math.sin(n + phase)),
            math.radians(3.0 * wave),
            math.radians(4.0 * math.sin(n * 0.7 + phase)),
        )
        key(head_pivot, frame)
        root.location.z = 0.015 * math.sin(n * 1.4 + phase)
        key(root, frame, "location")
        if action == "talk":
            shoulder_l.rotation_euler = (
                math.radians(-8 - 12 * max(0, wave)),
                math.radians(4 * wave),
                math.radians(-10 * wave),
            )
            shoulder_r.rotation_euler = (
                math.radians(-10 - 18 * max(0, -wave)),
                math.radians(-3 * wave),
                math.radians(14 * wave),
            )
        else:
            # Twice per shot, arm rises toward the mouth then returns.
            sip = max(0.0, math.sin((n + phase) * math.pi / 2))
            shoulder_r.rotation_euler = (
                math.radians(-62 * sip),
                math.radians(8 * sip),
                math.radians(12 * sip),
            )
            shoulder_l.rotation_euler = (math.radians(-7), 0, math.radians(4 * wave))
        key(shoulder_l, frame)
        key(shoulder_r, frame)

    # Turn complete person toward table after modeling in camera-facing local pose.
    return root


def build_people_and_tables(m, props, people):
    navy = fabric_material("Navy shirt", (0.012, 0.025, 0.075), (0.03, 0.08, 0.18))
    cream = fabric_material("Cream knit", (0.53, 0.43, 0.29), (0.83, 0.73, 0.55))
    coral = fabric_material("Coral blouse", (0.52, 0.075, 0.045), (0.82, 0.20, 0.10))
    olive = fabric_material("Olive overshirt", (0.09, 0.12, 0.025), (0.24, 0.29, 0.07))
    denim = fabric_material("Dark denim", (0.018, 0.035, 0.075), (0.04, 0.09, 0.16))
    charcoal = fabric_material("Charcoal trousers", (0.025, 0.025, 0.022), (0.08, 0.07, 0.06))

    table_setting("Foreground conversation table", (-0.35, -0.55), m, props)
    table_setting("Window conversation table", (-3.75, 4.75), m, props, seats=0)
    table_setting("Side conversation table", (2.25, 4.35), m, props)

    # Foreground pair.
    make_chair("Foreground left chair", (-1.42, -0.52), math.radians(-88), m["rust"], m, props)
    make_chair("Foreground right chair", (0.72, -0.50), math.radians(88), m["teal"], m, props)
    make_person(0, (-1.42, -0.52), math.radians(-88), coral, denim, m, people, "talk", 0)
    make_person(1, (0.72, -0.50), math.radians(88), cream, charcoal, m, people, "sip", 1)

    # Window banquette pair, positioned diagonally to read in silhouette.
    make_chair("Window chair", (-2.72, 4.76), math.radians(88), m["mustard"], m, props)
    make_person(2, (-4.55, 5.76), math.radians(-20), olive, charcoal, m, people, "sip", 2)
    make_person(3, (-2.72, 4.76), math.radians(120), navy, denim, m, people, "talk", 3)

    # Side pair.
    make_person(4, (2.25, 3.15), 0, cream, denim, m, people, "talk", 4)
    make_person(5, (2.25, 5.55), math.pi, coral, charcoal, m, people, "sip", 5)


# ---------------------------------------------------------------------------
# Lighting, camera, compositor, and render setup
# ---------------------------------------------------------------------------


def area_light(name, loc, energy, color, size, target, coll):
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.color = color
    data.shape = "DISK"
    data.size = size
    obj = bpy.data.objects.new(name, data)
    coll.objects.link(obj)
    obj.location = loc
    look_at(obj, target)
    return obj


def point_light(name, loc, energy, color, radius, coll):
    data = bpy.data.lights.new(name, "POINT")
    data.energy = energy
    data.color = color
    data.shadow_soft_size = radius
    obj = bpy.data.objects.new(name, data)
    coll.objects.link(obj)
    obj.location = loc
    return obj


def build_lighting(m, lights, props):
    # Pendant fixtures are visible practicals with matching soft area lights.
    for i, (x, y) in enumerate(((-3.5, -0.8), (0, 0.6), (3.3, 1.0), (-2.4, 4.4), (2.6, 4.7))):
        cylinder(f"Pendant cord {i}", (x, y, 5.55), 0.012, 1.25, m["black"], props, 10, bevel=0)
        bpy.ops.mesh.primitive_cone_add(
            vertices=48,
            radius1=0.48,
            radius2=0.12,
            depth=0.40,
            location=(x, y, 4.82),
        )
        shade = bpy.context.object
        shade.name = f"Brass pendant shade {i}"
        shade.data.materials.append(m["brass"])
        move_to_collection(shade, props)
        uv_sphere(f"Pendant glowing bulb {i}", (x, y, 4.65), (0.12, 0.12, 0.15), m["warm_glow"], props, 24, 16)
        point_light(f"Pendant warm light {i}", (x, y, 4.55), 520, (1.0, 0.42, 0.16), 0.55, lights)

    area_light("Warm room key", (-3.5, -3.0, 5.3), 900, (1.0, 0.48, 0.20), 4.0, (0, 1.5, 1.4), lights)
    area_light("Counter softbox", (5.0, 3.0, 5.6), 650, (1.0, 0.58, 0.28), 2.2, (4.4, 2.5, 1.4), lights)
    area_light("Storm window fill", (0, 9.0, 4.7), 1100, (0.16, 0.32, 0.62), 7.0, (0, 2.0, 2.0), lights)
    area_light("Left warm rim", (-6.8, 1.0, 3.2), 450, (1.0, 0.28, 0.10), 2.0, (-1, 1, 1.8), lights)

    # Brief exterior lightning pulse, still motivated from outside.
    lightning = area_light("Animated distant lightning", (0, 11.0, 6.0), 20, (0.45, 0.62, 1.0), 6.0, (0, 2, 2), lights)
    for frame, energy in ((1, 20), (92, 20), (96, 2600), (98, 120), (101, 1700), (104, 20), (240, 20)):
        lightning.data.energy = energy
        lightning.data.keyframe_insert("energy", frame=frame)


def configure_camera(cameras):
    data = bpy.data.cameras.new("Hero camera")
    camera = bpy.data.objects.new("Hero camera", data)
    cameras.objects.link(camera)
    camera.location = (0.15, -14.9, 4.25)
    data.lens = 30
    data.sensor_width = 36
    data.dof.use_dof = True
    data.dof.focus_distance = 15.0
    data.dof.aperture_fstop = 5.6
    data.dof.aperture_blades = 8
    look_at(camera, (0.0, 1.85, 2.25))
    bpy.context.scene.camera = camera
    return camera


def configure_world_and_render():
    scene = bpy.context.scene
    scene.frame_start = FRAME_START
    scene.frame_end = FRAME_END
    scene.render.fps = FPS
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.filepath = str(Path("//renders/coffee_shop_"))
    scene.render.film_transparent = False

    # Use AgX for broad highlight latitude and a cinematic warm grade.
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = 0.15

    world = bpy.data.worlds.new("Storm world") if not bpy.data.worlds else bpy.data.worlds[0]
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.006, 0.012, 0.025, 1)
    bg.inputs["Strength"].default_value = 0.16

    scene.use_nodes = True
    nodes, links = scene.node_tree.nodes, scene.node_tree.links
    nodes.clear()
    render = nodes.new("CompositorNodeRLayers")
    glare = nodes.new("CompositorNodeGlare")
    glare.glare_type = "FOG_GLOW"
    glare.quality = "HIGH"
    glare.threshold = 1.1
    glare.size = 6
    lens = nodes.new("CompositorNodeLensdist")
    lens.inputs["Distortion"].default_value = 0.012
    lens.inputs["Dispersion"].default_value = 0.004
    comp = nodes.new("CompositorNodeComposite")
    links.new(render.outputs["Image"], glare.inputs["Image"])
    links.new(glare.outputs["Image"], lens.inputs["Image"])
    links.new(lens.outputs["Image"], comp.inputs["Image"])


def organize_scene():
    # Hide controls in renders while retaining a clean Outliner hierarchy.
    for obj in bpy.data.objects:
        if obj.type == "EMPTY":
            obj.hide_render = True


def main():
    clear_scene()
    scene_root = collection("MIDCENTURY STORM CAFE")
    arch = collection("01 Architecture", scene_root)
    props = collection("02 Furniture and props", scene_root)
    people = collection("03 Animated patrons", scene_root)
    storm = collection("04 Exterior storm", scene_root)
    lights = collection("05 Lighting", scene_root)
    cameras = collection("06 Camera - exactly one", scene_root)

    mats = create_materials()
    build_architecture(mats, arch, storm)
    build_counter(mats, props)
    build_decor(mats, props)
    build_people_and_tables(mats, props, people)
    build_lighting(mats, lights, props)
    configure_camera(cameras)
    configure_world_and_render()
    organize_scene()

    scene = bpy.context.scene
    scene.frame_set(FRAME_START)
    scene["scene_description"] = (
        "Procedurally generated midcentury coffee shop with six animated patrons, "
        "warm interior practicals, storm rain, wet reflections, and one hero camera."
    )
    scene["render_note"] = (
        "EEVEE Next is selected for practical animation rendering. For maximum realism, "
        "switch to Cycles, GPU compute, 256 samples, and enable denoising."
    )
    output = Path(bpy.path.abspath("//coffee_shop_scene.blend"))
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    print(f"\nMidcentury Storm Cafe generated successfully: {output}")
    print(f"Objects: {len(bpy.data.objects)} | Materials: {len(bpy.data.materials)}")
    print(f"Animation: frames {FRAME_START}-{FRAME_END} at {FPS} fps")
    print(f"Cameras: {len(bpy.data.cameras)} (required: exactly 1)")


if __name__ == "__main__":
    main()
