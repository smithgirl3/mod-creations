"""
Procedural modern L-shaped sectional sofa for Blender 4.x and 5.x.

Run from Blender's Text Editor in a blank scene.  The script creates a detailed
presentation model plus a hidden, export-ready copy under SOFA_GAME_READY.
No external files, add-ons, or texture images are required.
"""

import bpy
import math
import traceback
from mathutils import Vector


# ---------------------------------------------------------------------------
# Global configuration
# ---------------------------------------------------------------------------

SOFA_COLLECTION = "SOFA_HIGH_DETAIL"
GAME_COLLECTION = "SOFA_GAME_READY"
STUDIO_COLLECTION = "STUDIO"
TAU = math.tau

PART_COLORS = {
    "Sofa_Frame": (0.52, 0.38, 0.25),
    "Seat_Cushions": (0.82, 0.70, 0.52),
    "Back_Cushions": (0.75, 0.58, 0.42),
    "Pillows": (0.40, 0.62, 0.86),
    "Legs": (0.26, 0.12, 0.05),
}


# ---------------------------------------------------------------------------
# Scene and collection helpers
# ---------------------------------------------------------------------------

def clear_scene():
    """Remove every object and orphaned local datablock from the scene."""
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.curves, bpy.data.meshes, bpy.data.materials,
                       bpy.data.cameras, bpy.data.lights):
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)


def new_collection(name, parent=None):
    collection = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(collection)
    return collection


def move_to_collection(obj, collection):
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    collection.objects.link(obj)


def create_empty(name, collection, color):
    obj = bpy.data.objects.new(name, None)
    collection.objects.link(obj)
    obj.empty_display_type = 'CUBE'
    obj.empty_display_size = 0.28
    obj.color = (*color, 1.0)
    obj["export_group"] = name
    return obj


def tag_part(obj, parent, category):
    obj.parent = parent
    obj["sofa_part"] = True
    obj["category"] = category


def set_smooth(obj):
    if obj.type == 'MESH':
        for polygon in obj.data.polygons:
            polygon.use_smooth = True


def named_socket(sockets, names, fallback_index=None):
    """Find a node socket across Blender's 4.x/5.x naming changes."""
    for name in names:
        socket = sockets.get(name)
        if socket is not None:
            return socket
    if fallback_index is not None and len(sockets) > fallback_index:
        return sockets[fallback_index]
    raise KeyError("None of the node sockets exist: " + ", ".join(names))


def node_input(node, names, fallback_index=None):
    return named_socket(node.inputs, names, fallback_index)


def node_output(node, names, fallback_index=None):
    return named_socket(node.outputs, names, fallback_index)


def material_input(node, names):
    return node_input(node, names)


def factor_input(node):
    """Blender 5.x renamed the common Fac socket to Factor."""
    return node_input(node, ("Fac", "Factor"), 0)


def scalar_output(node):
    """Return a scalar texture/value output in Blender 4.x or 5.x."""
    return node_output(node, ("Fac", "Factor", "Value", "Distance"), 0)


def set_principled(principled, base_color, roughness=0.5,
                   metallic=0.0, specular=0.35):
    material_input(principled, ("Base Color",)).default_value = (*base_color, 1.0)
    material_input(principled, ("Roughness",)).default_value = roughness
    material_input(principled, ("Metallic",)).default_value = metallic
    spec = material_input(principled, ("Specular IOR Level", "Specular"))
    if spec:
        spec.default_value = specular


def node(nodes, node_type, x, y, name=None):
    item = nodes.new(node_type)
    item.location = (x, y)
    if name:
        item.name = name
        item.label = name
    return item


# ---------------------------------------------------------------------------
# Procedural PBR materials
# ---------------------------------------------------------------------------

def create_linen_material():
    """Beige linen with crossed fibers, micro-normal and roughness breakup."""
    mat = bpy.data.materials.new("MAT_Sofa_Beige_Linen_PBR")
    mat.use_nodes = True
    mat.diffuse_color = (0.63, 0.49, 0.35, 1)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    out = node(nodes, "ShaderNodeOutputMaterial", 900, 0)
    bsdf = node(nodes, "ShaderNodeBsdfPrincipled", 650, 0, "Linen Principled")
    set_principled(bsdf, (0.67, 0.54, 0.41), 0.68, specular=0.28)
    tex = node(nodes, "ShaderNodeTexCoord", -1000, 0)
    mapping = node(nodes, "ShaderNodeMapping", -820, 0)
    mapping.inputs["Scale"].default_value = (8.0, 8.0, 8.0)
    noise = node(nodes, "ShaderNodeTexNoise", -590, 180, "Fiber Irregularity")
    # Blender 5.2 defaults new Noise Texture nodes to 1D.  Explicitly use 3D
    # so the Vector socket required by this procedural material is available.
    noise.noise_dimensions = '3D'
    noise.inputs["Scale"].default_value = 7.0
    noise.inputs["Detail"].default_value = 7.0
    noise.inputs["Roughness"].default_value = 0.75
    wave_a = node(nodes, "ShaderNodeTexWave", -580, -70, "Warp Fibers")
    wave_a.wave_type = 'BANDS'
    wave_a.bands_direction = 'X'
    wave_a.inputs["Scale"].default_value = 185.0
    wave_a.inputs["Distortion"].default_value = 4.0
    wave_a.inputs["Detail"].default_value = 3.0
    wave_b = node(nodes, "ShaderNodeTexWave", -580, -300, "Weft Fibers")
    wave_b.wave_type = 'BANDS'
    wave_b.bands_direction = 'Y'
    wave_b.inputs["Scale"].default_value = 210.0
    wave_b.inputs["Distortion"].default_value = 3.0
    mix_fiber = node(nodes, "ShaderNodeMath", -300, -130, "Woven Interlace")
    mix_fiber.operation = 'MULTIPLY'
    bump_mix = node(nodes, "ShaderNodeMath", -80, -80)
    bump_mix.operation = 'MULTIPLY_ADD'
    bump_mix.inputs[1].default_value = 0.72
    bump_mix.inputs[2].default_value = 0.12
    bump = node(nodes, "ShaderNodeBump", 390, -100, "Linen Micro Normal")
    bump.inputs["Strength"].default_value = 0.22
    bump.inputs["Distance"].default_value = 0.025
    ramp = node(nodes, "ShaderNodeValToRGB", -60, 190)
    ramp.color_ramp.elements[0].position = 0.22
    ramp.color_ramp.elements[0].color = (0.38, 0.27, 0.18, 1)
    ramp.color_ramp.elements[1].position = 0.83
    ramp.color_ramp.elements[1].color = (0.78, 0.67, 0.52, 1)
    rough_ramp = node(nodes, "ShaderNodeMapRange", 175, 265)
    rough_ramp.inputs["To Min"].default_value = 0.58
    rough_ramp.inputs["To Max"].default_value = 0.78
    links.new(tex.outputs["Generated"], mapping.inputs["Vector"])
    for texture in (noise, wave_a, wave_b):
        links.new(mapping.outputs["Vector"], texture.inputs["Vector"])
    links.new(wave_a.outputs["Color"], mix_fiber.inputs[0])
    links.new(wave_b.outputs["Color"], mix_fiber.inputs[1])
    links.new(mix_fiber.outputs[0], bump_mix.inputs[0])
    links.new(scalar_output(noise), bump_mix.inputs[1])
    links.new(bump_mix.outputs[0], bump.inputs["Height"])
    links.new(scalar_output(noise), factor_input(ramp))
    links.new(scalar_output(noise), rough_ramp.inputs["Value"])
    links.new(ramp.outputs["Color"], material_input(bsdf, ("Base Color",)))
    links.new(rough_ramp.outputs["Result"], material_input(bsdf, ("Roughness",)))
    links.new(bump.outputs["Normal"], material_input(bsdf, ("Normal",)))
    links.new(bsdf.outputs[0], out.inputs["Surface"])
    return mat


def create_fabric_material(name, color_a, color_b, style):
    """Create one of six distinct procedural pillow fabrics."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = (*color_a, 1)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    out = node(nodes, "ShaderNodeOutputMaterial", 820, 0)
    bsdf = node(nodes, "ShaderNodeBsdfPrincipled", 580, 0)
    set_principled(bsdf, color_a, 0.62, specular=0.3)
    tex = node(nodes, "ShaderNodeTexCoord", -900, 0)
    mapping = node(nodes, "ShaderNodeMapping", -720, 0)
    noise = node(nodes, "ShaderNodeTexNoise", -480, -180)
    noise.noise_dimensions = '3D'
    noise.inputs["Scale"].default_value = 75 if style != "boucle" else 18
    noise.inputs["Detail"].default_value = 6
    noise.inputs["Roughness"].default_value = 0.8
    bump = node(nodes, "ShaderNodeBump", 330, -150)
    bump.inputs["Strength"].default_value = 0.18 if style != "boucle" else 0.5
    bump.inputs["Distance"].default_value = 0.035
    pattern = None

    if style == "geometric":
        wave_x = node(nodes, "ShaderNodeTexWave", -450, 170)
        wave_x.wave_type = 'BANDS'
        wave_x.bands_direction = 'X'
        wave_x.inputs["Scale"].default_value = 8
        wave_y = node(nodes, "ShaderNodeTexWave", -450, 350)
        wave_y.wave_type = 'BANDS'
        wave_y.bands_direction = 'Y'
        wave_y.inputs["Scale"].default_value = 8
        pattern = node(nodes, "ShaderNodeMath", -180, 250)
        pattern.operation = 'MULTIPLY'
        links.new(mapping.outputs["Vector"], wave_x.inputs["Vector"])
        links.new(mapping.outputs["Vector"], wave_y.inputs["Vector"])
        links.new(wave_x.outputs["Color"], pattern.inputs[0])
        links.new(wave_y.outputs["Color"], pattern.inputs[1])
    elif style in {"stripe", "knit"}:
        pattern = node(nodes, "ShaderNodeTexWave", -430, 180)
        pattern.wave_type = 'BANDS'
        pattern.bands_direction = 'X' if style == "stripe" else 'Y'
        pattern.inputs["Scale"].default_value = 6 if style == "stripe" else 38
        pattern.inputs["Distortion"].default_value = 0.7 if style == "knit" else 0.08
        links.new(mapping.outputs["Vector"], pattern.inputs["Vector"])
    elif style == "embroidered":
        pattern = node(nodes, "ShaderNodeTexVoronoi", -430, 180)
        pattern.distance = 'EUCLIDEAN'
        pattern.feature = 'DISTANCE_TO_EDGE'
        pattern.inputs["Scale"].default_value = 9
        links.new(mapping.outputs["Vector"], pattern.inputs["Vector"])
    elif style == "boucle":
        pattern = node(nodes, "ShaderNodeTexVoronoi", -430, 180)
        pattern.feature = 'DISTANCE_TO_EDGE'
        pattern.inputs["Scale"].default_value = 42
        links.new(mapping.outputs["Vector"], pattern.inputs["Vector"])
    else:
        pattern = noise

    ramp = node(nodes, "ShaderNodeValToRGB", 40, 170)
    ramp.color_ramp.elements[0].color = (*color_a, 1)
    ramp.color_ramp.elements[1].color = (*color_b, 1)
    if style == "woven":
        source = scalar_output(pattern)
    else:
        source = node_output(
            pattern, ("Distance", "Value", "Fac", "Factor", "Color"), 0)
    links.new(tex.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    links.new(source, factor_input(ramp))
    links.new(scalar_output(noise), bump.inputs["Height"])
    links.new(ramp.outputs["Color"], material_input(bsdf, ("Base Color",)))
    links.new(bump.outputs["Normal"], material_input(bsdf, ("Normal",)))
    links.new(bsdf.outputs[0], out.inputs["Surface"])
    return mat


def create_wood_material():
    mat = bpy.data.materials.new("MAT_Walnut_Wood_PBR")
    mat.use_nodes = True
    mat.diffuse_color = (0.16, 0.065, 0.025, 1)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    out = node(nodes, "ShaderNodeOutputMaterial", 700, 0)
    bsdf = node(nodes, "ShaderNodeBsdfPrincipled", 470, 0)
    set_principled(bsdf, (0.18, 0.07, 0.025), 0.34, specular=0.38)
    tex = node(nodes, "ShaderNodeTexCoord", -800, 0)
    mapping = node(nodes, "ShaderNodeMapping", -620, 0)
    mapping.inputs["Scale"].default_value = (3, 3, 0.45)
    wave = node(nodes, "ShaderNodeTexWave", -400, 130)
    wave.wave_type = 'RINGS'
    wave.rings_direction = 'Z'
    wave.inputs["Scale"].default_value = 5.5
    wave.inputs["Distortion"].default_value = 7.0
    wave.inputs["Detail"].default_value = 5.0
    noise = node(nodes, "ShaderNodeTexNoise", -400, -150)
    noise.noise_dimensions = '3D'
    noise.inputs["Scale"].default_value = 4.0
    noise.inputs["Detail"].default_value = 7.0
    mix = node(nodes, "ShaderNodeMixRGB", -150, 100)
    mix.blend_type = 'MULTIPLY'
    mix.inputs[0].default_value = 0.72
    ramp = node(nodes, "ShaderNodeValToRGB", 40, 120)
    ramp.color_ramp.elements[0].color = (0.025, 0.008, 0.003, 1)
    ramp.color_ramp.elements[1].color = (0.34, 0.12, 0.035, 1)
    bump = node(nodes, "ShaderNodeBump", 240, -130)
    bump.inputs["Strength"].default_value = 0.22
    bump.inputs["Distance"].default_value = 0.05
    links.new(tex.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], wave.inputs["Vector"])
    links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    links.new(wave.outputs["Color"], mix.inputs[1])
    links.new(scalar_output(noise), mix.inputs[2])
    links.new(mix.outputs["Color"], factor_input(ramp))
    links.new(mix.outputs["Color"], bump.inputs["Height"])
    links.new(ramp.outputs["Color"], material_input(bsdf, ("Base Color",)))
    links.new(bump.outputs["Normal"], material_input(bsdf, ("Normal",)))
    links.new(bsdf.outputs[0], out.inputs["Surface"])
    return mat


def create_simple_material(name, color, roughness):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    set_principled(bsdf, color, roughness)
    mat.diffuse_color = (*color, 1)
    return mat


# ---------------------------------------------------------------------------
# Geometry primitives
# ---------------------------------------------------------------------------

def signed_power(value, power):
    return math.copysign(abs(value) ** power, value)


def create_superquadric(name, location, dimensions, material, collection,
                        exponent=0.34, segments=32, rings=16,
                        rotation=(0, 0, 0), compression=0.0, asymmetry=0.0):
    """Build a UV-mapped, mostly-quad rounded cushion with soft deformation."""
    a, b, c = (v * 0.5 for v in dimensions)
    vertices = []
    uvs = []

    # One vertex per pole avoids degenerate pole strips.
    vertices.append((0, 0, -c))
    uvs.append((0.5, 0.0))
    for j in range(1, rings):
        latitude = -math.pi / 2 + math.pi * j / rings
        cl = math.cos(latitude)
        sl = math.sin(latitude)
        for i in range(segments):
            longitude = TAU * i / segments
            co = math.cos(longitude)
            si = math.sin(longitude)
            x = a * signed_power(cl, exponent) * signed_power(co, exponent)
            y = b * signed_power(cl, exponent) * signed_power(si, exponent)
            z = c * signed_power(sl, exponent)
            # Settled filling: depressed center, fuller corners and tiny folds.
            nx, ny = x / max(a, 0.001), y / max(b, 0.001)
            top_weight = max(0.0, z / max(c, 0.001))
            center = math.exp(-3.6 * (nx * nx + ny * ny))
            z -= compression * center * top_weight
            z += asymmetry * math.sin(longitude * 3 + latitude * 2) * (1 - abs(sl))
            x *= 1.0 - 0.025 * top_weight * center
            y *= 1.0 - 0.04 * top_weight * center
            vertices.append((x, y, z))
            uvs.append((i / segments, j / rings))
    top_index = len(vertices)
    vertices.append((0, 0, c - compression * 0.55))
    uvs.append((0.5, 1.0))

    faces = []
    face_uvs = []
    first_ring = 1
    for i in range(segments):
        ni = (i + 1) % segments
        faces.append((0, first_ring + ni, first_ring + i))
        face_uvs.append((uvs[0], uvs[first_ring + ni], uvs[first_ring + i]))
    for j in range(rings - 2):
        row = 1 + j * segments
        next_row = row + segments
        for i in range(segments):
            ni = (i + 1) % segments
            faces.append((row + i, row + ni, next_row + ni, next_row + i))
            face_uvs.append((uvs[row + i], uvs[row + ni],
                             uvs[next_row + ni], uvs[next_row + i]))
    last_ring = 1 + (rings - 2) * segments
    for i in range(segments):
        ni = (i + 1) % segments
        faces.append((last_ring + i, last_ring + ni, top_index))
        face_uvs.append((uvs[last_ring + i], uvs[last_ring + ni], uvs[top_index]))

    mesh = bpy.data.meshes.new(name + "_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    uv_layer = mesh.uv_layers.new(name="UVMap")
    for polygon, coordinates in zip(mesh.polygons, face_uvs):
        for loop_index, uv in zip(polygon.loop_indices, coordinates):
            uv_layer.data[loop_index].uv = uv
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = rotation
    obj.data.materials.append(material)
    set_smooth(obj)
    bevel = obj.modifiers.new("Micro_Bevel", 'BEVEL')
    bevel.width = 0.018
    bevel.segments = 2
    return obj


def create_rounded_box(name, location, dimensions, radius, material,
                       collection, rotation=(0, 0, 0), segments=3):
    bpy.ops.mesh.primitive_cube_add(location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    move_to_collection(obj, collection)
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    bevel = obj.modifiers.new("Rounded_Edges", 'BEVEL')
    bevel.width = min(radius, min(dimensions) * 0.24)
    bevel.segments = segments
    bevel.limit_method = 'ANGLE'
    set_smooth(obj)
    # Bevel-generated texture coordinates remain valid; base UV is retained.
    if not obj.data.uv_layers:
        obj.data.uv_layers.new(name="UVMap")
    return obj


def rounded_rectangle_points(width, depth, z, radius, count_per_corner=8):
    points = []
    centers = [
        (width / 2 - radius, depth / 2 - radius, 0),
        (-width / 2 + radius, depth / 2 - radius, 90),
        (-width / 2 + radius, -depth / 2 + radius, 180),
        (width / 2 - radius, -depth / 2 + radius, 270),
    ]
    for cx, cy, start in centers:
        for k in range(count_per_corner):
            angle = math.radians(start + 90 * k / count_per_corner)
            points.append((cx + radius * math.cos(angle),
                           cy + radius * math.sin(angle), z))
    return points


def create_pipe(name, points, location, material, collection,
                thickness=0.016, cyclic=True, rotation=(0, 0, 0)):
    curve = bpy.data.curves.new(name + "_Curve", 'CURVE')
    curve.dimensions = '3D'
    curve.resolution_u = 1
    curve.bevel_depth = thickness
    curve.bevel_resolution = 2
    spline = curve.splines.new('NURBS' if len(points) > 5 else 'POLY')
    spline.points.add(len(points) - 1)
    for point, co in zip(spline.points, points):
        point.co = (*co, 1)
    spline.use_cyclic_u = cyclic
    if spline.type == 'NURBS':
        spline.order_u = min(3, len(points))
        spline.use_endpoint_u = not cyclic
    obj = bpy.data.objects.new(name, curve)
    collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = rotation
    obj.data.materials.append(material)
    return obj


def add_cushion_piping(cushion, dimensions, material, collection,
                       name_suffix="Piping"):
    width, depth, _ = dimensions
    points = rounded_rectangle_points(width * 0.975, depth * 0.965, 0,
                                      min(width, depth) * 0.12, 7)
    pipe = create_pipe(cushion.name + "_" + name_suffix, points,
                       cushion.location, material, collection, 0.018,
                       rotation=cushion.rotation_euler)
    pipe.parent = cushion.parent
    pipe["sofa_part"] = True
    pipe["category"] = cushion.get("category", "Seat_Cushions")
    return pipe


def create_stitches(name, location, width, depth, material, collection,
                    parent, rotation=(0, 0, 0)):
    """Add short raised stitch dashes around the front and side seams."""
    stitches = []
    for side in (-1, 1):
        for i in range(11):
            x = -width * 0.42 + i * width * 0.084
            y = side * depth * 0.493
            points = [(x - 0.022, y, 0), (x + 0.022, y, 0)]
            stitch = create_pipe(f"{name}_{side:+d}_{i:02d}", points, location,
                                 material, collection, 0.006, False, rotation)
            tag_part(stitch, parent, "Seat_Cushions")
            stitches.append(stitch)
    return stitches


def create_cylinder(name, location, radius, depth, material, collection,
                    rotation=(0, 0, 0), vertices=20, bevel=0.025):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius,
                                       depth=depth, location=location,
                                       rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    move_to_collection(obj, collection)
    obj.data.materials.append(material)
    mod = obj.modifiers.new("Soft_Edge", 'BEVEL')
    mod.width = bevel
    mod.segments = 2
    set_smooth(obj)
    if not obj.data.uv_layers:
        obj.data.uv_layers.new(name="UVMap")
    return obj


# ---------------------------------------------------------------------------
# Sofa construction
# ---------------------------------------------------------------------------

def build_frame(collection, parent, linen):
    parts = []
    specs = [
        ("Frame_Main_Platform", (-0.85, 0.10, 0.52), (5.15, 1.82, 0.50), 0.14),
        ("Frame_Chaise_Platform", (2.55, -0.72, 0.52), (1.90, 3.46, 0.50), 0.14),
        ("Frame_Back_Rail", (-0.15, 0.99, 1.23), (6.55, 0.30, 1.18), 0.13),
        ("Frame_Left_Arm", (-3.53, 0.08, 1.12), (0.42, 2.08, 1.35), 0.16),
        ("Frame_Right_Arm", (3.55, -0.68, 1.12), (0.42, 3.52, 1.35), 0.16),
    ]
    for name, loc, dims, radius in specs:
        obj = create_rounded_box(name, loc, dims, radius, linen, collection)
        tag_part(obj, parent, "Sofa_Frame")
        parts.append(obj)
    return parts


def build_seat_cushions(collection, parent, linen, stitch_mat):
    cushions = []
    seat_specs = [
        ("Seat_Cushion_Left", (-2.55, 0.02, 1.00), (1.55, 1.65, 0.43), 0.055),
        ("Seat_Cushion_Center", (-0.90, 0.02, 1.00), (1.54, 1.65, 0.43), 0.065),
        ("Seat_Cushion_Corner", (0.74, 0.02, 1.00), (1.54, 1.65, 0.43), 0.060),
        ("Seat_Cushion_Chaise", (2.45, -0.72, 1.00), (1.68, 3.20, 0.43), 0.070),
    ]
    for index, (name, loc, dims, compression) in enumerate(seat_specs):
        obj = create_superquadric(name, loc, dims, linen, collection,
                                  exponent=0.28, segments=36, rings=18,
                                  compression=compression,
                                  asymmetry=0.008 + index * 0.002)
        tag_part(obj, parent, "Seat_Cushions")
        cushions.append(obj)
        add_cushion_piping(obj, dims, linen, collection)
        if index < 3:
            create_stitches(name + "_Stitch", loc, dims[0], dims[1],
                            stitch_mat, collection, parent)
    return cushions


def build_back_cushions(collection, parent, linen):
    cushions = []
    specs = [
        ("Back_Cushion_Left", (-2.48, 0.67, 1.84), (1.56, 0.44, 1.38),
         (math.radians(-8), 0, math.radians(-1.5))),
        ("Back_Cushion_Center", (-0.83, 0.67, 1.84), (1.55, 0.44, 1.38),
         (math.radians(-8), 0, math.radians(1.0))),
        ("Back_Cushion_Corner", (0.80, 0.67, 1.84), (1.52, 0.44, 1.38),
         (math.radians(-8), 0, math.radians(-1.0))),
        ("Back_Cushion_Chaise", (2.42, 0.67, 1.84), (1.53, 0.44, 1.38),
         (math.radians(-8), 0, math.radians(1.5))),
    ]
    for i, (name, loc, dims, rotation) in enumerate(specs):
        obj = create_superquadric(name, loc, dims, linen, collection,
                                  exponent=0.34, segments=32, rings=18,
                                  rotation=rotation, compression=0.025,
                                  asymmetry=0.012 + i * 0.002)
        tag_part(obj, parent, "Back_Cushions")
        cushions.append(obj)
        # Piping follows the broad front silhouette in the cushion's X/Z plane.
        points = rounded_rectangle_points(dims[0] * .96, dims[2] * .94, 0,
                                          0.18, 7)
        points = [(x, -dims[1] * .49, y) for x, y, _ in points]
        pipe = create_pipe(name + "_Edge_Piping", points, loc, linen,
                           collection, 0.016, True, rotation)
        tag_part(pipe, parent, "Back_Cushions")
        # Three short fold creases where the cushion meets the seat.
        for fold_i in (-1, 0, 1):
            x = fold_i * dims[0] * 0.22
            crease = create_pipe(
                f"{name}_Fold_{fold_i:+d}",
                [(x - .10, -dims[1] * .505, -dims[2] * .44),
                 (x, -dims[1] * .525, -dims[2] * .34),
                 (x + .07, -dims[1] * .51, -dims[2] * .27)],
                loc, linen, collection, .009, False, rotation)
            tag_part(crease, parent, "Back_Cushions")
    return cushions


def build_arm_cushions(collection, parent, linen):
    specs = [
        ("Arm_Cushion_Left", (-3.25, -0.02, 1.62), (0.34, 1.48, 0.66),
         (0, math.radians(-7), math.radians(-3))),
        ("Arm_Cushion_Right", (3.27, -0.72, 1.62), (0.34, 2.70, 0.66),
         (0, math.radians(7), math.radians(2))),
    ]
    result = []
    for name, loc, dims, rotation in specs:
        obj = create_superquadric(name, loc, dims, linen, collection,
                                  exponent=.38, segments=28, rings=14,
                                  rotation=rotation, compression=.018,
                                  asymmetry=.012)
        tag_part(obj, parent, "Back_Cushions")
        result.append(obj)
    return result


def build_legs(collection, parent, wood):
    positions = [
        (-3.18, 0.69), (-3.18, -0.55), (1.35, 0.69), (1.35, -0.55),
        (1.84, -2.10), (3.25, -2.10), (3.25, 0.67),
    ]
    legs = []
    for i, (x, y) in enumerate(positions, 1):
        leg = create_rounded_box(f"Walnut_Leg_{i:02d}", (x, y, 0.20),
                                 (.22, .22, .40), .035, wood, collection,
                                 rotation=(math.radians(3), math.radians(-3),
                                           math.radians(45)), segments=2)
        tag_part(leg, parent, "Legs")
        legs.append(leg)
    return legs


def add_button(name, location, material, collection, parent, scale=.06):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8,
                                        radius=scale, location=location)
    button = bpy.context.object
    button.name = name
    move_to_collection(button, collection)
    button.scale = (1, .38, 1)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    button.data.materials.append(material)
    set_smooth(button)
    tag_part(button, parent, "Pillows")
    return button


def build_pillows(collection, parent, materials):
    """Six deliberately different pillows, naturally leaned and scattered."""
    pillows = []
    specs = [
        ("Pillow_Cream_Geometric", (-2.50, -0.19, 1.62), (.78, .27, .80),
         (math.radians(-10), math.radians(-8), math.radians(-13)), "geometric"),
        ("Pillow_Gray_Woven", (-1.66, -0.26, 1.51), (.65, .25, .67),
         (math.radians(-12), math.radians(6), math.radians(11)), "woven"),
        ("Pillow_Beige_Striped_Lumbar", (.05, -0.29, 1.47), (.94, .24, .48),
         (math.radians(-10), math.radians(-5), math.radians(-7)), "stripe"),
        ("Pillow_Boucle_Round", (1.11, -0.31, 1.53), (.70, .23, .70),
         (math.radians(-8), math.radians(8), math.radians(8)), "boucle"),
        ("Pillow_Embroidered", (2.20, -1.16, 1.48), (.74, .25, .76),
         (math.radians(-8), math.radians(-3), math.radians(-15)), "embroidered"),
    ]
    for name, loc, dims, rotation, style in specs:
        exponent = .52 if style == "boucle" else .38
        obj = create_superquadric(name, loc, dims, materials[style], collection,
                                  exponent=exponent, segments=32, rings=18,
                                  rotation=rotation, compression=.035,
                                  asymmetry=.018)
        tag_part(obj, parent, "Pillows")
        pillows.append(obj)
        if style != "boucle":
            points = rounded_rectangle_points(dims[0] * .97, dims[2] * .96, 0,
                                              min(dims[0], dims[2]) * .16, 6)
            points = [(x, -dims[1] * .51, y) for x, y, _ in points]
            pipe = create_pipe(name + "_Piping", points, loc, materials[style],
                               collection, .012, True, rotation)
            tag_part(pipe, parent, "Pillows")

    # Embroidered pillow receives a raised medallion and radiating threadwork.
    emb_loc = specs[4][1]
    add_button("Pillow_Embroidered_Center_Tuft",
               (emb_loc[0], emb_loc[1] - .14, emb_loc[2]),
               materials["embroidered"], collection, parent, .065)
    for index in range(8):
        angle = TAU * index / 8
        points = []
        for step in range(7):
            radius = .09 + step * .035
            points.append((radius * math.cos(angle + step * .04), 0,
                           radius * math.sin(angle + step * .04)))
        thread = create_pipe(f"Embroidered_Thread_{index:02d}", points,
                             (emb_loc[0], emb_loc[1] - .137, emb_loc[2]),
                             materials["embroidered"], collection, .006, False,
                             specs[4][3])
        tag_part(thread, parent, "Pillows")

    # Sixth pillow is a knitted cylindrical bolster with gathered ends.
    bolster = create_cylinder(
        "Pillow_Soft_Knit_Bolster", (2.66, -1.82, 1.42), .28, .88,
        materials["knit"], collection,
        rotation=(math.radians(90), math.radians(7), math.radians(-13)),
        vertices=32, bevel=.045)
    tag_part(bolster, parent, "Pillows")
    pillows.append(bolster)
    for side in (-1, 1):
        add_button(f"Knit_Bolster_End_Button_{side:+d}",
                   (2.66 + side * .10, -1.82 + side * .43, 1.42),
                   materials["knit"], collection, parent, .055)
    return pillows


# ---------------------------------------------------------------------------
# Optimized export copy
# ---------------------------------------------------------------------------

def evaluated_mesh_copy(source, depsgraph):
    """Bake mesh/curve plus modifiers into a clean mesh datablock."""
    evaluated = source.evaluated_get(depsgraph)
    mesh = bpy.data.meshes.new_from_object(
        evaluated, preserve_all_data_layers=True, depsgraph=depsgraph)
    copy = bpy.data.objects.new(source.name + "_GR", mesh)
    copy.matrix_world = source.matrix_world.copy()
    for slot in source.material_slots:
        if slot.material and slot.material.name not in copy.data.materials:
            copy.data.materials.append(slot.material)
    return copy


def create_game_ready_version(source_root, target_collection):
    """Bake and decimate an FBX/glTF-ready copy toward a 15k-30k triangle budget."""
    game_root = bpy.data.objects.new("Sectional_Sofa_GAME_READY", None)
    target_collection.objects.link(game_root)
    game_root["target_triangle_budget"] = "15000-30000"
    depsgraph = bpy.context.evaluated_depsgraph_get()
    copies = []
    sources = [
        obj for obj in bpy.context.scene.objects
        if obj.get("sofa_part") and obj.type in {'MESH', 'CURVE'}
    ]
    for source in sources:
        copy = evaluated_mesh_copy(source, depsgraph)
        target_collection.objects.link(copy)
        copy.parent = game_root
        copy.matrix_parent_inverse = game_root.matrix_world.inverted()
        copy["category"] = source.get("category", "Detail")
        copies.append(copy)

    initial_triangles = sum(
        sum(max(1, len(poly.vertices) - 2) for poly in obj.data.polygons)
        for obj in copies)
    target = 24000
    ratio = min(1.0, target / max(initial_triangles, 1))
    # Preserve silhouettes; only decimate when the baked copy exceeds budget.
    if ratio < .98:
        for obj in copies:
            if len(obj.data.polygons) < 30:
                continue
            modifier = obj.modifiers.new("Game_Ready_Decimate", 'DECIMATE')
            modifier.ratio = max(.20, ratio)
            modifier.use_collapse_triangulate = False
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)
            try:
                bpy.ops.object.modifier_apply(modifier=modifier.name)
            except RuntimeError:
                obj.modifiers.remove(modifier)
            obj.select_set(False)

    # Bake transforms, preserve UV maps, and hide duplicate from presentation.
    for obj in copies:
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        try:
            bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        except RuntimeError:
            pass
        obj.select_set(False)
    target_collection.hide_render = True
    target_collection.hide_viewport = True
    final_triangles = sum(
        sum(max(1, len(poly.vertices) - 2) for poly in obj.data.polygons)
        for obj in copies)
    game_root["triangle_count"] = final_triangles
    game_root["export_note"] = (
        "Unhide this collection and export Selected as FBX or glTF. "
        "Materials and UVMap layers are embedded.")
    return game_root


# ---------------------------------------------------------------------------
# Studio lighting, floor and camera
# ---------------------------------------------------------------------------

def point_camera(camera, target):
    direction = Vector(target) - camera.location
    camera.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()


def add_area_light(name, location, energy, size, color, collection, target):
    data = bpy.data.lights.new(name, 'AREA')
    data.energy = energy
    data.shape = 'DISK'
    data.size = size
    data.color = color
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat(
        '-Z', 'Y').to_euler()
    return obj


def build_studio(collection, floor_mat):
    bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, -0.015))
    floor = bpy.context.object
    floor.name = "Studio_Floor"
    move_to_collection(floor, collection)
    floor.data.materials.append(floor_mat)
    if not floor.data.uv_layers:
        floor.data.uv_layers.new(name="UVMap")

    add_area_light("Key_Softbox", (-4.8, -4.5, 6.8), 1150, 4.5,
                   (1.0, .82, .67), collection, (0, 0, 1))
    add_area_light("Fill_Softbox", (5.2, -1.6, 4.2), 850, 3.8,
                   (.70, .82, 1.0), collection, (0, 0, 1))
    add_area_light("Rim_Softbox", (1.5, 4.2, 5.4), 1050, 3.0,
                   (1.0, .88, .75), collection, (0, .2, 1.3))

    camera_data = bpy.data.cameras.new("Sofa_Preview_Camera")
    camera = bpy.data.objects.new("Sofa_Preview_Camera", camera_data)
    collection.objects.link(camera)
    camera.location = (8.4, -9.8, 6.4)
    camera.data.lens = 52
    camera.data.sensor_width = 36
    point_camera(camera, (0, -.20, 1.15))
    bpy.context.scene.camera = camera


def configure_scene():
    scene = bpy.context.scene
    try:
        scene.render.engine = 'BLENDER_EEVEE_NEXT'
    except TypeError:
        scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = 'RGBA'
    try:
        scene.view_settings.look = 'AgX - Medium High Contrast'
    except TypeError:
        # Some Blender builds expose the same look without the view prefix.
        try:
            scene.view_settings.look = 'Medium High Contrast'
        except Exception:
            pass
    scene.world.color = (0.025, 0.025, 0.025)
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.0


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_sectional_sofa():
    clear_scene()
    configure_scene()

    high = new_collection(SOFA_COLLECTION)
    game = new_collection(GAME_COLLECTION)
    studio = new_collection(STUDIO_COLLECTION)

    part_collections = {}
    part_roots = {}
    for category, color in PART_COLORS.items():
        part_collections[category] = new_collection(category, high)
        part_roots[category] = create_empty(category, part_collections[category],
                                            color)

    linen = create_linen_material()
    wood = create_wood_material()
    stitch = create_simple_material("MAT_Edge_Stitch_Thread",
                                    (.48, .35, .24), .64)
    floor_mat = create_simple_material("MAT_Studio_Warm_Gray",
                                       (.11, .105, .095), .48)
    pillow_materials = {
        "geometric": create_fabric_material(
            "MAT_Pillow_Cream_Geometric", (.78, .72, .61), (.32, .29, .24),
            "geometric"),
        "woven": create_fabric_material(
            "MAT_Pillow_Light_Gray_Woven", (.48, .50, .51), (.70, .72, .71),
            "woven"),
        "stripe": create_fabric_material(
            "MAT_Pillow_Beige_Striped", (.68, .55, .40), (.88, .79, .65),
            "stripe"),
        "boucle": create_fabric_material(
            "MAT_Pillow_Textured_Boucle", (.82, .76, .65), (.46, .39, .31),
            "boucle"),
        "embroidered": create_fabric_material(
            "MAT_Pillow_Embroidered", (.48, .35, .27), (.82, .67, .48),
            "embroidered"),
        "knit": create_fabric_material(
            "MAT_Pillow_Soft_Knit", (.62, .57, .52), (.34, .31, .29), "knit"),
    }

    build_frame(part_collections["Sofa_Frame"],
                part_roots["Sofa_Frame"], linen)
    build_seat_cushions(part_collections["Seat_Cushions"],
                        part_roots["Seat_Cushions"], linen, stitch)
    build_back_cushions(part_collections["Back_Cushions"],
                        part_roots["Back_Cushions"], linen)
    build_arm_cushions(part_collections["Back_Cushions"],
                       part_roots["Back_Cushions"], linen)
    build_legs(part_collections["Legs"], part_roots["Legs"], wood)
    build_pillows(part_collections["Pillows"], part_roots["Pillows"],
                  pillow_materials)

    master_root = bpy.data.objects.new("Modern_L_Sectional_Sofa", None)
    high.objects.link(master_root)
    master_root["asset_type"] = "Game-ready modern sectional sofa"
    master_root["units"] = "meters"
    for root in part_roots.values():
        root.parent = master_root

    create_game_ready_version(master_root, game)
    build_studio(studio, floor_mat)

    # Select the completed high-detail sofa and make its root active.
    bpy.ops.object.select_all(action='DESELECT')
    for obj in bpy.context.scene.objects:
        if obj == master_root or obj.get("sofa_part"):
            obj.select_set(True)
    bpy.context.view_layer.objects.active = master_root
    return master_root


if __name__ == "__main__":
    try:
        sofa = build_sectional_sofa()
        print("Sectional sofa generated successfully:", sofa.name)
    except Exception as exc:
        print("ERROR: Sectional sofa generation failed:", exc)
        traceback.print_exc()
        # Make failures visible when Blender's system console is closed.
        message = str(exc)

        def draw_error(self, _context):
            self.layout.label(text="Sofa generation failed.")
            self.layout.label(text=message[:240])
            self.layout.label(text="Open Window > Toggle System Console for details.")

        try:
            bpy.context.window_manager.popup_menu(
                draw_error, title="Sectional Sofa Script Error", icon='ERROR')
        except Exception:
            pass
        # Leave Blender responsive and in Object Mode after a recoverable error.
        try:
            if bpy.context.object and bpy.context.object.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass
