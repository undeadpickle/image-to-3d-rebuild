extends SceneTree
## Turntable / comparison renders of any GLB or scene on a neutral studio, then quits.
##
##   godot --path <project> --script res://tools/capture.gd -- \
##       --target=res://models/scan.glb --out=res://renders/scan \
##       [--views=34:-32,front:0,side:90,back34:150] [--pitch=18] [--fov=30] [--zoom=1.15] \
##       [--call=set_open_amount:0.6] [--frame=Model] [--bg=0.82,0.82,0.83] [--size=1280x960]
##
## Use the SAME views/pitch/zoom for the scan and the rebuild so the PNGs line up for
## side-by-side comparison. Framing uses visible MeshInstance3D nodes only (particles and
## multimeshes are ignored), skips anything in the group "no_aabb", and --frame=<NodePath>
## restricts it to one subtree (e.g. the model, not its FX). Prints the AABB and triangle
## count. Needs a window (not --headless).

var target := "res://models/scan.glb"
var out := "res://renders/view"
var views := {"34": -32.0, "front": 0.0, "side": 90.0, "back34": 150.0}
var pitch := 18.0
var fov := 30.0
var zoom := 1.15
var calls: Array = []
var bg := Color(0.82, 0.82, 0.83)
var size := Vector2i(1280, 960)
var frame_path := ""

func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		var kv := a.trim_prefix("--").split("=", true, 1)
		if kv.size() < 2: continue
		match kv[0]:
			"target": target = kv[1]
			"out": out = kv[1]
			"frame": frame_path = kv[1]
			"pitch": pitch = float(kv[1])
			"fov": fov = float(kv[1])
			"zoom": zoom = float(kv[1])
			"size":
				var wh := kv[1].split("x")
				size = Vector2i(int(wh[0]), int(wh[1]))
			"bg":
				var c := kv[1].split(",")
				bg = Color(float(c[0]), float(c[1]), float(c[2]))
			"call":
				for c in kv[1].split(","): calls.append(c.split(":"))
			"views":
				views.clear()
				for v in kv[1].split(","):
					var p := v.split(":")
					views[p[0]] = float(p[1])
	DisplayServer.window_set_size(size)
	root.size = size
	_run.call_deferred()

func _run() -> void:
	var env := WorldEnvironment.new()
	var e := Environment.new()
	e.background_mode = Environment.BG_COLOR
	e.background_color = bg
	e.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	e.ambient_light_color = Color(0.85, 0.86, 0.9)
	e.ambient_light_energy = 0.55
	e.tonemap_mode = Environment.TONE_MAPPER_AGX
	e.ssao_enabled = true
	e.glow_enabled = true
	e.glow_intensity = 0.6
	e.glow_bloom = 0.05
	e.glow_hdr_threshold = 1.1
	e.reflected_light_source = Environment.REFLECTION_SOURCE_BG
	env.environment = e
	root.add_child(env)
	var key := DirectionalLight3D.new()
	key.rotation_degrees = Vector3(-42, -35, 0)
	key.light_energy = 1.6
	key.shadow_enabled = true
	root.add_child(key)
	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-20, 140, 0)
	fill.light_energy = 0.45
	root.add_child(fill)

	var res = load(target)
	if res == null:
		push_error("could not load " + target); quit(1); return
	var inst: Node3D = res.instantiate()
	root.add_child(inst)
	await process_frame
	for c in calls:
		if inst.has_method(c[0]):
			inst.callv(c[0], Array(c.slice(1)).map(func(x): return float(x) if String(x).is_valid_float() else x))
	for i in 4: await process_frame
	var frame_node: Node = inst
	if frame_path != "":
		if inst.has_node(frame_path): frame_node = inst.get_node(frame_path)
		else: push_warning("--frame %s not found; children: %s" % [frame_path, inst.get_children().map(func(c): return c.name)])
	var aabb := _aabb(frame_node)
	print("AABB ", aabb, "  size ", aabb.size, "  tris ", _tris(inst))
	var center := aabb.get_center()
	var radius := aabb.size.length() * 0.5

	var floor := MeshInstance3D.new()
	var pm := PlaneMesh.new(); pm.size = Vector2(40, 40)
	floor.mesh = pm
	var fm := StandardMaterial3D.new(); fm.albedo_color = bg.darkened(0.02); fm.roughness = 1.0
	floor.material_override = fm
	floor.position.y = aabb.position.y
	root.add_child(floor)

	var cam := Camera3D.new()
	cam.fov = fov
	root.add_child(cam)
	cam.current = true
	for k in views.keys():
		var yaw := deg_to_rad(views[k])
		var p := deg_to_rad(pitch)
		var dist := radius / tan(deg_to_rad(fov * 0.5)) * zoom
		cam.position = center + Vector3(sin(yaw) * cos(p), sin(p), cos(yaw) * cos(p)) * dist
		cam.look_at(center, Vector3.UP)
		for i in 8: await process_frame
		var path := ProjectSettings.globalize_path(out + "_" + k + ".png")
		DirAccess.make_dir_recursive_absolute(path.get_base_dir())
		root.get_texture().get_image().save_png(path)
		print("saved ", path)
	quit()

func _aabb(n: Node) -> AABB:
	var box := AABB(); var first := true
	for c in n.find_children("*", "MeshInstance3D", true, false):
		var skip := false
		var q: Node = c
		while q and q != n:
			if q.is_in_group("no_aabb"): skip = true; break
			q = q.get_parent()
		if skip or not (c as Node3D).is_visible_in_tree(): continue
		var vi := c as VisualInstance3D
		var b: AABB = vi.global_transform * vi.get_aabb()
		if first: box = b; first = false
		else: box = box.merge(b)
	return box

func _tris(n: Node) -> int:
	var t := 0
	for c in n.find_children("*", "MeshInstance3D", true, false):
		var m: Mesh = (c as MeshInstance3D).mesh
		if m == null: continue
		for s in m.get_surface_count():
			var arr := m.surface_get_arrays(s)
			var idx = arr[Mesh.ARRAY_INDEX]
			t += (idx.size() / 3) if idx != null else (arr[Mesh.ARRAY_VERTEX].size() / 3)
	return t
