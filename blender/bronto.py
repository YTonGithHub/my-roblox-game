"""
Blocky "Bronto" (brontosaurus) model for Blender: geometry only.

How to use:
  1. Open Blender, go to the Scripting tab.
  2. Open this file (or paste it in) and press "Run Script".
  3. A mesh named "Bronto" is created in a "Bronto" collection.
     Re-running the script replaces it.

No textures are created. The mesh has:
  - a "UVMap" layer, unwrapped per part at a uniform world scale (1 UV unit =
    UV_UNIT model units), so tiling textures line up across the whole body;
  - three empty material slots ("Skin", "Belly", "Eye") to put your textures on.

The model faces +X, stands on Z = 0 and is about 11.7 units tall at the head
with SCALE = 1.0. Works in Blender 3.6 through 5.x.
"""

import bmesh
import bpy
from mathutils import Matrix, Vector

# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------
SCALE = 1.0          # overall size multiplier
SMOOTHNESS = 4       # extra rings between key sections (higher = smoother curves)
UV_UNIT = 1.0        # model units per 1.0 of UV space
NAME = "Bronto"

# --------------------------------------------------------------------------
# Shape data
#
# A part is a list of key cross-sections (x, z, width, height): the centre of
# the section in side view and its size. The keys are joined by a smooth
# spline, then lofted with a chamfered octagon profile.
# --------------------------------------------------------------------------
BODY_KEYS = [                     # tail tip -> chest
    (-14.00, 2.95, 0.12, 0.10),   # tail tip, curled slightly up
    (-13.20, 2.55, 0.40, 0.35),
    (-12.30, 2.32, 0.68, 0.60),
    (-11.30, 2.20, 0.90, 0.82),
    (-10.30, 2.20, 1.08, 0.98),   # lowest point of the tail
    (-9.30,  2.40, 1.25, 1.12),
    (-8.30,  2.70, 1.42, 1.32),
    (-7.40,  3.05, 1.65, 1.55),
    (-6.60,  3.45, 1.95, 1.85),   # base of the tail
    (-5.60,  3.90, 2.25, 2.25),   # hips
    (-4.20,  3.98, 2.45, 2.75),
    (-2.60,  3.95, 2.50, 3.00),   # deepest part of the body
    (-1.00,  3.85, 2.45, 2.95),
    (0.10,   3.80, 2.30, 2.70),   # shoulders
    (0.55,   3.78, 1.95, 2.15),
    (0.80,   3.80, 1.40, 1.50),   # front of chest
]
BODY_CHAMFER = 0.38
BODY_TOP_NARROW = 0.75            # top face narrower than the belly

NECK_KEYS = [                     # chest -> under the head
    (-0.40, 4.00, 1.70, 1.95),    # buried in the shoulders
    (-0.05, 5.10, 1.40, 1.50),
    (0.30,  6.20, 1.22, 1.28),
    (0.65,  7.30, 1.12, 1.15),
    (1.00,  8.30, 1.06, 1.08),
    (1.30,  9.20, 1.02, 1.04),
    (1.55,  9.95, 1.00, 1.00),
    (1.70,  10.55, 0.98, 0.98),
]
NECK_CHAMFER = 0.40

HEAD_KEYS = [                     # back of skull -> nose
    (1.15,  10.95, 0.80, 0.95),
    (1.35,  11.00, 1.08, 1.30),
    (1.80,  11.02, 1.18, 1.42),   # top of the skull
    (2.40,  10.95, 1.15, 1.32),
    (2.95,  10.82, 1.06, 1.15),   # eyes sit here
    (3.35,  10.72, 0.98, 1.00),   # snout
    (3.62,  10.68, 0.80, 0.80),   # nose
]
HEAD_CHAMFER = 0.38

# Legs: (x, y) foot position and keys from hip down to the sole as
# (x_offset, z, width_y, depth_x). The top key is hidden in the body and
# bulges out a little to form the thigh / shoulder.
LEG_POSITIONS = {
    "front": [(-0.30, 0.78), (-0.30, -0.78)],
    "back":  [(-4.40, 0.78), (-4.40, -0.78)],
}
LEG_KEYS = {
    "front": [
        (-0.15, 4.10, 1.15, 1.85),   # shoulder, hidden in the body
        (-0.10, 2.70, 1.05, 1.55),
        (0.00, 1.45, 0.92, 1.32),    # elbow
        (0.00, 0.60, 0.90, 1.28),
        (0.00, 0.20, 0.96, 1.36),
        (0.00, 0.00, 1.02, 1.44),    # sole
    ],
    "back": [
        (-0.60, 4.30, 1.20, 2.25),   # thigh, hidden in the body
        (-0.40, 3.00, 1.12, 1.85),
        (-0.12, 1.70, 0.98, 1.42),   # knee
        (0.00, 0.60, 0.90, 1.28),
        (0.00, 0.20, 0.96, 1.36),
        (0.00, 0.00, 1.02, 1.44),    # sole
    ],
}
LEG_CHAMFER = 0.30

# Eye: centre (x, |y|, z) and radius. Mirrored to both sides of the head.
EYE = (2.85, 0.52, 11.25, 0.24)

MAT_SKIN, MAT_BELLY, MAT_EYE = range(3)
MATERIALS = [("Skin", (0.43, 0.39, 0.37)),
             ("Belly", (0.74, 0.69, 0.62)),
             ("Eye", (0.02, 0.02, 0.02))]


# --------------------------------------------------------------------------
# Geometry helpers
# --------------------------------------------------------------------------
def catmull_rom(keys, steps):
    """Smoothly resample a list of equal-length tuples."""
    if steps <= 1 or len(keys) < 3:
        return list(keys)
    n = len(keys)
    out = []
    for i in range(n - 1):
        p0, p1 = keys[max(i - 1, 0)], keys[i]
        p2, p3 = keys[i + 1], keys[min(i + 2, n - 1)]
        for s in range(steps):
            t = s / steps
            t2, t3 = t * t, t * t * t
            out.append(tuple(
                0.5 * (2 * b + (c - a) * t + (2 * a - 5 * b + 4 * c - d) * t2
                       + (3 * b - a - 3 * c + d) * t3)
                for a, b, c, d in zip(p0, p1, p2, p3)))
    out.append(keys[-1])
    return out


def octagon(w, h, c, top_narrow=1.0):
    """Chamfered rectangle in (side, up) coords, counter-clockwise.

    Edges 6, 7 and 0 (the flat bottom and its two chamfers) are the underside.
    """
    w2, h2 = w / 2, h / 2
    t = top_narrow
    return [
        (w2 * (1 - c), -h2), (w2, -h2 * (1 - c)),
        (w2 * (1 + t) / 2, h2 * (1 - c)), (w2 * (1 - c) * t, h2),
        (-w2 * (1 - c) * t, h2), (-w2 * (1 + t) / 2, h2 * (1 - c)),
        (-w2, -h2 * (1 - c)), (-w2 * (1 - c), -h2),
    ]


UNDERSIDE = {6, 7, 0}


def loft(bm, uv, centers, sizes, chamfer, top_narrow=1.0,
         side=Vector((0, 1, 0)), belly_mat=None, end_mat=MAT_SKIN):
    """Loft octagon sections through `centers` (list of Vector).

    The profile's up axis is tangent x side, so for a forward-running path
    it points to +Z. Faces are wound outward, so no normal recalc is needed.
    """
    n = len(centers)
    rings, profiles, frames = [], [], []
    for i, (c, (w, h)) in enumerate(zip(centers, sizes)):
        tangent = (centers[min(i + 1, n - 1)] - centers[max(i - 1, 0)]).normalized()
        up = tangent.cross(side).normalized()
        prof = octagon(w, h, chamfer, top_narrow)
        rings.append([bm.verts.new(c + s * side + u * up) for s, u in prof])
        profiles.append(prof)
        frames.append((side, up))

    # UV: u runs around the ring, v along the part, both in world units.
    def ring_u(prof):
        us, acc = [0.0], 0.0
        for k in range(8):
            a, b = prof[k], prof[(k + 1) % 8]
            acc += ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
            us.append(acc)
        return us

    vs, acc = [0.0], 0.0
    for i in range(1, n):
        acc += (centers[i] - centers[i - 1]).length
        vs.append(acc)

    for i in range(n - 1):
        r0, r1 = rings[i], rings[i + 1]
        u0, u1 = ring_u(profiles[i]), ring_u(profiles[i + 1])
        for k in range(8):
            k2 = (k + 1) % 8
            f = bm.faces.new((r0[k], r0[k2], r1[k2], r1[k]))
            f.material_index = (belly_mat if belly_mat is not None and k in UNDERSIDE
                                else MAT_SKIN)
            for loop, (uu, vv) in zip(f.loops, ((u0[k], vs[i]), (u0[k + 1], vs[i]),
                                                (u1[k + 1], vs[i + 1]),
                                                (u1[k], vs[i + 1]))):
                loop[uv].uv = (uu / UV_UNIT, vv / UV_UNIT)

    for ring, prof, mat, flip in ((rings[0], profiles[0], MAT_SKIN, True),
                                  (rings[-1], profiles[-1], end_mat, False)):
        verts = list(reversed(ring)) if flip else ring
        pts = list(reversed(prof)) if flip else prof
        f = bm.faces.new(verts)
        f.material_index = mat
        for loop, (s, u) in zip(f.loops, pts):
            loop[uv].uv = (s / UV_UNIT, u / UV_UNIT)


def loft_side_view(bm, uv, keys, chamfer, **kw):
    pts = catmull_rom(keys, SMOOTHNESS)
    loft(bm, uv, [Vector((x, 0, z)) for x, z, _, _ in pts],
         [(w, h) for _, _, w, h in pts], chamfer, **kw)


def add_eye(bm, center, radius):
    mtx = Matrix.Translation(center) @ Matrix.Diagonal((1.0, 0.55, 1.0, 1.0))
    try:
        res = bmesh.ops.create_uvsphere(bm, u_segments=20, v_segments=12,
                                        radius=radius, matrix=mtx, calc_uvs=True)
    except TypeError:  # very old Blender used "diameter" (which was a radius)
        res = bmesh.ops.create_uvsphere(bm, u_segments=20, v_segments=12,
                                        diameter=radius, matrix=mtx, calc_uvs=True)
    for f in {f for v in res["verts"] for f in v.link_faces}:
        f.material_index = MAT_EYE
        f.smooth = True


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------
def build_mesh():
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")

    # Tail + body. The underside and the chest front get the Belly slot.
    loft_side_view(bm, uv, BODY_KEYS, BODY_CHAMFER, top_narrow=BODY_TOP_NARROW,
                   belly_mat=MAT_BELLY, end_mat=MAT_BELLY)
    loft_side_view(bm, uv, NECK_KEYS, NECK_CHAMFER)
    loft_side_view(bm, uv, HEAD_KEYS, HEAD_CHAMFER)

    for kind, positions in LEG_POSITIONS.items():
        keys = catmull_rom(LEG_KEYS[kind][:-2], 2) + LEG_KEYS[kind][-2:]
        for fx, fy in positions:
            loft(bm, uv,
                 [Vector((fx + dx, fy, z)) for dx, z, _, _ in keys],
                 [(w, d) for _, _, w, d in keys], LEG_CHAMFER)

    ex, ey, ez, er = EYE
    for sign in (1, -1):
        add_eye(bm, Vector((ex, sign * ey, ez)), er)

    bmesh.ops.scale(bm, vec=(SCALE,) * 3, verts=bm.verts)
    me = bpy.data.meshes.new(NAME)
    bm.to_mesh(me)
    bm.free()
    return me


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


def main():
    coll = clear_previous()
    me = build_mesh()
    for name, color in MATERIALS:
        mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        mat.diffuse_color = (*color, 1.0)   # viewport colour only, no textures
        me.materials.append(mat)

    obj = bpy.data.objects.new(NAME, me)
    coll.objects.link(obj)

    bpy.context.view_layer.update()
    for o in bpy.context.view_layer.objects:
        if o is not None:
            o.select_set(False)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    print(f"{NAME} created: {len(me.vertices)} verts, {len(me.polygons)} faces")


main()
