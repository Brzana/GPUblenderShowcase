"""GPUOffScreen -> GPUTexture -> HUD viewportu, bez transferu do RAM.

Demonstracja renderowania poza glownym framebufferem. Tekstura offscreen jest
wyswietlana bezposrednio w viewportcie; nie jest wykonywany readback pikseli.
"""

import bpy
import blf
import gpu
import time
from gpu_extras.batch import batch_for_shader


_KEY = "gpu_showcase_offscreen_v1"
_VERTEX = r"""
void main()
{
    v_uv = pos * 0.5 + 0.5;
    gl_Position = vec4(pos, 0.0, 1.0);
}
"""
_FRAGMENT = r"""
void main()
{
    vec2 p = (v_uv * 2.0 - 1.0) * vec2(1.0, 0.72);
    float r = length(p);
    float a = atan(p.y, p.x);
    float wave = 0.5 + 0.5 * sin(18.0 * r - time * 2.0 + 3.0 * sin(5.0 * a + time));
    float ring = exp(-18.0 * abs(fract(r * 5.0 - time * 0.18) - 0.5));
    vec3 col = mix(vec3(0.015, 0.025, 0.09), vec3(0.08, 0.8, 0.92), wave * 0.55 + ring * 0.45);
    col += vec3(0.35, 0.08, 0.8) * pow(max(0.0, 1.0 - r), 3.0);
    FragColor = vec4(col, 1.0);
}
"""


def _remove_previous():
    state = bpy.app.driver_namespace.pop(_KEY, None)
    if not state:
        return
    for handle in state.get("handles", ()):
        try:
            bpy.types.SpaceView3D.draw_handler_remove(handle, "WINDOW")
        except (ReferenceError, ValueError, RuntimeError):
            pass
    timer = state.get("timer")
    if timer and bpy.app.timers.is_registered(timer):
        bpy.app.timers.unregister(timer)
    offscreen = state.get("offscreen")
    if offscreen:
        try:
            offscreen.free()
        except (ReferenceError, RuntimeError):
            pass


def _render_offscreen(state):
    if state["rendered_tick"] == state["tick"]:
        return
    old_blend = gpu.state.blend_get()
    old_depth = gpu.state.depth_test_get()
    try:
        with state["offscreen"].bind():
            framebuffer = gpu.state.active_framebuffer_get()
            framebuffer.clear(color=(0.01, 0.015, 0.04, 1.0))
            gpu.state.blend_set("NONE")
            gpu.state.depth_test_set("NONE")
            state["shader"].uniform_float("time", time.perf_counter() - state["started"])
            state["quad"].draw(state["shader"])
    finally:
        gpu.state.blend_set(old_blend)
        gpu.state.depth_test_set(old_depth)
    state["rendered_tick"] = state["tick"]


def _draw_view(state):
    _render_offscreen(state)


def _draw_hud(state):
    region = bpy.context.region
    if region is None:
        return
    # Kotwicz podglad do GORY viewportu, zeby nie przykrywal dolnych slotow
    # HUD (01: 22/42, 02: 68/88, 03: 114/134).
    width, height = 300, 188
    margin = 24
    top_gap = 40
    x = margin
    y_top = region.height - top_gap
    y = max(160, y_top - height)
    old_blend = gpu.state.blend_get()
    old_depth = gpu.state.depth_test_get()
    try:
        gpu.state.blend_set("NONE")
        gpu.state.depth_test_set("NONE")
        state["image_shader"].uniform_sampler("image", state["offscreen"].texture_color)
        # Pozycje liczone na biezaco z region.height (batch jest tani: 4 wierzcholki).
        from gpu_extras.batch import batch_for_shader as _batch_for_shader
        preview_batch = _batch_for_shader(state["image_shader"], "TRI_FAN", {
            "pos": ((x, y, 0), (x + width, y, 0),
                    (x + width, y + height, 0), (x, y + height, 0)),
            "texCoord": ((0, 0), (1, 0), (1, 1), (0, 1)),
        })
        preview_batch.draw(state["image_shader"])
    finally:
        gpu.state.blend_set(old_blend)
        gpu.state.depth_test_set(old_depth)
    blf.size(0, 14)
    try:
        blf.enable(0, blf.SHADOW)
        blf.shadow(0, 3, 0.0, 0.0, 0.0, 1.0)
        try:
            blf.shadow_offset(0, 1, -1)
        except AttributeError:
            pass
    except Exception:
        pass
    try:
        blf.color(0, 0.35, 0.95, 1.0, 1.0)
        blf.position(0, x, y + height + 10, 0)
        blf.draw(0, "GPU OFFSCREEN  |  render-to-texture HUD")
    finally:
        try:
            blf.disable(0, blf.SHADOW)
        except Exception:
            pass


def _make_timer(state):
    def tick():
        if bpy.app.driver_namespace.get(_KEY) is not state:
            return None
        state["tick"] += 1
        wm = bpy.context.window_manager
        if wm:
            for window in wm.windows:
                for area in window.screen.areas:
                    if area.type == "VIEW_3D":
                        area.tag_redraw()
        return 1.0 / 30.0
    return tick


_remove_previous()
offscreen = gpu.types.GPUOffScreen(512, 320, format="RGBA8")
interface = gpu.types.GPUStageInterfaceInfo("offscreen_interface")
interface.smooth("VEC2", "v_uv")
info = gpu.types.GPUShaderCreateInfo()
info.push_constant("FLOAT", "time")
info.vertex_in(0, "VEC2", "pos")
info.vertex_out(interface)
info.fragment_out(0, "VEC4", "FragColor")
info.vertex_source(_VERTEX)
info.fragment_source(_FRAGMENT)
shader = gpu.shader.create_from_info(info)
quad = batch_for_shader(shader, "TRI_STRIP", {
    "pos": ((-1.0, -1.0), (1.0, -1.0), (-1.0, 1.0), (1.0, 1.0)),
})

image_shader = gpu.shader.from_builtin("IMAGE")
image_batch = batch_for_shader(image_shader, "TRI_FAN", {
    "pos": ((24, 72, 0), (324, 72, 0), (324, 260, 0), (24, 260, 0)),
    "texCoord": ((0, 0), (1, 0), (1, 1), (0, 1)),
})
state = {
    "offscreen": offscreen,
    "shader": shader,
    "quad": quad,
    "image_shader": image_shader,
    "image_batch": image_batch,
    "started": time.perf_counter(),
    "tick": 0,
    "rendered_tick": -1,
    "handles": [],
}
state["handles"].append(bpy.types.SpaceView3D.draw_handler_add(
    _draw_view, (state,), "WINDOW", "POST_VIEW"
))
state["handles"].append(bpy.types.SpaceView3D.draw_handler_add(
    _draw_hud, (state,), "WINDOW", "POST_PIXEL"
))
state["timer"] = _make_timer(state)
bpy.app.timers.register(state["timer"], first_interval=1.0 / 30.0)
bpy.app.driver_namespace[_KEY] = state
print("GPUOffScreen HUD uruchomiony. Tekstura jest wyswietlana bez readbacku do CPU.")
