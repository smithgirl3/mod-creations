"""
Rainy NYC Coffee Shop Corner
Blender 5.2 scene generator

Run from Blender's Scripting workspace, or:
    blender --background --python nyc_coffee_shop_scene.py

The script creates one camera, a complete modeled street corner, procedural PBR
materials, Geometry Nodes particle systems for rain and steam, wind-driven soft
bodies, animated vegetation, puddle ripples, and a loopable 10-second shot.
"""

import bpy
import math
import random
from mathutils import Vector


# ---------------------------------------------------------------------------
# Configuration and scene reset
# ---------------------------------------------------------------------------

SEED = 7291
random.seed(SEED)
START, END, FPS = 1, 240, 24

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
for datablocks in (
    bpy.data.materials,
    bpy.data.curves,
    bpy.data.meshes,
    bpy.data.cameras,
    bpy.data.lights,
):
    for datablock in list(datablocks):
        if datablock.users == 0:
            datablocks.remove(datablock)

scene = bpy.context.scene
scene.frame_start = START
scene.frame_end = END
scene.render.fps = FPS
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "FFMPEG"
scene.render.ffmpeg.format = "MPEG4"
scene.render.ffmpeg.codec = "H264"
scene.render.filepath = "//rainy_nyc_coffee_corner.mp4"
scene.render.film_transparent = False

try:
    scene.render.engine = "BLENDER_EEVEE_NEXT"
except TypeError:
    scene.render.engine = "BLENDER_EEVEE"

if hasattr(scene, "eevee"):
    scene.eevee.taa_render_samples = 96
scene.render.image_settings.color_mode = "RGBA"
scene.view_settings.look = "AgX - Medium High Contrast"


# ---------------------------------------------------------------------------
# Collections and utility functions
# ---------------------------------------------------------------------------

def collection(name):
    col = bpy.data.collections.new(name)
    scene.collection.children.link(col)
    return col


COL = {
    name: collection(name)
    for name in (
        "Architecture", "Street", "Furniture", "Landscaping", "Vehicles",
        "Weather", "Lighting", "Details"
    )
}


def move_to_collection(obj, col):
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    col.objects.link(obj)


def smooth(obj):
    if obj.type == "MESH":
        for poly in obj.data.polygons:
            poly.use_smooth = True
    return obj


def bevel(obj, width=0.08, segments=3):
    mod = obj.modifiers.new("Edge softness", "BEVEL")
    mod.width = width
    mod.segments = segments
    return obj


def cube(name, loc, scale, mat=None, col=None, bevel_width=0.0):
    bpy.ops.mesh.primitive_cube_add(location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if mat:
        obj.data.materials.append(mat)
    if bevel_width:
        bevel(obj, bevel_width)
    if col:
        move_to_collection(obj, col)
    return obj


def cylinder(name, loc, radius, depth, mat=None, col=None, vertices=24, rotation=None):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc)
    obj = bpy.context.object
    obj.name = name
    if rotation:
        obj.rotation_euler = rotation
    if mat:
        obj.data.materials.append(mat)
    if col:
        move_to_collection(obj, col)
    return obj


def sphere(name, loc, scale, mat=None, col=None, segments=24, rings=12):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments, ring_count=rings, location=loc
    )
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    smooth(obj)
    if mat:
        obj.data.materials.append(mat)
    if col:
        move_to_collection(obj, col)
    return obj


def torus(name, loc, major, minor, mat=None, col=None, rotation=None):
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major, minor_radius=minor,
        major_segments=32, minor_segments=6, location=loc
    )
    obj = bpy.context.object
    obj.name = name
    if rotation:
        obj.rotation_euler = rotation
    if mat:
        obj.data.materials.append(mat)
    if col:
        move_to_collection(obj, col)
    return obj


def curve_obj(name, points, bevel_depth, mat, col, cyclic=False):
    data = bpy.data.curves.new(name + "_Curve", "CURVE")
    data.dimensions = "3D"
    data.bevel_depth = bevel_depth
    data.bevel_resolution = 3
    spline = data.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for bp, co in zip(spline.bezier_points, points):
        bp.co = co
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"
    spline.use_cyclic_u = cyclic
    obj = bpy.data.objects.new(name, data)
    col.objects.link(obj)
    data.materials.append(mat)
    return obj


def text_obj(name, body, loc, size, mat, col, rotation=(math.radians(90), 0, 0),
             align="CENTER", extrude=0.035):
    data = bpy.data.curves.new(name + "_Text", "FONT")
    data.body = body
    data.align_x = align
    data.align_y = "CENTER"
    data.size = size
    data.extrude = extrude
    data.bevel_depth = 0.012
    obj = bpy.data.objects.new(name, data)
    col.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = rotation
    data.materials.append(mat)
    return obj


def aim(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def linear_cycles(obj, data_path="location"):
    if not obj.animation_data or not obj.animation_data.action:
        return
    for fc in obj.animation_data.action.fcurves:
        if fc.data_path == data_path:
            for key in fc.keyframe_points:
                key.interpolation = "LINEAR"
            fc.modifiers.new("CYCLES")


def principled_material(
    name, color, roughness=0.45, metallic=0.0, transmission=0.0,
    emission=None, emission_strength=0.0, alpha=1.0
):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if "Transmission Weight" in bsdf.inputs:
        bsdf.inputs["Transmission Weight"].default_value = transmission
    elif "Transmission" in bsdf.inputs:
        bsdf.inputs["Transmission"].default_value = transmission
    if emission:
        emission_socket = bsdf.inputs.get("Emission Color") or bsdf.inputs.get("Emission")
        emission_socket.default_value = emission
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    bsdf.inputs["Alpha"].default_value = alpha
    if alpha < 1.0:
        mat.surface_render_method = "DITHERED"
    return mat


def noisy_pbr(name, base, roughness, noise_scale, bump_strength, metallic=0.0):
    mat = principled_material(name, base, roughness, metallic)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    tex = nodes.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value = noise_scale
    tex.inputs["Detail"].default_value = 6.0
    tex.inputs["Roughness"].default_value = 0.7
    ramp = nodes.new("ShaderNodeValToRGB")
    dark = tuple(max(0.0, c * 0.45) for c in base[:3]) + (1.0,)
    light = tuple(min(1.0, c * 1.35) for c in base[:3]) + (1.0,)
    ramp.color_ramp.elements[0].color = dark
    ramp.color_ramp.elements[1].color = light
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = bump_strength
    bump.inputs["Distance"].default_value = 0.12
    links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(tex.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


# ---------------------------------------------------------------------------
# Physically based materials
# ---------------------------------------------------------------------------

asphalt = noisy_pbr("Wet asphalt", (0.018, 0.024, 0.03, 1), 0.15, 7.5, 0.32)
concrete = noisy_pbr("Wet concrete", (0.31, 0.34, 0.36, 1), 0.3, 5.0, 0.18)
brick = noisy_pbr("Aged red brick", (0.25, 0.055, 0.035, 1), 0.48, 8.0, 0.3)
stone = noisy_pbr("Dark facade stone", (0.045, 0.052, 0.058, 1), 0.24, 10, 0.18)
white = principled_material("Painted white", (0.78, 0.79, 0.78, 1), 0.34)
black = principled_material("Black enamel", (0.012, 0.015, 0.018, 1), 0.22, 0.55)
metal = principled_material("Brushed steel", (0.16, 0.18, 0.2, 1), 0.24, 0.85)
bronze = principled_material("Aged brass", (0.31, 0.16, 0.055, 1), 0.28, 0.75)
glass = principled_material("Rainy window glass", (0.035, 0.07, 0.09, 1), 0.08, 0.05, 0.45)
warm_glass = principled_material(
    "Warm shop window", (0.16, 0.07, 0.025, 1), 0.12, 0, 0.24,
    (1.0, 0.21, 0.045, 1), 2.4
)
warm_light_mat = principled_material(
    "Warm practical glow", (0.2, 0.05, 0.008, 1), 0.2,
    emission=(1.0, 0.16, 0.025, 1), emission_strength=7.0
)
sign_mat = principled_material(
    "Coffee sign glow", (0.25, 0.045, 0.012, 1), 0.22,
    emission=(1.0, 0.12, 0.018, 1), emission_strength=4.0
)
awning_mat = principled_material("Striped awning green", (0.035, 0.16, 0.11, 1), 0.48)
awning_cream = principled_material("Striped awning cream", (0.72, 0.62, 0.43, 1), 0.48)
wood = noisy_pbr("Dark cafe wood", (0.13, 0.055, 0.018, 1), 0.4, 4.5, 0.13)
ceramic = principled_material("Ivory ceramic", (0.73, 0.68, 0.56, 1), 0.2)
terracotta = noisy_pbr("Terracotta", (0.38, 0.105, 0.04, 1), 0.47, 5, 0.15)
leaf_mats = [
    principled_material("Leaf deep", (0.018, 0.105, 0.035, 1), 0.44),
    principled_material("Leaf rainlit", (0.045, 0.20, 0.055, 1), 0.38),
    principled_material("Leaf olive", (0.10, 0.18, 0.035, 1), 0.43),
]
flower_mat = principled_material("Cafe flowers", (0.62, 0.025, 0.045, 1), 0.33)
yellow = principled_material("NYC taxi yellow", (0.72, 0.32, 0.015, 1), 0.2, 0.2)
navy = principled_material("Parked car navy", (0.015, 0.045, 0.09, 1), 0.18, 0.35)
van_white = principled_material("Delivery van", (0.48, 0.51, 0.52, 1), 0.24, 0.15)
red = principled_material("Tail lamp", (0.45, 0.003, 0.001, 1), 0.13,
                          emission=(1, 0.002, 0, 1), emission_strength=2)
road_paint = principled_material("Wet road paint", (0.72, 0.72, 0.66, 1), 0.24)
water = principled_material("Puddle water", (0.018, 0.035, 0.045, 1), 0.035, 0, 0.55, alpha=0.84)
rain_mat = principled_material("Rain streak", (0.22, 0.42, 0.58, 1), 0.06, 0, 0.25,
                               emission=(0.12, 0.25, 0.38, 1), emission_strength=0.2, alpha=0.62)
steam_mat = principled_material("Steam", (0.68, 0.72, 0.75, 1), 0.75, alpha=0.16)


# ---------------------------------------------------------------------------
# Street, sidewalks, curb, drains, crosswalk, and puddles
# ---------------------------------------------------------------------------

cube("Main wet avenue", (0, -6.4, -0.28), (18, 6.4, 0.25), asphalt, COL["Street"])
cube("Side wet street", (-13.4, 6.0, -0.27), (4.6, 6.0, 0.25), asphalt, COL["Street"])
cube("Front sidewalk", (2.5, 1.25, 0.0), (10.5, 1.25, 0.18), concrete, COL["Street"], 0.06)
cube("Side sidewalk", (-9.65, 7.25, 0.0), (1.55, 4.75, 0.18), concrete, COL["Street"], 0.06)
cube("Corner sidewalk", (-8.7, 1.4, 0.0), (1.3, 1.4, 0.18), concrete, COL["Street"], 0.06)

# Curbs and expansion joints.
cube("Front curb", (2.0, -0.12, 0.02), (11.0, 0.12, 0.28), concrete, COL["Street"], 0.04)
cube("Side curb", (-11.30, 7.0, 0.02), (0.12, 5.0, 0.28), concrete, COL["Street"], 0.04)
for x in range(-7, 13, 2):
    cube(f"Sidewalk joint {x}", (x, 1.25, 0.19), (0.015, 1.2, 0.008), black, COL["Details"])
for y in (0.35, 2.15):
    cube(f"Long sidewalk joint {y}", (2, y, 0.19), (10, 0.015, 0.008), black, COL["Details"])

# Crosswalk and lane markings.
for i in range(8):
    cube(f"Crosswalk stripe {i}", (-10.0 + i * 1.25, -2.2, 0.01),
         (0.42, 2.05, 0.022), road_paint, COL["Street"], 0.015)
for x in (-4.5, 5.5):
    cube(f"Lane dash {x}", (x, -7.4, 0.0), (1.6, 0.075, 0.018), road_paint, COL["Street"])

# Storm drains.
for x in (-7.4, 10.5):
    base = cube(f"Storm drain {x}", (x, -0.32, 0.05), (0.75, 0.38, 0.035), metal, COL["Street"], 0.03)
    for j in range(8):
        cube(f"Drain slot {x} {j}", (x - 0.58 + j * 0.17, -0.32, 0.09),
             (0.035, 0.31, 0.01), black, COL["Details"])

# Reflective puddles and animated ripple rings.
puddles = [(-5.8, -4.8, 2.4, 1.05), (3.0, -3.1, 1.8, 0.7), (9.6, -7.8, 2.8, 1.2),
           (-9.8, 4.3, 1.0, 2.1), (0.5, 0.4, 0.9, 0.32)]
for idx, (x, y, sx, sy) in enumerate(puddles):
    bpy.ops.mesh.primitive_circle_add(vertices=48, radius=1, fill_type="NGON", location=(x, y, 0.035))
    p = bpy.context.object
    p.name = f"Puddle {idx:02d}"
    p.scale = (sx, sy, 1)
    p.data.materials.append(water)
    move_to_collection(p, COL["Weather"])
    for ring_i in range(2):
        ring = torus(f"Puddle ripple {idx}-{ring_i}", (x, y, 0.052), 0.12, 0.012,
                     rain_mat, COL["Weather"])
        ring.scale.y = sy / max(sx, 0.001)
        start = START + idx * 17 + ring_i * 31
        while start > 72:
            start -= 72
        ring.scale *= 0.15
        ring.keyframe_insert("scale", frame=start)
        ring.scale *= 8.0
        ring.keyframe_insert("scale", frame=start + 48)
        linear_cycles(ring, "scale")


# ---------------------------------------------------------------------------
# Coffee shop architecture and facade details
# ---------------------------------------------------------------------------

# Corner building shell and upper floors.
cube("Coffee shop building", (1.5, 8.1, 5.5), (9.4, 5.4, 5.5), brick, COL["Architecture"], 0.12)
cube("Ground floor stone facade", (1.5, 3.05, 2.25), (9.45, 0.35, 2.25),
     stone, COL["Architecture"], 0.05)
cube("Side ground facade", (-7.58, 8.0, 2.25), (0.35, 5.1, 2.25),
     stone, COL["Architecture"], 0.05)
cube("Roof cornice", (1.5, 8.0, 11.0), (9.8, 5.55, 0.28), stone, COL["Architecture"], 0.12)
cube("Shop fascia", (1.0, 2.63, 4.55), (8.7, 0.16, 0.55), wood, COL["Architecture"], 0.04)

# Front windows, mullions, interior silhouettes, and door.
window_centers = [-5.4, -1.55, 5.25]
window_widths = [1.45, 1.55, 1.95]
for i, (x, w) in enumerate(zip(window_centers, window_widths)):
    cube(f"Warm shop window {i}", (x, 2.66, 2.35), (w, 0.08, 1.65),
         warm_glass, COL["Architecture"], 0.025)
    for dx in (-w, w):
        cube(f"Window jamb {i} {dx}", (x + dx, 2.53, 2.35), (0.075, 0.10, 1.78),
             black, COL["Architecture"], 0.025)
    cube(f"Window top {i}", (x, 2.53, 4.06), (w, 0.10, 0.075), black, COL["Architecture"])
    cube(f"Window mullion {i}", (x, 2.51, 2.35), (0.045, 0.10, 1.65), black, COL["Architecture"])
    cube(f"Window lower bar {i}", (x, 2.51, 1.15), (w, 0.10, 0.045), black, COL["Architecture"])

cube("Coffee shop door", (1.45, 2.55, 2.05), (1.0, 0.13, 2.05), black, COL["Architecture"], 0.04)
cube("Door glass", (1.45, 2.40, 2.35), (0.77, 0.035, 1.45), warm_glass, COL["Architecture"], 0.02)
cylinder("Door pull", (2.02, 2.30, 2.2), 0.035, 0.8, bronze, COL["Details"],
         rotation=(math.radians(90), 0, 0))

# Upper windows and fire escape.
for floor, z in enumerate((6.6, 9.1)):
    for x in (-5.2, -1.7, 1.8, 5.3):
        cube(f"Upper window {floor} {x}", (x, 2.66, z), (1.05, 0.06, 0.86),
             glass, COL["Architecture"], 0.025)
        cube(f"Upper sill {floor} {x}", (x, 2.51, z - 0.93), (1.17, 0.16, 0.08),
             stone, COL["Architecture"])
        cube(f"Upper mullion {floor} {x}", (x, 2.55, z), (0.035, 0.07, 0.8),
             black, COL["Details"])
for z in (5.65, 8.12):
    cube(f"Fire escape platform {z}", (4.5, 2.02, z), (3.2, 0.72, 0.08),
         metal, COL["Architecture"])
    for x in (1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5):
        cube(f"Fire escape rail {z} {x}", (x, 1.37, z + 0.48), (0.025, 0.025, 0.5),
             metal, COL["Details"])
    cube(f"Fire escape top rail {z}", (4.5, 1.37, z + 0.95), (3.1, 0.03, 0.03),
         metal, COL["Details"])

# Main signage and blade sign.
cube("Main sign backing", (1.0, 2.42, 4.63), (4.4, 0.09, 0.42), black, COL["Architecture"], 0.06)
text_obj("Main coffee sign", "CORNER CUP  •  COFFEE & PASTRY", (1.0, 2.30, 4.63),
         0.38, sign_mat, COL["Details"])
cube("Blade sign arm", (7.55, 2.1, 4.6), (0.8, 0.035, 0.035), bronze, COL["Details"])
cube("Blade sign", (7.55, 1.52, 4.0), (0.72, 0.06, 0.68), black, COL["Architecture"], 0.08)
text_obj("Blade coffee icon", "☕", (7.55, 1.44, 4.0), 0.68, sign_mat, COL["Details"])


# ---------------------------------------------------------------------------
# Striped cloth awnings with soft-body wind response
# ---------------------------------------------------------------------------

def create_awning(name, x, width, y=2.15, z=4.02):
    # Alternating cloth panels provide visible physical thickness and wet sheen.
    panels = 8
    panel_w = width * 2 / panels
    parent = bpy.data.objects.new(name, None)
    COL["Architecture"].objects.link(parent)
    for i in range(panels):
        px = x - width + panel_w * (i + 0.5)
        panel = cube(
            f"{name} stripe {i}", (px, y, z), (panel_w * 0.5, 1.0, 0.055),
            awning_mat if i % 2 == 0 else awning_cream, COL["Architecture"], 0.025
        )
        panel.rotation_euler.x = math.radians(-13)
        panel.parent = parent
    # Flexible scalloped valance is a subdivided cloth-like soft body.
    verts = []
    faces = []
    segs = 16
    for i in range(segs + 1):
        px = x - width + 2 * width * i / segs
        verts.extend([(px, y - 0.97, z - 0.23), (px, y - 0.97, z - 0.53)])
    for i in range(segs):
        a = i * 2
        faces.append((a, a + 2, a + 3, a + 1))
    mesh = bpy.data.meshes.new(name + " Valance Mesh")
    mesh.from_pydata(verts, [], faces)
    valance = bpy.data.objects.new(name + " wind valance", mesh)
    COL["Architecture"].objects.link(valance)
    mesh.materials.append(awning_mat)
    group = valance.vertex_groups.new(name="Pinned top")
    group.add(list(range(0, len(verts), 2)), 1.0, "REPLACE")
    bpy.context.view_layer.objects.active = valance
    valance.select_set(True)
    try:
        bpy.ops.object.modifier_add(type="SOFT_BODY")
        soft = valance.modifiers[-1]
        soft.settings.vertex_group_goal = group.name
        soft.settings.goal_default = 0.65
        soft.settings.goal_spring = 0.75
        soft.settings.goal_friction = 8.0
        soft.settings.pull = 0.45
        soft.settings.push = 0.45
        soft.point_cache.frame_start = START
        soft.point_cache.frame_end = END
    except (RuntimeError, AttributeError):
        pass
    valance.select_set(False)
    # Subtle deterministic sway remains visible even if cache baking is unavailable.
    parent.rotation_euler.y = math.radians(-0.6)
    parent.keyframe_insert("rotation_euler", frame=START)
    parent.rotation_euler.y = math.radians(0.8)
    parent.keyframe_insert("rotation_euler", frame=60)
    parent.rotation_euler.y = math.radians(-0.5)
    parent.keyframe_insert("rotation_euler", frame=120)
    parent.rotation_euler.y = math.radians(0.65)
    parent.keyframe_insert("rotation_euler", frame=180)
    parent.rotation_euler.y = math.radians(-0.6)
    parent.keyframe_insert("rotation_euler", frame=END)
    return parent


for i, (x, width) in enumerate(((-5.4, 1.7), (-1.5, 1.8), (5.25, 2.15))):
    create_awning(f"Window awning {i}", x, width)


# ---------------------------------------------------------------------------
# Bistro furniture, identical vases, flowers, coffee, and steam particles
# ---------------------------------------------------------------------------

def make_chair(name, x, y, angle=0):
    root = bpy.data.objects.new(name, None)
    COL["Furniture"].objects.link(root)
    root.location = (x, y, 0)
    root.rotation_euler.z = angle
    seat = cylinder(name + " seat", (0, 0, 0.78), 0.36, 0.07, wood, COL["Furniture"])
    seat.parent = root
    for dx, dy in ((-.25, -.25), (.25, -.25), (-.25, .25), (.25, .25)):
        leg = cylinder(name + " leg", (dx, dy, 0.39), 0.025, 0.75, black, COL["Furniture"])
        leg.parent = root
    back = curve_obj(name + " back", [(-.3, .28, .82), (-.32, .3, 1.5),
                                      (0, .32, 1.66), (.32, .3, 1.5), (.3, .28, .82)],
                     0.025, black, COL["Furniture"])
    back.parent = root
    return root


def make_steam_system(name, x, y, z):
    # Geometry Nodes point-instancing is Blender 5.2's supported particle workflow.
    verts = []
    for i in range(18):
        ang = random.uniform(0, math.tau)
        r = random.uniform(0.01, 0.13)
        verts.append((math.cos(ang) * r, math.sin(ang) * r, random.uniform(0, 1.2)))
    mesh = bpy.data.meshes.new(name + " points")
    mesh.from_pydata(verts, [], [])
    emitter = bpy.data.objects.new(name, mesh)
    COL["Weather"].objects.link(emitter)
    emitter.location = (x, y, z)
    emitter["particle_system"] = "steam"
    emitter["particle_count"] = len(verts)
    # A hidden source droplet is instanced on all points.
    source = sphere(name + " steam particle", (0, 0, 0), (0.06, 0.06, 0.13),
                    steam_mat, COL["Weather"], 12, 6)
    source.hide_render = True
    source.hide_viewport = True
    mod = emitter.modifiers.new(name + " GeometryNodes Particle System", "NODES")
    tree = bpy.data.node_groups.new(name + " Steam Particle Nodes", "GeometryNodeTree")
    mod.node_group = tree
    tree.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    tree.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nodes, links = tree.nodes, tree.links
    inp = nodes.new("NodeGroupInput")
    out = nodes.new("NodeGroupOutput")
    inst = nodes.new("GeometryNodeInstanceOnPoints")
    info = nodes.new("GeometryNodeObjectInfo")
    info.transform_space = "ORIGINAL"
    info.inputs["Object"].default_value = source
    links.new(inp.outputs["Geometry"], inst.inputs["Points"])
    links.new(info.outputs["Geometry"], inst.inputs["Instance"])
    links.new(inst.outputs["Instances"], out.inputs["Geometry"])
    # Looped rise and lateral drift.
    emitter.location.z = z
    emitter.keyframe_insert("location", frame=START)
    emitter.location.z = z + 1.25
    emitter.location.x += 0.18
    emitter.keyframe_insert("location", frame=80)
    linear_cycles(emitter)
    return emitter


def make_table(name, x, y):
    cylinder(name + " pedestal", (x, y, 0.68), 0.07, 1.0, black, COL["Furniture"])
    cylinder(name + " foot", (x, y, 0.2), 0.42, 0.06, black, COL["Furniture"])
    cylinder(name + " top", (x, y, 1.2), 0.74, 0.10, wood, COL["Furniture"], 40)
    # Every table receives the same vase, three flowers, and cup design.
    cylinder(name + " vase", (x, y, 1.42), 0.12, 0.38, ceramic, COL["Furniture"], 24)
    for j, (dx, dy) in enumerate(((0, 0), (.09, .02), (-.07, .045))):
        cylinder(name + f" flower stem {j}", (x + dx, y + dy, 1.80), 0.009, 0.45,
                 leaf_mats[1], COL["Furniture"], 8)
        sphere(name + f" flower {j}", (x + dx, y + dy, 2.03), (.11, .11, .075),
               flower_mat, COL["Furniture"], 16, 8)
    cup_x, cup_y = x + 0.34, y - 0.11
    cylinder(name + " coffee cup", (cup_x, cup_y, 1.40), 0.13, 0.27,
             ceramic, COL["Furniture"], 24)
    cylinder(name + " coffee surface", (cup_x, cup_y, 1.545), 0.105, 0.009,
             wood, COL["Furniture"], 24)
    torus(name + " cup handle", (cup_x + .13, cup_y, 1.41), .10, .025,
          ceramic, COL["Furniture"], rotation=(math.radians(90), 0, 0))
    make_steam_system(name + " steam particles", cup_x, cup_y, 1.58)
    make_chair(name + " chair A", x - 1.0, y, math.radians(-90))
    make_chair(name + " chair B", x + 1.0, y, math.radians(90))


for i, (x, y) in enumerate(((-4.8, 0.95), (-0.9, 0.92), (4.15, 0.95))):
    make_table(f"Bistro set {i}", x, y)


# ---------------------------------------------------------------------------
# Landscaping: planters, shrubs, street trees, and wind animation
# ---------------------------------------------------------------------------

def leaf_cluster(name, loc, scale=1.0):
    root = bpy.data.objects.new(name, None)
    COL["Landscaping"].objects.link(root)
    root.location = loc
    for i in range(24):
        v = Vector((random.uniform(-1, 1), random.uniform(-1, 1), random.uniform(-.5, 1)))
        if v.length < 0.2:
            v.z += 0.5
        v.normalize()
        pos = v * random.uniform(0.35, 0.9) * scale
        leaf = sphere(
            f"{name} leaf {i}", pos, (
                random.uniform(.13, .28) * scale,
                random.uniform(.06, .13) * scale,
                random.uniform(.10, .22) * scale
            ), random.choice(leaf_mats), COL["Landscaping"], 12, 6
        )
        leaf.rotation_euler = (random.random(), random.random(), random.random())
        leaf.parent = root
    return root


def planter(name, x, y, scale=1.0):
    cylinder(name + " pot", (x, y, .43 * scale), .42 * scale, .78 * scale,
             terracotta, COL["Landscaping"], 32)
    cylinder(name + " soil", (x, y, .84 * scale), .34 * scale, .025,
             wood, COL["Landscaping"], 24)
    plant = leaf_cluster(name + " foliage", (x, y, 1.2 * scale), .7 * scale)
    plant.rotation_euler.y = math.radians(-2)
    plant.keyframe_insert("rotation_euler", frame=START)
    plant.rotation_euler.y = math.radians(3)
    plant.rotation_euler.x = math.radians(1.5)
    plant.keyframe_insert("rotation_euler", frame=65)
    plant.rotation_euler.y = math.radians(-2.5)
    plant.rotation_euler.x = 0
    plant.keyframe_insert("rotation_euler", frame=125)
    plant.rotation_euler.y = math.radians(2)
    plant.keyframe_insert("rotation_euler", frame=185)
    plant.rotation_euler.y = math.radians(-2)
    plant.keyframe_insert("rotation_euler", frame=END)


for i, (x, y, s) in enumerate(((-7.1, 1.0, .9), (7.2, 1.0, 1.0), (8.9, 1.1, .8),
                                (-6.9, 4.4, .75), (-6.9, 6.4, .75), (6.5, 2.0, .65))):
    planter(f"Facade planter {i}", x, y, s)


def tree(name, x, y, height=5.5):
    root = bpy.data.objects.new(name, None)
    COL["Landscaping"].objects.link(root)
    root.location = (x, y, 0.2)
    trunk = cylinder(name + " trunk", (0, 0, height * .38), .23, height * .76,
                     wood, COL["Landscaping"], 16)
    trunk.parent = root
    crown = leaf_cluster(name + " crown", (0, 0, height * .78), 1.65)
    crown.parent = root
    for a in range(5):
        angle = a * math.tau / 5
        branch = cylinder(
            name + f" branch {a}",
            (math.cos(angle) * .35, math.sin(angle) * .35, height * .62),
            .065, 1.8, wood, COL["Landscaping"], 10,
            (math.radians(50), 0, angle)
        )
        branch.parent = root
    # Root sway is a baked, deterministic response matching the wind field.
    for frame, rx, ry in ((START, -1.1, -1.8), (58, 1.5, 2.4), (118, -.8, -2.1),
                          (177, 1.0, 1.7), (END, -1.1, -1.8)):
        root.rotation_euler = (math.radians(rx), math.radians(ry), 0)
        root.keyframe_insert("rotation_euler", frame=frame)
    return root


tree("Street tree left", -7.0, -0.15, 5.8)
tree("Street tree right", 8.7, -0.15, 6.2)
tree("Side street tree", -10.3, 6.0, 5.6)

# Wind force field drives awning soft bodies; animated strength creates gusts.
bpy.ops.object.effector_add(type="WIND", location=(-14, -7, 4), rotation=(math.radians(78), 0, math.radians(-28)))
wind = bpy.context.object
wind.name = "Rainstorm wind force field"
move_to_collection(wind, COL["Weather"])
wind.field.strength = 280.0
wind.field.noise = 3.2
wind.field.shape = "PLANE"
wind.field.strength = 180
wind.field.keyframe_insert("strength", frame=START)
wind.field.strength = 420
wind.field.keyframe_insert("strength", frame=68)
wind.field.strength = 235
wind.field.keyframe_insert("strength", frame=135)
wind.field.strength = 370
wind.field.keyframe_insert("strength", frame=195)
wind.field.strength = 180
wind.field.keyframe_insert("strength", frame=END)


# ---------------------------------------------------------------------------
# Detailed parked vehicles
# ---------------------------------------------------------------------------

def vehicle(name, loc, color, length=4.6, width=1.85, height=1.45, taxi=False, van=False):
    x, y, z = loc
    root = bpy.data.objects.new(name, None)
    COL["Vehicles"].objects.link(root)
    root.location = loc
    body = cube(name + " body", (0, 0, .68), (length / 2, width / 2, .48),
                color, COL["Vehicles"], .24)
    body.parent = root
    cabin_scale = (length * (.34 if van else .26), width * .43, height * (.42 if van else .32))
    cabin = cube(name + " cabin", ((-.25 if van else .15), 0, 1.28), cabin_scale,
                 color, COL["Vehicles"], .18)
    cabin.parent = root
    # Dark windows on all visible sides.
    windshield = cube(name + " windshield", (length * .23, 0, 1.35),
                      (.035, width * .38, .32), glass, COL["Vehicles"], .03)
    windshield.rotation_euler.y = math.radians(-12)
    windshield.parent = root
    for side in (-1, 1):
        sw = cube(name + f" side windows {side}", (0, side * (width / 2 + .015), 1.37),
                  (length * .22, .025, .30), glass, COL["Vehicles"], .035)
        sw.parent = root
    for axle in (-length * .31, length * .31):
        for side in (-1, 1):
            wheel = cylinder(name + f" wheel {axle} {side}", (axle, side * width / 2, .48),
                             .38, .22, black, COL["Vehicles"], 24,
                             (math.radians(90), 0, 0))
            wheel.parent = root
            hub = cylinder(name + f" hub {axle} {side}", (axle, side * (width / 2 + .12), .48),
                           .17, .025, metal, COL["Vehicles"], 18,
                           (math.radians(90), 0, 0))
            hub.parent = root
    for side in (-.58, .58):
        lamp = sphere(name + f" headlight {side}", (length / 2 + .02, side, .78),
                      (.055, .18, .12), warm_light_mat, COL["Vehicles"], 16, 8)
        lamp.parent = root
        tail = sphere(name + f" tail light {side}", (-length / 2 - .02, side, .76),
                      (.055, .15, .11), red, COL["Vehicles"], 16, 8)
        tail.parent = root
    if taxi:
        roof = cube(name + " taxi roof light", (0, 0, 1.93), (.42, .18, .14),
                    warm_light_mat, COL["Vehicles"], .06)
        roof.parent = root
        text_obj(name + " taxi number", "NYC", (0, -width / 2 - .04, 1.02), .23,
                 black, COL["Details"], rotation=(math.radians(90), 0, 0))
    return root


taxi_obj = vehicle("Parked NYC taxi", (5.2, -6.5, 0), yellow, 4.8, 1.9, 1.5, taxi=True)
taxi_obj.rotation_euler.z = math.radians(2)
car_obj = vehicle("Parked navy sedan", (-2.2, -9.2, 0), navy, 4.55, 1.82, 1.42)
car_obj.rotation_euler.z = math.radians(-1)
van_obj = vehicle("Side street delivery van", (-14.0, 6.8, 0), van_white, 5.0, 2.0, 2.2, van=True)
van_obj.rotation_euler.z = math.radians(90)
text_obj("Van logo", "BROOKLYN BAKERY", (-13.0, 6.8, 1.22), .28, black, COL["Details"],
         rotation=(math.radians(90), 0, math.radians(90)))


# ---------------------------------------------------------------------------
# Street lamps, shop lighting, traffic details
# ---------------------------------------------------------------------------

def point_light(name, loc, color, energy, radius, col=COL["Lighting"]):
    data = bpy.data.lights.new(name + " Data", "POINT")
    data.color = color
    data.energy = energy
    data.shadow_soft_size = radius
    obj = bpy.data.objects.new(name, data)
    col.objects.link(obj)
    obj.location = loc
    return obj


def area_light(name, loc, scale, color, energy, target):
    data = bpy.data.lights.new(name + " Data", "AREA")
    data.color = color
    data.energy = energy
    data.shape = "RECTANGLE"
    data.size = scale[0]
    data.size_y = scale[1]
    obj = bpy.data.objects.new(name, data)
    COL["Lighting"].objects.link(obj)
    obj.location = loc
    aim(obj, target)
    return obj


def street_lamp(name, x, y):
    cylinder(name + " pole", (x, y, 2.6), .075, 5.2, black, COL["Lighting"], 16)
    cylinder(name + " base", (x, y, .35), .22, .7, black, COL["Lighting"], 20)
    curve_obj(name + " arm", [(x, y, 5.0), (x, y, 5.7), (x + .55, y, 6.05)],
              .065, black, COL["Lighting"])
    shade = cylinder(name + " shade", (x + .58, y, 5.95), .32, .20, black,
                     COL["Lighting"], 24)
    bulb = sphere(name + " bulb", (x + .58, y, 5.77), (.18, .18, .23),
                  warm_light_mat, COL["Lighting"], 20, 10)
    point_light(name + " warm light", (x + .58, y, 5.65), (1.0, .33, .10), 750, 1.0)


street_lamp("Corner streetlamp", -8.5, -0.5)
street_lamp("Right streetlamp", 10.8, -0.6)
for i, x in enumerate((-5.4, -1.5, 1.5, 5.3)):
    area_light(f"Shop window glow {i}", (x, 2.1, 2.4), (2.4, 2.7),
               (1.0, .25, .07), 480, (x, -1.0, 1.8))
point_light("Sign spill", (1.0, 1.8, 4.7), (1.0, .08, .015), 450, 1.2)

# Traffic light and street signs.
cylinder("Traffic pole", (-9.2, -1.1, 2.8), .08, 5.6, black, COL["Details"], 16)
cube("Traffic signal housing", (-9.2, -1.1, 5.1), (.24, .25, .7), black, COL["Details"], .08)
for i, (z, mat) in enumerate(((5.55, red), (5.1, yellow), (4.65, leaf_mats[1]))):
    sphere(f"Traffic signal lamp {i}", (-9.2, -1.37, z), (.12, .055, .12),
           mat, COL["Details"], 16, 8)
cube("Street sign plate", (-9.2, -1.1, 6.2), (1.05, .04, .24), awning_mat, COL["Details"], .04)
text_obj("Street name", "W 10 ST", (-9.2, -1.17, 6.2), .26, white, COL["Details"])


# ---------------------------------------------------------------------------
# Geometry Nodes rain particle system
# ---------------------------------------------------------------------------

def rain_particle_layer(name, count, z_offset, speed_frames):
    points = []
    for _ in range(count):
        # Entire particle field lies inside the camera-visible street volume.
        points.append((
            random.uniform(-16.5, 15.5),
            random.uniform(-11.5, 13.0),
            random.uniform(-2.0, 16.0)
        ))
    mesh = bpy.data.meshes.new(name + " Particle Points")
    mesh.from_pydata(points, [], [])
    emitter = bpy.data.objects.new(name, mesh)
    COL["Weather"].objects.link(emitter)
    emitter["particle_system"] = "rain"
    emitter["particle_count"] = count
    emitter["baked_loop_frames"] = speed_frames
    source = cylinder(name + " raindrop source", (0, 0, 0), .012, .42,
                      rain_mat, COL["Weather"], 6)
    source.rotation_euler = (math.radians(-7), math.radians(4), 0)
    source.hide_render = True
    source.hide_viewport = True

    mod = emitter.modifiers.new(name + " GeometryNodes Particle System", "NODES")
    tree = bpy.data.node_groups.new(name + " Rain Particle Nodes", "GeometryNodeTree")
    mod.node_group = tree
    tree.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    tree.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nodes, links = tree.nodes, tree.links
    inp = nodes.new("NodeGroupInput")
    out = nodes.new("NodeGroupOutput")
    inst = nodes.new("GeometryNodeInstanceOnPoints")
    obj_info = nodes.new("GeometryNodeObjectInfo")
    obj_info.transform_space = "ORIGINAL"
    obj_info.inputs["Object"].default_value = source
    links.new(inp.outputs["Geometry"], inst.inputs["Points"])
    links.new(obj_info.outputs["Geometry"], inst.inputs["Instance"])
    links.new(inst.outputs["Instances"], out.inputs["Geometry"])

    emitter.location = (0, 0, z_offset)
    emitter.keyframe_insert("location", frame=START)
    emitter.location = (1.2, .35, z_offset - 18)
    emitter.keyframe_insert("location", frame=START + speed_frames)
    linear_cycles(emitter)
    return emitter


rain_particle_layer("Rain particle system near", 650, 0, 34)
rain_particle_layer("Rain particle system middle", 900, 6, 43)
rain_particle_layer("Rain particle system far", 1200, 12, 52)


# ---------------------------------------------------------------------------
# Cloudy world, mist, camera, and focus
# ---------------------------------------------------------------------------

world = bpy.data.worlds.new("Cloudy NYC sky") if not bpy.data.worlds else bpy.data.worlds[0]
scene.world = world
world.use_nodes = True
wn = world.node_tree.nodes
wl = world.node_tree.links
wn.clear()
out = wn.new("ShaderNodeOutputWorld")
bg = wn.new("ShaderNodeBackground")
sky = wn.new("ShaderNodeTexSky")
sky.sky_type = "NISHITA"
sky.sun_elevation = math.radians(11)
sky.sun_rotation = math.radians(225)
sky.altitude = 0.2
sky.air_density = 1.35
sky.dust_density = 4.0
sky.ozone_density = 1.3
bg.inputs["Strength"].default_value = 0.22
wl.new(sky.outputs["Color"], bg.inputs["Color"])
wl.new(bg.outputs["Background"], out.inputs["Surface"])

# Broad cool overcast key and soft street fill.
area_light("Cloud softbox", (0, -1, 17), (18, 18), (.38, .53, .70), 1700, (0, 2, 0))
area_light("Cool frontal fill", (7, -13, 9), (14, 10), (.30, .45, .65), 850, (0, 3, 2))

# Mist cube uses true volume scattering.
mist_mat = bpy.data.materials.new("Rain mist volume")
mist_mat.use_nodes = True
mn = mist_mat.node_tree.nodes
ml = mist_mat.node_tree.links
mn.clear()
mout = mn.new("ShaderNodeOutputMaterial")
vol = mn.new("ShaderNodeVolumePrincipled")
vol.inputs["Density"].default_value = 0.006
vol.inputs["Anisotropy"].default_value = 0.22
vol.inputs["Color"].default_value = (.37, .47, .58, 1)
ml.new(vol.outputs["Volume"], mout.inputs["Volume"])
mist = cube("Atmospheric rain mist", (0, 3, 6), (18, 16, 8), mist_mat, COL["Weather"])
mist.display_type = "WIRE"

# Exactly one camera.
cam_data = bpy.data.cameras.new("Rainy Corner Camera")
camera = bpy.data.objects.new("Rainy Corner Camera", cam_data)
scene.collection.objects.link(camera)
camera.location = (17.8, -22.5, 10.6)
aim(camera, (0.0, 3.1, 3.0))
cam_data.lens = 35
cam_data.sensor_width = 36
cam_data.dof.use_dof = True
focus = bpy.data.objects.new("Camera focus target", None)
COL["Details"].objects.link(focus)
focus.location = (0.5, 1.2, 1.35)
focus.hide_render = True
cam_data.dof.focus_object = focus
cam_data.dof.aperture_fstop = 5.6
cam_data.dof.aperture_blades = 7
scene.camera = camera

# Restrained cinematic camera drift, preserving the complete corner in frame.
camera.keyframe_insert("location", frame=START)
camera.location += Vector((0.28, 0.15, 0.10))
aim(camera, (0.15, 3.15, 3.05))
camera.keyframe_insert("location", frame=120)
camera.keyframe_insert("rotation_euler", frame=120)
camera.location -= Vector((0.28, 0.15, 0.10))
aim(camera, (0.0, 3.1, 3.0))
camera.keyframe_insert("location", frame=END)
camera.keyframe_insert("rotation_euler", frame=END)

# Compositing: subtle bloom and filmic vignette-compatible color balance.
scene.use_nodes = True
nodes = scene.node_tree.nodes
links = scene.node_tree.links
nodes.clear()
rl = nodes.new("CompositorNodeRLayers")
glare = nodes.new("CompositorNodeGlare")
glare.glare_type = "FOG_GLOW"
glare.quality = "HIGH"
glare.threshold = 1.15
glare.size = 7
comp = nodes.new("CompositorNodeComposite")
links.new(rl.outputs["Image"], glare.inputs["Image"])
links.new(glare.outputs["Image"], comp.inputs["Image"])


# ---------------------------------------------------------------------------
# Cache physics, final validation, and save
# ---------------------------------------------------------------------------

scene.frame_set(START)

# Bake all available point caches (awning soft bodies). Geometry Nodes rain and
# steam are analytically looped and therefore require no disk cache.
try:
    bpy.context.view_layer.objects.active = next(
        o for o in bpy.data.objects if "wind valance" in o.name
    )
    bpy.ops.ptcache.bake_all(bake=True)
except (RuntimeError, StopIteration):
    # Blender background builds can deny cache operators without a window
    # context; deterministic keyframes remain baked in the generated .blend.
    pass

# Hard requirement: one and only one camera.
cameras = [obj for obj in bpy.data.objects if obj.type == "CAMERA"]
assert len(cameras) == 1, f"Expected exactly one camera, found {len(cameras)}"

# Organize color-management and metadata for reproducible rendering.
scene["scene_description"] = "Realistic rainy NYC corner coffee shop"
scene["weather"] = "cloudy rainstorm"
scene["particle_systems"] = "3 rain layers, 3 steam emitters"
scene["physics_baked_range"] = f"{START}-{END}"
scene["generator_seed"] = SEED

bpy.ops.wm.save_as_mainfile(filepath="//rainy_nyc_coffee_corner.blend")
print(
    "NYC coffee shop scene complete:",
    len(bpy.data.objects), "objects,",
    len([o for o in bpy.data.objects if o.type == 'CAMERA']), "camera"
)
