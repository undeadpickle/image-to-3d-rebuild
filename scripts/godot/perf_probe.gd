extends SceneTree
## Frame-time probe: runs a scripted sequence of method calls on a node and reports
## avg / 99th / worst frame time and peak draw calls for each phase.
##
##   godot --path <project> --script res://tools/perf_probe.gd -- \
##       --scene=res://demo.tscn [--node=Asset] \
##       --steps="idle:1.0,open:1.5,-:2.5,-:2.0,close:2.5" [--warmup=120]
##
## Each step is method:seconds. "-" or "idle" = call nothing, just measure.
## The phase right after the big moment (first open, first burst) is the one to watch:
## a worst frame far above the 99th percentile there = a shader/pipeline compile hitch.
## Run with a window (not --headless) on the target hardware; vsync caps the average.

var scene := ""
var node_path := ""
var steps := "idle:1.0,open:1.5,-:2.5,close:2.5"
var warmup := 120

func _initialize() -> void:
	for a in OS.get_cmdline_user_args():
		var kv := a.trim_prefix("--").split("=", true, 1)
		if kv.size() < 2: continue
		match kv[0]:
			"scene": scene = kv[1]
			"node": node_path = kv[1]
			"steps": steps = kv[1]
			"warmup": warmup = int(kv[1])
	var inst: Node = load(scene).instantiate()
	root.add_child(inst)
	var target: Node = inst.get_node(node_path) if node_path != "" else inst
	for i in warmup: await process_frame
	var report := []
	for s in steps.split(","):
		var p := s.split(":")
		var m := p[0]
		if m != "-" and m != "idle":
			if target.has_method(m): target.call(m)
			else: push_warning("no method " + m)
		report.append([s, await _sample(float(p[1]))])
	for r in report: print(r[0], "  ", r[1])
	quit()

func _sample(seconds: float) -> String:
	var ft: Array[float] = []
	var dc := 0
	var t0 := Time.get_ticks_usec()
	var last := t0
	while Time.get_ticks_usec() - t0 < seconds * 1e6:
		await process_frame
		var now := Time.get_ticks_usec()
		ft.append((now - last) / 1000.0)
		last = now
		dc = maxi(dc, int(Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME)))
	ft.sort()
	var avg := 0.0
	for f in ft: avg += f
	avg /= ft.size()
	return "avg %.1f ms (%.0f fps), 99th %.1f ms, worst %.1f ms, peak draw calls %d" % [avg, 1000.0 / avg, ft[int(ft.size() * 0.99)], ft[-1], dc]
