"""04 — Raymarched Mandelbulb: the same scaffold as 03, heavier math.

LECTURE STEP 4/6 — "What does full GLSL control buy me?"
GOAL: Show that 03's fullscreen-quad + GPUShaderCreateInfo pattern scales
      to a 58-step SDF raymarcher with lighting. Diff 03 vs 04 in lecture.
CONCEPTS:
  1. Fragment shader = raymarch loop (sphere tracing on mandelbulb()),
     normal by finite differences, diffuse + rim lighting.
  2. Miss rays output alpha 0 (transparent) so the scene shows through.
  3. Cost is per-pixel: shrinking the viewport speeds it up — good live
     demo of GPU fill-rate limits. Rotation via mouse does NOT move the
     shader camera (overlay, not scene material).
PREREQ: Run 03 first so students recognize the surrounding Python.
NEXT: 05 keeps custom GLSL but renders into a texture first.

This is a screen overlay (not a material or full-scene post-process).
The shader output is rendered directly to the viewport by a draw handler.
Tweak STEP_COUNT below if the demo machine is slow (try 32).
"""

import bpy
import blf
import gpu
import time
from gpu_extras.batch import batch_for_shader


_KEY = "gpu_showcase_raymarch_v1"
# HUD slot 3: title y=162, subtitle y=142 (above 03's 122/102).
STEP_COUNT = 58  # lower this on weak iGPUs if the viewport lags
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

    for (int i = 0; i < STEP_COUNT_PLACEHOLDER; ++i) {
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
""".replace("STEP_COUNT_PLACEHOLDER", str(STEP_COUNT))


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
    return True


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


def _draw(state):
    region = bpy.context.region
    if region is None:
        return
    shader = state["shader"]
    old_blend = gpu.state.blend_get()
    old_depth = gpu.state.depth_test_get()
    try:
        gpu.state.blend_set("ALPHA")
        gpu.state.depth_test_set("NONE")
        shader.bind()
        shader.uniform_float("time", time.perf_counter() - state["started"])
        shader.uniform_float("viewportSize", (region.width, region.height))
        state["batch"].draw(shader)
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
        blf.position(0, 22, 162, 0)
        blf.draw(0, "GPU RAYMARCH  |  Mandelbulb SDF  |  GLSL")
        blf.color(0, 0.9, 0.92, 0.95, 0.9)
        blf.position(0, 22, 142, 0)
        blf.draw(0, "Screen overlay; mouse orbit does not move the shader camera")
    finally:
        try:
            blf.disable(0, blf.SHADOW)
        except (AttributeError, RuntimeError):
            pass


def _make_timer(state):
    def tick():
        if bpy.app.driver_namespace.get(_KEY) is not state:
            return None
        _tag_redraw()
        return 1.0 / 30.0
    return tick


def main():
    if _remove_previous():
        _tag_redraw()
        print("GPU raymarch overlay stopped (toggle). Run again to show it.")
        return
    if not hasattr(gpu.types, "GPUShaderCreateInfo"):
        raise RuntimeError("This example needs GPUShaderCreateInfo (Blender 3.x+ with GPU module).")

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
    print("GPU raymarch overlay running. Re-run to toggle it off.")


if __name__ == "__main__":
    main()
