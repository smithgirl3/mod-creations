"""Build a game-ready modern leather sectional in Blender 4.4.

Run from Blender's Scripting workspace.  The generated sofa uses real-world
dimensions, has UVs on every visible mesh, and is ready for selected-object
FBX export.
"""

import math
from pathlib import Path

import bpy


# ---------------------------------------------------------------------------
# Scene and export settings
# ---------------------------------------------------------------------------

# Dimensions are authored in inches here and converted to Blender's meters.
INCH = 0.0254
OVERALL_WIDTH = 120.0 * INCH
OVERALL_DEPTH = 90.0 * INCH
OVERALL_HEIGHT = 34.0 * INCH

# Leave disabled to build and select the asset without writing a file.
EXPORT_FBX = False
EXPORT_PATH = Path.home() / "modern_brown_leather_sectional.fbx"


def inches(value):
    """Convert inches to meters."""
    return value * INCH


def clear_scene():
    """Remove all existing objects, meshes, materials, and collections."""
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials):
        for datablock in list(datablocks):
            if datablock.users == 0:
                datablocks.remove(datablock)
    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)


def configure_scene():
    """Use metric storage while displaying dimensions in imperial units."""
    scene = bpy.context.scene
    scene.unit_settings.system = "IMPERIAL"
    scene.unit_settings.length_unit = "INCHES"
    scene.unit_settings.scale_length = 1.0
    scene.render.engine = "BLENDER_EEVEE_NEXT"


# ---------------------------------------------------------------------------
# Material creation
# ---------------------------------------------------------------------------


def make_leather_material():
    """Create a warm brown leather shader with subtle procedural grain."""
    material = bpy.data.materials.new("MAT_Brown_Leather")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (620, 0)
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.location = (340, 0)
    shader.inputs["Base Color"].default_value = (0.19, 0.055, 0.022, 1.0)
    shader.inputs["Roughness"].default_value = 0.34
    shader.inputs["Metallic"].default_value = 0.0
    if "Coat Weight" in shader.inputs:
        shader.inputs["Coat Weight"].default_value = 0.12
        shader.inputs["Coat Roughness"].default_value = 0.22

    noise = nodes.new("ShaderNodeTexNoise")
    noise.location = (-420, -120)
    noise.inputs["Scale"].default_value = 180.0
    noise.inputs["Detail"].default_value = 2.0
    noise.inputs["Roughness"].default_value = 0.7

    bump = nodes.new("ShaderNodeBump")
    bump.location = (80, -120)
    bump.inputs["Strength"].default_value = 0.16
    bump.inputs["Distance"].default_value = 0.001

    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    return material


def make_wood_material():
    """Create a low-gloss dark walnut material for the feet."""
    material = bpy.data.materials.new("MAT_Dark_Walnut")
    material.use_nodes = True
    shader = material.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (0.035, 0.014, 0.007, 1.0)
    shader.inputs["Roughness"].default_value = 0.28
    return material


def make_deck_material():
    """Create a very dark backing material for hidden frame undersides."""
    material = bpy.data.materials.new("MAT_Frame_Underside")
    material.use_nodes = True
    shader = material.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (0.028, 0.022, 0.018, 1.0)
    shader.inputs["Roughness"].default_value = 0.65
    return material


# ---------------------------------------------------------------------------
# Mesh, bevel, UV, and organization helpers
# ---------------------------------------------------------------------------


def move_to_collection(obj, collection):
    """Move an object from Blender's default collection to an asset group."""
    for old_collection in list(obj.users_collection):
        old_collection.objects.unlink(obj)
    collection.objects.link(obj)


def create_rounded_box(
    name,
    dimensions_inches,
    location_inches,
    material,
    collection,
    bevel_inches=0.75,
    bevel_segments=2,
):
    """Create a low-poly beveled box and apply its game-ready geometry."""
    bpy.ops.mesh.primitive_cube_add(
        size=1.0,
        location=tuple(inches(v) for v in location_inches),
    )
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = tuple(inches(v) for v in dimensions_inches)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    bevel = obj.modifiers.new(name="Edge_Rounding", type="BEVEL")
    bevel.width = inches(bevel_inches)
    bevel.segments = bevel_segments
    bevel.limit_method = "ANGLE"
    bevel.angle_limit = math.radians(30.0)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=bevel.name)

    # Weighted corner normals keep broad leather panels visually flat.
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    obj.data.set_sharp_from_angle(angle=math.radians(40.0))

    obj.data.materials.append(material)
    move_to_collection(obj, collection)
    return obj


def unwrap_object(obj):
    """Smart-project one object's final visible geometry into a UV map."""
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    if not obj.data.uv_layers:
        obj.data.uv_layers.new(name="UVMap")
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(
        angle_limit=math.radians(66.0),
        island_margin=0.03,
        area_weight=0.0,
        correct_aspect=True,
        scale_to_bounds=False,
    )
    bpy.ops.object.mode_set(mode="OBJECT")
    obj.select_set(False)


def join_objects(objects, joined_name):
    """Join compatible pieces while retaining material slots and UV maps."""
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    joined = bpy.context.object
    joined.name = joined_name
    return joined


def apply_transforms_with_world_origin(obj):
    """Bake transforms so each object has an identity transform at world zero."""
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)


def triangle_count(objects):
    """Return the exact triangle count implied by all final mesh polygons."""
    return sum(
        len(polygon.vertices) - 2
        for obj in objects
        if obj.type == "MESH"
        for polygon in obj.data.polygons
    )


# ---------------------------------------------------------------------------
# Sofa construction
# ---------------------------------------------------------------------------


def build_sofa():
    """Construct the frame, cushions, armrests, and legs."""
    clear_scene()
    configure_scene()

    # Collections make the unjoined source categories easy to inspect.
    asset_collection = bpy.data.collections.new("Modern_Sectional_Sofa")
    bpy.context.scene.collection.children.link(asset_collection)
    frame_collection = bpy.data.collections.new("Frame")
    seat_collection = bpy.data.collections.new("Seat_Cushions")
    back_collection = bpy.data.collections.new("Back_Cushions")
    arm_collection = bpy.data.collections.new("Armrests")
    leg_collection = bpy.data.collections.new("Legs")
    for collection in (
        frame_collection,
        seat_collection,
        back_collection,
        arm_collection,
        leg_collection,
    ):
        asset_collection.children.link(collection)

    leather = make_leather_material()
    wood = make_wood_material()
    deck = make_deck_material()

    # The two-part platform creates the L footprint without overlapping faces.
    frame_parts = [
        create_rounded_box(
            "Frame_Main_Deck",
            (106, 37, 8),
            (3, 23.5, 8),
            deck,
            frame_collection,
            bevel_inches=0.5,
            bevel_segments=1,
        ),
        create_rounded_box(
            "Frame_Chaise_Deck",
            (35, 50, 8),
            (-38.5, -20, 8),
            deck,
            frame_collection,
            bevel_inches=0.5,
            bevel_segments=1,
        ),
        create_rounded_box(
            "Frame_Back_Rail",
            (106, 5, 22),
            (3, 42.5, 23),
            leather,
            frame_collection,
            bevel_inches=1.25,
            bevel_segments=2,
        ),
    ]

    # Three thick, separate seat cushions support readable deformation in-game.
    seat_cushions = [
        create_rounded_box(
            "Seat_Cushion_Chaise_Left",
            (31, 77, 7),
            (-38.5, -2.5, 15.5),
            leather,
            seat_collection,
            bevel_inches=2.0,
            bevel_segments=3,
        ),
        create_rounded_box(
            "Seat_Cushion_Center",
            (34, 31, 7),
            (-4.5, 20.5, 15.5),
            leather,
            seat_collection,
            bevel_inches=2.0,
            bevel_segments=3,
        ),
        create_rounded_box(
            "Seat_Cushion_Right",
            (34, 31, 7),
            (30.5, 20.5, 15.5),
            leather,
            seat_collection,
            bevel_inches=2.0,
            bevel_segments=3,
        ),
    ]

    # Exactly three plump back cushions fill the full seating width.
    back_cushions = [
        create_rounded_box(
            "Back_Cushion_Left",
            (32, 8, 15),
            (-37, 33.5, 25.5),
            leather,
            back_collection,
            bevel_inches=2.25,
            bevel_segments=3,
        ),
        create_rounded_box(
            "Back_Cushion_Center",
            (32, 8, 15),
            (-3, 33.5, 25.5),
            leather,
            back_collection,
            bevel_inches=2.25,
            bevel_segments=3,
        ),
        create_rounded_box(
            "Back_Cushion_Right",
            (32, 8, 15),
            (31, 33.5, 25.5),
            leather,
            back_collection,
            bevel_inches=2.25,
            bevel_segments=3,
        ),
    ]

    # The left arm runs beside the chaise; the right arm ends at the main seat.
    armrests = [
        create_rounded_box(
            "Armrest_Left_Chaise",
            (7, 90, 15),
            (-56.5, 0, 18.5),
            leather,
            arm_collection,
            bevel_inches=3.0,
            bevel_segments=3,
        ),
        create_rounded_box(
            "Armrest_Right",
            (7, 38, 15),
            (56.5, 21, 18.5),
            leather,
            arm_collection,
            bevel_inches=3.0,
            bevel_segments=3,
        ),
    ]

    # Six compact walnut feet distribute support around the L-shaped footprint.
    leg_specs = [
        ("Leg_Back_Left", (-52, 36, 2)),
        ("Leg_Back_Center", (0, 36, 2)),
        ("Leg_Back_Right", (52, 36, 2)),
        ("Leg_Front_Chaise_Left", (-52, -41, 2)),
        ("Leg_Front_Chaise_Right", (-25, -41, 2)),
        ("Leg_Front_Right", (52, 7, 2)),
    ]
    legs = [
        create_rounded_box(
            name,
            (4, 4, 4),
            location,
            wood,
            leg_collection,
            bevel_inches=0.3,
            bevel_segments=1,
        )
        for name, location in leg_specs
    ]

    # Apply UVs before joining so each modular piece receives an even layout.
    all_source_objects = (
        frame_parts + seat_cushions + back_cushions + armrests + legs
    )
    for obj in all_source_objects:
        unwrap_object(obj)

    # Join structural frame pieces and legs; cushions remain modular for games.
    sofa_frame = join_objects(frame_parts, "Sofa_Frame")
    sofa_legs = join_objects(legs, "Sofa_Legs")
    final_objects = [
        sofa_frame,
        *seat_cushions,
        *back_cushions,
        *armrests,
        sofa_legs,
    ]

    # Bake every transform and put every object origin at the asset world origin.
    for obj in final_objects:
        apply_transforms_with_world_origin(obj)

    # Record useful validation metadata directly on the main frame.
    triangles = triangle_count(final_objects)
    sofa_frame["triangle_count"] = triangles
    sofa_frame["overall_dimensions_inches"] = "120 W x 90 D x 34 H"
    sofa_frame["asset_type"] = "Game-ready L-shaped sectional sofa"
    if triangles >= 10_000:
        raise RuntimeError(f"Triangle budget exceeded: {triangles:,} triangles")

    # Validate actual geometry bounds against the requested dimensions.
    world_vertices = [
        obj.matrix_world @ vertex.co
        for obj in final_objects
        for vertex in obj.data.vertices
    ]
    size = tuple(
        max(vertex[axis] for vertex in world_vertices)
        - min(vertex[axis] for vertex in world_vertices)
        for axis in range(3)
    )
    expected = (OVERALL_WIDTH, OVERALL_DEPTH, OVERALL_HEIGHT)
    tolerance = 0.0001
    if any(abs(actual - target) > tolerance for actual, target in zip(size, expected)):
        measured = tuple(round(value / INCH, 3) for value in size)
        raise RuntimeError(f"Unexpected overall size in inches: {measured}")

    # Select all final meshes so Blender's FBX exporter can use Selection Only.
    bpy.ops.object.select_all(action="DESELECT")
    for obj in final_objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = sofa_frame

    # Optional export uses standard game-engine axis conversion and mesh only.
    if EXPORT_FBX:
        bpy.ops.export_scene.fbx(
            filepath=str(EXPORT_PATH),
            use_selection=True,
            object_types={"MESH"},
            apply_unit_scale=True,
            apply_scale_options="FBX_SCALE_UNITS",
            use_mesh_modifiers=True,
            mesh_smooth_type="FACE",
            add_leaf_bones=False,
            axis_forward="-Z",
            axis_up="Y",
        )

    print(
        f"Modern sectional complete: {len(final_objects)} objects, "
        f"{triangles:,} triangles, 120 x 90 x 34 inches."
    )
    return final_objects


# ---------------------------------------------------------------------------
# Script entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    build_sofa()
