"""Overlay wektorow normalnych aktywnej siatki — bez obiektow w scenie.

Uruchom skrypt z aktywnym obiektem typu Mesh. Ponowne uruchomienie usuwa
poprzedni handler. Dane geometrii sa pobierane raz; aby odswiezyc overlay,
uruchom skrypt ponownie.
"""

import bpy
import blf
import gpu
import math
from mathutils import Vector
from gpu_extras.batch import batch_for_shader


_KEY = "gpu_showcase_normal_overlay_v1"
_MAX_ARROWS = 7000


def _remove_previous():
    state = bpy.app.driver_namespace.pop(_KEY, None)
    if not state:
        return
    for key, region in (("view_handle", "WINDOW"), ("hud_handle", "WINDOW")):
        handle = state.get(key)
        if handle is not None:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(handle, region)
            except (ReferenceError, ValueError, RuntimeError):
                pass


def _build_batch(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        count = len(mesh.vertices)
        if count == 0:
            raise RuntimeError("Aktywny obiekt nie ma wierzcholkow.")

        step = max(1, math.ceil(count / _MAX_ARROWS))
        matrix = evaluated.matrix_world
        try:
            normal_matrix = matrix.to_3x3().inverted().transposed()
        except ValueError:
            normal_matrix = matrix.to_3x3()

        diagonal = (Vector(mesh.vertices[0].co) - Vector(mesh.vertices[-1].co)).length
        arrow_len = max(0.035, diagonal * 0.035)
        positions = []
        colors = []

        z_values = [vertex.co.z for i, vertex in enumerate(mesh.vertices) if i % step == 0]
        z_min = min(z_values)
        z_span = max(1e-6, max(z_values) - z_min)

        bounds_min = Vector((
            min(vertex.co.x for vertex in mesh.vertices),
            min(vertex.co.y for vertex in mesh.vertices),
            min(vertex.co.z for vertex in mesh.vertices),
        ))
        bounds_max = Vector((
            max(vertex.co.x for vertex in mesh.vertices),
            max(vertex.co.y for vertex in mesh.vertices),
            max(vertex.co.z for vertex in mesh.vertices),
        ))
        center = (bounds_min + bounds_max) * 0.5
        half_span = max(0.6, max(bounds_max - bounds_min) * 0.7)

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

        for index in range(0, count, step):
            vertex = mesh.vertices[index]
            origin = matrix @ vertex.co
            normal = normal_matrix @ vertex.normal
            if normal.length_squared < 1e-12:
                continue
            normal.normalize()
            heat = min(1.0, max(0.0, (vertex.co.z - z_min) / z_span))
            color = (0.15 + 0.85 * heat, 0.85 - 0.45 * heat, 1.0 - 0.75 * heat, 0.95)
            add_arrow(origin, normal, arrow_len, color)

        # Gestoe pole przeplywu wokol obiektu daje czytelny rezultat nawet dla
        # prostej siatki, np. domyslnego szescianu z zaledwie 8 wierzcholkami.
        field_resolution = 31
        local_to_world = matrix.to_3x3()
        field_len = max(0.035, diagonal * 0.045)
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
        return shader, batch, len(positions) // 6, field_arrows
    finally:
        evaluated.to_mesh_clear()


def _draw(state):
    region = bpy.context.region
    if region is None:
        return
    shader = state["shader"]
    shader.uniform_float("viewportSize", (region.width, region.height))
    shader.uniform_float("lineWidth", 1.6)
    state["batch"].draw(shader)


def _draw_hud(state):
    font_id = 0
    # Slot 0 (dolny): 22 / 42. Inne dema uzywaja wyzszych slotow.
    blf.size(font_id, 14)
    try:
        blf.enable(font_id, blf.SHADOW)
        blf.shadow(font_id, 3, 0.0, 0.0, 0.0, 1.0)
        try:
            blf.shadow_offset(font_id, 1, -1)
        except AttributeError:
            pass
    except Exception:
        pass
    try:
        blf.color(font_id, 0.35, 0.95, 1.0, 1.0)
        blf.position(font_id, 22, 42, 0)
        blf.draw(font_id, f"GPU FIELD + NORMALS  |  {state['label']}  |  {state['arrows']:,} strzalek")
        blf.color(font_id, 0.9, 0.92, 0.95, 0.9)
        blf.position(font_id, 22, 22, 0)
        blf.draw(font_id, "Overlay viewportu — geometria nie trafia do Outlinera")
    finally:
        try:
            blf.disable(font_id, blf.SHADOW)
        except Exception:
            pass


_remove_previous()
active = bpy.context.view_layer.objects.active
if active is None or active.type != "MESH":
    raise RuntimeError("Zaznacz aktywny obiekt Mesh i uruchom skrypt ponownie.")

shader, batch, arrow_count, field_count = _build_batch(active)
state = {
    "shader": shader,
    "batch": batch,
    "arrows": arrow_count,
    "field_arrows": field_count,
    "label": active.name,
}
state["view_handle"] = bpy.types.SpaceView3D.draw_handler_add(
    _draw, (state,), "WINDOW", "POST_VIEW"
)
state["hud_handle"] = bpy.types.SpaceView3D.draw_handler_add(
    _draw_hud, (state,), "WINDOW", "POST_PIXEL"
)
bpy.app.driver_namespace[_KEY] = state
print(f"GPU overlay uruchomiony: {active.name}, {arrow_count:,} strzalek pola i normalnych.")
