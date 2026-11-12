"""03 — Shader Toy: your first custom GLSL pixel shader.

LECTURE STEP 3/6 — "How do I take control of every pixel?"
GOAL: Draw a fullscreen animated gradient with ~15 lines of GLSL.
CONCEPTS:
  1. GPUShaderCreateInfo describes a custom shader: inputs (vertex_in),
     outputs (fragment_out), uniforms (push_constant) + GLSL sources.
  2. Vertex shader runs 4x (one per corner), fragment shader runs per pixel.
     v_uv interpolates across the quad: 0..1 UV space for math.
  3. `time` uniform animates; `viewportSize` keeps aspect correct.
     Nothing is read back to CPU — pixels stay on the GPU.
TRY IN LECTURE:
  - Change `12.0 * r` to `30.0 * r`, re-run: live GLSL edit loop.
  - Change the two mix() colors, re-run.
NEXT: 04 uses the EXACT same scaffold, only the fragment math gets
      heavier (Mandelbulb SDF raymarch). Compare the two files side by side.
"""

import bpy
import blf
import gpu
import time
from gpu_extras.batch import batch_for_shader


_KEY = "gpu_showcase_shader_toy_v1"

# Fullscreen quad: vertex positions in clip space (-1..1).
_VERTEX = r"""
void main()
{
    v_uv = pos * 0.5 + 0.5;
    gl_Position = vec4(pos, 0.0, 1.0);
}
"""

# Deliberately tiny fragment shader. Read it top to bottom in lecture:
# uv -> aspect fix -> distance from center -> animated rings -> color mix.
_FRAGMENT = r"""
void main()
{
    vec2 uv = v_uv * 2.0 - 1.0;
    uv.x *= viewportSize.x / max(viewportSize.y, 1.0);
    float r = length(uv);
    float rings = 0.5 + 0.5 * sin(12.0 * r - time * 2.0);
    float glow = exp(-3.0 * r);
    vec3 deep = vec3(0.02, 0.05, 0.16);
    vec3 cyan = vec3(0.1, 0.85, 0.95);
    vec3 color = mix(deep, cyan, rings * 0.45 + glow * 0.55);
    FragColor = vec4(color, 1.0);
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


def _draw(state):
    region = bpy.context.region
    if region is None:
        return
    old_blend = gpu.state.blend_get()
    old_depth = gpu.state.depth_test_get()
    try:
        gpu.state.blend_set("ALPHA")
        gpu.state.depth_test_set("NONE")
        state["shader"].uniform_float("time", time.perf_counter() - state["started"])
        state["shader"].uniform_float("viewportSize", (region.width, region.height))
        state["batch"].draw(state["shader"])
    finally:
        gpu.state.blend_set(old_blend)
        gpu.state.depth_test_set(old_depth)

    blf.size(0, 14)
    blf.color(0, 0.35, 0.95, 1.0, 1.0)
    blf.position(0, 22, 88, 0)
    blf.draw(0, "03 SHADER TOY  |  custom GLSL gradient  |  edit + re-run")
    blf.color(0, 0.9, 0.92, 0.95, 0.9)
    blf.position(0, 22, 68, 0)
    blf.draw(0, "Same scaffold as 04 raymarch — only fragment math differs")


def _make_timer(state):
    def tick():
        if bpy.app.driver_namespace.get(_KEY) is not state:
            return None
        wm = bpy.context.window_manager
        if wm:
            for window in wm.windows:
                for area in window.screen.areas:
                    if area.type == "VIEW_3D":
                        area.tag_redraw()
        return 1.0 / 30.0
    return tick


_remove_previous()
if not hasattr(gpu.types, "GPUShaderCreateInfo"):
    raise RuntimeError("This example needs GPUShaderCreateInfo (Blender 4.5+ recommended).")

# The recipe, line by line — point at each in lecture:
interface = gpu.types.GPUStageInterfaceInfo("toy_interface")
interface.smooth("VEC2", "v_uv")          # vertex -> fragment varying
info = gpu.types.GPUShaderCreateInfo()
info.push_constant("FLOAT", "time")        # per-frame uniform
info.push_constant("VEC2", "viewportSize")  # per-frame uniform
info.vertex_in(0, "VEC2", "pos")           # per-vertex input
info.vertex_out(interface)
info.fragment_out(0, "VEC4", "FragColor")  # per-pixel output
info.vertex_source(_VERTEX)
info.fragment_source(_FRAGMENT)
shader = gpu.shader.create_from_info(info)

batch = batch_for_shader(shader, "TRI_STRIP", {
    "pos": ((-1.0, -1.0), (1.0, -1.0), (-1.0, 1.0), (1.0, 1.0)),
})

state = {"shader": shader, "batch": batch, "started": time.perf_counter(), "handles": []}
state["handles"].append(bpy.types.SpaceView3D.draw_handler_add(
    _draw, (state,), "WINDOW", "POST_PIXEL"
))
state["timer"] = _make_timer(state)
bpy.app.timers.register(state["timer"], first_interval=1.0 / 30.0)
bpy.app.driver_namespace[_KEY] = state
print("03 shader toy running. Edit _FRAGMENT, re-run to see GLSL change live.")
