"""Animowany, ekranowy raymarching Mandelbulba w oknie 3D Viewportu.

To shaderowy overlay (nie material ani post-process calej sceny). Wyjscie
shadera jest renderowane bezposrednio do viewportu przez draw handler.
"""

import bpy
import blf
import gpu
import time
from gpu_extras.batch import batch_for_shader


_KEY = "gpu_showcase_raymarch_v1"
_VERTEX = r"""
void main()
{
    v_uv = pos * 0.5 + 0.5;
    gl_Position = vec4(pos, 0.0, 1.0);
}
"""

_FRAGMENT = r"""
float mandelbulb(vec3 p)
{
    vec3 z = p;
    float dr = 1.0;
    float r = 0.0;
    for (int i = 0; i < 7; ++i) {
        r = length(z);
        if (r > 2.2) break;
        float safe_r = max(r, 0.0001);
        float theta = acos(clamp(z.z / safe_r, -1.0, 1.0));
        float phi = atan(z.y, z.x);
        dr = pow(safe_r, 6.0) * 7.0 * dr + 1.0;
        float zr = pow(safe_r, 7.0);
        theta *= 7.0;
        phi *= 7.0;
        z = zr * vec3(sin(theta) * cos(phi), sin(phi) * sin(theta), cos(theta)) + p;
    }
    return 0.5 * log(max(r, 0.0001)) * r / max(dr, 0.0001);
}

vec3 rotate_y(vec3 p, float a)
{
    float c = cos(a), s = sin(a);
    return vec3(c * p.x + s * p.z, p.y, -s * p.x + c * p.z);
}

void main()
{
    vec2 uv = v_uv * 2.0 - 1.0;
    uv.x *= viewportSize.x / max(viewportSize.y, 1.0);
    vec3 ro = vec3(0.0, 0.0, 4.2);
    vec3 rd = normalize(vec3(uv * 0.78, -1.45));
    float t = 0.0;
    float d = 0.0;
    bool hit = false;

    for (int i = 0; i < 58; ++i) {
        vec3 p = rotate_y(ro + rd * t, time * 0.22);
        p.xy = mat2(cos(time * 0.13), -sin(time * 0.13), sin(time * 0.13), cos(time * 0.13)) * p.xy;
        d = mandelbulb(p);
        if (d < 0.0015) { hit = true; break; }
        t += max(d * 0.72, 0.001);
        if (t > 9.0) break;
    }

    if (!hit) {
        FragColor = vec4(0.0, 0.0, 0.0, 0.0);
        return;
    }

    vec3 p = rotate_y(ro + rd * t, time * 0.22);
    float e = 0.002;
    vec3 n = normalize(vec3(
        mandelbulb(p + vec3(e,0,0)) - mandelbulb(p - vec3(e,0,0)),
        mandelbulb(p + vec3(0,e,0)) - mandelbulb(p - vec3(0,e,0)),
        mandelbulb(p + vec3(0,0,e)) - mandelbulb(p - vec3(0,0,e))));
    vec3 light_dir = normalize(vec3(-0.45, 0.7, 0.55));
    float diffuse = max(dot(n, light_dir), 0.0);
    float rim = pow(1.0 - max(dot(-rd, n), 0.0), 2.5);
    float bands = 0.5 + 0.5 * sin(11.0 * t - time * 2.0 + p.y * 2.0);
    vec3 base = mix(vec3(0.04, 0.18, 0.55), vec3(0.05, 0.95, 0.8), bands);
    vec3 color = base * (0.25 + 0.85 * diffuse) + vec3(0.45, 0.12, 0.9) * rim;
    FragColor = vec4(color, 0.96);
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
    context = bpy.context
    region = context.region
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
    # Slot 1: 68 / 88 — celowo wyzej niz overlay 01 (22 / 42), zeby teksty
    # dwoch jednoczesnie uruchomionych dem sie nie nakladaly.
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
        blf.position(0, 22, 88, 0)
        blf.draw(0, "GPU RAYMARCH  |  Mandelbulb SDF  |  GLSL")
        blf.color(0, 0.9, 0.92, 0.95, 0.9)
        blf.position(0, 22, 68, 0)
        blf.draw(0, "Ekranowy overlay; obrot myszy/view nie zmienia kamery shadera")
    finally:
        try:
            blf.disable(0, blf.SHADOW)
        except Exception:
            pass


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
    raise RuntimeError("Ten przyklad wymaga GPUShaderCreateInfo (zalecany Blender 4.5+).")

interface = gpu.types.GPUStageInterfaceInfo("raymarch_interface")
interface.smooth("VEC2", "v_uv")
info = gpu.types.GPUShaderCreateInfo()
info.push_constant("FLOAT", "time")
info.push_constant("VEC2", "viewportSize")
info.vertex_in(0, "VEC2", "pos")
info.vertex_out(interface)
info.fragment_out(0, "VEC4", "FragColor")
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
print("GPU raymarch overlay uruchomiony. Uruchom skrypt ponownie, aby go wylaczyc.")
