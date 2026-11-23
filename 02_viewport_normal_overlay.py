"""02 — Mesh overlay with a built-in shader (no custom GLSL yet).

LECTURE STEP 2/6 — "How do I draw real data fast?"
GOAL: Same 3-step pattern as 01, but geometry comes from the active mesh.
CONCEPTS:
  1. Read mesh ONCE on CPU (evaluated mesh + matrix_world), upload as
     a LINES batch; GPU redraws it every frame for free.
  2. POLYLINE_FLAT_COLOR = built-in shader with per-vertex color.
     Still zero hand-written GLSL.
  3. POST_VIEW draws in world space (arrows stick to the object).
     HUD text uses POST_PIXEL (fixed screen position).
TRY: Select Cube vs Suzanne, re-run — arrow count label changes.
  Toggle wireframe: overlay stays (it is not scene geometry).
NEXT: 03 replaces the built-in shader with your own GLSL.

Run with an active Mesh object. Re-running toggles the overlay off.
Geometry is fetched once; re-run to refresh after selecting a new mesh.
"""

import bpy
import blf
import gpu
import math
from mathutils import Vector
from gpu_extras.batch import batch_for_shader


_KEY = "gpu_showcase_normal_overlay_v1"
_MAX_ARROWS = 7000
# HUD slot 1: title y=82, subtitle y=62 (above 01's 42/22).


def _remove_previous():
    state = bpy.app.driver_namespace.pop(_KEY, None)
    if not state:
        return False
    handles = list(state.get("handles", ()))
    # Back-compat with older key layout.
    for single in ("view_handle", "hud_handle"):
        handle = state.get(single)
        if handle is not None:
            handles.append(handle)
    for handle in handles:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(handle, "WINDOW")
        except (ReferenceError, ValueError, RuntimeError):
            pass
    return True


def _build_batch(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        count = len(mesh.vertices)
        if count == 0:
            raise RuntimeError("Active object has no vertices.")

        step = max(1, math.ceil(count / _MAX_ARROWS))
        matrix = evaluated.matrix_world
        try:
            normal_matrix = matrix.to_3x3().inverted().transposed()
        except ValueError:
            normal_matrix = matrix.to_3x3()

        # Single pass: collect sampled verts + bounds.
        sampled = []
        min_x = min_y = min_z = float("inf")
        max_x = max_y = max_z = float("-inf")
        for index in range(0, count, step):
            co = mesh.vertices[index].co
            sampled.append((index, co.x, co.y, co.z))
            min_x = min(min_x, co.x)
            min_y = min(min_y, co.y)
            min_z = min(min_z, co.z)
            max_x = max(max_x, co.x)
            max_y = max(max_y, co.y)
            max_z = max(max_z, co.z)

        bounds_min = Vector((min_x, min_y, min_z))
        bounds_max = Vector((max_x, max_y, max_z))
        z_span = max(1e-6, max_z - min_z)
        bounds_diag = (bounds_max - bounds_min).length

        arrow_len = max(0.035, bounds_diag * 0.035)
        center = (bounds_min + bounds_max) * 0.5
        half_span = max(0.6, bounds_diag * 0.7)

        positions = []
        colors = []

        def add_segment(a, b, color):
            positions.extend((tuple(a), tuple(b)))
            colors.extend((color, color))

        def add_arrow(origin, direction, length, color):
            if direction.length_squared < 1e-12:
                return
            direction.normalize()
            tip = origin + direction * length
            side = direction.cross(Vector((0.0, 0.0, 1.0)))
            if side.length_squared < 1e-8:
                side = direction.cross(Vector((1.0, 0.0, 0.0)))
            side.normalize()
            back = -direction * (length * 0.24)
            wing = length * 0.12
            add_segment(origin, tip, color)
            add_segment(tip, tip + back + side * wing, color)
            add_segment(tip, tip + back - side * wing, color)

        normal_arrows = 0
        for index, lx, ly, lz in sampled:
            vertex = mesh.vertices[index]
            origin = matrix @ vertex.co
            normal = normal_matrix @ vertex.normal
            if normal.length_squared < 1e-12:
                continue
            normal.normalize()
            # Heat by world height so colors match what you see.
            heat = min(1.0, max(0.0, (origin.z - (matrix @ bounds_min).z) / max(1e-6, ((matrix @ bounds_max).z - (matrix @ bounds_min).z))))
            color = (0.15 + 0.85 * heat, 0.85 - 0.45 * heat, 1.0 - 0.75 * heat, 0.95)
            add_arrow(origin, normal, arrow_len, color)
            normal_arrows += 1

        # Dense flow field around the object so even a default
        # cube (8 verts) gives a readable result.
        field_resolution = 31
        local_to_world = matrix.to_3x3()
        field_len = max(0.035, bounds_diag * 0.045)
        field_arrows = 0
        for iy in range(field_resolution):
            v = ((iy / (field_resolution - 1)) * 2.0 - 1.0) * half_span
            for ix in range(field_resolution):
                u = ((ix / (field_resolution - 1)) * 2.0 - 1.0) * half_span
                local_origin = Vector((center.x + u, center.y + v, center.z))
                local_direction = Vector((-v - 0.18 * u, u - 0.18 * v, 0.0))
                if local_direction.length_squared < 1e-10:
                    local_direction = Vector((1.0, 0.0, 0.0))
                direction = local_to_world @ local_direction
                origin = matrix @ local_origin
                add_arrow(origin, direction, field_len, (0.12, 0.82, 1.0, 0.8))
                field_arrows += 1

        shader = gpu.shader.from_builtin("POLYLINE_FLAT_COLOR")
        batch = batch_for_shader(shader, "LINES", {"pos": positions, "color": colors})
        return shader, batch, normal_arrows, field_arrows
    finally:
        evaluated.to_mesh_clear()


def _draw(state):
    region = bpy.context.region
    if region is None:
        return
    shader = state["shader"]
    shader.bind()
    shader.uniform_float("viewportSize", (region.width, region.height))
    # NOTE: lineWidth > 1 is clamped/ignored on some backends (Vulkan/Metal).
    shader.uniform_float("lineWidth", 1.6)
    state["batch"].draw(shader)


def _draw_hud(state):
    font_id = 0
    blf.size(font_id, 14)
    try:
        blf.enable(font_id, blf.SHADOW)
        blf.shadow(font_id, 3, 0.0, 0.0, 0.0, 1.0)
        try:
            blf.shadow_offset(font_id, 1, -1)
        except AttributeError:
            pass
    except (AttributeError, RuntimeError):
        pass
    try:
        blf.color(font_id, 0.35, 0.95, 1.0, 1.0)
        blf.position(font_id, 22, 82, 0)
        blf.draw(font_id, f"GPU FIELD + NORMALS  |  {state['label']}  |  {state['arrows'] + state['field_arrows']:,} arrows")
        blf.color(font_id, 0.9, 0.92, 0.95, 0.9)
        blf.position(font_id, 22, 62, 0)
        blf.draw(font_id, "Viewport overlay — geometry never reaches the Outliner")
    finally:
        try:
            blf.disable(font_id, blf.SHADOW)
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


def main():
    if _remove_previous():
        _tag_redraw()
        print("Normal overlay stopped (toggle). Run again to show it.")
        return
    active = bpy.context.view_layer.objects.active
    if active is None or active.type != "MESH":
        raise RuntimeError("Select an active Mesh object and run the script again.")

    shader, batch, arrow_count, field_count = _build_batch(active)
    state = {
        "shader": shader,
        "batch": batch,
        "arrows": arrow_count,
        "field_arrows": field_count,
        "label": active.name,
        "handles": [],
    }
    state["handles"].append(bpy.types.SpaceView3D.draw_handler_add(
        _draw, (state,), "WINDOW", "POST_VIEW"
    ))
    state["handles"].append(bpy.types.SpaceView3D.draw_handler_add(
        _draw_hud, (state,), "WINDOW", "POST_PIXEL"
    ))
    bpy.app.driver_namespace[_KEY] = state
    print(f"GPU overlay running: {active.name}, {arrow_count:,} normals + {field_count:,} flow arrows.")


if __name__ == "__main__":
    main()
