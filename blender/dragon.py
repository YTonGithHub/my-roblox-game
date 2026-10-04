"""
Detailed "Dragon" model for Blender.

How to use:
  1. Open Blender, go to the Scripting tab.
  2. Open this file (or paste it in) and press "Run Script".
  3. A mesh named "Dragon" is created in a "Dragon" collection.
     Re-running the script replaces it.

What you get:
  - one smooth-shaded mesh: four-legged dragon with an S-curved neck, horned
    head with an open mouth and fangs, raised bat-style wings, a row of back
    spikes and a long tail ending in a spade;
  - colour stored as a vertex colour attribute "Col" (red skin, darker back,
    gold banded belly, orange wing membranes, ivory horns and claws, gold
    spikes, yellow slit eyes). Every material reads it, and it exports with
    FBX / glTF;
  - material slots "Skin", "Mouth", "Teeth", "Horn", "Eye" and "Wing" so you
    can put your own textures on each region;
  - a "UVMap" unwrapped per part at a uniform world scale (1 UV unit =
    UV_UNIT model units), so tiling textures line up across the body.

The model faces +X, stands on Z = 0 and is about 13 units tall to the wing
tips and 25 long with SCALE = 1.0. Works in Blender 3.6 through 5.x.
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
RING_SPACING = 0.32   # distance between cross-sections (smaller = smoother)
SEGMENTS = 18         # vertices around the body / neck / head sections
LIMB_SEGMENTS = 12    # vertices around legs, toes and horns
BONE_SEGMENTS = 8     # vertices around the wing bones
TOE_SEGMENTS = 10     # vertices around each toe
UV_UNIT = 1.0         # model units per 1.0 of UV space
NAME = "Dragon"

ADD_WINGS = True
ADD_SPIKES = True
ADD_HORNS = True
ADD_TEETH = True

# Colours (sRGB 0..1)
SKIN = (0.70, 0.12, 0.11)          # main red skin
SKIN_TOP = (0.45, 0.06, 0.08)      # darker along the back
BELLY = (0.97, 0.78, 0.38)         # gold belly plates
BELLY_LINE = (0.80, 0.52, 0.20)    # grooves between belly plates
WING = (0.98, 0.52, 0.22)          # wing membrane
WING_EDGE = (0.78, 0.22, 0.12)     # membrane next to the wing bones
HORN = (0.96, 0.92, 0.80)          # horn tips and claws
HORN_BASE = (0.50, 0.38, 0.30)     # horn roots
SPIKE = (0.98, 0.76, 0.32)         # back spikes and tail spade
MOUTH = (0.90, 0.40, 0.45)         # inside of the mouth
TONGUE = (0.60, 0.05, 0.10)
TEETH = (0.98, 0.98, 0.95)
EYE = (1.00, 0.80, 0.08)           # yellow iris
PUPIL = (0.02, 0.02, 0.03)

BELLY_PLATE = 0.55    # length of one belly plate

# --------------------------------------------------------------------------
# Shape data. Side-view key sections (x, z, width, height) joined by a smooth
# spline and lofted with a rounded-box profile.
# --------------------------------------------------------------------------
BODY_KEYS = [                     # tail tip -> chest
    (-14.00, 2.60, 0.18, 0.16),   # tail tip (spade attaches here)
    (-12.50, 2.20, 0.45, 0.40),
    (-11.00, 2.30, 0.70, 0.62),
    (-9.50,  2.80, 0.95, 0.85),
    (-8.00,  3.50, 1.25, 1.15),
    (-6.50,  4.20, 1.60, 1.55),
    (-5.00,  4.75, 2.10, 2.10),
    (-3.60,  5.05, 2.80, 2.90),   # hips
    (-2.00,  5.15, 3.30, 3.50),
    (0.00,   5.15, 3.50, 3.70),   # middle of the body
    (1.80,   5.25, 3.40, 3.60),
    (3.00,   5.45, 3.00, 3.20),   # chest
    (3.80,   5.70, 2.30, 2.40),   # front of chest (rounded off)
]
NECK_KEYS = [                     # chest -> back of the head (S-curve)
    (2.00, 6.00, 2.50, 2.60),     # buried in the shoulders
    (3.40, 6.90, 2.00, 2.00),
    (4.40, 8.00, 1.65, 1.65),
    (5.00, 9.20, 1.45, 1.45),
    (5.50, 10.30, 1.35, 1.35),
    (6.10, 11.00, 1.30, 1.30),
    (6.80, 11.30, 1.25, 1.25),
]
HEAD_KEYS = [                     # back of skull -> snout (upper jaw)
    (6.30, 11.45, 1.40, 1.50),
    (7.00, 11.50, 1.60, 1.55),
    (7.80, 11.45, 1.55, 1.40),    # eyes
    (8.70, 11.30, 1.35, 1.15),
    (9.60, 11.15, 1.15, 0.95),
    (10.20, 11.08, 1.00, 0.80),   # snout tip (rounded off)
]
JAW_KEYS = [                      # throat -> chin (lower jaw, slightly open)
    (6.30, 10.60, 1.25, 1.10),
    (7.20, 10.45, 1.30, 0.90),
    (8.40, 10.15, 1.15, 0.70),
    (9.50, 9.95, 1.00, 0.55),
    (10.00, 9.88, 0.90, 0.50),    # chin (rounded off)
]
MOUTH_START_X = 7.6               # inside of the mouth starts here

BODY_SHAPE = dict(exponent=2.6, top_narrow=0.82)
NECK_SHAPE = dict(exponent=2.3, top_narrow=0.85)
HEAD_SHAPE = dict(exponent=2.8, top_narrow=0.85)
JAW_SHAPE = dict(exponent=2.8, top_narrow=1.0)
LIMB_SHAPE = dict(exponent=2.6, top_narrow=1.0)

# Legs: keys of (x, z, width_y, depth_x) from top to bottom, at a fixed y.
BACK_LEG_Y = 1.45
BACK_THIGH = [(-2.60, 5.30, 1.30, 2.20), (-2.40, 4.30, 1.50, 2.50),
              (-2.10, 3.10, 1.30, 1.80), (-1.90, 2.40, 1.00, 1.20)]
BACK_SHIN = [(-1.90, 2.50, 1.00, 1.20), (-2.40, 1.50, 0.90, 1.00),
             (-2.70, 0.80, 0.85, 0.90), (-2.60, 0.45, 0.90, 0.90)]
BACK_FOOT = [(-3.10, 0.30, 1.00, 0.60), (-2.30, 0.30, 1.10, 0.60),
             (-1.80, 0.28, 1.15, 0.55)]              # (x, z, w, h) heel -> ball
FRONT_LEG_Y = 1.30
FRONT_UPPER = [(2.10, 5.00, 1.00, 1.50), (2.30, 3.80, 1.00, 1.30),
               (2.10, 2.60, 0.85, 1.00)]
FRONT_LOWER = [(2.10, 2.70, 0.85, 0.95), (2.40, 1.40, 0.75, 0.80),
               (2.50, 0.55, 0.75, 0.80)]
FRONT_FOOT = [(2.20, 0.30, 0.95, 0.60), (2.90, 0.28, 1.00, 0.55)]
TOES = [-0.36, 0.0, 0.36]         # toe offsets across each foot
TOE_LENGTH = 0.80

# Wing (right side, mirrored to the left): shoulder, elbow, wrist, finger
# tips and the point on the body side where the membrane attaches.
WING_SHOULDER = (1.60, 1.05, 6.80)
WING_ELBOW = (0.80, 3.20, 8.40)
WING_WRIST = (1.60, 4.60, 10.20)
WING_FINGERS = [(-0.60, 7.60, 11.00), (-2.40, 7.00, 9.00), (-3.40, 5.00, 7.30)]
WING_BODY = (-2.60, 1.15, 6.40)
WING_SCALLOP = 0.22               # how deep the trailing edge curves in
WING_SIZE = 1.30                  # scales the wing out from the shoulder

EYE_POS = (7.90, 11.72, 0.21)     # (x, z, radius), snapped onto the head
HORN_PATH = [(6.70, 0.45, 11.80), (6.10, 0.60, 12.45), (5.30, 0.75, 12.85),
             (4.50, 0.85, 12.95)]  # right horn, root -> tip
HORN_RADII = [0.26, 0.20, 0.12, 0.03]

MAT_SKIN, MAT_MOUTH, MAT_TEETH, MAT_HORN, MAT_EYE, MAT_WING = range(6)

X_AXIS = Vector((1, 0, 0))
Y_AXIS = Vector((0, 1, 0))
Z_AXIS = Vector((0, 0, 1))


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def srgb_to_linear(c):
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c)


(SKIN_L, SKIN_TOP_L, BELLY_L, BELLY_LINE_L, WING_L, WING_EDGE_L, HORN_L,
 HORN_BASE_L, SPIKE_L, MOUTH_L, TONGUE_L, TEETH_L, EYE_L, PUPIL_L) = (
    srgb_to_linear(c) for c in (SKIN, SKIN_TOP, BELLY, BELLY_LINE, WING,
                                WING_EDGE, HORN, HORN_BASE, SPIKE, MOUTH,
                                TONGUE, TEETH, EYE, PUPIL))


def smoothstep(e0, e1, x):
    t = min(max((x - e0) / (e1 - e0), 0.0), 1.0)
    return t * t * (3 - 2 * t)


def mix(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def band(pos, period, width):
    """0..1 weight of a repeating band along a distance."""
    p = (pos / period) % 1.0
    edge = min(0.05, width / 3)
    return smoothstep(0.0, edge, p) * (1.0 - smoothstep(width - edge, width, p))


def skin(u, along, belly=1.0, top=True):
    """Red skin with a darker back and a gold plated belly.
    u is -1 (underside) .. 1 (top) of the section."""
    col = SKIN_L
    if top:
        col = mix(col, SKIN_TOP_L, smoothstep(0.30, 1.0, u))
    if belly:
        plate = mix(BELLY_L, BELLY_LINE_L, band(along, BELLY_PLATE, 0.16))
        col = mix(col, plate, belly * smoothstep(-0.30, -0.55, u))
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


def resample_polyline(points, radii, spacing):
    """Evenly spaced points (and interpolated radii) along a 3D polyline."""
    pts, rs = [Vector(points[0])], [radii[0]]
    for (a, ra), (b, rb) in zip(zip(points, radii), zip(points[1:], radii[1:])):
        a, b = Vector(a), Vector(b)
        steps = max(1, math.ceil((b - a).length / spacing))
        for s in range(1, steps + 1):
            t = s / steps
            pts.append(a.lerp(b, t))
            rs.append(ra + (rb - ra) * t)
    return pts, rs


def point_on_polyline(points, t):
    """Point at fraction t (0..1) of the length of a polyline."""
    lengths = [(b - a).length for a, b in zip(points, points[1:])]
    target = t * sum(lengths)
    for (a, b), seg in zip(zip(points, points[1:]), lengths):
        if target <= seg or seg == lengths[-1]:
            return a.lerp(b, min(target / seg, 1.0) if seg else 0.0)
        target -= seg
    return points[-1].copy()


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
             segments=SEGMENTS, mat_fn=None, mat=MAT_SKIN):
        """Loft rounded sections through `centers` (Vectors).

        The section's up axis is tangent x side, so for a forward-running path
        with side = +Y it points to +Z. Faces are wound outward.
        color_fn(u, s, along, center) -> linear RGB, with u / s in -1..1 across
        the section height / width and `along` the distance along the loft.
        mat_fn(u, s, along, center) -> material index (default `mat`).
        Returns [(center, up, tangent, w, h, along)] for every ring.
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

        rings, profiles, info, mats = [], [], [], {}
        for i, (c, (w, h)) in enumerate(zip(centers, sizes)):
            tangent = (centers[min(i + 1, n - 1)] - centers[max(i - 1, 0)]).normalized()
            sd = (side - tangent * side.dot(tangent)).normalized()
            up = tangent.cross(sd).normalized()
            prof = profile(w, h, exponent, top_narrow, segments)
            ring = []
            for s, u in prof:
                v = bm.verts.new(c + s * sd + u * up)
                un = u / (h / 2) if h > 1e-6 else 0.0
                sn = s / (w / 2) if w > 1e-6 else 0.0
                self.colors[v] = color_fn(un, sn, vs[i], c)
                mats[v] = mat_fn(un, sn, vs[i], c) if mat_fn else mat
                ring.append(v)
            rings.append(ring)
            profiles.append(prof)
            info.append((c, up, tangent, w, h, vs[i]))

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
        return info

    def side_loft(self, keys, color_fn, y=0.0, **kw):
        """Loft keys (x, z, w, h) lying in a plane of constant y."""
        pts = catmull_rom(keys, RING_SPACING)
        return self.loft([Vector((x, y, z)) for x, z, _, _ in pts],
                         [(w, h) for _, _, w, h in pts], color_fn, **kw)

    def tube(self, points, radii, color_fn, segments=BONE_SEGMENTS, **kw):
        """Round tube along a 3D polyline with tapering radii."""
        pts, rs = resample_polyline(points, radii, RING_SPACING)
        kw.setdefault("side", Z_AXIS)
        return self.loft(pts, [(2 * r, 2 * r) for r in rs], color_fn,
                         exponent=2.0, segments=segments, **kw)

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

    def cone(self, base, direction, radius, length, mat, color, segments=8, thin=1.0):
        """Pointed cone from `base` towards `direction`. thin < 1 flattens it
        sideways (across world Y) into a blade."""
        d = Vector(direction).normalized()
        rot = d.to_track_quat("Z", "Y").to_matrix().to_4x4()
        mtx = (Matrix.Translation(base + d * length / 2) @ rot
               @ Matrix.Diagonal((1.0, thin, 1.0, 1.0)))
        kw = dict(cap_ends=True, cap_tris=False, segments=segments, depth=length,
                  matrix=mtx, calc_uvs=True)
        try:
            res = bmesh.ops.create_cone(self.bm, radius1=radius, radius2=0.0, **kw)
        except TypeError:
            res = bmesh.ops.create_cone(self.bm, diameter1=radius, diameter2=0.0, **kw)
        self._finish(res["verts"], mat, color)

    def membrane(self, line_a, line_b, scallop, rows=7, cols=5, thick=0.035):
        """Thin closed wing panel between two polylines that start at the same
        point (the wrist). The far edge curves inwards by `scallop`."""
        bm = self.bm
        apex = line_a[0]
        normal = (line_a[-1] - apex).cross(line_b[-1] - apex).normalized()
        off = normal * thick

        grid = [[None] * (cols + 1) for _ in range(rows + 1)]
        for i in range(1, rows + 1):
            for j in range(cols + 1):
                a = j / cols
                t = i / rows * (1 - scallop * math.sin(math.pi * a))
                grid[i][j] = point_on_polyline(line_a, t).lerp(
                    point_on_polyline(line_b, t), a)

        def colour(i, j):
            a = j / cols
            near_bone = 1 - smoothstep(0.0, 0.22, min(a, 1 - a))
            near_wrist = 1 - smoothstep(0.0, 0.35, i / rows)
            return mix(WING_L, WING_EDGE_L, max(near_bone, near_wrist) * 0.8)

        layers = []
        for sgn in (1, -1):
            top = bm.verts.new(apex + off * sgn)
            self.colors[top] = WING_EDGE_L
            vs = [[top] * (cols + 1)]
            for i in range(1, rows + 1):
                row = []
                for j in range(cols + 1):
                    v = bm.verts.new(grid[i][j] + off * sgn)
                    self.colors[v] = colour(i, j)
                    row.append(v)
                vs.append(row)
            layers.append(vs)

        faces = []
        span = (line_b[-1] - line_a[-1]).length
        length = max((line_a[-1] - apex).length, (line_b[-1] - apex).length)

        def add(verts, uvs):
            f = bm.faces.new(verts)
            f.material_index = MAT_WING
            f.smooth = True
            for loop, (u, v) in zip(f.loops, uvs):
                loop[self.uv].uv = (u * span / UV_UNIT, v * length / UV_UNIT)
            faces.append(f)
            return f

        for vs in layers:
            for i in range(rows):
                for j in range(cols):
                    a0, a1, t0, t1 = j / cols, (j + 1) / cols, i / rows, (i + 1) / rows
                    if i == 0:
                        add((vs[0][0], vs[1][j], vs[1][j + 1]),
                            ((0.5, 0), (a0, t1), (a1, t1)))
                    else:
                        add((vs[i][j], vs[i][j + 1], vs[i + 1][j + 1], vs[i + 1][j]),
                            ((a0, t0), (a1, t0), (a1, t1), (a0, t1)))

        # Rim joining the two layers, with a crisp edge.
        top, bot = layers
        rim = ([(top[i][0], top[i + 1][0], bot[i + 1][0], bot[i][0]) for i in range(rows)]
               + [(top[rows][j], top[rows][j + 1], bot[rows][j + 1], bot[rows][j])
                  for j in range(cols)]
               + [(top[i + 1][cols], top[i][cols], bot[i][cols], bot[i + 1][cols])
                  for i in range(rows)])
        for t1, t2, b2, b1 in rim:
            verts = (t1, t2, b2, b1) if t1 is not t2 else (t1, b2, b1)
            if len(set(verts)) < 3:
                continue
            f = add(verts, ((0, 0), (1, 0), (1, 1), (0, 1))[:len(verts)])
            for e in f.edges:
                e.smooth = False
        bmesh.ops.recalc_face_normals(bm, faces=faces)

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
# Colour functions for the lofts
# --------------------------------------------------------------------------
def body_color(u, s, along, c):
    return skin(u, c.x)


def neck_color(u, s, along, c):
    return skin(u, along)


def head_color(u, s, along, c):
    inside = smoothstep(MOUTH_START_X - 0.3, MOUTH_START_X + 0.2, c.x)
    col = skin(u, along, belly=0.0)
    return mix(col, MOUTH_L, inside * smoothstep(-0.80, -0.92, u))   # palate


def head_mat(u, s, along, c):
    return MAT_MOUTH if c.x > MOUTH_START_X and u < -0.86 else MAT_SKIN


def jaw_color(u, s, along, c):
    inside = smoothstep(MOUTH_START_X - 0.3, MOUTH_START_X + 0.2, c.x)
    col = skin(u, along, top=False)
    col = mix(col, MOUTH_L, inside * smoothstep(0.80, 0.92, u))
    tongue = inside * smoothstep(0.90, 0.97, u) * (1 - smoothstep(0.35, 0.55, abs(s)))
    return mix(col, TONGUE_L, tongue * (1 - smoothstep(9.0, 9.6, c.x)))


def jaw_mat(u, s, along, c):
    return MAT_MOUTH if c.x > MOUTH_START_X and u > 0.86 else MAT_SKIN


def limb_color(u, s, along, c):
    return mix(SKIN_L, SKIN_TOP_L, 0.25 * smoothstep(1.5, 0.3, c.z))   # darker feet


def plain(color):
    return lambda u, s, along, c: color


# --------------------------------------------------------------------------
# Parts
# --------------------------------------------------------------------------
def build_body(b):
    body = b.side_loft(BODY_KEYS, body_color, **BODY_SHAPE, round_end=0.7)
    neck = b.side_loft(NECK_KEYS, neck_color, **NECK_SHAPE)
    b.side_loft(HEAD_KEYS, head_color, mat_fn=head_mat, **HEAD_SHAPE,
                round_start=0.7, round_end=0.5)
    b.side_loft(JAW_KEYS, jaw_color, mat_fn=jaw_mat, **JAW_SHAPE, round_end=0.5)
    return body, neck


def build_tail_spade(b):
    """Flat arrow-shaped spade on the end of the tail."""
    tip = Vector((BODY_KEYS[0][0], 0.0, BODY_KEYS[0][1]))
    prev = Vector((BODY_KEYS[1][0], 0.0, BODY_KEYS[1][1]))
    d = (tip - prev).normalized()
    keys = [(-0.25, 0.22, 0.20), (0.25, 1.40, 0.24), (0.55, 1.20, 0.22),
            (1.10, 0.55, 0.14), (1.55, 0.06, 0.05)]       # (offset, width, thick)
    centers = [tip + d * o for o, _, _ in keys]
    pts = catmull_rom([(c.x, c.z, w, h) for c, (_, w, h) in zip(centers, keys)], 0.12)
    b.loft([Vector((x, 0, z)) for x, z, _, _ in pts], [(w, h) for _, _, w, h in pts],
           plain(SPIKE_L), exponent=2.2, segments=LIMB_SEGMENTS, mat=MAT_HORN)


def build_legs(b):
    for sign in (1, -1):
        for upper, lower, foot, y, round_top in (
                (BACK_THIGH, BACK_SHIN, BACK_FOOT, sign * BACK_LEG_Y, 0.9),
                (FRONT_UPPER, FRONT_LOWER, FRONT_FOOT, sign * FRONT_LEG_Y, 0.6)):
            b.side_loft(upper, limb_color, y=y, **LIMB_SHAPE, segments=LIMB_SEGMENTS,
                        round_start=round_top, round_end=0.6)
            b.side_loft(lower, limb_color, y=y, **LIMB_SHAPE, segments=LIMB_SEGMENTS,
                        round_start=0.8)
            b.side_loft(foot, limb_color, y=y, **LIMB_SHAPE, segments=LIMB_SEGMENTS,
                        round_start=0.6)
            fx, fz = foot[-1][0], foot[-1][1]
            for t in TOES:
                spread = 0.15 * t
                toe = [(fx - 0.3, fz, 0.40, 0.48),
                       (fx + TOE_LENGTH * 0.6, fz - 0.05, 0.36, 0.42),
                       (fx + TOE_LENGTH, fz - 0.08, 0.32, 0.36)]
                pts = catmull_rom(toe, RING_SPACING)
                b.loft([Vector((x, y + t + spread * (x - fx), z)) for x, z, _, _ in pts],
                       [(w, h) for _, _, w, h in pts], limb_color, **LIMB_SHAPE,
                       segments=TOE_SEGMENTS, round_end=0.6)
                tip_x = fx + TOE_LENGTH + 0.08
                ty = y + t + spread * (tip_x - fx)
                b.cone(Vector((tip_x - 0.12, ty, fz - 0.10)), (1, 0.08 * t, -0.45),
                       0.13, 0.42, MAT_TEETH, HORN_L)
            if foot is BACK_FOOT:          # dew claw on the heel
                b.cone(Vector((foot[0][0] - 0.30, y, 0.28)), (-1, 0, -0.35),
                       0.12, 0.36, MAT_TEETH, HORN_L)


def build_wings(b):
    for sign in (1, -1):
        root = Vector(WING_SHOULDER)

        def m(p, grow=True):
            p = root + (Vector(p) - root) * (WING_SIZE if grow else 1.0)
            return Vector((p.x, sign * p.y, p.z))

        shoulder, elbow, wrist = m(WING_SHOULDER), m(WING_ELBOW), m(WING_WRIST)
        tips = [m(p) for p in WING_FINGERS]
        attach = m(WING_BODY, grow=False)    # stays on the body side

        # Bones: arm, then fingers fanning out from the wrist.
        b.tube([shoulder, elbow, wrist], [0.42, 0.30, 0.22], plain(SKIN_L),
               round_start=0.8, round_end=0.8)
        for tip, r in zip(tips, (0.15, 0.13, 0.12)):
            b.tube([wrist, tip], [r, 0.04], plain(SKIN_TOP_L), round_end=0.8)
        b.cone(wrist + Vector((0.1, 0, 0.1)), (0.8, 0, 0.6), 0.10, 0.45,
               MAT_TEETH, HORN_L)                               # thumb claw

        # Membrane panels between neighbouring lines from the wrist.
        arm_line = [wrist, elbow, shoulder]
        lines = [[wrist, t] for t in tips] + [[wrist, attach]]
        for la, lb in zip(lines, lines[1:]):
            b.membrane(la, lb, WING_SCALLOP)
        b.membrane([wrist, attach], arm_line, 0.0)               # inner panel


def build_horns(b):
    for sign in (1, -1):
        path = [Vector((x, sign * y, z)) for x, y, z in HORN_PATH]

        def horn_color(u, s, along, c):
            t = smoothstep(0.0, 1.6, along)
            col = mix(HORN_BASE_L, HORN_L, t)
            return mix(col, HORN_BASE_L, 0.35 * band(along, 0.32, 0.25) * (1 - t))

        b.tube(path, HORN_RADII, horn_color, segments=LIMB_SEGMENTS, side=Y_AXIS,
               mat=MAT_HORN, round_end=0.5)
        # Small swept-back spikes on the cheeks.
        b.cone(Vector((6.75, sign * 0.55, 10.75)), (-1, sign * 0.5, 0.15), 0.14, 0.60,
               MAT_HORN, HORN_L)
        b.cone(Vector((6.95, sign * 0.62, 11.15)), (-1, sign * 0.55, 0.35), 0.12, 0.50,
               MAT_HORN, HORN_L)


def build_spikes(b, body, neck):
    """Gold blade-shaped spikes along the top of the tail, back and neck."""
    def place(rings, keep):
        last = -10.0
        for c, up, tangent, w, h, along in rings:
            if not keep(c, along) or along - last < 0.62:
                continue
            last = along
            size = min(max(0.42 * h, 0.22), 0.95)
            direction = (up - tangent * 0.55).normalized()
            base = c + up * (h / 2 - 0.08 * size)
            b.cone(base, direction, 0.48 * size, size, MAT_HORN, SPIKE_L,
                   segments=6, thin=0.35)

    place(body, lambda c, along: along > 0.8 and c.x < 2.2)
    place(neck, lambda c, along: along > 1.6 and c.x < 6.1)


def build_face(b):
    ex, ez, r = EYE_POS
    for sign in (1, -1):
        loc, nor = b.snap((ex, sign * 5, ez), (0, -sign, 0))
        if loc is not None:
            center = loc - nor * 0.45 * r
            b.ellipsoid(center, (r * 1.15, 0.6 * r, r), nor, MAT_EYE, EYE_L, segs=(14, 10))
            b.ellipsoid(center + nor * 0.58 * r, (0.18 * r, 0.12 * r, 0.75 * r), nor,
                        MAT_EYE, PUPIL_L, segs=(10, 6))
            b.ellipsoid(center + nor * 0.5 * r + Z_AXIS * 0.42 * r + X_AXIS * 0.35 * r,
                        (0.16 * r, 0.09 * r, 0.16 * r), nor, MAT_EYE, TEETH_L, segs=(8, 6))
        loc, nor = b.snap((ex - 0.05, sign * 5, ez + 0.32), (0, -sign, 0))
        if loc is not None:                                     # brow ridge
            b.ellipsoid(loc - nor * 0.05, (0.42, 0.13, 0.13), nor, MAT_SKIN,
                        SKIN_TOP_L, segs=(14, 8))
        loc, nor = b.snap((10.05, sign * 0.22, 20), (0, 0, -1))
        if loc is not None:                                     # nostril
            b.ellipsoid(loc - nor * 0.02, (0.10, 0.04, 0.06), nor, MAT_SKIN,
                        PUPIL_L, segs=(10, 6))

    # Back of the throat, so the open mouth is closed off inside.
    b.ellipsoid(Vector((MOUTH_START_X, 0, 10.75)), (0.55, 0.50, 0.30), Y_AXIS,
                MAT_MOUTH, TONGUE_L, segs=(14, 8))


def build_teeth(b):
    def gap_z(x):
        z_up, _, h_up = section_at(HEAD_KEYS, x)
        z_lo, _, h_lo = section_at(JAW_KEYS, x)
        return 0.5 * ((z_up - h_up / 2) + (z_lo + h_lo / 2))

    xs = [7.9 + 0.30 * i for i in range(6)]
    for sign in (1, -1):
        for x in xs:
            _, w_up, _ = section_at(HEAD_KEYS, x)
            _, w_lo, _ = section_at(JAW_KEYS, x)
            loc, _ = b.snap((x, sign * w_up * 0.38, gap_z(x)), (0, 0, 1), max_dist=1.5)
            if loc is not None:
                b.cone(loc + Z_AXIS * 0.06, (0, 0, -1), 0.07, 0.26, MAT_TEETH, TEETH_L,
                       segments=6)
            loc, _ = b.snap((x + 0.15, sign * w_lo * 0.36, gap_z(x)), (0, 0, -1),
                            max_dist=1.5)
            if loc is not None:
                b.cone(loc - Z_AXIS * 0.06, (0, 0, 1), 0.06, 0.22, MAT_TEETH, TEETH_L,
                       segments=6)
        # Big fangs near the front of both jaws.
        loc, _ = b.snap((9.75, sign * 0.30, gap_z(9.75)), (0, 0, 1), max_dist=1.5)
        if loc is not None:
            b.cone(loc + Z_AXIS * 0.08, (0.05, 0, -1), 0.11, 0.48, MAT_TEETH, TEETH_L,
                   segments=8)
        loc, _ = b.snap((9.55, sign * 0.26, gap_z(9.55)), (0, 0, -1), max_dist=1.5)
        if loc is not None:
            b.cone(loc - Z_AXIS * 0.08, (0.05, 0, 1), 0.09, 0.38, MAT_TEETH, TEETH_L,
                   segments=8)


def build_mesh():
    b = Builder()
    body, neck = build_body(b)
    build_tail_spade(b)
    build_legs(b)
    b.build_bvh()        # face details below snap onto the head
    build_face(b)
    if ADD_TEETH:
        build_teeth(b)
    if ADD_HORNS:
        build_horns(b)
    if ADD_SPIKES:
        build_spikes(b, body, neck)
    if ADD_WINGS:
        build_wings(b)

    bm = b.bm
    bmesh.ops.scale(bm, vec=(SCALE,) * 3, verts=bm.verts)
    bm.verts.index_update()
    cols = [0.0] * (len(bm.verts) * 4)
    for v in bm.verts:
        cols[v.index * 4:v.index * 4 + 4] = (*b.colors.get(v, SKIN_L), 1.0)

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
    me.materials.append(make_material("Skin", SKIN))
    me.materials.append(make_material("Mouth", MOUTH, roughness=0.4))
    me.materials.append(make_material("Teeth", TEETH, roughness=0.3))
    me.materials.append(make_material("Horn", HORN, roughness=0.35))
    me.materials.append(make_material("Eye", EYE, roughness=0.08))
    me.materials.append(make_material("Wing", WING, roughness=0.7))

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
