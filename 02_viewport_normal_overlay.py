"""02 — Nakladka na mesh gotowym shaderem (jeszcze bez wlasnego GLSL).

KROK 02/6 — "Jak rysowac prawdziwe dane szybko?"
CEL: Ten sam 3-stopniowy wzorzec co w 01, ale geometria pochodzi z aktywnego mesha.
POJECIA:
  1. Mesh czytasz RAZ na CPU (mesh po modyfikatorach + matrix_world),
     wysylasz jako paczke LINES; GPU przerysowuje ja co klatke za darmo.
  2. POLYLINE_FLAT_COLOR = wbudowany shader z kolorem per-wierzcholek.
     Nadal zero recznie pisanego GLSL.
  3. POST_VIEW rysuje w swiecie (strzalki kleja sie do obiektu).
     Tekst HUD uzywa POST_PIXEL (stala pozycja na ekranie).
SPROBUJ: zaznacz Cube vs Suzanne, uruchom ponownie — licznik strzalek sie zmieni.
  Przelacz wireframe: nakladka zostaje (to nie jest geometria sceny).
NASTEPNY: 03 zamienia wbudowany shader na wlasny GLSL.

Uruchom z aktywnym obiektem Mesh. Re-run wylacza nakladke.
Geometria jest pobierana raz; po zaznaczeniu nowego mesha uruchom ponownie.
"""

import bpy  # scena, depsgraph, handlery rysowania
import blf  # napisy HUD
import gpu  # shadery i stan GPU
import math  # ceil do probkowania, zeby nie przekroczyc limitu strzalek
from mathutils import Vector  # wektory 3D: pozycje, normalne, mnozenie przez macierz
from gpu_extras.batch import batch_for_shader  # pakowanie pozycji+kolorow do rysowania


_KEY = "gpu_showcase_normal_overlay_v1"  # klucz w driver_namespace dla tego demka
_MAX_ARROWS = 7000  # bezpiecznik: nie wysylamy wiecej strzalek normalnych niz tyle
# Slot HUD 1: tytul y=82, podtytul y=62 (powyzej slota 01: 42/22).


def _remove_previous():
    # Wylacz poprzednie uruchomienie (toggle OFF przy re-runie).
    state = bpy.app.driver_namespace.pop(_KEY, None)
    if not state:
        return False
    handles = list(state.get("handles", ()))
    # Zgodnosc wstecz ze starszym ukladem kluczy (view_handle/hud_handle).
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
    # Zbuduj paczke linii RAZ na CPU. To najwazniejsza funkcja w tym pliku.
    # Zwraca: (shader, batch, liczba_normalnych, liczba_strzalek_tla).
    depsgraph = bpy.context.evaluated_depsgraph_get()  # graf zaleznosci - widzi modyfikatory
    evaluated = obj.evaluated_get(depsgraph)  # kopia obiektu PO modyfikatorach
    mesh = evaluated.to_mesh()  # tymczasowy mesh do odczytu wierzcholkow
    try:
        count = len(mesh.vertices)
        if count == 0:
            raise RuntimeError("Aktywny obiekt nie ma wierzcholkow.")

        # Jesli mesh ma 100k wierzcholkow, bierzemy co N-ty zeby zmiescic sie w limicie.
        step = max(1, math.ceil(count / _MAX_ARROWS))
        matrix = evaluated.matrix_world  # macierz obiektu: lokalne -> swiat
        try:
            # Normalne transformuja sie macierza odwrotno-transponowana (regula matematyczna).
            normal_matrix = matrix.to_3x3().inverted().transposed()
        except ValueError:
            normal_matrix = matrix.to_3x3()  # awaryjnie: zwykla macierz 3x3

        # Jeden przebieg: zbierz probkowane wierzcholki + rozmiar obiektu (bounding box).
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
        bounds_diag = (bounds_max - bounds_min).length  # przekatna = "wielkosc" obiektu

        # Dlugosc strzalki skalowana do obiektu: 3.5% przekatnej, min 0.035.
        arrow_len = max(0.035, bounds_diag * 0.035)
        center = (bounds_min + bounds_max) * 0.5  # srodek obiektu
        half_span = max(0.6, bounds_diag * 0.7)  # polowa zasiegu siatki tla

        positions = []  # tu beda pary punktow: poczatek-koniec kazdej kreski
        colors = []  # kolor per-wierzcholek (RGBA)

        def add_segment(a, b, color):
            # Jedna kreska = 2 punkty + 2 kolory. Shader LINES laczy je w pary.
            positions.extend((tuple(a), tuple(b)))
            colors.extend((color, color))

        def add_arrow(origin, direction, length, color):
            # Strzalka = trzon + 2 skrzydelka grotu.
            if direction.length_squared < 1e-12:
                return  # zerowy wektor - nie ma czego rysowac
            direction.normalize()  # sprowadz do dlugosci 1
            tip = origin + direction * length  # czubek strzalki
            # Wektor "w bok" do narysowania grotu (iloczyn wektorowy z osia Z).
            side = direction.cross(Vector((0.0, 0.0, 1.0)))
            if side.length_squared < 1e-8:
                # Jesli strzalka patrzy akurat w Z, wez inna os zeby nie dzielic przez zero.
                side = direction.cross(Vector((1.0, 0.0, 0.0)))
            side.normalize()
            back = -direction * (length * 0.24)  # cofniecie grotu
            wing = length * 0.12  # szerokosc grotu
            add_segment(origin, tip, color)  # trzon
            add_segment(tip, tip + back + side * wing, color)  # lewe skrzydelko
            add_segment(tip, tip + back - side * wing, color)  # prawe skrzydelko

        # --- Strzalki normalnych (niebiesko-cyjanowe, kolorowane wysokoscia) ---
        normal_arrows = 0
        for index, lx, ly, lz in sampled:
            vertex = mesh.vertices[index]
            origin = matrix @ vertex.co  # pozycja lokalna -> swiat (operator @ to mnozenie macierzy)
            normal = normal_matrix @ vertex.normal  # normalna lokalna -> swiat
            if normal.length_squared < 1e-12:
                continue
            normal.normalize()
            # "Heat": im wyzej w Z swiata, tym bardziej cyjan. Liczone po transformacji.
            heat = min(1.0, max(0.0, (origin.z - (matrix @ bounds_min).z) / max(1e-6, ((matrix @ bounds_max).z - (matrix @ bounds_min).z))))
            color = (0.15 + 0.85 * heat, 0.85 - 0.45 * heat, 1.0 - 0.75 * heat, 0.95)
            add_arrow(origin, normal, arrow_len, color)
            normal_arrows += 1

        # --- Geste pole przeplywu wokol obiektu (zeby kostka z 8 wierzcholkow tez cos pokazala) ---
        field_resolution = 31  # siatka 31x31 = 961 strzalek tla
        local_to_world = matrix.to_3x3()
        field_len = max(0.035, bounds_diag * 0.045)
        field_arrows = 0
        for iy in range(field_resolution):
            v = ((iy / (field_resolution - 1)) * 2.0 - 1.0) * half_span
            for ix in range(field_resolution):
                u = ((ix / (field_resolution - 1)) * 2.0 - 1.0) * half_span
                local_origin = Vector((center.x + u, center.y + v, center.z))
                # Sztuczny wirowy kierunek pola (wyglada jak przeplyw wokol obiektu).
                local_direction = Vector((-v - 0.18 * u, u - 0.18 * v, 0.0))
                if local_direction.length_squared < 1e-10:
                    local_direction = Vector((1.0, 0.0, 0.0))
                direction = local_to_world @ local_direction
                origin = matrix @ local_origin
                add_arrow(origin, direction, field_len, (0.12, 0.82, 1.0, 0.8))
                field_arrows += 1

        # Gotowy shader z kolorem per-wierzcholek + paczka linii. Od tej pory GPU rysuje samo.
        shader = gpu.shader.from_builtin("POLYLINE_FLAT_COLOR")
        batch = batch_for_shader(shader, "LINES", {"pos": positions, "color": colors})
        return shader, batch, normal_arrows, field_arrows
    finally:
        evaluated.to_mesh_clear()  # WAZNE: zwolnij tymczasowy mesh, inaczej wyciek pamieci


def _draw(state):
    # Rysowanie 3D co klatke: ustaw szerokosc linii i pchnij batch na GPU.
    region = bpy.context.region
    if region is None:
        return
    shader = state["shader"]
    shader.bind()
    shader.uniform_float("viewportSize", (region.width, region.height))  # ten shader tego wymaga
    # UWAGA: lineWidth > 1 bywa ignorowane na Vulkan/Metal - wtedy linie maja 1px i to normalne.
    shader.uniform_float("lineWidth", 1.6)
    state["batch"].draw(shader)


def _draw_hud(state):
    # Napis z nazwa obiektu i liczba strzalek.
    font_id = 0
    blf.size(font_id, 14)
    try:
        blf.enable(font_id, blf.SHADOW)  # cien pod tekstem dla czytelnosci
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
        blf.draw(font_id, "Nakladka viewportu — geometria nigdy nie trafia do Outlinera")
    finally:
        try:
            blf.disable(font_id, blf.SHADOW)
        except (AttributeError, RuntimeError):
            pass


def _tag_redraw():
    # Popros o przerysowanie wszystkich widokow 3D.
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
        print("Nakladka normalnych wylaczona (przelacznik). Uruchom znow zeby pokazac.")
        return
    # Musi byc zaznaczony aktywny obiekt typu MESH - inaczej nie mamy czego czytac.
    active = bpy.context.view_layer.objects.active
    if active is None or active.type != "MESH":
        raise RuntimeError("Zaznacz aktywny obiekt Mesh i uruchom skrypt ponownie.")

    # Budujemy batch RAZ tutaj. Potem tylko rysujemy go co klatke.
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
        _draw, (state,), "WINDOW", "POST_VIEW"  # strzalki w swiecie 3D
    ))
    state["handles"].append(bpy.types.SpaceView3D.draw_handler_add(
        _draw_hud, (state,), "WINDOW", "POST_PIXEL"  # tekst jako HUD
    ))
    bpy.app.driver_namespace[_KEY] = state
    print(f"Nakladka GPU dziala: {active.name}, {arrow_count:,} normalnych + {field_count:,} strzalek tla.")


if __name__ == "__main__":
    main()
