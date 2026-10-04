"""
Blocky "Bronto" (brontosaurus) model for Blender.

How to use:
  1. Open Blender, go to the Scripting tab.
  2. Open this file (or paste it in) and press "Run Script".
  3. A single mesh named "Bronto" is created in a "Bronto" collection.
     Re-running the script replaces it.

The model faces +X, stands on Z = 0, and is about 12 units tall at the head
with SCALE = 1.0. Body, neck, tail and legs are lofted from chamfered
(octagonal) cross-sections to get the faceted low-poly look, and a
procedural studded texture gives the plastic-brick surface.

Works in Blender 3.6 through 5.x.
"""

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------
SCALE = 1.0               # overall size multiplier
STUD_SIZE = 0.24          # size of one stud on the surface (in model units)
CHAMFER = 0.35            # how much the corners of each section are cut (0..0.9)
BODY_COLOR = (0.43, 0.39, 0.37)    # grey-taupe skin (sRGB)
BELLY_COLOR = (0.74, 0.69, 0.62)   # lighter chest / belly (sRGB)
ADD_SCENE_EXTRAS = True   # add ground, sun and camera for a quick preview

NAME = "Bronto"

# --------------------------------------------------------------------------
# Shape data.  Each section is (x, z, width, height): the centre of the
# cross-section in side view plus its size.  Lofts go tail -> nose.
# --------------------------------------------------------------------------
BODY_SECTIONS = [
    (-13.6, 3.25, 0.14, 0.12),   # tail tip
    (-11.0, 3.45, 0.95, 0.70),
    (-8.5,  3.65, 1.60, 1.25),
    (-6.6,  3.75, 2.15, 1.75),
    (-5.2,  3.55, 2.60, 2.50),   # hips
    (-3.8,  3.60, 3.30, 3.75),
    (-1.8,  3.73, 3.50, 4.25),   # hump, highest point of the back
    (0.2,   3.65, 3.30, 3.90),
    (1.4,   3.65, 2.80, 3.30),   # shoulders / chest
    (1.75,  3.80, 2.00, 2.40),   # chest front cap
]

NECK_SECTIONS = [
    (0.30, 4.20, 2.00, 2.20),    # buried in the chest
    (0.80, 6.00, 1.55, 1.65),
    (1.40, 8.00, 1.30, 1.35),
    (1.90, 9.80, 1.18, 1.22),
    (2.30, 10.90, 1.12, 1.15),
    (2.45, 11.30, 1.10, 1.10),   # tucked into the back of the head
]

HEAD_SECTIONS = [
    (2.00, 11.35, 1.25, 1.35),   # back of skull
    (2.60, 11.40, 1.35, 1.45),
    (3.40, 11.30, 1.20, 1.15),
    (4.10, 11.15, 1.00, 0.85),   # snout
    (4.30, 11.15, 0.75, 0.60),   # nose cap
]

# Legs: (x, y) position, then sections top -> ground as (z, width_y, depth_x).
LEG_POSITIONS = [(0.25, 1.05), (0.25, -1.05), (-3.75, 1.05), (-3.75, -1.05)]
LEG_SECTIONS = [
    (2.60, 1.25, 1.60),          # hidden inside the belly
    (1.40, 1.15, 1.45),
    (0.35, 1.15, 1.45),
    (0.00, 1.30, 1.60),          # slightly flared foot
]

# Eye: centre (x, |y|, z) and radius. Mirrored to both sides of the head.
EYE = (3.55, 0.58, 11.65, 0.19)

# Material slot indices
MAT_BODY, MAT_BELLY, MAT_EYE, MAT_SHINE = range(4)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def srgb_to_linear(c):
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c)


def octagon(w, h, c=CHAMFER):
    """Chamfered rectangle in (side, up) coords. Edge 7->0 is the bottom."""
    w2, h2 = w / 2, h / 2
    return [
        (w2 * (1 - c), -h2), (w2, -h2 * (1 - c)),
        (w2, h2 * (1 - c)), (w2 * (1 - c), h2),
        (-w2 * (1 - c), h2), (-w2, h2 * (1 - c)),
        (-w2, -h2 * (1 - c)), (-w2 * (1 - c), -h2),
    ]


BOTTOM_EDGES = {6, 7, 0}   # bottom face plus the two lower chamfers


def loft(bm, centers, sizes, side=Vector((0, 1, 0)), belly=False, cap_mat=None):
    """Loft octagonal sections through `centers`.

    centers: list of Vector, sizes: list of (side_size, up_size).
    The section's "up" axis is tangent x side, so for a forward-running path
    it points to +Z and the bottom edges are the underside.
    """
    rings = []
    n = len(centers)
    for i, (c, (w, h)) in enumerate(zip(centers, sizes)):
        a = centers[max(i - 1, 0)]
        b = centers[min(i + 1, n - 1)]
        tangent = (b - a).normalized()
        up = tangent.cross(side).normalized()
        rings.append([bm.verts.new(c + s * side + u * up) for s, u in octagon(w, h)])

    for i in range(n - 1):
        r0, r1 = rings[i], rings[i + 1]
        for k in range(8):
            k2 = (k + 1) % 8
            f = bm.faces.new((r0[k], r0[k2], r1[k2], r1[k]))
            f.material_index = MAT_BELLY if (belly and k in BOTTOM_EDGES) else MAT_BODY

    start = bm.faces.new(rings[0])
    end = bm.faces.new(rings[-1])
    start.material_index = MAT_BODY
    end.material_index = MAT_BODY if cap_mat is None else cap_mat


def add_sphere(bm, center, radius, scale, mat_index):
    mtx = Matrix.Translation(center) @ Matrix.Diagonal((*scale, 1.0))
    try:
        res = bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=10,
                                        radius=radius, matrix=mtx)
    except TypeError:  # very old Blender used "diameter" (which was a radius)
        res = bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=10,
                                        diameter=radius, matrix=mtx)
    faces = {f for v in res["verts"] for f in v.link_faces}
    for f in faces:
        f.material_index = mat_index
        f.smooth = True


def side_view(sections):
    return ([Vector((x, 0, z)) for x, z, _, _ in sections],
            [(w, h) for _, _, w, h in sections])


# --------------------------------------------------------------------------
# Studded surface texture
# --------------------------------------------------------------------------
def make_stud_image(size=64):
    """Grey tile: flat background, raised rounded-square stud, dark groove."""
    name = "BrontoStudTile"
    old = bpy.data.images.get(name)
    if old:
        bpy.data.images.remove(old)
    img = bpy.data.images.new(name, size, size, alpha=False)

    def smooth(e0, e1, x):
        t = min(max((x - e0) / (e1 - e0), 0.0), 1.0)
        return t * t * (3 - 2 * t)

    half, radius = 0.36, 0.10
    px = []
    for j in range(size):
        for i in range(size):
            u = (i + 0.5) / size - 0.5
            v = (j + 0.5) / size - 0.5
            qx = abs(u) - (half - radius)
            qy = abs(v) - (half - radius)
            d = (math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - radius)
            groove = 1.0 - smooth(0.0, 0.035, abs(d + 0.02))
            inside = 1.0 - smooth(-0.03, 0.0, d)
            val = 0.72 + 0.25 * inside - 0.45 * groove
            px.extend((val, val, val, 1.0))
    img.pixels[:] = px
    img.pack()
    return img


def make_material(name, color, stud_img=None, roughness=0.55, emission=None):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()

    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (600, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (300, 0)
    bsdf.inputs["Roughness"].default_value = roughness
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    lin = (*srgb_to_linear(color), 1.0)
    mat.diffuse_color = lin  # viewport solid-mode colour

    if stud_img is None:
        bsdf.inputs["Base Color"].default_value = lin
        if emission is not None:
            key = "Emission Color" if "Emission Color" in bsdf.inputs else "Emission"
            bsdf.inputs[key].default_value = (*emission, 1.0)
            bsdf.inputs["Emission Strength"].default_value = 1.0
        return mat

    coord = nt.nodes.new("ShaderNodeTexCoord")
    coord.location = (-900, 0)
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.location = (-700, 0)
    mapping.inputs["Scale"].default_value = (1 / STUD_SIZE,) * 3
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.location = (-500, 0)
    tex.image = stud_img
    tex.projection = "BOX"
    tex.projection_blend = 0.1
    tex.extension = "REPEAT"
    nt.links.new(coord.outputs["Object"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], tex.inputs["Vector"])

    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.location = (-200, 150)
    ramp.color_ramp.elements[0].position = 0.25
    ramp.color_ramp.elements[0].color = tuple(v * 0.55 for v in lin[:3]) + (1.0,)
    ramp.color_ramp.elements[1].position = 0.97
    ramp.color_ramp.elements[1].color = lin
    nt.links.new(tex.outputs["Color"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])

    bump = nt.nodes.new("ShaderNodeBump")
    bump.location = (0, -200)
    bump.inputs["Strength"].default_value = 0.6
    bump.inputs["Distance"].default_value = 0.02
    nt.links.new(tex.outputs["Color"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------
def clear_previous():
    coll = bpy.data.collections.get(NAME)
    if coll:
        for obj in list(coll.objects):
            data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if isinstance(data, bpy.types.Mesh) and data.users == 0:
                bpy.data.meshes.remove(data)
    else:
        coll = bpy.data.collections.new(NAME)
        bpy.context.scene.collection.children.link(coll)
    return coll


def build_mesh():
    bm = bmesh.new()

    centers, sizes = side_view(BODY_SECTIONS)
    loft(bm, centers, sizes, belly=True, cap_mat=MAT_BELLY)   # tail + body

    centers, sizes = side_view(NECK_SECTIONS)
    loft(bm, centers, sizes)                                   # neck

    centers, sizes = side_view(HEAD_SECTIONS)
    loft(bm, centers, sizes)                                   # head

    for lx, ly in LEG_POSITIONS:                               # legs
        centers = [Vector((lx, ly, z)) for z, _, _ in LEG_SECTIONS]
        sizes = [(w, d) for _, w, d in LEG_SECTIONS]
        loft(bm, centers, sizes)

    ex, ey, ez, er = EYE                                       # eyes
    for sign in (1, -1):
        add_sphere(bm, Vector((ex, sign * ey, ez)), er, (1.0, 0.55, 1.0), MAT_EYE)
        add_sphere(bm, Vector((ex + 0.07, sign * (ey + 0.09), ez + 0.07)),
                   er * 0.32, (1.0, 0.6, 1.0), MAT_SHINE)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.ops.scale(bm, vec=(SCALE, SCALE, SCALE), verts=bm.verts)

    me = bpy.data.meshes.new(NAME)
    bm.to_mesh(me)
    bm.free()
    return me


def add_scene_extras(coll):
    ground = bpy.data.meshes.new(NAME + "_Ground")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=40 * SCALE)
    bm.to_mesh(ground)
    bm.free()
    gobj = bpy.data.objects.new(NAME + "_Ground", ground)
    gobj.data.materials.append(make_material("BrontoGrass", (0.33, 0.78, 0.13),
                                             stud_img=bpy.data.images["BrontoStudTile"]))
    coll.objects.link(gobj)

    sun_data = bpy.data.lights.new(NAME + "_Sun", "SUN")
    sun_data.energy = 4.0
    sun = bpy.data.objects.new(NAME + "_Sun", sun_data)
    sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(-35))
    coll.objects.link(sun)

    cam_data = bpy.data.cameras.new(NAME + "_Camera")
    cam_data.lens = 35
    cam = bpy.data.objects.new(NAME + "_Camera", cam_data)
    cam.location = Vector((14, -30, 9)) * SCALE
    target = Vector((-3, 0, 5)) * SCALE
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    coll.objects.link(cam)
    bpy.context.scene.camera = cam

    world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (*srgb_to_linear((0.45, 0.70, 0.95)), 1.0)
        bg.inputs["Strength"].default_value = 1.0


def main():
    coll = clear_previous()
    stud = make_stud_image()

    me = build_mesh()
    me.materials.append(make_material("BrontoSkin", BODY_COLOR, stud))
    me.materials.append(make_material("BrontoBelly", BELLY_COLOR, stud))
    me.materials.append(make_material("BrontoEye", (0.02, 0.02, 0.02), roughness=0.15))
    me.materials.append(make_material("BrontoEyeShine", (1, 1, 1), roughness=0.1,
                                      emission=(1, 1, 1)))

    obj = bpy.data.objects.new(NAME, me)
    coll.objects.link(obj)

    if ADD_SCENE_EXTRAS:
        add_scene_extras(coll)

    bpy.context.view_layer.update()
    for o in bpy.context.view_layer.objects:
        if o is not None:
            o.select_set(False)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    print(f"{NAME} created: {len(me.vertices)} verts, {len(me.polygons)} faces")


main()
