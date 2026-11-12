"""01 — Hello Viewport: your first GPU draw (START HERE for GPU).

LECTURE STEP 1/6 — "How does GPU scripting work?"
GOAL: Draw one triangle in the 3D Viewport without adding any object
      to the scene, and understand the 3-step GPU pattern.
CONCEPTS:
  1. draw_handler = "call my function every time the viewport redraws".
     POST_VIEW draws in 3D world space, POST_PIXEL draws 2D HUD on top.
  2. Built-in shader + batch = the smallest GPU program.
     CPU uploads 3 positions ONCE; GPU re-draws them every frame.
  3. driver_namespace stores handles so re-running the script cleans up.
TRY IN LECTURE:
  - Run, orbit the view: the triangle stays fixed in 3D space.
  - Re-run: it disappears (toggle behaviour). Run 99_stop_showcase.py too.
NEXT: 02 shows the same pattern with real mesh data.
"""

import bpy
import blf
import gpu
from gpu_extras.batch import batch_for_shader


_KEY = "gpu_showcase_hello_v1"


def _remove_previous():
    state = bpy.app.driver_namespace.pop(_KEY, None)
    if not state:
        return
    for handle in state.get("handles", ()):
        try:
            bpy.types.SpaceView3D.draw_handler_remove(handle, "WINDOW")
        except (ReferenceError, ValueError, RuntimeError):
            pass


def _draw_3d():
    # Runs on every viewport redraw. No per-frame Python math here —
    # just "draw what the GPU already has".
    shader = _draw_3d.shader
    batch = _draw_3d.batch
    shader.bind()
    # Single uniform: RGBA color. GPU fills every pixel of the triangle.
    shader.uniform_float("color", (0.15, 0.8, 1.0, 1.0))
    batch.draw(shader)


def _draw_hud():
    font_id = 0
    blf.size(font_id, 14)
    blf.color(font_id, 0.35, 0.95, 1.0, 1.0)
    blf.position(font_id, 22, 42, 0)
    blf.draw(font_id, "01 HELLO  |  one GPU triangle, zero scene objects")
    blf.color(font_id, 0.9, 0.92, 0.95, 0.9)
    blf.position(font_id, 22, 22, 0)
    blf.draw(font_id, "POST_VIEW = 3D space  |  re-run script to remove")


_remove_previous()

# --- STEP 1: describe geometry (CPU, once) ---------------------------------
# Three 3D points. That is the only data we ever send to the GPU.
positions = (
    (0.0, 0.0, 0.0),
    (1.5, 0.0, 0.0),
    (0.75, 1.2, 0.0),
)

# --- STEP 2: pick a ready-made GPU program ---------------------------------
# 3D_UNIFORM_COLOR is a built-in shader: position in, flat color out.
# No GLSL to write for this step.
shader = gpu.shader.from_builtin("3D_UNIFORM_COLOR")
batch = batch_for_shader(shader, "TRIS", {"pos": positions})

# Attach to the draw function so it can use them every redraw.
_draw_3d.shader = shader
_draw_3d.batch = batch

# --- STEP 3: ask Blender to call us on every redraw -------------------------
state = {"handles": []}
state["handles"].append(bpy.types.SpaceView3D.draw_handler_add(
    _draw_3d, (), "WINDOW", "POST_VIEW"
))
state["handles"].append(bpy.types.SpaceView3D.draw_handler_add(
    _draw_hud, (), "WINDOW", "POST_PIXEL"
))
bpy.app.driver_namespace[_KEY] = state
print("01 hello viewport running: one triangle, no scene objects. Re-run to remove.")
