# Blender GPU Showcase — from CPU bottleneck to GPU simulation

Lecture-ordered demos: each script adds **one new GPU idea**.
Full presenter script with timing in [`LECTURE.md`](LECTURE.md).

> Story: **CPU uploads once, GPU redraws every frame.**

## Requirements & running

- Blender **4.5+** recommended (compute needs `gpu.compute`, which depends
  on Blender build, driver and backend — check on the demo machine first).
- Open a `.py` in Blender: **Scripting > Text Editor > Open > Run Script**.
- Re-running a script removes its draw handlers/timer (toggle). Or run
  `99_stop_showcase.py` to stop everything at once.
- `00` prints to the system console (Windows:
  **Window > Toggle System Console**). It creates nothing.

## Presentation order (difficulty ramps 00 → 06)

| Step | File | What students learn |
|------|------|---------------------|
| 0 | `00_cpu_baseline.py` | **Why GPU:** pure-Python integration of 50k particles, timed. No drawing. Keep the ms/frame number for the finale. |
| 1 | `01_hello_viewport.py` | **How GPU draw works:** one triangle, builtin shader, `POST_VIEW` + `POST_PIXEL`. Zero scene objects, zero custom GLSL. |
| 2 | `02_viewport_normal_overlay.py` | **Real data, same pattern:** active mesh → `LINES` batch with `POLYLINE_FLAT_COLOR`. Mesh read once, redrawn by GPU. Needs an active Mesh. |
| 3 | `03_shader_toy_gradient.py` | **First custom GLSL:** fullscreen quad + `GPUShaderCreateInfo`, ~15-line animated fragment shader. Edit + re-run live. |
| 4 | `04_viewport_raymarch.py` | **Full GLSL control:** same scaffold as 03, fragment becomes a 58-step Mandelbulb SDF raymarcher. Screen overlay, not a material. |
| 5 | `05_offscreen_hud.py` | **Compose on GPU:** render to `GPUOffScreen` texture, blit to HUD with `IMAGE` shader. No pixel readback to CPU. |
| 6 | `06_compute_particle_flow.py` | **Finale:** 102 400 particles in `RGBA32F` ping-pong textures. Compute writes state, vertex shader `texelFetch`es it. No readback, no particle objects. |

Short (45 min) version: 00 → 01 → 03 → 06.

## Backend comparison

Run two Blender instances with the same example:

```text
blender --gpu-backend opengl
blender --gpu-backend vulkan
```

Backend availability depends on the build (Metal needs a Metal build;
check `blender --help` on the demo machine).

## Honest technical caveats

- Public Blender Python API exposes `gpu.compute` and compute image
  read/write; `gpu.types.GPUStorageBuf` is not a standard public type —
  so the particle demo uses two `RGBA32F` textures (ping-pong), not SSBO.
  Initial states upload from CPU once; positions never return to RAM.
- 102 400 is a simulation-state count, not an FPS guarantee. Result
  depends on GPU, driver, viewport resolution and backend.
- Blender does not guarantee identical compute support everywhere.
  Rehearse on the lecture machine first.
- No "60+ FPS" promises — show Blender's own FPS/statistics on target
  hardware and compare identical viewport + settings.

## Stopping

Re-run the same file to remove its handler/timer, run
`99_stop_showcase.py` to clear all, or just close Blender (script GPU
resources are freed on close).
