extends SceneTree
## Export a procedural (@tool / built-in-_ready) Godot scene to GLB, at rest pose.
##
##   godot --headless --path <project> --script res://tools/export_glb.gd -- \
##       --scene=res://asset/asset.tscn --out=res://export/asset.glb [--call=set_open_amount:0]
##
## Shader materials do not survive glTF, so every surface material is swapped for a plain
## StandardMaterial3D whose NAME is the material's class key. The bake script and the web
## viewer re-apply the real look by that name. Name your materials on purpose:
##   mat.resource_name = "wood"     (or "metal", "cloth", "glass" …)
## Fallbacks when resource_name is empty: the shader file name ("wood.gdshader" -> "wood"),
## else "mat<N>". Lights and nodes in the group "no_export" are removed first.

var scene := ""
var out := "res://export/asset.glb"
var calls: Array = []

func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		var kv := a.trim_prefix("--").split("=", true, 1)
		if kv.size() < 2: continue
		match kv[0]:
			"scene": scene = kv[1]
			"out": out = kv[1]
			"call":
				for c in kv[1].split(","): calls.append(c.split(":"))
	if scene == "":
		push_error("--scene=res://... is required"); quit(1); return
	var inst: Node3D = load(scene).instantiate()
	root.add_child(inst)
	await process_frame
	for c in calls:
		if inst.has_method(c[0]):
			inst.callv(c[0], Array(c.slice(1)).map(func(x): return float(x) if String(x).is_valid_float() else x))
	await process_frame
	for n in inst.find_children("*", "Light3D", true, false) + inst.find_children("*", "GPUParticles3D", true, false):
		n.free()
	for n in inst.find_children("*", "", true, false):
		if is_instance_valid(n) and n.is_in_group("no_export"): n.free()
	var names := {}
	var counter := 0
	for mi in inst.find_children("*", "MeshInstance3D", true, false):
		var mesh: Mesh = mi.mesh
		if mesh == null: continue
		if not (mesh is ArrayMesh):
			var am := ArrayMesh.new()
			for s in mesh.get_surface_count():
				am.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, mesh.surface_get_arrays(s))
				am.surface_set_material(s, mesh.surface_get_material(s))
			mi.mesh = am
			mesh = am
		for s in mesh.get_surface_count():
			var src: Material = mi.get_surface_override_material(s)
			if src == null: src = mi.material_override
			if src == null: src = mesh.surface_get_material(s)
			var key := ""
			if src:
				key = src.resource_name
				if key == "" and src is ShaderMaterial and src.shader:
					key = src.shader.resource_path.get_file().get_basename()
			if key == "":
				if not names.has(src): names[src] = "mat%d" % counter; counter += 1
				key = names[src]
			var m := StandardMaterial3D.new()
			m.resource_name = key
			if src is BaseMaterial3D:
				m.albedo_color = src.albedo_color; m.metallic = src.metallic; m.roughness = src.roughness
			mesh.surface_set_material(s, m)
			mi.set_surface_override_material(s, null)
		mi.material_override = null
		print(mi.name, ": ", range(mesh.get_surface_count()).map(func(i): return mesh.surface_get_material(i).resource_name))
	var doc := GLTFDocument.new()
	var state := GLTFState.new()
	var err := doc.append_from_scene(inst, state)
	if err == OK:
		var path := ProjectSettings.globalize_path(out)
		DirAccess.make_dir_recursive_absolute(path.get_base_dir())
		err = doc.write_to_filesystem(state, path)
	print("export ", out, ": ", error_string(err))
	quit(0 if err == OK else 1)
