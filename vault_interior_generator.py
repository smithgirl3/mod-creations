"""
Retro-futuristic underground vault interior generator for Blender 5.2.

Paste this complete file into Blender's Text Editor and choose Run Script.
The scene is rebuilt from scratch and contains two ready-to-render cameras:
CAM_Atrium and CAM_Corridor.
"""

import bpy
import math
from mathutils import Vector


# ---------------------------------------------------------------------------
# Scene reset and collection helpers
# ---------------------------------------------------------------------------

for datablocks in (
    bpy.data.objects,
    bpy.data.meshes,
    bpy.data.curves,
    bpy.data.materials,
    bpy.data.cameras,
    bpy.data.lights,
):
    # Objects are removed first; orphaned generated data is then safe to remove.
    if datablocks == bpy.data.objects:
        for block in list(datablocks):
            datablocks.remove(block, do_unlink=True)

for collection in list(bpy.data.collections):
    if collection.name != "Collection":
        bpy.data.collections.remove(collection)

root = bpy.context.scene.collection
default_collection = bpy.data.collections.get("Collection")
if default_collection:
    default_collection.name = "Vault_Structure"
else:
    default_collection = bpy.data.collections.new("Vault_Structure")
    root.children.link(default_collection)

COLLECTIONS = {"structure": default_collection}
for key, name in (
    ("props", "Vault_Props"),
    ("lighting", "Vault_Lighting"),
    ("decals", "Vault_Signs_Decals"),
    ("cameras", "Vault_Cameras"),
):
    collection = bpy.data.collections.new(name)
    root.children.link(collection)
    COLLECTIONS[key] = collection


def move_to_collection(obj, key):
    """Move an operator-created object into one named scene collection."""
    target = COLLECTIONS[key]
    for collection in list(obj.users_collection):
        collection.objects.unlink(obj)
    target.objects.link(obj)
    return obj


def smooth_object(obj):
    if obj.type == "MESH":
        for polygon in obj.data.polygons:
            polygon.use_smooth = True


def add_bevel(obj, width=0.06, segments=3):
    modifier = obj.modifiers.new("Soft industrial edges", "BEVEL")
    modifier.width = width
    modifier.segments = segments
    modifier.limit_method = "ANGLE"
    return obj


# ---------------------------------------------------------------------------
# Procedural materials: painted metal, steel, concrete, rubber, and emissives
# ---------------------------------------------------------------------------

def principled_input(shader, name):
    socket = shader.inputs.get(name)
    if socket is None:
        raise RuntimeError(f"Blender shader input '{name}' is unavailable")
    return socket


def make_worn_material(name, base_color, metallic, roughness, dirt_color,
                       noise_scale=5.0, wear_strength=0.22):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    noise = nodes.new("ShaderNodeTexNoise")
    ramp = nodes.new("ShaderNodeValToRGB")
    bump = nodes.new("ShaderNodeBump")
    texcoord = nodes.new("ShaderNodeTexCoord")

    noise.inputs["Scale"].default_value = noise_scale
    noise.inputs["Detail"].default_value = 6.0
    noise.inputs["Roughness"].default_value = 0.72
    ramp.color_ramp.elements[0].position = 0.30
    ramp.color_ramp.elements[0].color = (*dirt_color, 1.0)
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = (*base_color, 1.0)
    principled_input(shader, "Metallic").default_value = metallic
    principled_input(shader, "Roughness").default_value = roughness
    bump.inputs["Strength"].default_value = wear_strength
    bump.inputs["Distance"].default_value = 0.08

    links.new(texcoord.outputs["Generated"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], principled_input(shader, "Base Color"))
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], principled_input(shader, "Normal"))
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    return material


def make_emissive(name, color, strength=8.0):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    shader = material.node_tree.nodes.get("Principled BSDF")
    principled_input(shader, "Base Color").default_value = (*color, 1.0)
    principled_input(shader, "Roughness").default_value = 0.28
    principled_input(shader, "Emission Color").default_value = (*color, 1.0)
    principled_input(shader, "Emission Strength").default_value = strength
    return material


MAT = {
    "blue": make_worn_material(
        "Vault Blue - Worn Paint", (0.035, 0.18, 0.31), 0.72, 0.33,
        (0.012, 0.022, 0.028), 7.5, 0.18
    ),
    "yellow": make_worn_material(
        "Muted Safety Yellow", (0.56, 0.40, 0.075), 0.48, 0.38,
        (0.10, 0.045, 0.015), 8.5, 0.28
    ),
    "white": make_worn_material(
        "Aged Off White", (0.55, 0.57, 0.52), 0.32, 0.48,
        (0.12, 0.13, 0.12), 6.0, 0.16
    ),
    "steel": make_worn_material(
        "Bare Steel Edge Wear", (0.20, 0.23, 0.24), 0.92, 0.27,
        (0.035, 0.027, 0.020), 13.0, 0.34
    ),
    "dark": make_worn_material(
        "Dark Structural Metal", (0.045, 0.055, 0.058), 0.82, 0.42,
        (0.012, 0.013, 0.012), 9.0, 0.25
    ),
    "concrete": make_worn_material(
        "Stained Concrete", (0.19, 0.20, 0.19), 0.05, 0.78,
        (0.055, 0.050, 0.043), 4.2, 0.42
    ),
    "rust": make_worn_material(
        "Oxidized Metal", (0.25, 0.075, 0.025), 0.58, 0.65,
        (0.055, 0.022, 0.009), 10.0, 0.38
    ),
    "rubber": make_worn_material(
        "Aged Rubber", (0.018, 0.022, 0.021), 0.0, 0.72,
        (0.004, 0.005, 0.004), 16.0, 0.18
    ),
    "fabric": make_worn_material(
        "Faded Bedding", (0.13, 0.21, 0.23), 0.0, 0.88,
        (0.035, 0.045, 0.042), 22.0, 0.16
    ),
    "screen_green": make_emissive("CRT Green Emission", (0.08, 0.72, 0.32), 6.0),
    "screen_amber": make_emissive("Amber Indicator Emission", (1.0, 0.28, 0.025), 9.0),
    "light": make_emissive("Cold Fluorescent Emission", (0.56, 0.86, 1.0), 12.0),
}


# ---------------------------------------------------------------------------
# Reusable procedural geometry primitives
# ---------------------------------------------------------------------------

def assign_material(obj, material):
    obj.data.materials.append(material)
    return obj


def box(name, location, scale, material, collection="structure", bevel=0.04):
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = (scale[0] / 2, scale[1] / 2, scale[2] / 2)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    assign_material(obj, material)
    move_to_collection(obj, collection)
    if bevel:
        add_bevel(obj, bevel)
    return obj


def cylinder(name, location, radius, depth, material, rotation=(0, 0, 0),
             vertices=32, collection="props", bevel=0.03):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices, radius=radius, depth=depth,
        location=location, rotation=rotation
    )
    obj = bpy.context.object
    obj.name = name
    assign_material(obj, material)
    move_to_collection(obj, collection)
    if bevel:
        add_bevel(obj, bevel)
    smooth_object(obj)
    return obj


def sphere(name, location, radius, material, collection="props"):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=32, ring_count=16, radius=radius, location=location
    )
    obj = bpy.context.object
    obj.name = name
    assign_material(obj, material)
    move_to_collection(obj, collection)
    smooth_object(obj)
    return obj


def pipe_curve(name, points, radius, material=MAT["steel"], collection="props"):
    curve_data = bpy.data.curves.new(name + "_Path", "CURVE")
    curve_data.dimensions = "3D"
    curve_data.resolution_u = 2
    curve_data.bevel_depth = radius
    curve_data.bevel_resolution = 3
    spline = curve_data.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for point, coordinate in zip(spline.points, points):
        point.co = (*coordinate, 1.0)
    obj = bpy.data.objects.new(name, curve_data)
    COLLECTIONS[collection].objects.link(obj)
    assign_material(obj, material)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.convert(target="MESH")
    obj.select_set(False)
    return obj


def arch_shell(name, y_start, y_end, width=6.0, shoulder=2.55, rise=2.0):
    """Build the curved corridor skin as generated quad strips."""
    profile = [(-width / 2, 0.0), (-width / 2, shoulder)]
    segments = 18
    for index in range(1, segments):
        angle = math.pi - math.pi * index / segments
        profile.append((math.cos(angle) * width / 2, shoulder + math.sin(angle) * rise))
    profile.extend([(width / 2, shoulder), (width / 2, 0.0)])

    vertices = []
    for y in (y_start, y_end):
        vertices.extend((x, y, z) for x, z in profile)
    count = len(profile)
    faces = []
    for index in range(count - 1):
        faces.append((index, index + 1, count + index + 1, count + index))
    mesh = bpy.data.meshes.new(name + "_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    COLLECTIONS["structure"].objects.link(obj)
    assign_material(obj, MAT["white"])
    solidify = obj.modifiers.new("Armored shell thickness", "SOLIDIFY")
    solidify.thickness = 0.16
    solidify.offset = 0.0
    bevel_mod = obj.modifiers.new("Panel edge softening", "BEVEL")
    bevel_mod.width = 0.035
    bevel_mod.segments = 2
    return obj


def arch_rib(name, y, width=6.1, shoulder=2.5, rise=2.1):
    points = [(-width / 2, y, 0.0), (-width / 2, y, shoulder)]
    for index in range(19):
        angle = math.pi - math.pi * index / 18
        points.append((math.cos(angle) * width / 2, y, shoulder + math.sin(angle) * rise))
    points.extend([(width / 2, y, shoulder), (width / 2, y, 0.0)])
    return pipe_curve(name, points, 0.14, MAT["blue"], "structure")


def wall_with_opening(prefix, axis, fixed, start, end, z_height,
                      opening_center=None, opening_width=2.2, opening_height=2.8,
                      thickness=0.22, material=MAT["white"]):
    """Create a wall along X or Y, optionally leaving a walkable doorway."""
    if opening_center is None:
        intervals = [(start, end, 0.0, z_height)]
    else:
        left = opening_center - opening_width / 2
        right = opening_center + opening_width / 2
        intervals = [
            (start, left, 0.0, z_height),
            (right, end, 0.0, z_height),
            (left, right, opening_height, z_height),
        ]
    for index, (a, b, bottom, top) in enumerate(intervals):
        if b <= a or top <= bottom:
            continue
        if axis == "X":
            location = ((a + b) / 2, fixed, (bottom + top) / 2)
            size = (b - a, thickness, top - bottom)
        else:
            location = (fixed, (a + b) / 2, (bottom + top) / 2)
            size = (thickness, b - a, top - bottom)
        box(f"{prefix}_{index:02d}", location, size, material, bevel=0.025)


def add_text(name, body, location, rotation, size=0.28, color=None,
             extrude=0.008, align="CENTER"):
    curve = bpy.data.curves.new(name + "_Font", "FONT")
    curve.body = body
    curve.align_x = align
    curve.align_y = "CENTER"
    curve.size = size
    curve.extrude = extrude
    curve.bevel_depth = 0.003
    obj = bpy.data.objects.new(name, curve)
    obj.location = location
    obj.rotation_euler = rotation
    COLLECTIONS["decals"].objects.link(obj)
    assign_material(obj, color or MAT["yellow"])
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.convert(target="MESH")
    obj.select_set(False)
    return obj


# ---------------------------------------------------------------------------
# Architecture and layout: entrance, corridor, atrium, and three rooms
# ---------------------------------------------------------------------------

# Corridor shell, floor panels, expansion seams, and structural ribs.
box("Corridor_Floor", (0, -8.0, -0.14), (6.0, 24.0, 0.28), MAT["concrete"])
arch_shell("Corridor_Curved_Shell", -20.0, 4.0)
for rib_index, y in enumerate(range(-19, 5, 3)):
    arch_rib(f"Corridor_Rib_{rib_index:02d}", y)
for seam_index, y in enumerate(range(-18, 4, 2)):
    box(f"Floor_Expansion_Seam_{seam_index:02d}", (0, y, 0.012),
        (5.75, 0.045, 0.024), MAT["rubber"], bevel=0)
for side in (-1, 1):
    box(f"Corridor_Base_Trim_{side}", (side * 2.84, -8, 0.32),
        (0.14, 24, 0.64), MAT["blue"], bevel=0.03)

# Main circular vault entrance door and its gear-like segmented face.
cylinder("Main_Vault_Door", (0, -20.32, 2.55), 2.48, 0.56, MAT["steel"],
         rotation=(math.pi / 2, 0, 0), vertices=64, collection="structure", bevel=0.08)
cylinder("Main_Vault_Door_Blue_Inset", (0, -20.00, 2.55), 2.08, 0.10, MAT["blue"],
         rotation=(math.pi / 2, 0, 0), vertices=64, collection="structure", bevel=0.04)
cylinder("Main_Vault_Door_Hub", (0, -19.91, 2.55), 0.48, 0.22, MAT["yellow"],
         rotation=(math.pi / 2, 0, 0), vertices=32, collection="structure", bevel=0.03)
for spoke in range(8):
    angle = spoke * math.tau / 8
    x, z = math.cos(angle) * 1.24, 2.55 + math.sin(angle) * 1.24
    bar = box(f"Vault_Door_Spoke_{spoke:02d}", (x, -19.89, z),
              (1.38, 0.14, 0.23), MAT["yellow"], "structure", 0.035)
    bar.rotation_euler.y = -angle
add_text("Vault_Number", "V-33", (0, -19.77, 3.45),
         (math.pi / 2, 0, 0), 0.34, MAT["yellow"])

# Atrium floor, high walls, doorway openings, ceiling, beams, and balcony.
box("Atrium_Floor", (0, 12, -0.18), (14, 16, 0.36), MAT["concrete"])
wall_with_opening("Atrium_West_Wall", "Y", -7, 4, 20, 7.4, 11, 2.4, 3.0)
wall_with_opening("Atrium_East_Wall", "Y", 7, 4, 20, 7.4, 11, 2.4, 3.0)
wall_with_opening("Atrium_North_Wall", "X", 20, -7, 7, 7.4, 0, 2.6, 3.0)
box("Atrium_Ceiling", (0, 12, 7.48), (14.4, 16.4, 0.28), MAT["dark"])
for beam_index, y in enumerate((5, 9, 13, 17, 19.5)):
    box(f"Atrium_Ceiling_Beam_{beam_index:02d}", (0, y, 7.16),
        (14.2, 0.28, 0.42), MAT["blue"], bevel=0.04)

# Upper balcony and railings on both long sides.
for side in (-1, 1):
    x = side * 5.75
    box(f"Balcony_Deck_{side}", (x, 12, 3.16), (2.4, 15.2, 0.25), MAT["steel"])
    box(f"Balcony_Kickplate_{side}", (side * 4.58, 12, 3.38),
        (0.12, 15.0, 0.42), MAT["yellow"])
    for y in range(5, 20, 2):
        cylinder(f"Balcony_Post_{side}_{y}", (side * 4.48, y, 3.88),
                 0.045, 1.35, MAT["steel"], collection="structure", bevel=0)
    pipe_curve(f"Balcony_Top_Rail_{side}",
               [(side * 4.48, 4.5, 4.52), (side * 4.48, 19.5, 4.52)],
               0.065, MAT["steel"], "structure")
    pipe_curve(f"Balcony_Mid_Rail_{side}",
               [(side * 4.48, 4.5, 4.02), (side * 4.48, 19.5, 4.02)],
               0.035, MAT["steel"], "structure")

# Navigable staircase to the east balcony.
step_count = 12
for index in range(step_count):
    height = (index + 1) * 3.15 / step_count
    y = 7.2 + index * 0.38
    box(f"Balcony_Stair_{index:02d}", (5.65, y, height / 2),
        (1.8, 0.42, height), MAT["steel"], bevel=0.025)
pipe_curve("Stair_Handrail",
           [(4.7, 7.0, 0.85), (4.7, 11.75, 4.0)],
           0.055, MAT["yellow"], "structure")

# Central reactor / air-scrubber column as the atrium focal point.
cylinder("Reactor_Base", (0, 12.2, 0.28), 1.6, 0.56, MAT["dark"],
         vertices=48, collection="structure")
cylinder("Reactor_Core", (0, 12.2, 3.25), 0.82, 6.0, MAT["steel"],
         vertices=32, collection="structure")
for z in (0.7, 2.0, 3.4, 4.8, 6.1):
    cylinder(f"Reactor_Blue_Band_{z}", (0, 12.2, z), 0.98, 0.22, MAT["blue"],
             vertices=32, collection="structure")
for side in (-1, 1):
    pipe_curve(f"Reactor_Coolant_Pipe_{side}",
               [(side * 0.62, 12.2, 1.0), (side * 2.0, 12.2, 1.0),
                (side * 2.0, 12.2, 5.5), (side * 0.65, 12.2, 5.5)],
               0.11, MAT["yellow"], "props")

# Recessed wall emblem: a generic retro vault "V", built as mesh text.
box("Atrium_Logo_Panel", (0, 19.84, 4.7), (5.4, 0.12, 3.5), MAT["blue"])
add_text("Atrium_Vault_Emblem", "V", (0, 19.70, 4.7),
         (math.pi / 2, 0, 0), 2.4, MAT["yellow"], 0.035)
add_text("Atrium_Motto", "PREPARE  •  PRESERVE  •  PROSPER",
         (0, 19.66, 3.25), (math.pi / 2, 0, 0), 0.22, MAT["white"])

# Rooms: bunk room west, office east, utility room north.
box("Bunk_Room_Floor", (-10.25, 11, -0.14), (6.5, 7.0, 0.28), MAT["concrete"])
wall_with_opening("Bunk_East", "Y", -7.0, 7.5, 14.5, 3.5, 11, 2.4, 2.8)
wall_with_opening("Bunk_West", "Y", -13.5, 7.5, 14.5, 3.5)
wall_with_opening("Bunk_South", "X", 7.5, -13.5, -7, 3.5)
wall_with_opening("Bunk_North", "X", 14.5, -13.5, -7, 3.5)
box("Bunk_Room_Ceiling", (-10.25, 11, 3.58), (6.7, 7.2, 0.18), MAT["dark"])

box("Office_Floor", (10.25, 11, -0.14), (6.5, 7.0, 0.28), MAT["concrete"])
wall_with_opening("Office_West", "Y", 7.0, 7.5, 14.5, 3.5, 11, 2.4, 2.8)
wall_with_opening("Office_East", "Y", 13.5, 7.5, 14.5, 3.5)
wall_with_opening("Office_South", "X", 7.5, 7, 13.5, 3.5)
wall_with_opening("Office_North", "X", 14.5, 7, 13.5, 3.5)
box("Office_Ceiling", (10.25, 11, 3.58), (6.7, 7.2, 0.18), MAT["dark"])

box("Utility_Floor", (0, 23.25, -0.14), (8.0, 6.5, 0.28), MAT["concrete"])
wall_with_opening("Utility_South", "X", 20.0, -4, 4, 4.0, 0, 2.6, 2.9)
wall_with_opening("Utility_North", "X", 26.5, -4, 4, 4.0)
wall_with_opening("Utility_West", "Y", -4, 20, 26.5, 4.0)
wall_with_opening("Utility_East", "Y", 4, 20, 26.5, 4.0)
box("Utility_Ceiling", (0, 23.25, 4.08), (8.2, 6.7, 0.18), MAT["dark"])


# ---------------------------------------------------------------------------
# Bulkhead frames, control consoles, furniture, pipes, vents, and signs
# ---------------------------------------------------------------------------

def bulkhead_frame(name, location, rotation_z=0.0):
    """Open segmented bulkhead frame; keeps every room physically accessible."""
    x, y, z = location
    parent = bpy.data.objects.new(name, None)
    parent.location = location
    parent.rotation_euler.z = rotation_z
    COLLECTIONS["props"].objects.link(parent)
    pieces = (
        ((-1.25, 0, 1.4), (0.32, 0.35, 2.8)),
        ((1.25, 0, 1.4), (0.32, 0.35, 2.8)),
        ((-0.72, 0, 2.83), (0.78, 0.35, 0.28)),
        ((0.72, 0, 2.83), (0.78, 0.35, 0.28)),
    )
    for index, (offset, size) in enumerate(pieces):
        obj = box(f"{name}_Segment_{index}", (x, y, z), size,
                  MAT["yellow"], "props", 0.045)
        obj.location = offset
        obj.parent = parent
    # A visible open sliding door leaf beside the opening.
    leaf = box(f"{name}_Open_Leaf", (x, y, z), (1.65, 0.20, 2.45),
               MAT["blue"], "props", 0.04)
    leaf.location = (2.15, 0.02, 1.35)
    leaf.parent = parent
    for stripe in (-0.55, 0.0, 0.55):
        strip = box(f"{name}_Leaf_Rib_{stripe}", (x, y, z),
                    (0.12, 0.28, 2.25), MAT["steel"], "props", 0.02)
        strip.location = (2.15 + stripe, -0.02, 1.35)
        strip.parent = parent
    return parent


bulkhead_frame("Bunk_Bulkhead", (-6.88, 11, 0), math.pi / 2)
bulkhead_frame("Office_Bulkhead", (6.88, 11, 0), math.pi / 2)
bulkhead_frame("Utility_Bulkhead", (0, 19.88, 0), 0)


def console(name, location, rotation_z=0.0):
    parent = bpy.data.objects.new(name, None)
    parent.location = location
    parent.rotation_euler.z = rotation_z
    COLLECTIONS["props"].objects.link(parent)
    body = box(name + "_Body", (0, 0, 0), (1.45, 0.62, 1.18), MAT["blue"], "props")
    body.location = (0, 0, 0.59)
    body.parent = parent
    top = box(name + "_SlopedTop", (0, 0, 0), (1.36, 0.65, 0.22), MAT["steel"], "props")
    top.location = (0, -0.10, 1.14)
    top.rotation_euler.x = math.radians(-18)
    top.parent = parent
    screen = box(name + "_CRT", (0, 0, 0), (0.62, 0.055, 0.36),
                 MAT["screen_green"], "props", 0.025)
    screen.location = (-0.22, -0.37, 1.23)
    screen.rotation_euler.x = math.radians(18)
    screen.parent = parent
    for index in range(3):
        lamp = sphere(name + f"_Lamp_{index}", (0, 0, 0), 0.055,
                      MAT["screen_amber"], "props")
        lamp.location = (0.35 + index * 0.18, -0.39, 1.13)
        lamp.parent = parent
    return parent


console("Corridor_Access_Console", (2.53, -15.4, 0), -math.pi / 2)
console("Atrium_Status_Console", (-5.9, 16.5, 0), math.pi / 2)
console("Utility_Control_Console", (2.9, 24.5, 0), math.pi / 2)


def metal_bunk(name, location, rotation_z=0):
    parent = bpy.data.objects.new(name, None)
    parent.location = location
    parent.rotation_euler.z = rotation_z
    COLLECTIONS["props"].objects.link(parent)
    for x in (-0.48, 0.48):
        for y in (-0.98, 0.98):
            post = cylinder(name + f"_Post_{x}_{y}", (0, 0, 0), 0.045, 2.15,
                            MAT["steel"], collection="props", bevel=0)
            post.location = (x, y, 1.08)
            post.parent = parent
    for level in (0.44, 1.42):
        frame = box(name + f"_Frame_{level}", (0, 0, 0),
                    (1.08, 2.08, 0.12), MAT["steel"], "props", 0.025)
        frame.location = (0, 0, level)
        frame.parent = parent
        mattress = box(name + f"_Mattress_{level}", (0, 0, 0),
                       (0.92, 1.92, 0.16), MAT["fabric"], "props", 0.07)
        mattress.location = (0, 0, level + 0.12)
        mattress.parent = parent
        pillow = box(name + f"_Pillow_{level}", (0, 0, 0),
                     (0.64, 0.36, 0.12), MAT["white"], "props", 0.08)
        pillow.location = (0, 0.70, level + 0.24)
        pillow.parent = parent


metal_bunk("Bunk_A", (-11.8, 9.2, 0), 0)
metal_bunk("Bunk_B", (-8.8, 9.2, 0), 0)


def locker(name, location):
    box(name, location, (0.72, 0.58, 2.05), MAT["blue"], "props", 0.04)
    box(name + "_Door", (location[0], location[1] - 0.302, location[2] + 0.03),
        (0.64, 0.035, 1.88), MAT["steel"], "props", 0.018)
    for z in (location[2] - 0.58, location[2] + 0.58):
        for offset in (-0.12, 0, 0.12):
            box(name + f"_Vent_{z}_{offset}",
                (location[0] + offset, location[1] - 0.326, z),
                (0.08, 0.018, 0.025), MAT["dark"], "props", 0)


for index in range(3):
    locker(f"Bunk_Locker_{index}", (-12.8 + index * 0.82, 13.85, 1.03))


def desk_and_chair():
    box("Office_Desk_Top", (10.4, 12.6, 0.93), (2.4, 1.0, 0.14), MAT["steel"], "props")
    for x in (9.45, 11.35):
        for y in (12.25, 12.95):
            box(f"Office_Desk_Leg_{x}_{y}", (x, y, 0.46),
                (0.10, 0.10, 0.92), MAT["dark"], "props", 0.02)
    box("Office_Chair_Seat", (10.4, 10.9, 0.58), (0.72, 0.72, 0.13), MAT["fabric"], "props")
    box("Office_Chair_Back", (10.4, 11.24, 1.10), (0.72, 0.12, 0.92), MAT["fabric"], "props")
    cylinder("Office_Chair_Stem", (10.4, 10.9, 0.29), 0.07, 0.5,
             MAT["steel"], collection="props", bevel=0)
    console("Office_Terminal", (10.4, 13.15, 0.98), math.pi)


desk_and_chair()


def crate(name, location, scale=(1.0, 0.75, 0.62), material=MAT["yellow"]):
    box(name, location, scale, material, "props", 0.035)
    for x in (-scale[0] * 0.42, scale[0] * 0.42):
        box(name + f"_Band_{x}", (location[0] + x, location[1], location[2]),
            (0.08, scale[1] + 0.04, scale[2] + 0.04), MAT["steel"], "props", 0.01)


crate("Utility_Crate_A", (-2.9, 25.8, 0.35))
crate("Utility_Crate_B", (-1.8, 25.8, 0.35), material=MAT["blue"])
crate("Atrium_Supply_Crate", (5.8, 18.6, 0.35), (1.2, 0.9, 0.7), MAT["blue"])

# Utility tanks, wall piping, corridor conduits, and vents.
for index, x in enumerate((-2.7, -1.35, 0.0)):
    cylinder(f"Utility_Tank_{index}", (x, 24.2, 1.25), 0.48, 2.5,
             MAT["steel"], vertices=32, collection="props")
    cylinder(f"Utility_Tank_Cap_{index}", (x, 24.2, 2.55), 0.31, 0.18,
             MAT["yellow"], vertices=24, collection="props")
    pipe_curve(f"Utility_Tank_Pipe_{index}",
               [(x, 24.2, 2.65), (x, 23.0, 2.65), (3.5, 23.0, 2.65)],
               0.07, MAT["rust"], "props")

for side in (-1, 1):
    pipe_curve(f"Corridor_Conduit_{side}",
               [(side * 2.72, -18.5, 2.1), (side * 2.72, 3.2, 2.1)],
               0.065, MAT["yellow"], "props")
    for y in (-16, -10, -4, 2):
        cylinder(f"Conduit_Junction_{side}_{y}", (side * 2.72, y, 2.1),
                 0.12, 0.16, MAT["steel"], rotation=(0, math.pi / 2, 0),
                 vertices=16, collection="props", bevel=0.015)


def wall_vent(name, location, rotation=(math.pi / 2, 0, 0)):
    box(name + "_Frame", location, (1.45, 0.16, 0.76), MAT["steel"], "props", 0.03)
    for index in range(6):
        x = location[0] - 0.55 + index * 0.22
        box(name + f"_Slat_{index}", (x, location[1] - 0.095, location[2]),
            (0.07, 0.035, 0.58), MAT["dark"], "props", 0.01)


wall_vent("Corridor_Vent_A", (0, -8.0, 4.34))
wall_vent("Bunk_Vent", (-10.2, 14.38, 2.65))
wall_vent("Office_Vent", (10.2, 14.38, 2.65))

# Warning stripes and room labels.
for index in range(7):
    stripe = box(f"Utility_Hazard_Stripe_{index}", (-1.2 + index * 0.4, 19.73, 0.18),
                 (0.22, 0.025, 0.55), MAT["yellow"] if index % 2 == 0 else MAT["dark"],
                 "decals", 0)
    stripe.rotation_euler.y = math.radians(-30)
add_text("Bunk_Label", "RESIDENTIAL  03", (-6.74, 11, 3.15),
         (math.pi / 2, 0, math.pi / 2), 0.22, MAT["yellow"])
add_text("Office_Label", "OVERSEER ADMIN", (6.74, 11, 3.15),
         (math.pi / 2, 0, -math.pi / 2), 0.22, MAT["yellow"])
add_text("Utility_Label", "AUTHORIZED PERSONNEL ONLY", (0, 19.72, 3.25),
         (math.pi / 2, 0, 0), 0.22, MAT["screen_amber"])
add_text("Corridor_Direction", "ATRIUM  ↑", (2.78, -6.5, 1.65),
         (math.pi / 2, 0, -math.pi / 2), 0.26, MAT["yellow"])


# ---------------------------------------------------------------------------
# Industrial lighting and optional subtle atrium atmosphere
# ---------------------------------------------------------------------------

def area_light(name, location, rotation, energy=500, size=2.0,
               color=(0.53, 0.76, 1.0)):
    data = bpy.data.lights.new(name + "_Data", "AREA")
    data.energy = energy
    data.shape = "RECTANGLE"
    data.size = size
    data.size_y = 0.32
    data.color = color
    obj = bpy.data.objects.new(name, data)
    obj.location = location
    obj.rotation_euler = rotation
    COLLECTIONS["lighting"].objects.link(obj)
    return obj


def fluorescent_fixture(name, location, rotation=(0, 0, 0), length=2.2, energy=420):
    housing = box(name + "_Housing", location, (length + 0.20, 0.42, 0.15),
                  MAT["dark"], "lighting", 0.035)
    housing.rotation_euler = rotation
    diffuser_location = (location[0], location[1], location[2] - 0.10)
    diffuser = box(name + "_Diffuser", diffuser_location, (length, 0.25, 0.06),
                   MAT["light"], "lighting", 0.025)
    diffuser.rotation_euler = rotation
    light = area_light(name + "_Light", (location[0], location[1], location[2] - 0.15),
                       (0, 0, rotation[2]), energy, length)
    light.rotation_euler.x = 0
    return light


for index, y in enumerate((-16, -12, -8, -4, 0, 3)):
    fluorescent_fixture(f"Corridor_Light_{index:02d}", (0, y, 4.28), length=1.9, energy=330)
for index, y in enumerate((6, 10, 14, 18)):
    fluorescent_fixture(f"Atrium_Light_{index:02d}", (0, y, 7.12), length=3.0, energy=720)
for room, x, y, z in (
    ("Bunk", -10.2, 11, 3.42),
    ("Office", 10.2, 11, 3.42),
    ("Utility", 0, 23.3, 3.92),
):
    fluorescent_fixture(room + "_Ceiling_Light", (x, y, z), length=2.2, energy=410)

# Warm accents prevent the blue-green mood from becoming monochromatic.
for index, position in enumerate(((-5.8, 5.0, 2.0), (5.8, 5.0, 2.0),
                                  (-5.8, 18.8, 2.0), (5.8, 18.8, 2.0))):
    light = area_light(f"Atrium_Amber_Sconce_{index}", position,
                       (math.pi / 2, 0, 0), 180, 0.6, (1.0, 0.25, 0.06))
    light.rotation_euler.y = math.pi / 2 if position[0] < 0 else -math.pi / 2

# Principled-volume cube; set density to zero below if clear air is preferred.
fog_material = bpy.data.materials.new("Atrium_Subtle_Volume")
fog_material.use_nodes = True
fog_nodes = fog_material.node_tree.nodes
fog_links = fog_material.node_tree.links
fog_nodes.clear()
fog_output = fog_nodes.new("ShaderNodeOutputMaterial")
fog = fog_nodes.new("ShaderNodeVolumePrincipled")
fog.inputs["Density"].default_value = 0.012
fog.inputs["Color"].default_value = (0.18, 0.30, 0.31, 1.0)
fog.inputs["Anisotropy"].default_value = 0.22
fog_links.new(fog.outputs["Volume"], fog_output.inputs["Volume"])
fog_cube = box("Atrium_Atmosphere", (0, 12, 3.7), (13.5, 15.4, 7.0),
               fog_material, "lighting", 0)
fog_cube.display_type = "WIRE"


# ---------------------------------------------------------------------------
# Camera rig, world mood, render settings, and final organization
# ---------------------------------------------------------------------------

def camera(name, location, target, lens=35):
    data = bpy.data.cameras.new(name + "_Data")
    data.lens = lens
    data.sensor_width = 36
    data.dof.use_dof = True
    data.dof.focus_distance = (Vector(target) - Vector(location)).length
    data.dof.aperture_fstop = 5.6
    obj = bpy.data.objects.new(name, data)
    obj.location = location
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    COLLECTIONS["cameras"].objects.link(obj)
    return obj


atrium_camera = camera("CAM_Atrium", (6.0, 7.0, 4.8), (0, 13.0, 2.5), 29)
corridor_camera = camera("CAM_Corridor", (0.9, -16.8, 1.72), (0, -2.0, 1.65), 30)
bpy.context.scene.camera = atrium_camera

world = bpy.data.worlds.new("Vault_World") if not bpy.data.worlds else bpy.data.worlds[0]
bpy.context.scene.world = world
world.use_nodes = True
background = world.node_tree.nodes.get("Background")
background.inputs["Color"].default_value = (0.008, 0.014, 0.018, 1.0)
background.inputs["Strength"].default_value = 0.12

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE_NEXT"
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.render.resolution_percentage = 50
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = "//vault_atrium.png"
scene.render.film_transparent = False
scene.render.image_settings.color_mode = "RGBA"
scene.view_settings.look = "AgX - Medium High Contrast"

# Add metadata and save no external files: the user's current .blend remains in control.
scene["vault_generator"] = "Retro-futuristic Vault Interior"
scene["generated_for_blender"] = "5.2.0"
scene["navigation_note"] = (
    "Ground floor connects corridor, atrium, bunk room, office, utility room; "
    "east staircase reaches balcony."
)

# Select the atrium camera for a clean result after running.
bpy.ops.object.select_all(action="DESELECT")
atrium_camera.select_set(True)
bpy.context.view_layer.objects.active = atrium_camera

print(
    "Vault interior generated:",
    len(bpy.data.objects), "objects in",
    len(COLLECTIONS), "organized collections."
)
