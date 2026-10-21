class_name ProcBuilder
extends RefCounted
## Procedural mesh builder for clean, game-ready rebuilds of AI scans.
## One SurfaceTool per material key, so each material ends up as one surface (one draw call).
##
##   var b := ProcBuilder.new()
##   b.use("wood", 0.4)                      # material key + per-part tint (vertex color R)
##   b.box(Transform3D(Basis(), Vector3(0, 0.25, 0)), Vector3(0.5, 0.25, 0.3), 0.012)
##   b.use("metal")
##   b.cylinder(Transform3D(Basis(), Vector3(0, 0.5, 0)), 0.04, 0.01, 16)
##   b.lathe([Vector2(0, 0), Vector2(0.06, 0), Vector2(0.05, 0.12), Vector2(0.09, 0.2)], 24)
##   var mi := b.commit("Body", {"wood": wood_mat, "metal": metal_mat})
##
## Vertex color carries shader masks: R = per-part tint (vary planks / panels),
## G = 1 on chamfer edges (edge wear, highlights). UV0 is a planar box projection in
## meters, so tiling shaders keep a constant texel density across parts.
## Godot treats CLOCKWISE triangles as front faces; tri() orients every triangle from
## its normals, so callers never worry about winding.

var tools := {}
var cur := "default"
var tint := 0.5
var edge := 0.0

func use(mat: String, t: float = 0.5) -> void:
	cur = mat
	tint = t
	if not tools.has(mat):
		var s := SurfaceTool.new()
		s.begin(Mesh.PRIMITIVE_TRIANGLES)
		tools[mat] = s

## Build an ArrayMesh (one surface per material key) wrapped in a MeshInstance3D.
## Set each material's resource_name to its key so export_glb.gd / the bake keep the class.
func commit(node_name: String, mats: Dictionary = {}) -> MeshInstance3D:
	var mesh := ArrayMesh.new()
	for key in tools.keys():
		var s: SurfaceTool = tools[key]
		s.index()
		s.commit(mesh)
		var m: Material = mats.get(key, null)
		if m == null:
			m = StandardMaterial3D.new()
		if m.resource_name == "": m.resource_name = key
		mesh.surface_set_material(mesh.get_surface_count() - 1, m)
	var mi := MeshInstance3D.new()
	mi.name = node_name
	mi.mesh = mesh
	return mi

# ---------------------------------------------------------------- core
func _v(s: SurfaceTool, p: Vector3, n: Vector3, uv: Vector2) -> void:
	s.set_normal(n)
	s.set_uv(uv)
	s.set_color(Color(tint, edge, 0))
	s.add_vertex(p)

func tri(a: Vector3, b: Vector3, c: Vector3, na: Vector3, nb: Vector3, nc: Vector3, ua: Vector2, ub: Vector2, uc: Vector2) -> void:
	if not tools.has(cur): use(cur, tint)
	var s: SurfaceTool = tools[cur]
	if (b - a).cross(c - a).dot(na + nb + nc) > 0.0:
		_v(s, a, na, ua); _v(s, c, nc, uc); _v(s, b, nb, ub)
	else:
		_v(s, a, na, ua); _v(s, b, nb, ub); _v(s, c, nc, uc)

func quad_n(a: Vector3, b: Vector3, c: Vector3, d: Vector3, na: Vector3, nb: Vector3, nc: Vector3, nd: Vector3, ua: Vector2, ub: Vector2, uc: Vector2, ud: Vector2) -> void:
	tri(a, b, c, na, nb, nc, ua, ub, uc)
	tri(a, c, d, na, nc, nd, ua, uc, ud)

static func _uv(p: Vector3, n: Vector3) -> Vector2:
	var an := n.abs()
	if an.x >= an.y and an.x >= an.z:
		return Vector2(p.z, p.y)
	elif an.y >= an.z:
		return Vector2(p.x, p.z)
	return Vector2(p.x, p.y)

func _face(xf: Transform3D, pts: Array, n: Vector3, uvn: Vector3) -> void:
	var wn := (xf.basis * n).normalized()
	var w := []
	var u := []
	for p in pts:
		w.append(xf * p)
		u.append(_uv(p, uvn))
	if pts.size() == 4:
		quad_n(w[0], w[1], w[2], w[3], wn, wn, wn, wn, u[0], u[1], u[2], u[3])
	else:
		tri(w[0], w[1], w[2], wn, wn, wn, u[0], u[1], u[2])

static func _fp(h: Vector3, b: float, axis: int, s: Vector3) -> Vector3:
	var p := Vector3(s.x * (h.x - b), s.y * (h.y - b), s.z * (h.z - b))
	p[axis] = s[axis] * h[axis]
	return p

# ---------------------------------------------------------------- primitives
## Chamfered box: half extents h, chamfer b. Chamfers catch light — never ship razor edges.
func box(xf: Transform3D, h: Vector3, b: float) -> void:
	b = minf(b, minf(h.x, minf(h.y, h.z)) * 0.9)
	for axis in 3:
		for sg: float in [-1.0, 1.0]:
			var n := Vector3.ZERO
			n[axis] = sg
			var ua := (axis + 1) % 3
			var va := (axis + 2) % 3
			var pts := []
			for c in [Vector2(-1, -1), Vector2(1, -1), Vector2(1, 1), Vector2(-1, 1)]:
				var s := Vector3.ZERO
				s[axis] = sg; s[ua] = c.x; s[va] = c.y
				pts.append(_fp(h, b, axis, s))
			_face(xf, pts, n, n)
	if b <= 0.0:
		return
	edge = 1.0
	for a1 in 3:
		for a2 in range(a1 + 1, 3):
			var a3 := 3 - a1 - a2
			for s1: float in [-1.0, 1.0]:
				for s2: float in [-1.0, 1.0]:
					var n := Vector3.ZERO
					n[a1] = s1; n[a2] = s2
					var sa := Vector3.ZERO; sa[a1] = s1; sa[a2] = s2; sa[a3] = -1.0
					var sb := sa; sb[a3] = 1.0
					var pts := [_fp(h, b, a1, sa), _fp(h, b, a1, sb), _fp(h, b, a2, sb), _fp(h, b, a2, sa)]
					var uvn := Vector3.ZERO; uvn[a1] = 1.0
					_face(xf, pts, n.normalized(), uvn)
	for sx: float in [-1.0, 1.0]:
		for sy: float in [-1.0, 1.0]:
			for sz: float in [-1.0, 1.0]:
				var s := Vector3(sx, sy, sz)
				_face(xf, [_fp(h, b, 0, s), _fp(h, b, 1, s), _fp(h, b, 2, s)], s.normalized(), Vector3(0, 0, 1))
	edge = 0.0

static func _ap(x: float, r: float, t: float, cy: float, cz: float) -> Vector3:
	return Vector3(x, cy + r * sin(t), cz + r * cos(t))

## Thick ring segment around the X axis, x0..x1, radii r0..r1, angles t0..t1 (barrel lids,
## arches, straps that follow a curve, pipe bends). Center (cy, cz).
func arc(x0: float, x1: float, r0: float, r1: float, t0: float, t1: float, cy: float, cz: float, seg: int) -> void:
	if x0 > x1:
		var tmp := x0; x0 = x1; x1 = tmp
	for i in seg:
		var ta := lerpf(t0, t1, float(i) / seg)
		var tb := lerpf(t0, t1, float(i + 1) / seg)
		var da := Vector3(0, sin(ta), cos(ta))
		var db := Vector3(0, sin(tb), cos(tb))
		quad_n(_ap(x0, r1, ta, cy, cz), _ap(x1, r1, ta, cy, cz), _ap(x1, r1, tb, cy, cz), _ap(x0, r1, tb, cy, cz), da, da, db, db,
			Vector2(x0, r1 * ta), Vector2(x1, r1 * ta), Vector2(x1, r1 * tb), Vector2(x0, r1 * tb))
		quad_n(_ap(x0, r0, ta, cy, cz), _ap(x1, r0, ta, cy, cz), _ap(x1, r0, tb, cy, cz), _ap(x0, r0, tb, cy, cz), -da, -da, -db, -db,
			Vector2(x0, r0 * ta), Vector2(x1, r0 * ta), Vector2(x1, r0 * tb), Vector2(x0, r0 * tb))
		for xs: float in [x0, x1]:
			var nx := Vector3(-1, 0, 0) if xs == x0 else Vector3(1, 0, 0)
			quad_n(_ap(xs, r0, ta, cy, cz), _ap(xs, r1, ta, cy, cz), _ap(xs, r1, tb, cy, cz), _ap(xs, r0, tb, cy, cz), nx, nx, nx, nx,
				Vector2(r0 * ta, r0), Vector2(r1 * ta, r1), Vector2(r1 * tb, r1), Vector2(r0 * tb, r0))
	for k in 2:
		var t := t0 if k == 0 else t1
		var tg := Vector3(0, cos(t), -sin(t)) * (-1.0 if k == 0 else 1.0)
		quad_n(_ap(x0, r0, t, cy, cz), _ap(x1, r0, t, cy, cz), _ap(x1, r1, t, cy, cz), _ap(x0, r1, t, cy, cz), tg, tg, tg, tg,
			Vector2(x0, r0), Vector2(x1, r0), Vector2(x1, r1), Vector2(x0, r1))

## Convex polygon given as (z, y) points, extruded along X (profiles, trims, brackets).
func prism_x(x0: float, x1: float, poly: PackedVector2Array) -> void:
	if x0 > x1:
		var tmp := x0; x0 = x1; x1 = tmp
	var c := Vector2.ZERO
	for p in poly: c += p
	c /= poly.size()
	for xs: float in [x0, x1]:
		var n := Vector3(-1, 0, 0) if xs == x0 else Vector3(1, 0, 0)
		for i in range(1, poly.size() - 1):
			tri(Vector3(xs, poly[0].y, poly[0].x), Vector3(xs, poly[i].y, poly[i].x), Vector3(xs, poly[i + 1].y, poly[i + 1].x), n, n, n, poly[0], poly[i], poly[i + 1])
	var run := 0.0
	for i in poly.size():
		var p := poly[i]
		var q := poly[(i + 1) % poly.size()]
		var e := q - p
		if e.length() < 1e-5:
			continue
		var n2 := Vector2(e.y, -e.x).normalized()
		if n2.dot((p + q) * 0.5 - c) < 0.0:
			n2 = -n2
		var n := Vector3(0, n2.y, n2.x)
		var L := e.length()
		quad_n(Vector3(x0, p.y, p.x), Vector3(x1, p.y, p.x), Vector3(x1, q.y, q.x), Vector3(x0, q.y, q.x), n, n, n, n,
			Vector2(run, x0), Vector2(run, x1), Vector2(run + L, x1), Vector2(run + L, x0))
		run += L

## Flattened dome facing n (rivets, studs, knobs, gem cabochons).
func dome(c: Vector3, n: Vector3, r: float, sides: int = 8, rings: int = 3) -> void:
	n = n.normalized()
	var t1 := n.cross(Vector3.UP if absf(n.y) < 0.9 else Vector3.RIGHT).normalized()
	var t2 := n.cross(t1)
	var prev := []
	var prevn := []
	for j in rings + 1:
		var phi := PI * 0.5 * float(j) / rings
		var ring := []
		var ringn := []
		for i in sides:
			var a := TAU * float(i) / sides
			var radial := t1 * cos(a) + t2 * sin(a)
			ring.append(c + radial * r * cos(phi) + n * r * 0.65 * sin(phi))
			ringn.append((radial * cos(phi) + n * sin(phi) * 1.4).normalized())
		if j > 0:
			for i in sides:
				var k := (i + 1) % sides
				quad_n(prev[i], prev[k], ring[k], ring[i], prevn[i], prevn[k], ringn[k], ringn[i], Vector2.ZERO, Vector2.ZERO, Vector2.ZERO, Vector2.ZERO)
		prev = ring
		prevn = ringn

## Capped cylinder; axis = local Y of xf, half height hh (coins, pegs, posts, hinges).
func cylinder(xf: Transform3D, r: float, hh: float, sides: int = 12) -> void:
	var up := (xf.basis * Vector3.UP).normalized()
	for i in sides:
		var a0 := TAU * float(i) / sides
		var a1 := TAU * float(i + 1) / sides
		var p0 := Vector3(cos(a0) * r, 0, sin(a0) * r)
		var p1 := Vector3(cos(a1) * r, 0, sin(a1) * r)
		var top := Vector3(0, hh, 0)
		tri(xf * top, xf * (p0 + top), xf * (p1 + top), up, up, up, Vector2.ZERO, Vector2.ZERO, Vector2.ZERO)
		tri(xf * -top, xf * (p1 - top), xf * (p0 - top), -up, -up, -up, Vector2.ZERO, Vector2.ZERO, Vector2.ZERO)
		var n0 := (xf.basis * p0).normalized()
		var n1 := (xf.basis * p1).normalized()
		quad_n(xf * (p0 - top), xf * (p1 - top), xf * (p1 + top), xf * (p0 + top), n0, n1, n1, n0,
			Vector2(r * a0, -hh), Vector2(r * a1, -hh), Vector2(r * a1, hh), Vector2(r * a0, hh))

## Surface of revolution around local Y from a (radius, height) profile (goblets, vases,
## bottles, lamp posts, knobs). Smooth normals from the profile slope.
func lathe(profile: Array, segments: int = 24, xf: Transform3D = Transform3D()) -> void:
	for k in profile.size() - 1:
		var p0: Vector2 = profile[k]
		var p1: Vector2 = profile[k + 1]
		var d := p1 - p0
		if d.length() < 1e-6: continue
		var n2 := Vector2(d.y, -d.x).normalized()  # outward for a profile drawn bottom -> top
		for i in segments:
			var a0 := TAU * i / segments
			var a1 := TAU * (i + 1) / segments
			var v00 := xf * Vector3(cos(a0) * p0.x, p0.y, sin(a0) * p0.x)
			var v01 := xf * Vector3(cos(a1) * p0.x, p0.y, sin(a1) * p0.x)
			var v10 := xf * Vector3(cos(a0) * p1.x, p1.y, sin(a0) * p1.x)
			var v11 := xf * Vector3(cos(a1) * p1.x, p1.y, sin(a1) * p1.x)
			var na := (xf.basis * Vector3(cos(a0) * n2.x, n2.y, sin(a0) * n2.x)).normalized()
			var nb := (xf.basis * Vector3(cos(a1) * n2.x, n2.y, sin(a1) * n2.x)).normalized()
			var u0 := float(i) / segments
			var u1 := float(i + 1) / segments
			if (v01 - v00).length() > 1e-7 or (v11 - v10).length() > 1e-7:
				quad_n(v00, v01, v11, v10, na, nb, nb, na, Vector2(u0, p0.y), Vector2(u1, p0.y), Vector2(u1, p1.y), Vector2(u0, p1.y))
