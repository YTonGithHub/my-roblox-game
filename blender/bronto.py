"""
Detailed "Bronto" (brontosaurus) model for Blender.

How to use:
  1. Open Blender, go to the Scripting tab.
  2. Open this file (or paste it in) and press "Run Script".
  3. A mesh named "Bronto" is created in a "Bronto" collection.
     Re-running the script replaces it.

What you get:
  - one smooth-shaded mesh built from rounded cross-sections (no blocky
    octagons), with toenails, nostrils, a mouth line, brows and eye highlights;
  - colour stored as a vertex colour attribute "Col" (grey-taupe skin, a
    slightly darker back, a lighter belly) that the "Skin" material displays
    and that exports with FBX / glTF;
  - a "UVMap" unwrapped per part at a uniform world scale (1 UV unit =
    UV_UNIT model units) if you want to put your own textures on later.

The model faces +X, stands on Z = 0 and is about 11.7 units tall at the head
with SCALE = 1.0. Works in Blender 3.6 through 5.x.
"""

import math

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------
SCALE = 1.0          # overall size multiplier
SMOOTHNESS = 5       # extra rings between key sections (higher = smoother curves)
SEGMENTS = 24        # vertices around each cross-section (higher = rounder)
UV_UNIT = 1.0        # model units per 1.0 of UV space
NAME = "Bronto"

ADD_TOENAILS = True
ADD_NOSTRILS = True
ADD_MOUTH = True
ADD_BROWS = True

# Colours (sRGB 0..1)
BACK_COLOR = (0.37, 0.34, 0.32)    # top of the back / neck, slightly darker
SKIN_COLOR = (0.46, 0.42, 0.40)    # main grey-taupe skin
BELLY_COLOR = (0.76, 0.71, 0.64)   # underside of the body and chest
EYE_COLOR = (0.01, 0.01, 0.01)
SHINE_COLOR = (1.0, 1.0, 1.0)
NAIL_COLOR = (0.70, 0.66, 0.58)
MOUTH_COLOR = (0.16, 0.13, 0.12)

# --------------------------------------------------------------------------
# Shape data
#
# A part is a list of key cross-sections (x, z, width, height): the centre of
# the section in side view and its size. The keys are joined by a smooth
# spline and lofted with a rounded-box (superellipse) profile.
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
    (0.80,   3.80, 1.40, 1.50),   # front of chest (rounded off below)
]
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
HEAD_KEYS = [                     # back of skull -> nose
    (1.15,  10.95, 0.80, 0.95),
    (1.35,  11.00, 1.08, 1.30),
    (1.80,  11.02, 1.18, 1.42),   # top of the skull
    (2.40,  10.95, 1.15, 1.32),
    (2.95,  10.82, 1.06, 1.15),   # eyes sit here
    (3.35,  10.72, 0.98, 1.00),   # snout
    (3.62,  10.68, 0.80, 0.80),   # nose (rounded off below)
]

# Profile roundness per part: 2 = ellipse, higher = squarer. top_narrow < 1
# makes the top of the section narrower than the bottom.
BODY_SHAPE = dict(exponent=2.6, top_narrow=0.80)
NECK_SHAPE = dict(exponent=2.3, top_narrow=0.92)
HEAD_SHAPE = dict(exponent=2.6, top_narrow=0.85)
LEG_SHAPE = dict(exponent=2.8, top_narrow=1.0)

# Legs: (x, y) foot position and keys from hip down to the sole as
# (x_offset, z, width_y, depth_x). The top key is hidden in the body and
# bulges out a little to form the thigh / shoulder.
LEG_POSITIONS = {
    "front": [(-0.30, 0.78), (-0.30, -0.78)],
    "back":  [(-4.40, 0.78), (-4.40, -0.78)],
}
LEG_KEYS = {
    "front": [
        (-0.15, 4.00, 0.75, 1.45),   # shoulder, hidden in the body
        (-0.10, 2.70, 0.95, 1.55),
        (0.00, 1.45, 0.92, 1.32),    # elbow
        (0.00, 0.60, 0.90, 1.28),
        (0.00, 0.20, 0.96, 1.36),
        (0.00, 0.00, 1.02, 1.44),    # sole
    ],
    "back": [
        (-0.45, 4.10, 0.80, 1.60),   # thigh, hidden in the body
        (-0.40, 3.00, 1.00, 1.85),
        (-0.12, 1.70, 0.98, 1.42),   # knee
        (0.00, 0.60, 0.90, 1.28),
        (0.00, 0.20, 0.96, 1.36),
        (0.00, 0.00, 1.02, 1.44),    # sole
    ],
}

# Shoulder / hip muscles: the body's sides are pushed out smoothly around
# (x, z) by `amount`, fading over the (x, z) radii. This hides the tops of the
# legs and gives the body its shape.
LEG_MUSCLES = [
    # x,     z,    radius_x, radius_z, amount
    (-0.35, 3.00, 1.05, 1.10, 0.30),   # shoulders
    (-4.75, 3.20, 1.35, 1.25, 0.34),   # hips
]

# Eye: (x, z, radius). It is snapped onto both sides of the head.
EYE = (2.85, 11.25, 0.24)

MAT_SKIN, MAT_EYE, MAT_SHINE, MAT_NAIL, MAT_MOUTH = range(5)

Y_AXIS = Vector((0, 1, 0))
Z_AXIS = Vector((0, 0, 1))


# --------------------------------------------------------------------------
# Small maths helpers
# --------------------------------------------------------------------------
def srgb_to_linear(c):
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c)


def smoothstep(e0, e1, x):
    t = min(max((x - e0) / (e1 - e0), 0.0), 1.0)
    return t * t * (3 - 2 * t)


def lerp3(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


BACK_LIN, SKIN_LIN, BELLY_LIN = (srgb_to_linear(c) for c in
                                 (BACK_COLOR, SKIN_COLOR, BELLY_COLOR))


def skin_color(u_norm, belly, dorsal):
    """Colour for a skin vertex. u_norm is -1 (underside) .. 1 (top)."""
    col = SKIN_LIN
    if dorsal:
        col = lerp3(col, BACK_LIN, smoothstep(0.35, 1.0, u_norm))
    if belly:
        col = lerp3(col, BELLY_LIN, belly * smoothstep(-0.10, -0.70, u_norm))
    return col


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


def profile(w, h, exponent, top_narrow, segments):
    """Rounded-box section in (side, up) coords, counter-clockwise from the
    bottom centre."""
    e = 2.0 / exponent
    pts = []
    for k in range(segments):
        t = -math.pi / 2 + 2 * math.pi * k / segments
        c, s = math.cos(t), math.sin(t)
        x = w / 2 * math.copysign(abs(c) ** e, c)
        y = h / 2 * math.copysign(abs(s) ** e, s)
        if y > 0 and h > 0:
            x *= 1 - (1 - top_narrow) * (2 * y / h)
        pts.append((x, y))
    return pts


def add_dome(centers, sizes, roundness, at_end, steps=4):
    """Extend a loft with shrinking rings so that end is rounded off."""
    if at_end:
        c0, c1, (w, h) = centers[-1], centers[-2], sizes[-1]
    else:
        c0, c1, (w, h) = centers[0], centers[1], sizes[0]
    t = (c0 - c1).normalized()
    depth = roundness * 0.5 * min(w, h)
    cs, ss = [], []
    for j in range(1, steps + 1):
        a = j / (steps + 0.5) * math.pi / 2
        cs.append(c0 + t * depth * math.sin(a))
        ss.append((w * math.cos(a), h * math.cos(a)))
    if at_end:
        return centers + cs, sizes + ss
    return cs[::-1] + centers, ss[::-1] + sizes


# --------------------------------------------------------------------------
# Mesh builder
# --------------------------------------------------------------------------
class Builder:
    def __init__(self):
        self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.new("UVMap")
        self.colors = {}          # BMVert -> linear RGB
        self.bvh = None

    def loft(self, centers, sizes, exponent=2.5, top_narrow=1.0, side=Y_AXIS,
             belly=None, dorsal=False, round_start=0.0, round_end=0.0,
             flat_end=False, mat=MAT_SKIN, color=None, segments=SEGMENTS):
        """Loft rounded sections through `centers` (Vectors).

        The section's up axis is tangent x side, so for a forward-running path
        it points to +Z. Faces are wound outward.
        belly: optional function(center) -> 0..1 weight of the belly colour.
        Returns [(vert, side)] where side is -1..1 across the section width.
        """
        bm = self.bm
        centers, sizes = list(centers), list(sizes)
        if round_start:
            centers, sizes = add_dome(centers, sizes, round_start, at_end=False)
        if round_end:
            centers, sizes = add_dome(centers, sizes, round_end, at_end=True)

        n = len(centers)
        rings, profiles, out = [], [], []
        for i, (c, (w, h)) in enumerate(zip(centers, sizes)):
            tangent = (centers[min(i + 1, n - 1)] - centers[max(i - 1, 0)]).normalized()
            up = tangent.cross(side).normalized()
            prof = profile(w, h, exponent, top_narrow, segments)
            bw = belly(c) if belly else 0.0
            ring = []
            for s, u in prof:
                v = bm.verts.new(c + s * side + u * up)
                self.colors[v] = color or skin_color(u / (h / 2) if h > 1e-6 else 0.0,
                                                     bw, dorsal)
                ring.append(v)
                out.append((v, s / (w / 2) if w > 1e-6 else 0.0))
            rings.append(ring)
            profiles.append(prof)

        def ring_u(prof):
            us, acc = [0.0], 0.0
            for k in range(segments):
                a, b = prof[k], prof[(k + 1) % segments]
                acc += math.hypot(a[0] - b[0], a[1] - b[1])
                us.append(acc)
            return us

        vs, acc = [0.0], 0.0
        for i in range(1, n):
            acc += (centers[i] - centers[i - 1]).length
            vs.append(acc)

        for i in range(n - 1):
            r0, r1 = rings[i], rings[i + 1]
            u0, u1 = ring_u(profiles[i]), ring_u(profiles[i + 1])
            for k in range(segments):
                k2 = (k + 1) % segments
                f = bm.faces.new((r0[k], r0[k2], r1[k2], r1[k]))
                f.material_index = mat
                f.smooth = True
                for loop, (uu, vv) in zip(f.loops, ((u0[k], vs[i]), (u0[k + 1], vs[i]),
                                                    (u1[k + 1], vs[i + 1]),
                                                    (u1[k], vs[i + 1]))):
                    loop[self.uv].uv = (uu / UV_UNIT, vv / UV_UNIT)

        for ring, prof, flip, flat in ((rings[0], profiles[0], True, False),
                                       (rings[-1], profiles[-1], False, flat_end)):
            verts = ring[::-1] if flip else ring
            pts = prof[::-1] if flip else prof
            f = bm.faces.new(verts)
            f.material_index = mat
            f.smooth = not flat
            if flat:
                for e in f.edges:
                    e.smooth = False      # crisp edge around the sole
            for loop, (s, u) in zip(f.loops, pts):
                loop[self.uv].uv = (s / UV_UNIT, u / UV_UNIT)
        return out

    def ellipsoid(self, center, radii, normal, mat, color, segs=(16, 10)):
        """Ellipsoid whose local Y axis (radii[1]) points along `normal`."""
        rot = normal.to_track_quat("Y", "Z").to_matrix().to_4x4()
        mtx = Matrix.Translation(center) @ rot @ Matrix.Diagonal((*radii, 1.0))
        kw = dict(u_segments=segs[0], v_segments=segs[1], matrix=mtx, calc_uvs=True)
        try:
            res = bmesh.ops.create_uvsphere(self.bm, radius=1.0, **kw)
        except TypeError:   # very old Blender used "diameter" (which was a radius)
            res = bmesh.ops.create_uvsphere(self.bm, diameter=1.0, **kw)
        for v in res["verts"]:
            self.colors[v] = color
        for f in {f for v in res["verts"] for f in v.link_faces}:
            f.material_index = mat
            f.smooth = True

    def build_bvh(self):
        self.bvh = BVHTree.FromBMesh(self.bm)

    def snap(self, origin, direction, max_dist=20.0):
        """Ray-cast onto the surface built so far. Returns (point, normal)."""
        d = Vector(direction).normalized()
        loc, nor, _, _ = self.bvh.ray_cast(Vector(origin), d, max_dist)
        if loc is None:
            return None, None
        if nor.dot(d) > 0:
            nor = -nor
        return loc, nor


def side_view(keys):
    pts = catmull_rom(keys, SMOOTHNESS)
    return ([Vector((x, 0, z)) for x, z, _, _ in pts],
            [(w, h) for _, _, w, h in pts])


# --------------------------------------------------------------------------
# Parts
# --------------------------------------------------------------------------
def build_body(b):
    centers, sizes = side_view(BODY_KEYS)
    # Lighter belly along the body, fading out down the tail.
    body = b.loft(centers, sizes, **BODY_SHAPE, dorsal=True,
                  belly=lambda c: smoothstep(-12.5, -7.0, c.x), round_end=0.7)
    for v, side in body:
        push = 0.0
        for mx, mz, rx, rz, amount in LEG_MUSCLES:
            d = ((v.co.x - mx) / rx) ** 2 + ((v.co.z - mz) / rz) ** 2
            push += amount * math.exp(-2.5 * d)
        v.co.y += math.copysign(push * smoothstep(0.3, 1.0, abs(side)), side)

    centers, sizes = side_view(NECK_KEYS)
    b.loft(centers, sizes, **NECK_SHAPE, dorsal=True)

    centers, sizes = side_view(HEAD_KEYS)
    b.loft(centers, sizes, **HEAD_SHAPE, dorsal=True,
           round_start=0.6, round_end=0.6)

    for kind, positions in LEG_POSITIONS.items():
        keys = catmull_rom(LEG_KEYS[kind][:-2], 2) + LEG_KEYS[kind][-2:]
        for fx, fy in positions:
            b.loft([Vector((fx + dx, fy, z)) for dx, z, _, _ in keys],
                   [(w, d) for _, _, w, d in keys], **LEG_SHAPE, flat_end=True)



def build_eyes(b):
    ex, ez, r = EYE
    eye_lin = srgb_to_linear(EYE_COLOR)
    shine_lin = srgb_to_linear(SHINE_COLOR)
    fwd = Vector((1, 0, 0))
    for sign in (1, -1):
        loc, nor = b.snap((ex, sign * 5, ez), (0, -sign, 0))
        if loc is None:
            continue
        center = loc - nor * 0.30 * r
        b.ellipsoid(center, (r, 0.62 * r, r), nor, MAT_EYE, eye_lin, segs=(20, 12))
        shine = center + nor * 0.55 * r + Z_AXIS * 0.42 * r + fwd * 0.30 * r
        b.ellipsoid(shine, (0.24 * r, 0.10 * r, 0.24 * r), nor, MAT_SHINE, shine_lin,
                    segs=(10, 6))

        if ADD_BROWS:
            loc, nor = b.snap((ex - 0.03, sign * 5, ez + 1.15 * r), (0, -sign, 0))
            if loc is not None:
                b.ellipsoid(loc - nor * 0.05, (1.3 * r, 0.38 * r, 0.40 * r), nor,
                            MAT_SKIN, skin_color(0.6, 0.0, True), segs=(14, 8))


def build_nostrils(b):
    nose_x = HEAD_KEYS[-1][0]
    dark = srgb_to_linear(MOUTH_COLOR)
    for sign in (1, -1):
        loc, nor = b.snap((nose_x + 0.10, sign * 0.15, 20), (0, 0, -1))
        if loc is not None:
            b.ellipsoid(loc - nor * 0.01, (0.06, 0.03, 0.045), nor, MAT_MOUTH, dark,
                        segs=(10, 6))


def build_mouth(b):
    """Thin smiling groove from one cheek, round the nose, to the other."""
    nose_x = HEAD_KEYS[-1][0]
    back_x = 2.45

    def mouth_z(x):
        return 10.47 + (nose_x - x) * 0.05 + 0.08 * smoothstep(2.75, back_x, x)

    pts = []
    xs = [back_x + (nose_x - back_x) * i / 8 for i in range(9)]
    for x in xs:                                         # left cheek -> nose
        loc, nor = b.snap((x, 5, mouth_z(x)), (0, -1, 0))
        if loc is not None:
            pts.append(loc - nor * 0.012)
    for y in (0.22, 0.11, 0.0, -0.11, -0.22):            # round the front
        loc, nor = b.snap((nose_x + 5, y, mouth_z(nose_x) - 0.02), (-1, 0, 0))
        if loc is not None:
            pts.append(loc - nor * 0.012)
    for x in reversed(xs):                               # nose -> right cheek
        loc, nor = b.snap((x, -5, mouth_z(x)), (0, 1, 0))
        if loc is not None:
            pts.append(loc - nor * 0.012)
    if len(pts) < 4:
        return
    smooth_pts = [Vector(p) for p in catmull_rom([tuple(p) for p in pts], 3)]
    b.loft(smooth_pts, [(0.07, 0.07)] * len(smooth_pts), exponent=2.0, side=Z_AXIS,
           round_start=0.9, round_end=0.9, mat=MAT_MOUTH,
           color=srgb_to_linear(MOUTH_COLOR), segments=8)


def build_toenails(b):
    nail = srgb_to_linear(NAIL_COLOR)
    for kind, positions in LEG_POSITIONS.items():
        for fx, fy in positions:
            for dy, size in ((-0.30, 0.9), (0.0, 1.0), (0.30, 0.9)):
                loc, nor = b.snap((fx + 2.5, fy + dy, 0.13), (-1, 0, 0), max_dist=3.0)
                if loc is not None:
                    b.ellipsoid(loc - nor * 0.025,
                                (0.15 * size, 0.07 * size, 0.11 * size),
                                nor, MAT_NAIL, nail, segs=(12, 8))


def build_mesh():
    b = Builder()
    build_body(b)
    b.build_bvh()   # details below snap onto the body surface
    build_eyes(b)
    if ADD_NOSTRILS:
        build_nostrils(b)
    if ADD_MOUTH:
        build_mouth(b)
    if ADD_TOENAILS:
        build_toenails(b)

    bm = b.bm
    bmesh.ops.scale(bm, vec=(SCALE,) * 3, verts=bm.verts)
    bm.verts.index_update()
    cols = [0.0] * (len(bm.verts) * 4)
    for v in bm.verts:
        cols[v.index * 4:v.index * 4 + 4] = (*b.colors.get(v, SKIN_LIN), 1.0)

    me = bpy.data.meshes.new(NAME)
    bm.to_mesh(me)
    bm.free()

    attr = me.color_attributes.new("Col", "FLOAT_COLOR", "POINT")
    attr.data.foreach_set("color", cols)
    try:
        me.color_attributes.active_color = attr
        me.color_attributes.render_color_index = me.color_attributes.active_color_index
    except AttributeError:
        pass
    if hasattr(me, "use_auto_smooth"):   # Blender < 4.1: needed for sharp soles
        me.use_auto_smooth = True
        me.auto_smooth_angle = math.pi
    return me


# --------------------------------------------------------------------------
# Materials
# --------------------------------------------------------------------------
def make_material(name, color, roughness=0.6, use_vertex_color=False, emission=False):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    lin = (*srgb_to_linear(color), 1.0)
    mat.diffuse_color = lin               # viewport solid-mode colour
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (400, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (100, 0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Base Color"].default_value = lin
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    if use_vertex_color:
        vc = nt.nodes.new("ShaderNodeVertexColor")
        vc.location = (-200, 0)
        vc.layer_name = "Col"
        nt.links.new(vc.outputs["Color"], bsdf.inputs["Base Color"])
    if emission:
        key = "Emission Color" if "Emission Color" in bsdf.inputs else "Emission"
        bsdf.inputs[key].default_value = lin
        bsdf.inputs["Emission Strength"].default_value = 1.0
    return mat


# --------------------------------------------------------------------------
# Scene
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


def main():
    coll = clear_previous()
    me = build_mesh()
    me.materials.append(make_material("Skin", SKIN_COLOR, use_vertex_color=True))
    me.materials.append(make_material("Eye", EYE_COLOR, roughness=0.1))
    me.materials.append(make_material("EyeShine", SHINE_COLOR, roughness=0.1,
                                      emission=True))
    me.materials.append(make_material("Nail", NAIL_COLOR, roughness=0.4))
    me.materials.append(make_material("Mouth", MOUTH_COLOR, roughness=0.8))

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
