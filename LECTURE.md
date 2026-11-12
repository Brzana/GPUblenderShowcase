# Lecture Guide — GPU Scripting in Blender (00 → 06)

A 60–90 minute lecture flow. Each script is one lecture step; difficulty
ramps one new idea at a time. Nothing is added to the scene or Outliner
until the finale — and even then, particles stay in GPU textures.

## The story in one paragraph

> **CPU uploads once, GPU redraws every frame.**
> We start by feeling the CPU bottleneck (00), then draw one triangle
> with zero scene objects (01), then real mesh data with a built-in shader
> (02), then take over every pixel with our own GLSL (03 → 04), then
> compose passes through a texture without touching RAM (05), and finally
> simulate 100k particles where state never returns to the CPU (06).

Say that sentence at the start. Repeat the bold part at every step.

## Mental model to draw on the board (2 min)

```
CPU (Python, once)                GPU (every redraw)
─────────────────                 ──────────────────
positions / mesh /                draw_handler(POS­­­T_VIEW / POST_PIXEL)
  initial texture  ──upload──▶        │
                                     ├─ builtin shader (01, 02)
                                     ├─ custom GLSL   (03, 04, 05)
                                     ├─ offscreen tex (05)
                                     └─ compute→vertex (06)
```

Three recurring pieces in every file — point them out each time:

1. **Describe data** (`batch_for_shader` / `GPUTexture` / `GPUOffScreen`).
2. **Pick a GPU program** (`from_builtin` or `create_from_info`).
3. **Register a redraw hook** (`draw_handler_add` + `driver_namespace`
   cleanup + optional `bpy.app.timers` for animation).

`POST_VIEW` = 3D world space. `POST_PIXEL` = 2D screen overlay / HUD.

## Timetable

| Min   | Step | File                          | One new idea                       |
|-------|------|-------------------------------|------------------------------------|
| 0–10  | 0    | `00_cpu_baseline.py`          | CPU cost, measured. No drawing.    |
| 10–20 | 1    | `01_hello_viewport.py`        | draw_handler + builtin shader.     |
| 20–32 | 2    | `02_viewport_normal_overlay.py` | Real mesh → batch, still no GLSL. |
| 32–44 | 3    | `03_shader_toy_gradient.py`   | First custom GLSL (15 lines).      |
| 44–56 | 4    | `04_viewport_raymarch.py`     | Same scaffold, SDF raymarch.       |
| 56–68 | 5    | `05_offscreen_hud.py`         | Render-to-texture, no readback.    |
| 68–85 | 6    | `06_compute_particle_flow.py` | Compute ping-pong → vertex fetch.  |
| 85–90 | —    | `99_stop_showcase.py`         | Cleanup + Q&A.                     |

45-minute version: run 00 → 01 → 03 → 06 only, mention 02/04/05 as
"same pattern, see LECTURE headers".

## Step-by-step presenter notes

### 00 — CPU baseline (10 min)
- Run: Text Editor > Open > Run Script. Output is in
  **Window > Toggle System Console** (no viewport change — that is the point).
- Read the "ms per frame" line aloud. Write it on the board.
- Ask: *"What happens at 200k particles? What if we also draw objects?"*
- Key line: *"This is simulation only. Drawing would cost extra. Keep
  this number — step 06 beats it without the CPU."*
- Exercise: change `PARTICLE_COUNT` to 5_000, re-run, observe ~linear scaling.

### 01 — Hello viewport (10 min)
- The minimal GPU script (~70 lines). Show the 3 steps in the file.
- Run, orbit: triangle sticks in 3D (POST_VIEW). Re-run: gone (toggle).
- Ask: *"Where is the triangle in the Outliner?"* (Nowhere — GPU only.)
- Pitfall: drawing the wrong shader type (`2D` vs `3D`) — positions
  interpret differently. Keep `3D_UNIFORM_COLOR` + `POST_VIEW` paired.

### 02 — Normal overlay (12 min)
- Same pattern as 01, but `positions` come from the evaluated mesh.
  Emphasize: **mesh is read once**, batch is drawn every frame.
- Select Cube, run; select Suzanne, re-run — label + arrow count change.
- Toggle wireframe/X-ray: overlay persists (it is not geometry).
- Concept: `matrix_world` + normal matrix move data to world space on CPU
  once, so the vertex work doesn't repeat per frame.
- Question: *"Why cap at 7000 arrows? What would 200k lines cost?"*

### 03 — Shader toy gradient (12 min)
- First `GPUShaderCreateInfo`. Walk the recipe lines:
  `interface` → `push_constant` → `vertex_in/out` → `fragment_out` →
  `vertex/fragment_source`.
- Live edit: change `12.0 * r` → `30.0 * r`, re-run. Instant GLSL loop.
- Live edit 2: swap the two `mix` colors.
- Key line: *"Vertex runs 4×, fragment runs per pixel. `time` is the only
  thing the CPU sends per frame."*

### 04 — Raymarch (12 min)
- Open 03 and 04 side by side. Python scaffold is identical; only
  `_FRAGMENT` grew (SDF + 58-step loop + lighting).
- Run; shrink the viewport — FPS rises (fill-rate bound, per-pixel cost).
- Miss rays return alpha 0 so the scene shows through — not a material.
- Honest caveat: orbiting the view doesn't move the shader camera (overlay).
- Question: *"What would make this faster? (fewer steps, lower res,
  simpler SDF). What stays the same? (the Python side)."*

### 05 — Offscreen HUD (12 min)
- Two passes, zero RAM copies: `offscreen.bind()` renders to texture,
  `IMAGE` shader blits it top-left.
- `rendered_tick` guard: render once per tick, display every redraw.
- Resize viewport: preview stays top-anchored (`region.height` math).
- Key line: *"This is compositing without `read_pixels`. The texture is
  the handoff."*
- Bridge to finale: *"06 uses the same handoff idea, but the texture
  carries simulation state instead of colors."*

### 06 — Compute finale (17 min)
- Recall 00's number. Same force field, now: compute writes `state_out`,
  vertex shader `texelFetch`es it. Positions never return to RAM.
- Diagram ping-pong on the board: `tex[0] ⇄ tex[1]`, `current` flips.
- `dispatched_tick` guard: one simulation step per timer tick regardless
  of viewport count.
- Honest caveats (say aloud): particle count ≠ guaranteed FPS; result
  depends on GPU/driver/resolution/backend; verify on the demo machine.
- Closer: *"CPU uploads a spiral once. After that, Python only says
  'step' and 'draw'."*

## How to handle failure live

- `gpu.compute` missing (old Blender/driver/backend): 06 raises with a
  clear message. Fall back to 00–05 — they don't need compute.
- Overlapping HUD texts: run `99_stop_showcase.py`, then start one demo.
- Stale overlay after selecting a new mesh: re-run 02 (by design — data
  snapshot, teaches the upload-once model).

## Backend comparison (optional 5 min)

Run two Blender instances on the same machine:

```text
blender --gpu-backend opengl
blender --gpu-backend vulkan
```

Same script, same viewport size, compare feel + Blender's own FPS/statistics.
Metal availability depends on build — check `blender --help`. No FPS
promises in this repo; measure on target hardware.

## Homework / exercises

1. 01: draw a quad instead of a triangle; change its color per frame.
2. 02: color arrows by normal-Y instead of Z.
3. 03: add a second moving center (`sin(time)` offset) to the rings.
4. 05: double the offscreen size — what changes, what doesn't?
5. 06: halve `_SIZE` to 160 — relate tick cost to 00's scaling curve.

## Files

- `00_cpu_baseline.py` — measurement, no drawing.
- `01_hello_viewport.py` — minimal draw (start GPU here).
- `02_viewport_normal_overlay.py` — mesh → batch, builtin shader.
- `03_shader_toy_gradient.py` — minimal custom GLSL.
- `04_viewport_raymarch.py` — SDF raymarch, same scaffold as 03.
- `05_offscreen_hud.py` — render-to-texture HUD.
- `06_compute_particle_flow.py` — compute ping-pong finale.
- `99_stop_showcase.py` — stops all demos at once.
