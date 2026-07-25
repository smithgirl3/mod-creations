"""
create_realistic_cat.py
=======================

Procedurally builds an extremely realistic, render-ready domestic cat scene
for **Blender 5.2.0** (Cycles).

The script creates, entirely in code (no external assets, everything is
procedural):

  1. Anatomically shaped cat body (skull, muzzle, brow ridges, cheeks,
     whisker pads, eyelids, muscle volumes, legs, paws, tapered tail, ears)
     built from a metaball "armature", voxel-remeshed into a single organic
     mesh and refined with smoothing, procedural displacement and a
     geometry-nodes micro-detail modifier.
  2. Separate mesh objects for the body, eyes (sclera/iris + cornea +
     wet-line), whiskers, nose and inner mouth (teeth, tongue, cavity).
  3. A three-layer particle fur system (dense undercoat, longer guard
     hairs, tactile whiskers) with per-strand variation in length,
     thickness, clumping, kink and randomness, driven by procedurally
     painted vertex groups, shaded with the Principled Hair BSDF
     (melanin parametrization, root->tip variation, agouti banding,
     per-strand random color/roughness).
  4. A procedural mackerel-tabby coat pattern shared by the skin shader and
     the fur shaders so the pelt reads correctly through the hair.
  5. PBR feline skin with subsurface scattering, micro-normal pore bumps,
     paw-pad/belly color variation and ear translucency.
  6. Physically based eyes: SSS sclera, radial-fiber iris with true shader
     displacement, vertical slit pupil, IOR-1.376 refractive cornea with a
     shadow-ray bypass, and a glossy wet-line meniscus for eyelid
     reflections.
  7. Photoreal lighting: procedural multiple-scattering sky environment
     (HDRI-style image-based lighting), soft warm key, cool rim for fur
     highlights and a gentle fill, plus a ground plane.
  8. Cycles path tracing configured for maximum quality: 2048+ samples,
     OpenImageDenoise (albedo+normal, accurate prefilter), light tree,
     thick 3D hair curves, caustics enabled and a DOF portrait camera.

Usage
-----
    blender -b -P create_realistic_cat.py            # build scene only
    blender -b -P create_realistic_cat.py -- --render  # build + render
    blender -P create_realistic_cat.py               # build in the UI

The scene is left fully render-ready: press F12 (or pass ``--render``) to
produce the final image at ``//cat_render.png``.
"""

import math
import random
import sys

import bpy
from mathutils import Euler, Vector

random.seed(4711)

# ---------------------------------------------------------------------------
# Global anatomical landmarks (metres, cat faces +Y, up is +Z, ground z=0)
# ---------------------------------------------------------------------------
EYE_R = 0.0098                       # eyeball radius
EYE_POS = {                          # eye centres (recessed into the skull)
    'L': Vector(( 0.0195, 0.2915, 0.334)),
    'R': Vector((-0.0195, 0.2915, 0.334)),
}
NOSE_POS = Vector((0.0, 0.341, 0.310))
MOUTH_POS = Vector((0.0, 0.306, 0.287))
WHISKER_PAD = {                      # centre of each whisker pad
    'L': Vector(( 0.0135, 0.333, 0.302)),
    'R': Vector((-0.0135, 0.333, 0.302)),
}
HEAD_TARGET = Vector((0.0, 0.30, 0.33))   # camera aim point


# ---------------------------------------------------------------------------
# Small node helpers (robust against socket-name changes between versions)
# ---------------------------------------------------------------------------
def new_node(nt, bl_idname, location=(0.0, 0.0), **attrs):
    node = nt.nodes.new(bl_idname)
    node.location = location
    for key, value in attrs.items():
        try:
            setattr(node, key, value)
        except Exception:
            pass
    return node


def set_in(node, key, value):
    """Set a node input by (candidate) name or integer index, silently
    skipping sockets that do not exist in this Blender version."""
    candidates = key if isinstance(key, (list, tuple)) else [key]
    for cand in candidates:
        try:
            if isinstance(cand, int):
                node.inputs[cand].default_value = value
                return True
            for inp in node.inputs:
                if inp.name == cand:
                    inp.default_value = value
                    return True
        except Exception:
            continue
    return False


def get_in(node, key):
    if isinstance(key, int):
        return node.inputs[key]
    for inp in node.inputs:
        if inp.name == key:
            return inp
    raise KeyError(f"No input '{key}' on node {node.bl_idname}")


def safe_set(obj, attr, value):
    try:
        setattr(obj, attr, value)
        return True
    except Exception:
        return False


def math_node(nt, op, a, b=None, loc=(0, 0), clamp=False):
    """Create a math node; a/b may be sockets or floats. Returns output."""
    n = new_node(nt, 'ShaderNodeMath', loc, operation=op)
    n.use_clamp = clamp
    for idx, val in enumerate((a, b)):
        if val is None:
            continue
        if hasattr(val, 'is_linked'):          # it's a socket
            nt.links.new(val, n.inputs[idx])
        else:
            n.inputs[idx].default_value = val
    return n.outputs[0]


def mix_color(nt, fac, col_a, col_b, loc=(0, 0)):
    """Color mix using the modern Mix node.  fac/col_* may be sockets or
    plain values.  Returns the color result socket."""
    n = new_node(nt, 'ShaderNodeMix', loc, data_type='RGBA')
    # Resolve sockets by name + type so this is robust across versions.
    fac_in = next(s for s in n.inputs if s.name == 'Factor'
                  and s.type == 'VALUE')
    a_in = next(s for s in n.inputs if s.name == 'A' and s.type == 'RGBA')
    b_in = next(s for s in n.inputs if s.name == 'B' and s.type == 'RGBA')
    result = next(s for s in n.outputs if s.type == 'RGBA')
    for sock, val in ((fac_in, fac), (a_in, col_a), (b_in, col_b)):
        if hasattr(val, 'is_linked'):
            nt.links.new(val, sock)
        else:
            sock.default_value = val
    return result


def map_range(nt, value, fmin, fmax, tmin, tmax, loc=(0, 0),
              interp='LINEAR', clamp=True):
    n = new_node(nt, 'ShaderNodeMapRange', loc)
    safe_set(n, 'interpolation_type', interp)
    n.clamp = clamp
    if hasattr(value, 'is_linked'):
        nt.links.new(value, get_in(n, 'Value'))
    else:
        set_in(n, 'Value', value)
    set_in(n, 'From Min', fmin)
    set_in(n, 'From Max', fmax)
    set_in(n, 'To Min', tmin)
    set_in(n, 'To Max', tmax)
    return n.outputs[0]


def color_ramp(nt, fac, stops, loc=(0, 0), interpolation='LINEAR'):
    """stops = [(position, (r,g,b,a)), ...]; returns (color_out, alpha_out)."""
    n = new_node(nt, 'ShaderNodeValToRGB', loc)
    ramp = n.color_ramp
    ramp.interpolation = interpolation
    # Reuse the two default elements, add the rest.
    while len(ramp.elements) > len(stops):
        ramp.elements.remove(ramp.elements[-1])
    while len(ramp.elements) < len(stops):
        ramp.elements.new(stops[len(ramp.elements) - 1][0])
    for elem, (pos, col) in zip(ramp.elements, stops):
        elem.position = pos
        elem.color = col
    nt.links.new(fac, n.inputs['Fac'])
    return n.outputs['Color'], n.outputs['Alpha']


def fresh_material(name):
    mat = bpy.data.materials.new(name)
    if mat.node_tree is None and hasattr(mat, 'use_nodes'):
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    return mat, nt


# ---------------------------------------------------------------------------
# Scene reset
# ---------------------------------------------------------------------------
def reset_scene():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for block_coll in (bpy.data.meshes, bpy.data.materials, bpy.data.curves,
                       bpy.data.metaballs, bpy.data.lights, bpy.data.cameras,
                       bpy.data.particles, bpy.data.textures,
                       bpy.data.node_groups, bpy.data.worlds):
        for block in list(block_coll):
            if block.users == 0:
                block_coll.remove(block)
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.0


def select_only(objs):
    bpy.ops.object.select_all(action='DESELECT')
    if not isinstance(objs, (list, tuple)):
        objs = [objs]
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


# ---------------------------------------------------------------------------
# 1. Body: metaball anatomy -> voxel remesh -> organic refinement
# ---------------------------------------------------------------------------
def _metaball_anatomy():
    """Return a list of (position, radius) metaball elements describing the
    full cat anatomy. Mirrored elements are expanded automatically."""
    E = []

    def add(co, r, mirror=False):
        E.append((Vector(co), r))
        if mirror:
            E.append((Vector((-co[0], co[1], co[2])), r))

    # --- torso / muscle masses -------------------------------------------
    add((0.0,  0.085, 0.245), 0.085)          # chest & shoulder mass
    add((0.0,  0.000, 0.238), 0.082)          # rib cage
    add((0.0, -0.080, 0.235), 0.080)          # abdomen
    add((0.0, -0.160, 0.232), 0.078)          # hindquarters
    add((0.050, -0.170, 0.205), 0.055, True)  # haunch (thigh muscle bulge)
    add((0.045,  0.090, 0.220), 0.045, True)  # deltoid / shoulder bulge
    add((0.0,  0.045, 0.205), 0.070)          # sternum / lower chest

    # --- neck & skull ------------------------------------------------------
    add((0.0, 0.155, 0.272), 0.056)           # neck base
    add((0.0, 0.200, 0.300), 0.048)           # upper neck
    add((0.0, 0.235, 0.325), 0.048)           # occiput (back of skull)
    add((0.0, 0.262, 0.332), 0.052)           # cranium
    add((0.028, 0.285, 0.315), 0.026, True)   # cheek (zygomatic) volume
    add((0.020, 0.292, 0.351), 0.016, True)   # brow ridge
    add((0.0, 0.315, 0.305), 0.024)           # muzzle
    add((0.0, 0.332, 0.300), 0.017)           # muzzle tip
    add((0.013, 0.331, 0.302), 0.010, True)   # whisker pad
    add((0.0, 0.325, 0.284), 0.013)           # chin
    add((0.0, 0.318, 0.287), 0.013)           # lower lip
    add((0.0, 0.306, 0.288), 0.018)           # lower jaw

    # --- forelegs (dense overlapping chain so the limb stays connected) ----
    add((0.042, 0.090, 0.150), 0.037, True)   # upper foreleg / triceps
    add((0.042, 0.090, 0.115), 0.033, True)
    add((0.042, 0.092, 0.088), 0.030, True)   # forearm
    add((0.042, 0.094, 0.062), 0.028, True)
    add((0.042, 0.098, 0.038), 0.027, True)   # lower foreleg
    add((0.042, 0.106, 0.016), 0.024, True)   # front paw heel
    add((0.042, 0.122, 0.014), 0.020, True)   # front paw toes

    # --- hind legs ----------------------------------------------------------
    add((0.050, -0.172, 0.150), 0.047, True)  # thigh
    add((0.050, -0.185, 0.115), 0.036, True)
    add((0.050, -0.193, 0.088), 0.031, True)  # lower leg / hock
    add((0.050, -0.196, 0.062), 0.028, True)
    add((0.050, -0.192, 0.038), 0.026, True)  # cannon
    add((0.050, -0.166, 0.016), 0.024, True)  # hind paw heel
    add((0.050, -0.144, 0.014), 0.020, True)  # hind paw toes

    # --- tapered tail (S-curve) --------------------------------------------
    n_seg = 11
    for i in range(n_seg):
        t = i / (n_seg - 1)
        y = -0.235 - 0.285 * t
        z = 0.225 - 0.095 * t + 0.130 * t * t
        x = 0.012 * math.sin(t * math.pi * 1.5)
        r = 0.0205 * (1.0 - 0.62 * t) + 0.004
        add((x, y, z), r)

    return E


def build_body():
    """Metaball anatomy -> mesh, unified with ears & eyelid rings via voxel
    remesh, then organically refined."""
    # -- metaball ------------------------------------------------------------
    mball = bpy.data.metaballs.new("CatMeta")
    mball.resolution = 0.006
    mball.render_resolution = 0.006
    mobj = bpy.data.objects.new("CatMeta", mball)
    bpy.context.collection.objects.link(mobj)
    for co, r in _metaball_anatomy():
        ele = mball.elements.new()
        ele.type = 'BALL'
        ele.co = co
        ele.radius = r

    select_only(mobj)
    bpy.ops.object.convert(target='MESH')
    body = bpy.context.view_layer.objects.active
    body.name = "CatBody"
    body.data.name = "CatBody"

    # -- ears (flattened cones, fused during remesh) -------------------------
    parts = []
    for side in (1, -1):
        bpy.ops.mesh.primitive_cone_add(
            vertices=48, radius1=0.023, radius2=0.0015, depth=0.058,
            location=(side * 0.031, 0.243, 0.392))
        ear = bpy.context.view_layer.objects.active
        ear.scale = (1.0, 0.42, 1.0)                    # flatten front-back
        ear.rotation_euler = Euler((math.radians(-12),
                                    side * math.radians(18),
                                    side * math.radians(-8)), 'XYZ')
        parts.append(ear)

    # -- eyelid rings (fused ridges around the eye sockets) ------------------
    for key in ('L', 'R'):
        pos = EYE_POS[key].copy()
        pos.y -= 0.0025
        bpy.ops.mesh.primitive_torus_add(
            major_radius=0.0118, minor_radius=0.0062,
            major_segments=48, minor_segments=16,
            location=pos, rotation=(math.radians(90), 0, 0))
        parts.append(bpy.context.view_layer.objects.active)

    select_only([body] + parts)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.join()

    # -- unify everything into a single organic surface ----------------------
    body.data.remesh_voxel_size = 0.0032
    body.data.remesh_voxel_adaptivity = 0.0
    select_only(body)
    bpy.ops.object.voxel_remesh()
    bpy.ops.object.shade_smooth()

    # -- organic refinement stack --------------------------------------------
    smooth = body.modifiers.new("OrganicSmooth", 'SMOOTH')
    smooth.factor = 0.55
    smooth.iterations = 4

    # low-frequency muscle/skin unevenness
    disp_tex = bpy.data.textures.new("CatSkinUneven", 'CLOUDS')
    disp_tex.noise_scale = 0.09
    disp_tex.noise_depth = 3
    disp = body.modifiers.new("MuscleDetail", 'DISPLACE')
    disp.texture = disp_tex
    disp.strength = 0.0022
    disp.mid_level = 0.5

    subsurf = body.modifiers.new("Subdivision", 'SUBSURF')
    subsurf.levels = 1
    subsurf.render_levels = 2

    # geometry-nodes micro displacement (pores / fine skin breakup)
    gn = build_micro_detail_nodegroup()
    gn_mod = body.modifiers.new("SkinMicroDetail", 'NODES')
    gn_mod.node_group = gn

    return body


def build_micro_detail_nodegroup():
    """Geometry Nodes group: displace along the normal with fine procedural
    noise to break up the mathematically smooth surface."""
    gn = bpy.data.node_groups.new("CatSkinMicroDetail", 'GeometryNodeTree')
    gn.interface.new_socket("Geometry", in_out='INPUT',
                            socket_type='NodeSocketGeometry')
    gn.interface.new_socket("Geometry", in_out='OUTPUT',
                            socket_type='NodeSocketGeometry')

    n_in = new_node(gn, 'NodeGroupInput', (-600, 0))
    n_out = new_node(gn, 'NodeGroupOutput', (400, 0))
    set_pos = new_node(gn, 'GeometryNodeSetPosition', (200, 0))
    normal = new_node(gn, 'GeometryNodeInputNormal', (-600, -200))
    noise = new_node(gn, 'ShaderNodeTexNoise', (-400, -200))
    set_in(noise, 'Scale', 140.0)
    set_in(noise, 'Detail', 6.0)
    set_in(noise, 'Roughness', 0.55)

    centered = math_node(gn, 'SUBTRACT', noise.outputs['Fac'], 0.5,
                         (-200, -200))
    amount = math_node(gn, 'MULTIPLY', centered, 0.0008, (-40, -200))
    scale_vec = new_node(gn, 'ShaderNodeVectorMath', (60, -120),
                         operation='SCALE')
    gn.links.new(normal.outputs['Normal'], scale_vec.inputs[0])
    gn.links.new(amount, scale_vec.inputs['Scale'])

    gn.links.new(n_in.outputs['Geometry'], set_pos.inputs['Geometry'])
    gn.links.new(scale_vec.outputs['Vector'], set_pos.inputs['Offset'])
    gn.links.new(set_pos.outputs['Geometry'], n_out.inputs['Geometry'])
    return gn


# ---------------------------------------------------------------------------
# 2. Vertex groups controlling fur density / length / whisker emission
# ---------------------------------------------------------------------------
def smoothstep(edge0, edge1, x):
    t = max(0.0, min(1.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def paint_fur_vertex_groups(body):
    vg_density = body.vertex_groups.new(name="FurDensity")
    vg_length = body.vertex_groups.new(name="FurLength")
    vg_whisker = body.vertex_groups.new(name="WhiskerRegion")

    eye_l, eye_r = EYE_POS['L'], EYE_POS['R']
    pad_l, pad_r = WHISKER_PAD['L'], WHISKER_PAD['R']

    for v in body.data.vertices:
        co = v.co

        # ---- density: bald around eyes, nose leather, lips, paw soles -----
        w = 1.0
        d_eye = min((co - eye_l).length, (co - eye_r).length)
        w *= smoothstep(0.010, 0.016, d_eye)
        d_nose = (co - NOSE_POS).length
        w *= 0.12 + 0.88 * smoothstep(0.006, 0.013, d_nose)
        d_mouth = (co - MOUTH_POS).length
        w *= 0.35 + 0.65 * smoothstep(0.006, 0.014, d_mouth)
        if co.z < 0.008:                                   # paw soles / pads
            w *= 0.15
        vg_density.add([v.index], w, 'REPLACE')

        # ---- length: plush torso & tail, short face and lower legs --------
        length = 0.55
        # torso
        if -0.24 < co.y < 0.16 and co.z > 0.12:
            length = 0.95
        # tail gets bushy
        if co.y < -0.25:
            length = 1.0
        # face shortens toward the muzzle
        face_fac = smoothstep(0.20, 0.32, co.y)
        length = length * (1.0 - face_fac) + 0.22 * face_fac
        # lower legs & paws short
        leg_fac = 1.0 - smoothstep(0.04, 0.14, co.z)
        length = length * (1.0 - leg_fac) + 0.45 * leg_fac
        vg_length.add([v.index], max(0.05, min(1.0, length)), 'REPLACE')

        # ---- whisker pad emission region -----------------------------------
        d_pad = min((co - pad_l).length, (co - pad_r).length)
        w_whisk = 1.0 - smoothstep(0.006, 0.011, d_pad)
        if w_whisk > 0.0:
            vg_whisker.add([v.index], w_whisk, 'REPLACE')

    return vg_density, vg_length, vg_whisker


# ---------------------------------------------------------------------------
# 3. Eyes, nose, mouth, whiskers
# ---------------------------------------------------------------------------
def build_eyes():
    """Sclera+iris eyeball, refractive cornea and a glossy wet-line torus
    per eye. Object local +Y is the optical axis."""
    eyeballs, corneas, wetlines = [], [], []
    mat_eye = make_eyeball_material()
    mat_cornea = make_cornea_material()
    mat_wet = make_wetline_material()

    for key, side in (('L', 1), ('R', -1)):
        pos = EYE_POS[key]

        bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=32,
                                             radius=EYE_R, location=pos)
        eye = bpy.context.view_layer.objects.active
        eye.name = f"CatEyeball.{key}"
        eye.rotation_euler = Euler((0, 0, side * math.radians(-4)), 'XYZ')
        bpy.ops.object.shade_smooth()
        eye.data.materials.append(mat_eye)
        eyeballs.append(eye)

        cpos = pos.copy()
        cpos.y += 0.0009
        bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=32,
                                             radius=EYE_R * 1.03,
                                             location=cpos)
        cornea = bpy.context.view_layer.objects.active
        cornea.name = f"CatCornea.{key}"
        cornea.scale = (1.0, 1.12, 1.0)          # corneal bulge
        cornea.rotation_euler = Euler((0, 0, side * math.radians(-4)), 'XYZ')
        bpy.ops.object.shade_smooth()
        cornea.data.materials.append(mat_cornea)
        corneas.append(cornea)

        wpos = pos.copy()
        wpos.y += 0.0012
        bpy.ops.mesh.primitive_torus_add(major_radius=EYE_R * 0.99,
                                         minor_radius=0.0009,
                                         major_segments=48, minor_segments=12,
                                         location=wpos,
                                         rotation=(math.radians(90), 0, 0))
        wet = bpy.context.view_layer.objects.active
        wet.name = f"CatWetline.{key}"
        bpy.ops.object.shade_smooth()
        wet.data.materials.append(mat_wet)
        wetlines.append(wet)

    return eyeballs, corneas, wetlines


def build_nose():
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=1.0,
                                          location=NOSE_POS)
    nose = bpy.context.view_layer.objects.active
    nose.name = "CatNose"
    nose.scale = (0.0078, 0.0045, 0.0058)
    nose.rotation_euler = Euler((math.radians(-18), 0, 0), 'XYZ')
    bpy.ops.object.shade_smooth()
    nose.data.materials.append(make_nose_material())
    return nose


def build_mouth():
    """Inner mouth: dark cavity shell, tongue and teeth (canines +
    incisors). Mostly hidden behind the closed lips, as on a real cat."""
    objs = []

    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=16,
                                         radius=1.0, location=MOUTH_POS)
    cavity = bpy.context.view_layer.objects.active
    cavity.name = "CatMouthCavity"
    cavity.scale = (0.008, 0.010, 0.006)
    bpy.ops.object.shade_smooth()
    cavity.data.materials.append(make_mouth_material())
    objs.append(cavity)

    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=16,
                                         radius=1.0,
                                         location=(0, 0.300, 0.2875))
    tongue = bpy.context.view_layer.objects.active
    tongue.name = "CatTongue"
    tongue.scale = (0.0060, 0.008, 0.0030)
    bpy.ops.object.shade_smooth()
    tongue.data.materials.append(make_tongue_material())
    objs.append(tongue)

    teeth_parts = []
    mat_teeth = make_teeth_material()
    # upper canines (point down) and lower canines (point up)
    for side in (1, -1):
        for z, rot_x, y in ((0.2925, math.radians(180), 0.3210),
                            (0.2825, 0.0, 0.3190)):
            bpy.ops.mesh.primitive_cone_add(vertices=16, radius1=0.0021,
                                            radius2=0.0002, depth=0.0105,
                                            location=(side * 0.0085, y, z),
                                            rotation=(rot_x, 0, 0))
            tooth = bpy.context.view_layer.objects.active
            bpy.ops.object.shade_smooth()
            teeth_parts.append(tooth)
    # incisor rows
    for i in range(6):
        x = (i - 2.5) * 0.0022
        for z, rot_x in ((0.2895, math.radians(180)), (0.2820, 0.0)):
            bpy.ops.mesh.primitive_cone_add(vertices=10, radius1=0.0009,
                                            radius2=0.0002, depth=0.0038,
                                            location=(x, 0.3235, z + 0.002),
                                            rotation=(rot_x, 0, 0))
            tooth = bpy.context.view_layer.objects.active
            bpy.ops.object.shade_smooth()
            teeth_parts.append(tooth)

    select_only(teeth_parts)
    bpy.ops.object.join()
    teeth = bpy.context.view_layer.objects.active
    teeth.name = "CatTeeth"
    teeth.data.materials.append(mat_teeth)
    objs.append(teeth)
    return objs


def build_whiskers():
    """Explicit whisker geometry: tapered bezier tubes grown from the
    whisker pads plus superciliary (eyebrow) whiskers, converted to mesh."""
    curve = bpy.data.curves.new("CatWhiskers", 'CURVE')
    curve.dimensions = '3D'
    curve.bevel_depth = 0.00024
    curve.bevel_resolution = 4
    curve.use_fill_caps = True
    curve.resolution_u = 16

    def add_whisker(root, direction, length, sag):
        spline = curve.splines.new('BEZIER')
        spline.bezier_points.add(2)
        d = direction.normalized()
        p0 = root
        p1 = root + d * (length * 0.5) + Vector((0, 0, sag * 0.25))
        p2 = root + d * length + Vector((0, 0, sag))
        for pt, co, radius in zip(spline.bezier_points,
                                  (p0, p1, p2), (1.0, 0.55, 0.10)):
            pt.co = co
            pt.handle_left_type = pt.handle_right_type = 'AUTO'
            pt.radius = radius

    # mystacial whiskers (4 columns x 3 rows per side)
    for side in (1, -1):
        pad = WHISKER_PAD['L' if side > 0 else 'R']
        for row in range(3):
            for col in range(4):
                jitter = Vector((random.uniform(-0.0008, 0.0008),
                                 random.uniform(-0.0012, 0.0012),
                                 random.uniform(-0.0008, 0.0008)))
                root = Vector((pad.x + side * 0.0012,
                               pad.y - 0.005 + col * 0.0032,
                               pad.z - 0.0042 + row * 0.0042)) + jitter
                direction = Vector((side * 1.0,
                                    0.16 + col * 0.08 + random.uniform(-0.04, 0.04),
                                    0.02 + (row - 1) * 0.10 + random.uniform(-0.03, 0.03)))
                length = random.uniform(0.050, 0.080)
                sag = -random.uniform(0.006, 0.014)
                add_whisker(root, direction, length, sag)

    # superciliary (eyebrow) whiskers
    for side in (1, -1):
        eye = EYE_POS['L' if side > 0 else 'R']
        for i in range(3):
            root = Vector((eye.x + side * 0.004,
                           eye.y - 0.006 + i * 0.003,
                           eye.z + 0.013)) + Vector(
                               (random.uniform(-0.001, 0.001),
                                random.uniform(-0.001, 0.001), 0))
            direction = Vector((side * 0.45, 0.35,
                                0.85 + random.uniform(-0.1, 0.1)))
            add_whisker(root, direction, random.uniform(0.028, 0.042),
                        -random.uniform(0.001, 0.004))

    obj = bpy.data.objects.new("CatWhiskers", curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(make_whisker_material())
    select_only(obj)
    bpy.ops.object.convert(target='MESH')      # separate whisker mesh object
    whiskers = bpy.context.view_layer.objects.active
    bpy.ops.object.shade_smooth()
    return whiskers


# ---------------------------------------------------------------------------
# 4. Shared procedural coat pattern (mackerel tabby)
# ---------------------------------------------------------------------------
def coat_pattern(nt, loc=(-1200, 0)):
    """Build the tabby coat pattern from Generated coordinates and return a
    factor socket: 0 = pale ground colour, 1 = dark stripe."""
    x, y = loc
    tc = new_node(nt, 'ShaderNodeTexCoord', (x, y))
    mapping = new_node(nt, 'ShaderNodeMapping', (x + 180, y))
    nt.links.new(tc.outputs['Generated'], mapping.inputs['Vector'])

    wave = new_node(nt, 'ShaderNodeTexWave', (x + 380, y),
                    wave_type='BANDS', bands_direction='Y',
                    wave_profile='SIN')
    set_in(wave, 'Scale', 10.0)
    set_in(wave, 'Distortion', 5.5)
    set_in(wave, 'Detail', 3.0)
    set_in(wave, 'Detail Scale', 1.4)
    nt.links.new(mapping.outputs['Vector'], wave.inputs['Vector'])

    noise = new_node(nt, 'ShaderNodeTexNoise', (x + 380, y - 260))
    set_in(noise, 'Scale', 16.0)
    set_in(noise, 'Detail', 8.0)
    set_in(noise, 'Roughness', 0.6)
    nt.links.new(mapping.outputs['Vector'], noise.inputs['Vector'])

    mottling = math_node(nt, 'MULTIPLY', noise.outputs['Fac'], 0.45,
                         (x + 580, y - 220))
    combined = math_node(nt, 'ADD', wave.outputs['Fac'], mottling,
                         (x + 580, y - 60))
    stripe = map_range(nt, combined, 0.55, 0.95, 0.0, 1.0,
                       (x + 780, y), interp='SMOOTHSTEP')
    return stripe


# ---------------------------------------------------------------------------
# 5. Materials
# ---------------------------------------------------------------------------
def make_skin_material():
    """PBR feline skin: tabby-toned epidermis, SSS, pore micro-normals,
    darker paw pads, lighter belly and translucent ear cartilage."""
    mat, nt = fresh_material("CatSkin")
    out = new_node(nt, 'ShaderNodeOutputMaterial', (900, 0))
    bsdf = new_node(nt, 'ShaderNodeBsdfPrincipled', (400, 0))

    stripe = coat_pattern(nt, (-1600, 300))

    # base coat colours (skin shows the pattern under the fur)
    skin_col = mix_color(nt, stripe,
                         (0.42, 0.30, 0.20, 1.0),      # pale warm ground
                         (0.10, 0.065, 0.045, 1.0),    # dark stripe skin
                         (-500, 300))

    geo = new_node(nt, 'ShaderNodeNewGeometry', (-1300, -250))
    sep = new_node(nt, 'ShaderNodeSeparateXYZ', (-1100, -250))
    nt.links.new(geo.outputs['Position'], sep.inputs['Vector'])

    # belly / chest lightening (low z, but above the paws)
    belly_lo = map_range(nt, sep.outputs['Z'], 0.10, 0.22, 1.0, 0.0,
                         (-900, -180), interp='SMOOTHSTEP')
    belly_hi = map_range(nt, sep.outputs['Z'], 0.02, 0.09, 0.0, 1.0,
                         (-900, -340), interp='SMOOTHSTEP')
    belly_mask = math_node(nt, 'MULTIPLY', belly_lo, belly_hi, (-700, -250))
    belly_fac = math_node(nt, 'MULTIPLY', belly_mask, 0.55, (-560, -250))
    skin_col = mix_color(nt, belly_fac, skin_col,
                         (0.62, 0.52, 0.42, 1.0), (-340, 200))

    # paw pads: rosy-brown leather near the ground
    pad_mask = map_range(nt, sep.outputs['Z'], 0.012, 0.004, 0.0, 1.0,
                         (-900, -500), interp='SMOOTHSTEP')
    skin_col = mix_color(nt, pad_mask, skin_col,
                         (0.30, 0.13, 0.11, 1.0), (-160, 160))

    # subtle warm flush around the nose/muzzle
    muzzle_mask = map_range(nt, sep.outputs['Y'], 0.30, 0.345, 0.0, 1.0,
                            (-900, -660), interp='SMOOTHSTEP')
    muzzle_fac = math_node(nt, 'MULTIPLY', muzzle_mask, 0.35, (-700, -660))
    skin_col = mix_color(nt, muzzle_fac, skin_col,
                         (0.55, 0.34, 0.28, 1.0), (0, 120))

    nt.links.new(skin_col, get_in(bsdf, 'Base Color'))

    # subsurface scattering tuned for thin feline skin
    set_in(bsdf, 'Subsurface Weight', 0.30)
    set_in(bsdf, 'Subsurface Radius', (0.014, 0.006, 0.0035))
    set_in(bsdf, 'Subsurface Scale', 0.9)
    set_in(bsdf, 'Roughness', 0.55)
    set_in(bsdf, 'Specular IOR Level', 0.35)
    set_in(bsdf, 'IOR', 1.44)

    # pad roughness: pads are smoother/waxier
    rough = map_range(nt, pad_mask, 0.0, 1.0, 0.55, 0.35, (-160, -420))
    nt.links.new(rough, get_in(bsdf, 'Roughness'))

    # micro-normals: fine pores + coarser wrinkle breakup, chained bumps
    pore = new_node(nt, 'ShaderNodeTexNoise', (-600, -700))
    set_in(pore, 'Scale', 650.0)
    set_in(pore, 'Detail', 4.0)
    wrinkle = new_node(nt, 'ShaderNodeTexNoise', (-600, -930))
    set_in(wrinkle, 'Scale', 45.0)
    set_in(wrinkle, 'Detail', 6.0)
    set_in(wrinkle, 'Roughness', 0.65)

    bump1 = new_node(nt, 'ShaderNodeBump', (-300, -800))
    set_in(bump1, 'Strength', 0.10)
    set_in(bump1, 'Distance', 0.0004)
    nt.links.new(wrinkle.outputs['Fac'], bump1.inputs['Height'])
    bump2 = new_node(nt, 'ShaderNodeBump', (-80, -720))
    set_in(bump2, 'Strength', 0.05)
    set_in(bump2, 'Distance', 0.0002)
    nt.links.new(pore.outputs['Fac'], bump2.inputs['Height'])
    nt.links.new(bump1.outputs['Normal'], bump2.inputs['Normal'])
    nt.links.new(bump2.outputs['Normal'], get_in(bsdf, 'Normal'))

    # ear translucency (light through the pinna)
    ear_mask = map_range(nt, sep.outputs['Z'], 0.395, 0.435, 0.0, 1.0,
                         (200, -400), interp='SMOOTHSTEP')
    ear_fac = math_node(nt, 'MULTIPLY', ear_mask, 0.45, (380, -400))
    transl = new_node(nt, 'ShaderNodeBsdfTranslucent', (400, -560))
    set_in(transl, 'Color', (0.80, 0.45, 0.35, 1.0))
    mix_shader = new_node(nt, 'ShaderNodeMixShader', (680, 0))
    nt.links.new(ear_fac, mix_shader.inputs['Fac'])
    nt.links.new(bsdf.outputs['BSDF'], mix_shader.inputs[1])
    nt.links.new(transl.outputs['BSDF'], mix_shader.inputs[2])
    nt.links.new(mix_shader.outputs['Shader'], out.inputs['Surface'])
    return mat


def _fur_material(name, melanin_base, melanin_span, redness, tint,
                  roughness, radial_roughness, coat,
                  random_color, random_roughness):
    """Shared builder for the Principled Hair BSDF fur materials with
    coat-pattern melanin, root->tip variation, agouti ticking and
    per-strand randomness."""
    mat, nt = fresh_material(name)
    out = new_node(nt, 'ShaderNodeOutputMaterial', (1000, 0))
    hair = new_node(nt, 'ShaderNodeBsdfHairPrincipled', (700, 0))
    safe_set(hair, 'model', 'CHIANG')          # physically-based far-field
    hair.parametrization = 'MELANIN'

    set_in(hair, 'Melanin Redness', redness)
    set_in(hair, 'Tint', tint)
    set_in(hair, 'Roughness', roughness)
    set_in(hair, 'Radial Roughness', radial_roughness)
    set_in(hair, 'Coat', coat)
    set_in(hair, 'IOR', 1.55)
    set_in(hair, 'Offset', math.radians(2.0))
    set_in(hair, 'Random Color', random_color)
    set_in(hair, 'Random Roughness', random_roughness)

    # coat pattern sampled at the strand root (Generated coords are
    # inherited from the emitter surface for hair in Cycles)
    stripe = coat_pattern(nt, (-1600, 200))
    melanin = math_node(nt, 'MULTIPLY_ADD', stripe, melanin_span,
                        (-500, 200))
    # MULTIPLY_ADD: a*b + c
    melanin.node.inputs[2].default_value = melanin_base

    info = new_node(nt, 'ShaderNodeHairInfo', (-1200, -300))

    # root->tip: darker roots, sun-bleached tips
    root_fac = map_range(nt, info.outputs['Intercept'], 0.0, 1.0, 1.18, 0.78,
                         (-900, -300))
    melanin = math_node(nt, 'MULTIPLY', melanin, root_fac, (-300, 100))

    # agouti ticking: banded pigment along each strand on the pale ground
    band_phase = math_node(nt, 'MULTIPLY', info.outputs['Intercept'],
                           math.tau * 2.2, (-900, -480))
    band_sin = math_node(nt, 'SINE', band_phase, None, (-760, -480))
    band = math_node(nt, 'MULTIPLY_ADD', band_sin, 0.5, (-620, -480))
    band.node.inputs[2].default_value = 0.5
    ground_amt = math_node(nt, 'SUBTRACT', 1.0, stripe, (-620, -620))
    ticking = math_node(nt, 'MULTIPLY', band, ground_amt, (-480, -540))
    tick_fac = math_node(nt, 'MULTIPLY', ticking, 0.30, (-340, -540))
    tick_mul = math_node(nt, 'SUBTRACT', 1.0, tick_fac, (-200, -540))
    melanin = math_node(nt, 'MULTIPLY', melanin, tick_mul, (-60, 60))

    clamp = new_node(nt, 'ShaderNodeClamp', (120, 60))
    set_in(clamp, 'Min', 0.02)
    set_in(clamp, 'Max', 1.0)
    nt.links.new(melanin, clamp.inputs['Value'])
    nt.links.new(clamp.outputs['Result'], get_in(hair, 'Melanin'))

    # per-strand randomisation
    nt.links.new(info.outputs['Random'], get_in(hair, 'Random'))

    nt.links.new(hair.outputs['BSDF'], out.inputs['Surface'])
    return mat


def make_guard_fur_material():
    return _fur_material(
        "CatFur_Guard",
        melanin_base=0.35, melanin_span=0.52, redness=0.65,
        tint=(1.0, 0.90, 0.78, 1.0),
        roughness=0.22, radial_roughness=0.30, coat=0.10,
        random_color=0.55, random_roughness=0.30)


def make_undercoat_fur_material():
    return _fur_material(
        "CatFur_Undercoat",
        melanin_base=0.16, melanin_span=0.30, redness=0.50,
        tint=(1.0, 0.94, 0.86, 1.0),
        roughness=0.34, radial_roughness=0.42, coat=0.0,
        random_color=0.80, random_roughness=0.45)


def make_whisker_hair_material():
    """Near-white translucent keratin for the particle whiskers."""
    mat, nt = fresh_material("CatFur_Whisker")
    out = new_node(nt, 'ShaderNodeOutputMaterial', (400, 0))
    hair = new_node(nt, 'ShaderNodeBsdfHairPrincipled', (100, 0))
    safe_set(hair, 'model', 'CHIANG')
    hair.parametrization = 'MELANIN'
    set_in(hair, 'Melanin', 0.03)
    set_in(hair, 'Melanin Redness', 0.3)
    set_in(hair, 'Tint', (1.0, 0.98, 0.95, 1.0))
    set_in(hair, 'Roughness', 0.18)
    set_in(hair, 'Radial Roughness', 0.25)
    set_in(hair, 'IOR', 1.55)
    nt.links.new(hair.outputs['BSDF'], out.inputs['Surface'])
    return mat


def make_whisker_material():
    """Keratin shader for the explicit whisker tube meshes."""
    mat, nt = fresh_material("CatWhiskerMesh")
    out = new_node(nt, 'ShaderNodeOutputMaterial', (400, 0))
    bsdf = new_node(nt, 'ShaderNodeBsdfPrincipled', (100, 0))
    set_in(bsdf, 'Base Color', (0.90, 0.88, 0.85, 1.0))
    set_in(bsdf, 'Roughness', 0.32)
    set_in(bsdf, 'Subsurface Weight', 0.45)
    set_in(bsdf, 'Subsurface Radius', (0.002, 0.002, 0.0018))
    set_in(bsdf, 'Subsurface Scale', 0.5)
    set_in(bsdf, 'Specular IOR Level', 0.5)
    set_in(bsdf, 'IOR', 1.55)
    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat


def make_eyeball_material():
    """Procedural cat eye: SSS sclera, layered amber->green iris with radial
    fibers and true displacement, limbal ring and a vertical slit pupil.
    Optical axis is local +Y."""
    mat, nt = fresh_material("CatEyeball")
    safe_set(mat, 'displacement_method', 'BOTH')
    out = new_node(nt, 'ShaderNodeOutputMaterial', (1400, 0))
    bsdf = new_node(nt, 'ShaderNodeBsdfPrincipled', (1100, 0))

    tc = new_node(nt, 'ShaderNodeTexCoord', (-1600, 0))
    sep = new_node(nt, 'ShaderNodeSeparateXYZ', (-1400, 0))
    nt.links.new(tc.outputs['Object'], sep.inputs['Vector'])
    X, Y, Z = sep.outputs['X'], sep.outputs['Y'], sep.outputs['Z']

    # radial distance from the optical axis, normalised to the eye radius
    x2 = math_node(nt, 'MULTIPLY', X, X, (-1200, 150))
    z2 = math_node(nt, 'MULTIPLY', Z, Z, (-1200, 0))
    r2 = math_node(nt, 'ADD', x2, z2, (-1050, 80))
    r = math_node(nt, 'SQRT', r2, None, (-900, 80))
    r_norm = math_node(nt, 'DIVIDE', r, EYE_R, (-750, 80))

    # polar angle around the axis, for the radial iris fibers
    angle = math_node(nt, 'ARCTAN2', Z, X, (-1200, -200))

    # ---- vertical slit pupil (narrow in X, tall in Z) ----------------------
    px = math_node(nt, 'MULTIPLY', X, 4.5, (-1200, 320))
    px2 = math_node(nt, 'MULTIPLY', px, px, (-1050, 320))
    pz2 = math_node(nt, 'MULTIPLY', Z, Z, (-1050, 440))
    pr2 = math_node(nt, 'ADD', px2, pz2, (-900, 380))
    pr = math_node(nt, 'SQRT', pr2, None, (-750, 380))
    pr_norm = math_node(nt, 'DIVIDE', pr, EYE_R, (-600, 380))
    pupil_mask = map_range(nt, pr_norm, 0.50, 0.58, 1.0, 0.0,
                           (-450, 380), interp='SMOOTHSTEP')

    # ---- radial iris fibers -------------------------------------------------
    fib_ang = math_node(nt, 'MULTIPLY', angle, 14.0, (-1050, -200))
    fib_rad = math_node(nt, 'MULTIPLY', r_norm, 2.5, (-1050, -330))
    fib_vec = new_node(nt, 'ShaderNodeCombineXYZ', (-900, -260))
    nt.links.new(fib_ang, fib_vec.inputs['X'])
    nt.links.new(fib_rad, fib_vec.inputs['Y'])
    fibers = new_node(nt, 'ShaderNodeTexNoise', (-750, -260))
    set_in(fibers, 'Scale', 1.4)
    set_in(fibers, 'Detail', 7.0)
    set_in(fibers, 'Roughness', 0.62)
    nt.links.new(fib_vec.outputs['Vector'], fibers.inputs['Vector'])

    # ---- depth-layered iris colour (inner amber -> outer green) ------------
    iris_col, _ = color_ramp(
        nt, r_norm,
        [(0.40, (0.38, 0.21, 0.05, 1.0)),      # amber collarette
         (0.62, (0.20, 0.20, 0.06, 1.0)),      # hazel transition
         (0.85, (0.08, 0.16, 0.06, 1.0))],     # green periphery
        (-450, -60))
    # fiber modulation of the iris value
    fib_centered = math_node(nt, 'SUBTRACT', fibers.outputs['Fac'], 0.5,
                             (-450, -300))
    fib_amt = math_node(nt, 'MULTIPLY', fib_centered, 0.55, (-300, -300))
    fib_mul = math_node(nt, 'ADD', fib_amt, 1.0, (-160, -300))
    fib_vec3 = new_node(nt, 'ShaderNodeCombineXYZ', (-20, -300))
    for ax in ('X', 'Y', 'Z'):
        nt.links.new(fib_mul, fib_vec3.inputs[ax])
    iris_lit = new_node(nt, 'ShaderNodeVectorMath', (120, -160),
                        operation='MULTIPLY')
    nt.links.new(iris_col, iris_lit.inputs[0])
    nt.links.new(fib_vec3.outputs['Vector'], iris_lit.inputs[1])

    # limbal ring (dark rim where iris meets sclera)
    limbal = map_range(nt, r_norm, 0.76, 0.90, 0.0, 1.0,
                       (120, -420), interp='SMOOTHSTEP')
    limbal_dark = math_node(nt, 'MULTIPLY', limbal, 0.85, (280, -420))
    iris_final = mix_color(nt, limbal_dark,
                           iris_lit.outputs['Vector'],
                           (0.03, 0.03, 0.02, 1.0), (420, -120))

    # sclera (barely visible on cats)
    iris_mask = map_range(nt, r_norm, 0.90, 0.97, 1.0, 0.0,
                          (420, -420), interp='SMOOTHSTEP')
    with_sclera = mix_color(nt, iris_mask,
                            (0.28, 0.19, 0.15, 1.0),   # dark conjunctiva rim
                            iris_final, (620, -60))
    final_col = mix_color(nt, pupil_mask, with_sclera,
                          (0.005, 0.005, 0.006, 1.0), (820, 0))
    nt.links.new(final_col, get_in(bsdf, 'Base Color'))

    set_in(bsdf, 'Roughness', 0.50)
    set_in(bsdf, 'Specular IOR Level', 0.05)
    set_in(bsdf, 'Subsurface Weight', 0.05)
    set_in(bsdf, 'Subsurface Radius', (0.002, 0.001, 0.0008))
    set_in(bsdf, 'Subsurface Scale', 0.3)
    set_in(bsdf, 'IOR', 1.40)
    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])

    # ---- true iris displacement (fiber relief, fades at pupil & sclera) ---
    disp_zone = math_node(nt, 'MULTIPLY', iris_mask,
                          math_node(nt, 'SUBTRACT', 1.0, pupil_mask,
                                    (620, -560)),
                          (780, -560))
    disp_h = math_node(nt, 'MULTIPLY', fibers.outputs['Fac'], disp_zone,
                       (940, -560))
    disp = new_node(nt, 'ShaderNodeDisplacement', (1100, -560))
    set_in(disp, 'Midlevel', 0.5)
    set_in(disp, 'Scale', 0.00045)
    nt.links.new(disp_h, disp.inputs['Height'])
    nt.links.new(disp.outputs['Displacement'], out.inputs['Displacement'])
    return mat


def make_cornea_material():
    """Refractive cornea, IOR 1.376, with a shadow-ray bypass so it does not
    cast opaque shadows; smooth enough for caustic-like highlights."""
    mat, nt = fresh_material("CatCornea")
    out = new_node(nt, 'ShaderNodeOutputMaterial', (600, 0))
    bsdf = new_node(nt, 'ShaderNodeBsdfPrincipled', (100, 0))
    set_in(bsdf, 'Base Color', (1.0, 1.0, 1.0, 1.0))
    set_in(bsdf, 'Roughness', 0.0)
    set_in(bsdf, 'Transmission Weight', 1.0)
    set_in(bsdf, 'IOR', 1.376)                 # human/feline cornea IOR
    set_in(bsdf, 'Specular IOR Level', 0.5)

    lp = new_node(nt, 'ShaderNodeLightPath', (100, 300))
    transp = new_node(nt, 'ShaderNodeBsdfTransparent', (100, -250))
    mix = new_node(nt, 'ShaderNodeMixShader', (380, 0))
    nt.links.new(lp.outputs['Is Shadow Ray'], mix.inputs['Fac'])
    nt.links.new(bsdf.outputs['BSDF'], mix.inputs[1])
    nt.links.new(transp.outputs['BSDF'], mix.inputs[2])
    nt.links.new(mix.outputs['Shader'], out.inputs['Surface'])
    return mat


def make_wetline_material():
    """Glossy tear-film meniscus hugging the eyelid margin."""
    mat, nt = fresh_material("CatWetline")
    out = new_node(nt, 'ShaderNodeOutputMaterial', (400, 0))
    bsdf = new_node(nt, 'ShaderNodeBsdfPrincipled', (100, 0))
    set_in(bsdf, 'Base Color', (0.9, 0.9, 0.9, 1.0))
    set_in(bsdf, 'Roughness', 0.04)
    set_in(bsdf, 'Transmission Weight', 0.85)
    set_in(bsdf, 'IOR', 1.33)                  # tear fluid
    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat


def make_nose_material():
    """Nose leather: pink-brick colour, pebbled micro-bump, waxy coat."""
    mat, nt = fresh_material("CatNose")
    out = new_node(nt, 'ShaderNodeOutputMaterial', (600, 0))
    bsdf = new_node(nt, 'ShaderNodeBsdfPrincipled', (300, 0))
    set_in(bsdf, 'Base Color', (0.36, 0.15, 0.12, 1.0))
    set_in(bsdf, 'Roughness', 0.30)
    set_in(bsdf, 'Subsurface Weight', 0.25)
    set_in(bsdf, 'Subsurface Radius', (0.008, 0.0035, 0.002))
    set_in(bsdf, 'Subsurface Scale', 0.6)
    set_in(bsdf, 'Coat Weight', 0.15)          # moist sheen
    set_in(bsdf, 'Coat Roughness', 0.12)

    # pebbled nose-leather texture (voronoi cells + fine noise)
    voro = new_node(nt, 'ShaderNodeTexVoronoi', (-300, -200))
    set_in(voro, 'Scale', 750.0)
    set_in(voro, 'Randomness', 0.9)
    fine = new_node(nt, 'ShaderNodeTexNoise', (-300, -450))
    set_in(fine, 'Scale', 2200.0)
    set_in(fine, 'Detail', 3.0)
    bump1 = new_node(nt, 'ShaderNodeBump', (-60, -260))
    set_in(bump1, 'Strength', 0.35)
    set_in(bump1, 'Distance', 0.0003)
    nt.links.new(voro.outputs['Distance'], bump1.inputs['Height'])
    bump2 = new_node(nt, 'ShaderNodeBump', (120, -180))
    set_in(bump2, 'Strength', 0.12)
    set_in(bump2, 'Distance', 0.0001)
    nt.links.new(fine.outputs['Fac'], bump2.inputs['Height'])
    nt.links.new(bump1.outputs['Normal'], bump2.inputs['Normal'])
    nt.links.new(bump2.outputs['Normal'], get_in(bsdf, 'Normal'))
    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat


def make_teeth_material():
    mat, nt = fresh_material("CatTeeth")
    out = new_node(nt, 'ShaderNodeOutputMaterial', (400, 0))
    bsdf = new_node(nt, 'ShaderNodeBsdfPrincipled', (100, 0))
    set_in(bsdf, 'Base Color', (0.88, 0.85, 0.78, 1.0))
    set_in(bsdf, 'Roughness', 0.25)
    set_in(bsdf, 'Subsurface Weight', 0.35)
    set_in(bsdf, 'Subsurface Radius', (0.003, 0.0025, 0.002))
    set_in(bsdf, 'Subsurface Scale', 0.4)
    set_in(bsdf, 'Specular IOR Level', 0.55)
    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat


def make_tongue_material():
    mat, nt = fresh_material("CatTongue")
    out = new_node(nt, 'ShaderNodeOutputMaterial', (500, 0))
    bsdf = new_node(nt, 'ShaderNodeBsdfPrincipled', (200, 0))
    set_in(bsdf, 'Base Color', (0.70, 0.32, 0.35, 1.0))
    set_in(bsdf, 'Roughness', 0.42)
    set_in(bsdf, 'Subsurface Weight', 0.55)
    set_in(bsdf, 'Subsurface Radius', (0.009, 0.004, 0.0025))
    set_in(bsdf, 'Subsurface Scale', 0.7)
    # papillae bump
    noise = new_node(nt, 'ShaderNodeTexNoise', (-150, -250))
    set_in(noise, 'Scale', 400.0)
    set_in(noise, 'Detail', 4.0)
    bump = new_node(nt, 'ShaderNodeBump', (30, -200))
    set_in(bump, 'Strength', 0.25)
    set_in(bump, 'Distance', 0.0003)
    nt.links.new(noise.outputs['Fac'], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], get_in(bsdf, 'Normal'))
    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat


def make_mouth_material():
    mat, nt = fresh_material("CatMouthCavity")
    out = new_node(nt, 'ShaderNodeOutputMaterial', (400, 0))
    bsdf = new_node(nt, 'ShaderNodeBsdfPrincipled', (100, 0))
    set_in(bsdf, 'Base Color', (0.22, 0.07, 0.07, 1.0))
    set_in(bsdf, 'Roughness', 0.55)
    set_in(bsdf, 'Subsurface Weight', 0.3)
    set_in(bsdf, 'Subsurface Radius', (0.008, 0.003, 0.002))
    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat


def make_ground_material():
    mat, nt = fresh_material("Ground")
    out = new_node(nt, 'ShaderNodeOutputMaterial', (500, 0))
    bsdf = new_node(nt, 'ShaderNodeBsdfPrincipled', (200, 0))
    noise = new_node(nt, 'ShaderNodeTexNoise', (-200, 0))
    set_in(noise, 'Scale', 8.0)
    set_in(noise, 'Detail', 8.0)
    col, _ = color_ramp(nt, noise.outputs['Fac'],
                        [(0.3, (0.045, 0.040, 0.036, 1.0)),
                         (0.7, (0.085, 0.075, 0.065, 1.0))], (0, 0))
    nt.links.new(col, get_in(bsdf, 'Base Color'))
    set_in(bsdf, 'Roughness', 0.85)
    bump = new_node(nt, 'ShaderNodeBump', (0, -260))
    set_in(bump, 'Strength', 0.2)
    nt.links.new(noise.outputs['Fac'], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], get_in(bsdf, 'Normal'))
    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat


# ---------------------------------------------------------------------------
# 6. Fur particle systems
# ---------------------------------------------------------------------------
def _add_hair_system(body, name, *, count, length, material_slot,
                     vg_density=None, vg_length=None, seed=0,
                     children=0, child_viewport_percent=5,
                     clump=0.0, clump_shape=0.0,
                     rough_uniform=0.0, rough_uniform_size=1.0,
                     rough_endpoint=0.0, rough_end_shape=1.0,
                     rough_random=0.0, rough_random_size=1.0,
                     kink=None, kink_amplitude=0.0, kink_frequency=2.0,
                     radius_scale=0.0002, root_radius=1.0, tip_radius=0.0,
                     length_random=0.0, child_length=1.0,
                     child_radius=2.0, hair_step=5, render_step=5):
    """Create and fully configure one hair particle system on `body`."""
    body.modifiers.new(name, 'PARTICLE_SYSTEM')
    psys = body.particle_systems[-1]
    psys.name = name
    psys.seed = seed
    ps = psys.settings
    ps.name = name

    ps.type = 'HAIR'
    ps.count = count
    ps.hair_length = length
    ps.hair_step = hair_step
    safe_set(ps, 'use_advanced_hair', True)
    ps.emit_from = 'FACE'
    ps.distribution = 'JIT'
    ps.use_even_distribution = True
    ps.use_modifier_stack = True               # emit from the refined surface
    ps.use_hair_bspline = True
    ps.render_step = render_step
    ps.display_step = 3
    safe_set(ps, 'display_percentage', 10)

    # strand-level randomness
    safe_set(ps, 'length_random', length_random)

    # thickness / taper (metres via radius_scale)
    ps.radius_scale = radius_scale
    ps.root_radius = root_radius
    ps.tip_radius = tip_radius
    safe_set(ps, 'use_close_tip', True)

    # children for density & realism
    if children > 0:
        ps.child_type = 'INTERPOLATED'
        ps.rendered_child_count = children
        safe_set(ps, 'child_percent', child_viewport_percent)
        ps.child_length = child_length
        ps.child_radius = child_radius
        ps.clump_factor = clump
        ps.clump_shape = clump_shape
        # uniform (low-frequency) roughness
        ps.roughness_1 = rough_uniform
        ps.roughness_1_size = rough_uniform_size
        # random (high-frequency) roughness
        ps.roughness_2 = rough_random
        ps.roughness_2_size = rough_random_size
        ps.roughness_2_threshold = 0.0
        # endpoint flyaway
        ps.roughness_endpoint = rough_endpoint
        safe_set(ps, 'roughness_end_shape', rough_end_shape)
        if kink:
            ps.kink = kink
            ps.kink_amplitude = kink_amplitude
            ps.kink_frequency = kink_frequency
    else:
        ps.child_type = 'NONE'

    if vg_density:
        psys.vertex_group_density = vg_density
    if vg_length:
        psys.vertex_group_length = vg_length

    ps.material = material_slot                # 1-based material slot index
    return psys


def build_fur(body):
    """Three particle systems: dense soft undercoat, longer guard hairs and
    thick tactile whiskers, each with its own hair shader."""
    mat_skin = make_skin_material()
    mat_guard = make_guard_fur_material()
    mat_under = make_undercoat_fur_material()
    mat_whisk = make_whisker_hair_material()
    for m in (mat_skin, mat_guard, mat_under, mat_whisk):
        body.data.materials.append(m)
    # slots: 1=skin  2=guard  3=undercoat  4=whisker-hair

    # -- undercoat: short, dense, soft and curly -----------------------------
    _add_hair_system(
        body, "FurUndercoat",
        count=6500, length=0.015, material_slot=3, seed=11,
        vg_density="FurDensity", vg_length="FurLength",
        children=140, child_viewport_percent=4,
        clump=0.25, clump_shape=0.2,
        rough_uniform=0.003, rough_uniform_size=0.8,
        rough_random=0.006, rough_random_size=0.45,
        rough_endpoint=0.002, rough_end_shape=1.0,
        kink='CURL', kink_amplitude=0.0013, kink_frequency=5.0,
        radius_scale=0.00012, root_radius=1.0, tip_radius=0.05,
        length_random=0.30, child_length=0.95, child_radius=1.3)

    # -- guard hairs: longer, sleeker, carry the visible coat ---------------
    _add_hair_system(
        body, "FurGuard",
        count=4000, length=0.028, material_slot=2, seed=23,
        vg_density="FurDensity", vg_length="FurLength",
        children=80, child_viewport_percent=4,
        clump=0.10, clump_shape=-0.1,
        rough_uniform=0.004, rough_uniform_size=1.2,
        rough_random=0.004, rough_random_size=0.35,
        rough_endpoint=0.004, rough_end_shape=1.2,
        kink='WAVE', kink_amplitude=0.0007, kink_frequency=2.5,
        radius_scale=0.00020, root_radius=1.0, tip_radius=0.02,
        length_random=0.40, child_length=0.98, child_radius=1.5)

    # -- tactile whiskers grown from the whisker pads ------------------------
    _add_hair_system(
        body, "FurWhiskers",
        count=14, length=0.052, material_slot=4, seed=37,
        vg_density="WhiskerRegion",
        children=0,
        radius_scale=0.00045, root_radius=1.0, tip_radius=0.08,
        length_random=0.40, hair_step=6, render_step=5)


# ---------------------------------------------------------------------------
# 7. Lighting, world, camera, ground
# ---------------------------------------------------------------------------
def point_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()


def build_world():
    """Procedural multiple-scattering sky: physically based image-based
    environment lighting (HDRI-style) with a low warm sun."""
    world = bpy.data.worlds.new("CatWorld")
    if world.node_tree is None and hasattr(world, 'use_nodes'):
        world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    out = new_node(nt, 'ShaderNodeOutputWorld', (400, 0))
    bg = new_node(nt, 'ShaderNodeBackground', (150, 0))
    sky = new_node(nt, 'ShaderNodeTexSky', (-150, 0))
    safe_set(sky, 'sky_type', 'MULTIPLE_SCATTERING')
    safe_set(sky, 'sun_elevation', math.radians(16.0))
    safe_set(sky, 'sun_rotation', math.radians(215.0))   # sun behind-left
    safe_set(sky, 'sun_intensity', 1.0)
    safe_set(sky, 'sun_size', math.radians(1.2))
    safe_set(sky, 'altitude', 60.0)
    safe_set(sky, 'air_density', 1.0)
    safe_set(sky, 'ozone_density', 1.2)
    nt.links.new(sky.outputs['Color'], bg.inputs['Color'])
    set_in(bg, 'Strength', 0.12)
    nt.links.new(bg.outputs['Background'], out.inputs['Surface'])
    bpy.context.scene.world = world


def build_lights():
    # soft warm key light, camera-left
    key_data = bpy.data.lights.new("KeyLight", 'AREA')
    key_data.shape = 'SQUARE'
    key_data.size = 0.9
    key_data.energy = 55.0
    key_data.color = (1.0, 0.955, 0.90)
    key = bpy.data.objects.new("KeyLight", key_data)
    key.location = (0.95, 0.80, 0.80)
    bpy.context.collection.objects.link(key)
    point_at(key, HEAD_TARGET)

    # cool rim light from behind for fur-edge highlights
    rim_data = bpy.data.lights.new("RimLight", 'AREA')
    rim_data.shape = 'RECTANGLE'
    rim_data.size = 0.35
    rim_data.size_y = 0.9
    rim_data.energy = 90.0
    rim_data.color = (0.88, 0.93, 1.0)
    rim = bpy.data.objects.new("RimLight", rim_data)
    rim.location = (-0.65, -0.85, 0.85)
    bpy.context.collection.objects.link(rim)
    point_at(rim, (0.0, -0.05, 0.28))

    # broad dim fill to open the shadows
    fill_data = bpy.data.lights.new("FillLight", 'AREA')
    fill_data.shape = 'SQUARE'
    fill_data.size = 1.6
    fill_data.energy = 12.0
    fill_data.color = (0.92, 0.95, 1.0)
    fill = bpy.data.objects.new("FillLight", fill_data)
    fill.location = (-1.0, 0.9, 0.45)
    bpy.context.collection.objects.link(fill)
    point_at(fill, HEAD_TARGET)


def build_ground():
    bpy.ops.mesh.primitive_plane_add(size=60.0, location=(0, 0, 0))
    ground = bpy.context.view_layer.objects.active
    ground.name = "Ground"
    ground.data.materials.append(make_ground_material())
    return ground


def build_camera(eye_focus):
    cam_data = bpy.data.cameras.new("CatCamera")
    cam_data.lens = 55.0
    cam_data.sensor_width = 36.0
    cam_data.dof.use_dof = True
    cam_data.dof.focus_object = eye_focus
    cam_data.dof.aperture_fstop = 8.0
    cam_data.dof.aperture_blades = 9
    cam = bpy.data.objects.new("CatCamera", cam_data)
    cam.location = (0.95, 1.25, 0.50)
    bpy.context.collection.objects.link(cam)
    point_at(cam, (0.0, 0.16, 0.28))           # frame the whole cat
    bpy.context.scene.camera = cam
    return cam


# ---------------------------------------------------------------------------
# 8. Render configuration (Cycles, max quality)
# ---------------------------------------------------------------------------
def configure_render():
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    cy = scene.cycles

    # try GPU, gracefully fall back to CPU
    try:
        prefs = bpy.context.preferences.addons['cycles'].preferences
        for backend in ('OPTIX', 'CUDA', 'HIP', 'METAL', 'ONEAPI'):
            try:
                prefs.compute_device_type = backend
                prefs.get_devices()
                if any(d.type != 'CPU' for d in prefs.devices):
                    for d in prefs.devices:
                        d.use = True
                    cy.device = 'GPU'
                    break
            except Exception:
                continue
    except Exception:
        pass

    # path tracing, high quality
    cy.samples = 2048
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = 0.008
    safe_set(cy, 'use_light_tree', True)
    cy.max_bounces = 12
    cy.diffuse_bounces = 6
    cy.glossy_bounces = 6
    cy.transmission_bounces = 12
    cy.transparent_max_bounces = 32
    cy.caustics_reflective = True              # eye highlights
    cy.caustics_refractive = True
    cy.blur_glossy = 0.5
    cy.sample_clamp_indirect = 10.0

    # OpenImageDenoise
    cy.use_denoising = True
    safe_set(cy, 'denoiser', 'OPENIMAGEDENOISE')
    safe_set(cy, 'denoising_input_passes', 'RGB_ALBEDO_NORMAL')
    safe_set(cy, 'denoising_prefilter', 'ACCURATE')
    safe_set(cy, 'denoising_use_gpu', True)

    # hair rendering: true 3D curve primitives
    try:
        scene.cycles_curves.shape = 'THICK'
        scene.cycles_curves.subdivisions = 3
    except Exception:
        pass

    # output
    scene.render.resolution_x = 3840
    scene.render.resolution_y = 2160
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_depth = '16'
    scene.render.filepath = '//cat_render.png'
    scene.render.film_transparent = False

    # filmic-quality tonemapping
    safe_set(scene.view_settings, 'view_transform', 'AgX')
    try:
        scene.view_settings.look = 'AgX - Medium High Contrast'
    except Exception:
        pass
    scene.view_settings.exposure = 0.0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    reset_scene()

    body = build_body()
    paint_fur_vertex_groups(body)

    eyeballs, corneas, wetlines = build_eyes()
    nose = build_nose()
    mouth_objs = build_mouth()
    whiskers = build_whiskers()

    build_fur(body)

    # parent facial parts to the body so the model moves as one unit
    children = eyeballs + corneas + wetlines + [nose, whiskers] + mouth_objs
    select_only(children + [body])
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.parent_set(type='OBJECT', keep_transform=True)

    build_ground()
    build_world()
    build_lights()
    build_camera(eyeballs[0])
    configure_render()

    stats = (f"Cat built: {len(body.data.vertices)} body verts, "
             f"{len(body.particle_systems)} hair systems, "
             f"{len(bpy.data.materials)} materials")
    print(stats)

    if "--render" in sys.argv:
        bpy.ops.render.render(write_still=True)
        print(f"Rendered to {bpy.path.abspath(bpy.context.scene.render.filepath)}")


if __name__ == "__main__":
    main()
