"""
Detailed green "TRex" model for Blender.

How to use:
  1. Open Blender, go to the Scripting tab.
  2. Open this file (or paste it in) and press "Run Script".
  3. A mesh named "TRex" is created in a "TRex" collection.
     Re-running the script replaces it.

What you get:
  - one smooth-shaded mesh: big open-mouthed head with teeth, short thick
    neck, horizontal body, long tapering tail, huge thighs, small two-claw
    arms and long three-toed feet with white claws;
  - colour stored as a vertex colour attribute "Col" (green skin with dark
    stripes, lighter back, pale belly / throat, pink mouth, red tongue, white
    teeth and claws, cyan eyes). Every material reads it, and it exports with
    FBX / glTF;
  - material slots "Skin", "Mouth", "Teeth" and "Eye" so you can put your own
    textures on each region;
  - a "UVMap" unwrapped per part at a uniform world scale (1 UV unit =
    UV_UNIT model units), so tiling textures line up across the body.

The model faces +X, stands on Z = 0, is about 10 units tall and 27 long
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
SCALE = 1.0           # overall size multiplier
RING_SPACING = 0.21   # distance between cross-sections (smaller = smoother)
SEGMENTS = 22         # vertices around the body / head sections
LIMB_SEGMENTS = 16    # vertices around legs, arms and toes
UV_UNIT = 1.0         # model units per 1.0 of UV space
NAME = "TRex"

ADD_TEETH = True
ADD_STRIPES = True

# Colours (sRGB 0..1)
GREEN = (0.30, 0.52, 0.32)         # main skin
GREEN_TOP = (0.40, 0.63, 0.41)     # lighter strip along the top
STRIPE = (0.15, 0.33, 0.19)        # dark stripes
BELLY = (0.84, 0.80, 0.84)         # pale belly, throat and back of the shins
MOUTH = (0.93, 0.47, 0.56)         # pink inside of the mouth
TONGUE = (0.85, 0.08, 0.14)        # red tongue / throat
TEETH = (0.97, 0.97, 0.95)         # teeth and claws
EYE = (0.10, 0.82, 0.92)           # cyan iris
PUPIL = (0.02, 0.04, 0.06)

STRIPE_PERIOD = 1.5    # distance between stripes along the body
STRIPE_WIDTH = 0.42    # fraction of the period that is dark

# --------------------------------------------------------------------------
# Shape data. Side-view key sections (x, z, width, height) joined by a smooth
# spline and lofted with a rounded-box profile.
# --------------------------------------------------------------------------
BODY_KEYS = [                     # tail tip -> chest
    (-14.40, 7.05, 0.10, 0.10),
    (-12.10, 7.05, 0.70, 0.55),
    (-10.30, 7.00, 1.20, 1.00),
    (-8.60,  6.98, 1.65, 1.45),
    (-6.80,  6.85, 2.15, 2.05),
    (-5.00,  6.70, 2.60, 2.65),
    (-3.40,  6.60, 3.10, 3.30),
    (-2.00,  6.55, 3.50, 3.85),
    (0.30,   6.55, 3.80, 4.40),   # hips
    (2.10,   6.60, 3.70, 4.60),
    (3.60,   6.40, 3.40, 4.55),
    (4.70,   5.90, 3.00, 4.00),   # chest
    (5.40,   5.30, 2.20, 2.60),   # front of chest (rounded off)
]
HEAD_KEYS = [                     # neck -> snout (upper jaw)
    (3.00,  7.00, 3.30, 3.60),    # buried in the shoulders
    (4.40,  7.50, 2.95, 3.00),
    (5.50,  7.95, 2.60, 2.55),
    (6.40,  8.30, 2.60, 2.35),    # back of the head
    (7.40,  8.55, 2.65, 2.20),
    (8.60,  8.62, 2.60, 2.10),    # brow / horns
    (9.80,  8.55, 2.40, 1.95),    # eyes
    (11.00, 8.45, 2.20, 1.75),
    (12.00, 8.38, 2.00, 1.55),
    (12.50, 8.35, 1.80, 1.35),    # snout tip (rounded off)
]
JAW_KEYS = [                      # throat -> chin (lower jaw)
    (4.90,  5.20, 2.20, 2.40),    # buried in the chest
    (6.00,  5.85, 2.30, 2.00),
    (7.20,  6.15, 2.30, 1.65),
    (8.60,  6.35, 2.15, 1.25),
    (10.00, 6.40, 1.95, 1.15),
    (11.30, 6.55, 1.75, 0.85),
    (11.90, 6.68, 1.60, 0.60),    # chin (rounded off)
]
MOUTH_START_X = 6.8               # inside of the mouth starts here

BODY_SHAPE = dict(exponent=2.6, top_narrow=0.82)
HEAD_SHAPE = dict(exponent=3.0, top_narrow=0.90)
JAW_SHAPE = dict(exponent=3.0, top_narrow=1.0)
LIMB_SHAPE = dict(exponent=2.8, top_narrow=1.0)

LEG_Y = 1.85                      # distance of each leg from the centre line
LEG_X = 0.0                       # hip position along the body
# Leg chain, each piece is keys of (x, z, width_y, depth_x), top -> bottom.
THIGH_KEYS = [
    (0.10, 7.50, 1.40, 2.30),     # hidden in the hip
    (0.00, 6.40, 1.70, 3.30),
    (0.10, 5.00, 1.70, 3.40),     # widest part of the drumstick
    (0.40, 3.70, 1.50, 2.60),
    (0.60, 2.90, 1.25, 1.70),     # knee
]
SHIN_KEYS = [
    (0.60, 3.10, 1.30, 1.70),
    (0.00, 2.00, 1.20, 1.40),
    (-0.50, 1.15, 1.15, 1.25),    # ankle
    (-0.35, 0.55, 1.10, 1.15),
]
FOOT_KEYS = [                     # heel -> ball of the foot, (x, z, w, h)
    (-1.30, 0.38, 1.30, 0.76),
    (0.00,  0.38, 1.45, 0.76),
    (0.90,  0.36, 1.50, 0.72),
]
TOES = [-0.47, 0.0, 0.47]         # toe offsets across the foot
TOE_LENGTH = 1.05

ARM_Y = 1.55
UPPER_ARM_KEYS = [(3.55, 5.00, 0.60, 0.70), (3.70, 4.20, 0.55, 0.62),
                  (3.80, 3.60, 0.50, 0.55)]
FOREARM_KEYS = [(3.70, 3.60, 0.48, 0.50), (4.20, 3.48, 0.44, 0.46),
                (4.65, 3.42, 0.42, 0.42)]

EYE_POS = (9.75, 9.05, 0.30)      # (x, z, radius), snapped onto the head
HORN_X = 7.90                     # brow horns on the top corners of the head

MAT_SKIN, MAT_MOUTH, MAT_TEETH, MAT_EYE = range(4)

X_AXIS = Vector((1, 0, 0))
Y_AXIS = Vector((0, 1, 0))
Z_AXIS = Vector((0, 0, 1))


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def srgb_to_linear(c):
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c)


(GREEN_L, GREEN_TOP_L, STRIPE_L, BELLY_L, MOUTH_L, TONGUE_L, TEETH_L, EYE_L,
 PUPIL_L) = (srgb_to_linear(c) for c in (GREEN, GREEN_TOP, STRIPE, BELLY, MOUTH,
                                          TONGUE, TEETH, EYE, PUPIL))


def smoothstep(e0, e1, x):
    t = min(max((x - e0) / (e1 - e0), 0.0), 1.0)
    return t * t * (3 - 2 * t)


def mix(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def stripe(pos, period=STRIPE_PERIOD, width=STRIPE_WIDTH):
    """0..1 dark-stripe weight for a position along the body."""
    if not ADD_STRIPES:
        return 0.0
    p = (pos / period) % 1.0
    edge = 0.06
    return smoothstep(0.0, edge, p) * (1.0 - smoothstep(width - edge, width, p))


def skin(u, along, stripes=True, belly=0.0, top=True):
    """Green skin colour. u is -1 (underside) .. 1 (top) of the section."""
    col = GREEN_L
    if top:
        col = mix(col, GREEN_TOP_L, smoothstep(0.55, 1.0, u))
    if stripes:
        col = mix(col, STRIPE_L, stripe(along) * smoothstep(-0.15, 0.15, u))
    if belly:
        col = mix(col, BELLY_L, belly * smoothstep(-0.25, -0.55, u))
    return col


def catmull_rom(keys, spacing):
    """Resample key tuples with a smooth spline, about `spacing` apart
    (distance measured on the first two values of each key)."""
    n = len(keys)
    if n < 2:
        return list(keys)
    out = []
    for i in range(n - 1):
        p0, p1 = keys[max(i - 1, 0)], keys[i]
        p2, p3 = keys[i + 1], keys[min(i + 2, n - 1)]
        steps = max(2, math.ceil(math.hypot(p2[0] - p1[0], p2[1] - p1[1]) / spacing))
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


def section_at(keys, x):
    """Linearly interpolate (z, w, h) of side-view keys at position x."""
    for a, b in zip(keys, keys[1:]):
        if a[0] <= x <= b[0]:
            t = (x - a[0]) / (b[0] - a[0])
            return tuple(p + (q - p) * t for p, q in zip(a[1:], b[1:]))
    k = keys[0] if x < keys[0][0] else keys[-1]
    return k[1:]


# --------------------------------------------------------------------------
# Mesh builder
# --------------------------------------------------------------------------
class Builder:
    def __init__(self):
        self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.new("UVMap")
        self.colors = {}          # BMVert -> linear RGB
        self.bvh = None

    def loft(self, centers, sizes, color_fn, exponent=2.5, top_narrow=1.0,
             side=Y_AXIS, round_start=0.0, round_end=0.0, flat_end=False,
             segments=SEGMENTS, mat_fn=None):
        """Loft rounded sections through `centers` (Vectors).

        The section's up axis is tangent x side, so for a forward-running path
        it points to +Z. Faces are wound outward.
        color_fn(u, s, along, center) -> linear RGB, with u / s in -1..1 across
        the section height / width and `along` the distance along the loft.
        mat_fn(u, s, along, center) -> material index (default Skin).
        """
        bm = self.bm
        centers, sizes = list(centers), list(sizes)
        if round_start:
            centers, sizes = add_dome(centers, sizes, round_start, at_end=False)
        if round_end:
            centers, sizes = add_dome(centers, sizes, round_end, at_end=True)
        n = len(centers)

        vs, acc = [0.0], 0.0
        for i in range(1, n):
            acc += (centers[i] - centers[i - 1]).length
            vs.append(acc)

        rings, profiles, mats = [], [], {}
        for i, (c, (w, h)) in enumerate(zip(centers, sizes)):
            tangent = (centers[min(i + 1, n - 1)] - centers[max(i - 1, 0)]).normalized()
            up = tangent.cross(side).normalized()
            prof = profile(w, h, exponent, top_narrow, segments)
            ring = []
            for s, u in prof:
                v = bm.verts.new(c + s * side + u * up)
                un = u / (h / 2) if h > 1e-6 else 0.0
                sn = s / (w / 2) if w > 1e-6 else 0.0
                self.colors[v] = color_fn(un, sn, vs[i], c)
                mats[v] = mat_fn(un, sn, vs[i], c) if mat_fn else MAT_SKIN
                ring.append(v)
            rings.append(ring)
            profiles.append(prof)

        def ring_u(prof):
            us, total = [0.0], 0.0
            for k in range(segments):
                a, b = prof[k], prof[(k + 1) % segments]
                total += math.hypot(a[0] - b[0], a[1] - b[1])
                us.append(total)
            return us

        def face_mat(verts):
            ms = [mats[v] for v in verts]
            return max(set(ms), key=ms.count)

        for i in range(n - 1):
            r0, r1 = rings[i], rings[i + 1]
            u0, u1 = ring_u(profiles[i]), ring_u(profiles[i + 1])
            for k in range(segments):
                k2 = (k + 1) % segments
                quad = (r0[k], r0[k2], r1[k2], r1[k])
                f = bm.faces.new(quad)
                f.material_index = face_mat(quad)
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
            f.material_index = face_mat(verts)
            f.smooth = not flat
            if flat:
                for e in f.edges:
                    e.smooth = False
            for loop, (s, u) in zip(f.loops, pts):
                loop[self.uv].uv = (s / UV_UNIT, u / UV_UNIT)

    def side_loft(self, keys, color_fn, **kw):
        """Loft side-view keys (x, z, w, h) lying in the y = 0 plane."""
        pts = catmull_rom(keys, RING_SPACING)
        self.loft([Vector((x, 0, z)) for x, z, _, _ in pts],
                  [(w, h) for _, _, w, h in pts], color_fn, **kw)

    def limb(self, keys, y, color_fn, vertical=True, **kw):
        """Loft limb keys (x, z, width_y, depth) at a fixed y."""
        pts = catmull_rom(keys, RING_SPACING)
        kw.setdefault("segments", LIMB_SEGMENTS)
        self.loft([Vector((x, y, z)) for x, z, _, _ in pts],
                  [(w, d) for _, _, w, d in pts], color_fn, **LIMB_SHAPE, **kw)

    def ellipsoid(self, center, radii, normal, mat, color, segs=(16, 10)):
        """Ellipsoid whose local Y axis (radii[1]) points along `normal`."""
        rot = normal.to_track_quat("Y", "Z").to_matrix().to_4x4()
        mtx = Matrix.Translation(center) @ rot @ Matrix.Diagonal((*radii, 1.0))
        kw = dict(u_segments=segs[0], v_segments=segs[1], matrix=mtx, calc_uvs=True)
        try:
            res = bmesh.ops.create_uvsphere(self.bm, radius=1.0, **kw)
        except TypeError:
            res = bmesh.ops.create_uvsphere(self.bm, diameter=1.0, **kw)
        self._finish(res["verts"], mat, color)

    def cone(self, base, direction, radius, length, mat, color, segments=8):
        """Pointed cone from `base` towards `direction`."""
        d = Vector(direction).normalized()
        rot = d.to_track_quat("Z", "Y").to_matrix().to_4x4()
        mtx = Matrix.Translation(base + d * length / 2) @ rot
        kw = dict(cap_ends=True, cap_tris=False, segments=segments, depth=length,
                  matrix=mtx, calc_uvs=True)
        try:
            res = bmesh.ops.create_cone(self.bm, radius1=radius, radius2=0.0, **kw)
        except TypeError:
            res = bmesh.ops.create_cone(self.bm, diameter1=radius, diameter2=0.0, **kw)
        self._finish(res["verts"], mat, color)

    def _finish(self, verts, mat, color):
        for v in verts:
            self.colors[v] = color
        for f in {f for v in verts for f in v.link_faces}:
            f.material_index = mat
            f.smooth = True

    def build_bvh(self):
        self.bvh = BVHTree.FromBMesh(self.bm)

    def snap(self, origin, direction, max_dist=20.0):
        d = Vector(direction).normalized()
        loc, nor, _, _ = self.bvh.ray_cast(Vector(origin), d, max_dist)
        if loc is None:
            return None, None
        if nor.dot(d) > 0:
            nor = -nor
        return loc, nor


# --------------------------------------------------------------------------
# Parts
# --------------------------------------------------------------------------
def body_color(u, s, along, c):
    return skin(u, c.x, belly=1.0)


def head_color(u, s, along, c):
    inside = smoothstep(MOUTH_START_X - 0.4, MOUTH_START_X + 0.2, c.x)
    col = skin(u, c.x, stripes=c.x < 6.6,
               belly=(1.0 - inside) * smoothstep(4.6, 5.6, c.x))   # pale throat only
    return mix(col, MOUTH_L, inside * smoothstep(-0.80, -0.92, u))   # palate


def head_mat(u, s, along, c):
    return MAT_MOUTH if c.x > MOUTH_START_X and u < -0.86 else MAT_SKIN


def jaw_color(u, s, along, c):
    inside = smoothstep(MOUTH_START_X - 0.4, MOUTH_START_X + 0.2, c.x)
    col = skin(u, c.x, stripes=False, belly=1.0, top=False)
    col = mix(col, MOUTH_L, inside * smoothstep(0.80, 0.92, u))
    tongue = inside * smoothstep(0.90, 0.97, u) * (1 - smoothstep(0.35, 0.55, abs(s)))
    return mix(col, TONGUE_L, tongue * smoothstep(MOUTH_START_X, 8.0, c.x)
               * (1 - smoothstep(10.6, 11.4, c.x)))


def jaw_mat(u, s, along, c):
    return MAT_MOUTH if c.x > MOUTH_START_X and u > 0.86 else MAT_SKIN


def limb_color(back_pale=False):
    def fn(u, s, along, c):
        col = skin(1.0 if not back_pale else u, along * 1.25, top=False)
        if back_pale:          # u < 0 is the back of the shin
            col = mix(col, BELLY_L, smoothstep(-0.55, -0.85, u))
        return col
    return fn


def plain_skin(u, s, along, c):
    return skin(u, 0.7, stripes=False)


def build_body(b):
    b.side_loft(BODY_KEYS, body_color, **BODY_SHAPE, round_end=0.7)
    b.side_loft(HEAD_KEYS, head_color, mat_fn=head_mat, **HEAD_SHAPE, round_end=0.5)
    b.side_loft(JAW_KEYS, jaw_color, mat_fn=jaw_mat, **JAW_SHAPE, round_end=0.5)


def build_legs(b):
    shift = lambda keys: [(x + LEG_X, *rest) for x, *rest in keys]
    for sign in (1, -1):
        y = sign * LEG_Y
        b.limb(shift(THIGH_KEYS), y, limb_color(), round_start=0.9, round_end=0.6)
        b.limb(shift(SHIN_KEYS), y, limb_color(back_pale=True))
        b.limb(shift(FOOT_KEYS), y, plain_skin, round_start=0.6)
        fx, fz = FOOT_KEYS[-1][0] + LEG_X, FOOT_KEYS[-1][1]
        for t in TOES:
            spread = 0.18 * t                      # outer toes splay a little
            toe = [(fx - 0.3, fz, 0.48, 0.58),
                   (fx + TOE_LENGTH * 0.6, fz - 0.06, 0.44, 0.50),
                   (fx + TOE_LENGTH, fz - 0.10, 0.40, 0.42)]
            pts = catmull_rom(toe, RING_SPACING)
            b.loft([Vector((x, y + t + spread * (x - fx), z)) for x, z, _, _ in pts],
                   [(w, h) for _, _, w, h in pts], plain_skin, **LIMB_SHAPE,
                   segments=LIMB_SEGMENTS, round_end=0.6)


def build_arms(b):
    for sign in (1, -1):
        y = sign * ARM_Y
        b.limb(UPPER_ARM_KEYS, y, limb_color())
        b.limb(FOREARM_KEYS, y, limb_color(), round_end=0.5)


def build_details(b):
    teeth = TEETH_L

    # Claws: three per foot, a dew claw at the heel, two per hand.
    for sign in (1, -1):
        y = sign * LEG_Y
        fx, fz = FOOT_KEYS[-1][0] + LEG_X, FOOT_KEYS[-1][1]
        for t in TOES:
            tip_x = fx + TOE_LENGTH + 0.12
            ty = y + t + 0.18 * t * (tip_x - fx)
            b.cone(Vector((tip_x - 0.15, ty, fz - 0.12)), (1, 0.08 * t, -0.45),
                   0.17, 0.55, MAT_TEETH, teeth)
        hx = FOOT_KEYS[0][0] + LEG_X
        b.cone(Vector((hx - 0.35, y, 0.30)), (-1, 0, -0.35), 0.15, 0.45, MAT_TEETH, teeth)
        hx, hz = FOREARM_KEYS[-1][0], FOREARM_KEYS[-1][1]
        for dy in (-0.11, 0.11):
            b.cone(Vector((hx + 0.05, sign * ARM_Y + dy, hz - 0.05)), (0.7, 0, -1),
                   0.09, 0.42, MAT_TEETH, teeth)

    # Eyes: cyan iris, slit pupil, highlight. Brow bump above, horn behind.
    ex, ez, r = EYE_POS
    for sign in (1, -1):
        loc, nor = b.snap((ex, sign * 5, ez), (0, -sign, 0))
        if loc is None:
            continue
        center = loc - nor * 0.45 * r
        b.ellipsoid(center, (r, 0.6 * r, r), nor, MAT_EYE, EYE_L, segs=(20, 12))
        b.ellipsoid(center + nor * 0.58 * r, (0.22 * r, 0.12 * r, 0.70 * r), nor,
                    MAT_EYE, PUPIL_L, segs=(12, 8))
        b.ellipsoid(center + nor * 0.5 * r + Z_AXIS * 0.45 * r + X_AXIS * 0.35 * r,
                    (0.18 * r, 0.10 * r, 0.18 * r), nor, MAT_EYE, TEETH_L, segs=(8, 6))
        loc, nor = b.snap((ex - 0.1, sign * 5, ez + 0.42), (0, -sign, 0))
        if loc is not None:
            b.ellipsoid(loc - nor * 0.06, (0.55, 0.16, 0.16), nor, MAT_SKIN,
                        GREEN_L, segs=(14, 8))

        _, w, h = section_at(HEAD_KEYS, HORN_X)
        loc, nor = b.snap((HORN_X, sign * w * 0.36, 20), (0, 0, -1))
        if loc is not None:
            b.cone(loc - Z_AXIS * 0.15, (-0.9, sign * 0.25, 1.0), 0.38, 0.95,
                   MAT_SKIN, GREEN_TOP_L, segments=12)

        # Nostrils on top of the snout.
        loc, nor = b.snap((12.3, sign * 0.38, 20), (0, 0, -1))
        if loc is not None:
            b.ellipsoid(loc - nor * 0.02, (0.13, 0.05, 0.08), nor, MAT_SKIN,
                        STRIPE_L, segs=(10, 6))

    # Back of the throat, so the open mouth is closed off inside.
    b.ellipsoid(Vector((MOUTH_START_X + 0.1, 0, 7.20)), (0.8, 0.70, 0.45), Y_AXIS,
                MAT_MOUTH, TONGUE_L, segs=(16, 10))

    if ADD_TEETH:
        build_teeth(b)


def mouth_path(step=0.40):
    """(x, y-fraction-of-width) points round the jaw line: left side, front
    arc, right side."""
    side_xs = []
    x = 7.6
    while x < 11.3:
        side_xs.append(x)
        x += step
    pts = [(x, 1) for x in side_xs]
    pts += [(11.55 + 0.25 * math.cos(a), math.sin(a))
            for a in (math.radians(d) for d in (60, 25, -25, -60))]
    pts += [(x, -1) for x in reversed(side_xs)]
    return pts


def build_teeth(b):
    for x, frac in mouth_path():
        z_up, w_up, h_up = section_at(HEAD_KEYS, x)
        z_lo, w_lo, h_lo = section_at(JAW_KEYS, x)
        gap_z = 0.5 * ((z_up - h_up / 2) + (z_lo + h_lo / 2))
        y_up = frac * w_up * 0.38
        y_lo = frac * w_lo * 0.36
        size = 1.0 if 8.0 < x < 11.0 else 0.85
        loc, _ = b.snap((x, y_up, gap_z), (0, 0, 1), max_dist=2.0)
        if loc is not None:
            b.cone(loc + Z_AXIS * 0.10, (0, 0, -1), 0.14 * size, 0.48 * size,
                   MAT_TEETH, TEETH_L, segments=6)
        loc, _ = b.snap((x + 0.2, y_lo, gap_z), (0, 0, -1), max_dist=2.0)
        if loc is not None:
            b.cone(loc - Z_AXIS * 0.10, (0, 0, 1), 0.12 * size, 0.40 * size,
                   MAT_TEETH, TEETH_L, segments=6)


def build_mesh():
    b = Builder()
    build_body(b)
    build_legs(b)
    build_arms(b)
    b.build_bvh()        # details below snap onto the surface built so far
    build_details(b)

    bm = b.bm
    bmesh.ops.scale(bm, vec=(SCALE,) * 3, verts=bm.verts)
    bm.verts.index_update()
    cols = [0.0] * (len(bm.verts) * 4)
    for v in bm.verts:
        cols[v.index * 4:v.index * 4 + 4] = (*b.colors.get(v, GREEN_L), 1.0)

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
    if hasattr(me, "use_auto_smooth"):   # Blender < 4.1
        me.use_auto_smooth = True
        me.auto_smooth_angle = math.pi
    return me


# --------------------------------------------------------------------------
# Materials and scene
# --------------------------------------------------------------------------
def make_material(name, color, roughness=0.6):
    """Material that shows the vertex colours (swap in your own texture)."""
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.diffuse_color = (*srgb_to_linear(color), 1.0)   # viewport solid colour
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (400, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (100, 0)
    bsdf.inputs["Roughness"].default_value = roughness
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    vc = nt.nodes.new("ShaderNodeVertexColor")
    vc.location = (-200, 0)
    vc.layer_name = "Col"
    nt.links.new(vc.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


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
    me.materials.append(make_material("Skin", GREEN))
    me.materials.append(make_material("Mouth", MOUTH, roughness=0.4))
    me.materials.append(make_material("Teeth", TEETH, roughness=0.3))
    me.materials.append(make_material("Eye", EYE, roughness=0.08))

    obj = bpy.data.objects.new(NAME, me)
    coll.objects.link(obj)

    bpy.context.view_layer.update()
    for o in bpy.context.view_layer.objects:
        if o is not None:
            o.select_set(False)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    print(f"{NAME} created: {len(me.vertices)} verts, {tris} triangles")


main()
