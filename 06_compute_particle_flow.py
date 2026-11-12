"""06 — FINALE: 102 400 particles, compute shader + ping-pong textures.

LECTURE STEP 6/6 — "How do I simulate AND draw without the CPU?"
GOAL: Tie the whole story together. Compare against 00's CPU number.
CONCEPTS:
  1. State texture RGBA32F = (x, y, vx, vy). CPU uploads initial spiral
     ONCE; afterwards compute shader reads state_in, writes state_out.
  2. Ping-pong: two textures swap roles each tick. No readback to RAM.
  3. Vertex shader texelFetch()es the current state texture — position
     lookup by UV. gl_Points drawn with viewProjectionMatrix.
  4. One dispatch per timer tick (dispatched_tick guard) so N viewports
     don't speed up the sim. Same force field as 00 for fair comparison.
DEMO LINE: "00 integrated 50k particles on CPU in X ms. This integrates
  102k on GPU without the positions ever returning to RAM."
CLEANUP: re-run script, or run 99_stop_showcase.py.
"""

import bpy
import blf
import gpu
import math
from gpu_extras.batch import batch_for_shader


_KEY = "gpu_showcase_compute_particles_v1"
_SIZE = 320
_LOCAL_SIZE = 16
_COUNT = _SIZE * _SIZE
_DT = 1.0 / 60.0

_COMPUTE = r"""
void main()
{
    ivec2 cell = ivec2(gl_GlobalInvocationID.xy);
    ivec2 dims = imageSize(state_in);
    if (cell.x >= dims.x || cell.y >= dims.y) return;

    vec4 state = imageLoad(state_in, cell);
    vec2 p = state.xy;
    vec2 v = state.zw;
    float inv_r = inversesqrt(dot(p, p) + 0.2);
    vec2 tangent = vec2(-p.y, p.x) * inv_r;
    vec2 acceleration = tangent * 0.45 - p * 0.08 - v * 0.12;
    v += acceleration * delta_time;
    p += v * delta_time;

    if (p.x < -5.5 || p.x > 5.5) { p.x = clamp(p.x, -5.5, 5.5); v.x = -v.x; }
    if (p.y < -5.5 || p.y > 5.5) { p.y = clamp(p.y, -5.5, 5.5); v.y = -v.y; }
    imageStore(state_out, cell, vec4(p, v));
}
"""

_DRAW_VERTEX = r"""
void main()
{
    ivec2 dims = textureSize(state_tex, 0);
    ivec2 cell = clamp(ivec2(uv * vec2(dims)), ivec2(0), dims - ivec2(1));
    vec4 state = texelFetch(state_tex, cell, 0);
    v_speed = length(state.zw);
    gl_Position = viewProjectionMatrix * vec4(state.xy, 0.0, 1.0);
}
"""

_DRAW_FRAGMENT = r"""
void main()
{
    vec2 q = gl_PointCoord * 2.0 - 1.0;
    float r2 = dot(q, q);
    if (r2 > 1.0) discard;
    float speed = clamp(v_speed * 1.8, 0.0, 1.0);
    vec3 color = mix(vec3(0.04, 0.45, 1.0), vec3(0.2, 1.0, 0.72), speed);
    float glow = 1.0 - smoothstep(0.0, 1.0, r2);
    FragColor = vec4(color, 0.35 + glow * 0.65);
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


def _create_textures():
    values = []
    golden_angle = 2.399963229728653
    for i in range(_COUNT):
        radius = 4.4 * math.sqrt((i + 0.5) / _COUNT)
        angle = i * golden_angle
        x = radius * math.cos(angle)
        y = radius * math.sin(angle)
        vx = -0.15 * math.sin(angle)
        vy = 0.15 * math.cos(angle)
        values.extend((x, y, vx, vy))
    # Buffer musi byc plaski: total = W*H*C. Krotka (W,H,C) nie dziala
    # we wszystkich wersjach Blendera (stad TypeError 409600 vs 320).
    total = _SIZE * _SIZE * 4
    assert len(values) == total, f"zly rozmiar danych: {len(values)} != {total}"
    initial_data = gpu.types.Buffer("FLOAT", total, values)
    first = gpu.types.GPUTexture((_SIZE, _SIZE), format="RGBA32F", data=initial_data)
    second = gpu.types.GPUTexture((_SIZE, _SIZE), format="RGBA32F")
    return (first, second), initial_data


def _draw_simulation(state):
    context = bpy.context
    if context.region_data is None:
        return

    # Jeden krok na tick timera, takze liczba otwartych viewportow nie zmienia
    # predkosci symulacji.
    if state["dispatched_tick"] != state["tick"]:
        source_index = state["current"]
        target_index = 1 - source_index
        compute = state["compute_shader"]
        compute.image("state_in", state["textures"][source_index])
        compute.image("state_out", state["textures"][target_index])
        compute.uniform_float("delta_time", _DT)
        gpu.compute.dispatch(compute, _SIZE // _LOCAL_SIZE, _SIZE // _LOCAL_SIZE, 1)
        state["current"] = target_index
        state["dispatched_tick"] = state["tick"]

    old_blend = gpu.state.blend_get()
    old_depth = gpu.state.depth_test_get()
    try:
        gpu.state.blend_set("ALPHA")
        gpu.state.depth_test_set("NONE")
        gpu.state.point_size_set(3.0)
        draw_shader = state["draw_shader"]
        draw_shader.uniform_float("viewProjectionMatrix", context.region_data.perspective_matrix)
        draw_shader.uniform_sampler("state_tex", state["textures"][state["current"]])
        state["batch"].draw(draw_shader)
    finally:
        gpu.state.blend_set(old_blend)
        gpu.state.depth_test_set(old_depth)
        gpu.state.point_size_set(1.0)


def _draw_hud(state):
    # Slot 2: 114 / 134 — powyzej slotow 01 (22/42) i 02 (68/88).
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
        blf.position(0, 22, 134, 0)
        blf.draw(0, f"GPU COMPUTE  |  {state['count']:,} particles  |  RGBA32F ping-pong")
        blf.color(0, 0.9, 0.92, 0.95, 0.9)
        blf.position(0, 22, 114, 0)
        blf.draw(0, "compute -> tekstura -> vertex shader -> viewport (bez readbacku)")
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
        return _DT
    return tick


_remove_previous()
required = ("GPUShaderCreateInfo", "GPUTexture")
if not all(hasattr(gpu.types, name) for name in required) or not hasattr(gpu, "compute"):
    raise RuntimeError("Compute demo wymaga aktualnego Blendera z gpu.compute (zalecany 4.5+).")

compute_info = gpu.types.GPUShaderCreateInfo()
compute_info.push_constant("FLOAT", "delta_time")
compute_info.image(0, "RGBA32F", "FLOAT_2D", "state_in", qualifiers={"READ"})
compute_info.image(1, "RGBA32F", "FLOAT_2D", "state_out", qualifiers={"WRITE"})
compute_info.local_group_size(_LOCAL_SIZE, _LOCAL_SIZE, 1)
compute_info.compute_source(_COMPUTE)
compute_shader = gpu.shader.create_from_info(compute_info)

draw_interface = gpu.types.GPUStageInterfaceInfo("particle_interface")
draw_interface.smooth("FLOAT", "v_speed")
draw_info = gpu.types.GPUShaderCreateInfo()
draw_info.push_constant("MAT4", "viewProjectionMatrix")
draw_info.sampler(0, "FLOAT_2D", "state_tex")
draw_info.vertex_in(0, "VEC2", "uv")
draw_info.vertex_out(draw_interface)
draw_info.fragment_out(0, "VEC4", "FragColor")
draw_info.vertex_source(_DRAW_VERTEX)
draw_info.fragment_source(_DRAW_FRAGMENT)
draw_shader = gpu.shader.create_from_info(draw_info)

textures, initial_data = _create_textures()
uvs = [((x + 0.5) / _SIZE, (y + 0.5) / _SIZE)
       for y in range(_SIZE) for x in range(_SIZE)]
batch = batch_for_shader(draw_shader, "POINTS", {"uv": uvs})

state = {
    "compute_shader": compute_shader,
    "draw_shader": draw_shader,
    "textures": textures,
    "current": 0,
    "initial_data": initial_data,
    "batch": batch,
    "count": _COUNT,
    "tick": 0,
    "dispatched_tick": -1,
    "handles": [],
}
state["handles"].append(bpy.types.SpaceView3D.draw_handler_add(
    _draw_simulation, (state,), "WINDOW", "POST_VIEW"
))
state["handles"].append(bpy.types.SpaceView3D.draw_handler_add(
    _draw_hud, (state,), "WINDOW", "POST_PIXEL"
))
state["timer"] = _make_timer(state)
bpy.app.timers.register(state["timer"], first_interval=_DT)
bpy.app.driver_namespace[_KEY] = state
print(f"GPU compute particles uruchomione: {_COUNT:,} czastek; stan nie jest kopiowany do CPU.")
