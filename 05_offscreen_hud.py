"""05 — Offscreen render-to-texture HUD (no CPU readback).

LECTURE STEP 5/6 — "How do I compose GPU passes without the CPU?"
GOAL: Render an animated shader into GPUOffScreen (512x320 texture),
      then blit that texture into the viewport HUD. Pixels never touch RAM.
CONCEPTS:
  1. offscreen.bind() redirects drawing to a texture-backed framebuffer.
  2. Render ONCE per timer tick (rendered_tick guard), display every redraw.
     Offscreen work needs a GPU context, so it stays in the draw handler.
  3. Built-in IMAGE shader displays the texture as a HUD quad anchored to
     the TOP of the viewport (bottom slots belong to 01-04/06 HUDs).
TRY: Resize the viewport — preview stays top-left (region.height math).
NEXT: 06 (finale) — compute writes state, vertex shader reads it. Same
      "GPU stays on GPU" idea, but for simulation instead of pixels.
"""

import bpy
import blf
import gpu
import time
from gpu_extras.batch import batch_for_shader


_KEY = "gpu_showcase_offscreen_v1"
_OFFSCREEN_W, _OFFSCREEN_H = 512, 320
# Preview size in the HUD; anchored to the top so it never covers 01-04/06.
_PREVIEW_W, _PREVIEW_H = 300, 188
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
        return False
    for handle in state.get("handles", ()):
        try:
            bpy.types.SpaceView3D.draw_handler_remove(handle, "WINDOW")
        except (ReferenceError, ValueError, RuntimeError):
            pass
    timer = state.get("timer")
    if timer is not None:
        try:
            if bpy.app.timers.is_registered(timer):
                bpy.app.timers.unregister(timer)
        except (ReferenceError, ValueError, RuntimeError):
            pass
    offscreen = state.get("offscreen")
    if offscreen is not None:
        try:
            offscreen.free()
        except (ReferenceError, RuntimeError):
            pass
    return True


def _create_offscreen():
    try:
        return gpu.types.GPUOffScreen(_OFFSCREEN_W, _OFFSCREEN_H, format="RGBA8")
    except TypeError:
        # Older builds accept only (width, height).
        return gpu.types.GPUOffScreen(_OFFSCREEN_W, _OFFSCREEN_H)


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
            shader = state["shader"]
            shader.bind()
            shader.uniform_float("time", time.perf_counter() - state["started"])
            state["quad"].draw(shader)
    finally:
        gpu.state.blend_set(old_blend)
        gpu.state.depth_test_set(old_depth)
    state["rendered_tick"] = state["tick"]


def _draw_view(state):
    _render_offscreen(state)


def _preview_batch(state, x, y):
    # Rebuild only when position changes (e.g. viewport resize), not every redraw.
    key = (round(x), round(y))
    if state.get("preview_key") == key and state.get("preview_batch") is not None:
        return state["preview_batch"]
    batch = batch_for_shader(state["image_shader"], "TRI_FAN", {
        "pos": ((x, y, 0), (x + _PREVIEW_W, y, 0),
                (x + _PREVIEW_W, y + _PREVIEW_H, 0), (x, y + _PREVIEW_H, 0)),
        "texCoord": ((0, 0), (1, 0), (1, 1), (0, 1)),
    })
    state["preview_batch"] = batch
    state["preview_key"] = key
    return batch


def _draw_hud(state):
    region = bpy.context.region
    if region is None:
        return
    margin = 24
    top_gap = 40
    x = margin
    y_top = region.height - top_gap
    y = max(160, y_top - _PREVIEW_H)
    old_blend = gpu.state.blend_get()
    old_depth = gpu.state.depth_test_get()
    try:
        gpu.state.blend_set("NONE")
        gpu.state.depth_test_set("NONE")
        image_shader = state["image_shader"]
        image_shader.bind()
        image_shader.uniform_sampler("image", state["offscreen"].texture_color)
        _preview_batch(state, x, y).draw(image_shader)
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
    except (AttributeError, RuntimeError):
        pass
    try:
        blf.color(0, 0.35, 0.95, 1.0, 1.0)
        blf.position(0, x, y + _PREVIEW_H + 10, 0)
        blf.draw(0, "GPU OFFSCREEN  |  render-to-texture HUD")
    finally:
        try:
            blf.disable(0, blf.SHADOW)
        except (AttributeError, RuntimeError):
            pass


def _tag_redraw():
    try:
        wm = bpy.context.window_manager
    except (AttributeError, RuntimeError):
        return
    if not wm:
        return
    try:
        for window in wm.windows:
            for area in window.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()
    except (AttributeError, ReferenceError, RuntimeError):
        pass


def _make_timer(state):
    def tick():
        if bpy.app.driver_namespace.get(_KEY) is not state:
            return None
        state["tick"] += 1
        _tag_redraw()
        return 1.0 / 30.0
    return tick


def main():
    if _remove_previous():
        _tag_redraw()
        print("GPUOffScreen HUD stopped (toggle). Run again to show it.")
        return
    offscreen = _create_offscreen()
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

    state = {
        "offscreen": offscreen,
        "shader": shader,
        "quad": quad,
        "image_shader": image_shader,
        "preview_batch": None,
        "preview_key": None,
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
    print("GPUOffScreen HUD running. Texture is displayed with no CPU readback. Re-run to toggle.")


if __name__ == "__main__":
    main()
