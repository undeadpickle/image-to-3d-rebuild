extends Node
## Scripted showcase for a deterministic demo video (template — edit SCENE, CAM_KEYS, events).
## Attach to the root Node of a new scene (tools/movie_director.tscn) and render with Movie Maker:
##
##   godot --path <project> --write-movie renders/video/demo.avi --fixed-fps 30 \
##         --resolution 1920x1080 res://tools/movie_director.tscn
##   ffmpeg -y -i renders/video/demo.avi -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p \
##         -movflags +faststart media/demo.mp4
##
## Rules that keep it deterministic and good-looking:
## - Everything runs on game time (delta). Never Time.get_ticks_* in anything that is filmed:
##   with --fixed-fps the engine runs slower or faster than real time.
## - Set project display/window/size/viewport_width|height to 1920x1080 (the --resolution flag
##   alone does not change the render target size on every platform).
## - Leave at least (longest action + 1 s) between events that touch the same object;
##   is_busy() guards drop calls that arrive mid-animation.
## - Captions: one line, under ~60 characters at 40 px, shown >= 3 s.

const SCENE := "res://demo.tscn"
const TARGET := "Asset"                 # node with open()/close()/is_busy() or similar
const CAMERA := "CamRig/Camera3D"

const CAM_KEYS := [  # time (s), position, look-at; smoothstep between keys
	[0.0, Vector3(-1.2, 1.35, 3.1), Vector3(0, 0.45, 0)],
	[4.0, Vector3(-0.9, 1.05, 2.3), Vector3(0, 0.45, 0)],
	[10.0, Vector3(0.9, 1.25, 2.4), Vector3(0, 0.5, 0)],
	[16.0, Vector3(-1.0, 1.35, 3.0), Vector3(0, 0.45, 0)],
]

var demo: Node
var target
var cam: Camera3D
var t := 0.0
var _events: Array = []
var _caption: Label
var _caption_bg: ColorRect

func _ready() -> void:
	demo = load(SCENE).instantiate()
	add_child(demo)
	target = demo.get_node(TARGET)
	cam = demo.get_node(CAMERA)
	_build_overlay()
	_events = [
		[0.5, func(): _say("Title or first beat")],
		[2.0, func(): target.call("open")],
		[8.0, func(): _say("Second beat")],
		[9.0, func(): target.call("close")],
		[16.5, func(): get_tree().quit()],
	]

func _process(delta: float) -> void:
	t += delta
	while not _events.is_empty() and _events[0][0] <= t:
		_events.pop_front()[1].call()
	_update_camera()

func _update_camera() -> void:
	var i := 0
	while i < CAM_KEYS.size() - 2 and CAM_KEYS[i + 1][0] <= t: i += 1
	var a = CAM_KEYS[i]
	var b = CAM_KEYS[i + 1]
	var u := clampf((t - a[0]) / (b[0] - a[0]), 0.0, 1.0)
	u = u * u * (3.0 - 2.0 * u)  # ease in/out between keys (slow in, slow out)
	cam.global_position = (a[1] as Vector3).lerp(b[1], u)
	cam.look_at((a[2] as Vector3).lerp(b[2], u), Vector3.UP)
	# impact shake without drift: use the camera's h/v offsets, never its position
	var sh: float = target.get("impact_shake") if target.get("impact_shake") != null else 0.0
	cam.h_offset = sin(t * 91.0) * sh
	cam.v_offset = sin(t * 137.0 + 1.3) * sh * 1.3

func _build_overlay() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	_caption_bg = ColorRect.new()
	_caption_bg.color = Color(0, 0, 0, 0.45)
	_caption_bg.anchor_left = 0.0; _caption_bg.anchor_right = 1.0; _caption_bg.anchor_top = 1.0; _caption_bg.anchor_bottom = 1.0
	_caption_bg.offset_top = -120; _caption_bg.offset_bottom = -40
	_caption_bg.modulate.a = 0.0
	layer.add_child(_caption_bg)
	_caption = Label.new()
	_caption.add_theme_font_size_override("font_size", 40)
	_caption.add_theme_color_override("font_color", Color("#f2e7d6"))
	_caption.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_caption.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_caption.set_anchors_preset(Control.PRESET_FULL_RECT)
	_caption_bg.add_child(_caption)

func _say(text: String, hold := 4.0) -> void:
	_caption.text = text
	var tw := create_tween()
	tw.tween_property(_caption_bg, "modulate:a", 1.0, 0.35)
	tw.tween_interval(hold)
	tw.tween_property(_caption_bg, "modulate:a", 0.0, 0.4)
