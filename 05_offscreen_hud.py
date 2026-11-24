"""05 — Render do tekstury HUD (bez odczytu do CPU).

KROK 05/6 — "Jak skladac przebiegi GPU bez CPU?"
CEL: Wyrenderuj animowany shader do GPUOffScreen (tekstura 512x320),
     potem wyswietl te teksture w HUDzie viewportu. Piksele nigdy nie dotykaja RAM.
POJECIA:
  1. offscreen.bind() przekierowuje rysowanie do tekstury zamiast na ekran.
  2. Renderuj RAZ na tick timera (straznik rendered_tick), wyswietlaj co przerysowanie.
     Praca offscreen musi byc w draw handlerze, bo tam jest kontekst GPU.
  3. Gotowy shader IMAGE wyswietla teksture jako quad HUD przypiety do GORY
     viewportu (dolne sloty zajmuja HUDy 01-04/06).
SPROBUJ: zmien rozmiar viewportu — podglad zostaje w lewym gornym rogu (matematyka region.height).
NASTEPNY: 06 (final) — compute zapisuje stan, vertex shader go czyta. Ta sama idea
  "GPU zostaje na GPU", ale dla symulacji zamiast dla pikseli.
"""

import bpy  # handlery, timery
import blf  # napisy
import gpu  # offscreen, shadery wlasne i wbudowane
import time  # animacja
from gpu_extras.batch import batch_for_shader


_KEY = "gpu_showcase_offscreen_v1"
_OFFSCREEN_W, _OFFSCREEN_H = 512, 320  # rozmiar tekstury roboczej (nie musi byc jak ekran)
# Rozmiar podgladu w HUD; przypiety do gory zeby nie przykryc napisow 01-04/06.
_PREVIEW_W, _PREVIEW_H = 300, 188
# Vertex jak w 03/04 - quad na caly "ekran" tekstury.
_VERTEX = r"""
void main()
{
    v_uv = pos * 0.5 + 0.5;
    gl_Position = vec4(pos, 0.0, 1.0);
}
"""
# Fragment rysowany DO TEKSTURY (nie na ekran). Fale + pierscienie w UV.
_FRAGMENT = r"""
void main()
{
    vec2 p = (v_uv * 2.0 - 1.0) * vec2(1.0, 0.72);
    float r = length(p);  // odleglosc od srodka tekstury
    float a = atan(p.y, p.x);  // kat do efektu falowania
    float wave = 0.5 + 0.5 * sin(18.0 * r - time * 2.0 + 3.0 * sin(5.0 * a + time));
    float ring = exp(-18.0 * abs(fract(r * 5.0 - time * 0.18) - 0.5));  // cienkie pierscienie
    vec3 col = mix(vec3(0.015, 0.025, 0.09), vec3(0.08, 0.8, 0.92), wave * 0.55 + ring * 0.45);
    col += vec3(0.35, 0.08, 0.8) * pow(max(0.0, 1.0 - r), 3.0);  // fioletowa poswiata w srodku
    FragColor = vec4(col, 1.0);
}
"""


def _remove_previous():
    # Toggle + sprzatanie: handlery, timer i zwolnienie tekstury offscreen.
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
    offscreen = state.get("offscreen")
    if offscreen is not None:
        try:
            offscreen.free()  # zwolnij pamiec GPU
        except (ReferenceError, RuntimeError):
            pass
    return True


def _create_offscreen():
    try:
        return gpu.types.GPUOffScreen(_OFFSCREEN_W, _OFFSCREEN_H, format="RGBA8")
    except TypeError:
        # Starsze buildy przyjmuja tylko (width, height) bez formatu.
        return gpu.types.GPUOffScreen(_OFFSCREEN_W, _OFFSCREEN_H)


def _render_offscreen(state):
    # Render do tekstury - TYLKO raz na tick timera, nie co przerysowanie!
    # (wiele viewportow = wiele redrawow, ale symulacja/animacja ma isc raz).
    if state["rendered_tick"] == state["tick"]:
        return
    old_blend = gpu.state.blend_get()
    old_depth = gpu.state.depth_test_get()
    try:
        with state["offscreen"].bind():  # "od teraz rysujemy do tekstury, nie na ekran"
            framebuffer = gpu.state.active_framebuffer_get()
            framebuffer.clear(color=(0.01, 0.015, 0.04, 1.0))  # wyczysc teksture ciemnym
            gpu.state.blend_set("NONE")
            gpu.state.depth_test_set("NONE")
            shader = state["shader"]
            shader.bind()
            shader.uniform_float("time", time.perf_counter() - state["started"])
            state["quad"].draw(shader)  # narysuj fale do tekstury
    finally:
        gpu.state.blend_set(old_blend)
        gpu.state.depth_test_set(old_depth)
    state["rendered_tick"] = state["tick"]  # zapamietaj ze ten tick juz wyrenderowany


def _draw_view(state):
    # Handler POST_VIEW: jego jedyne zadanie to odswiezyc teksture jesli trzeba.
    # Nie rysuje nic wprost do viewportu 3D.
    _render_offscreen(state)


def _preview_batch(state, x, y):
    # Zbuduj quad podgladu w miejscu (x,y) ekranu. Przebuduj tylko gdy pozycja sie zmienila
    # (np. resize okna), nie co klatke - oszczednosc.
    key = (round(x), round(y))
    if state.get("preview_key") == key and state.get("preview_batch") is not None:
        return state["preview_batch"]
    # IMAGE w POST_PIXEL oczekuje pozycji 2D w pikselach + TRI_STRIP
    # (bl, br, tl, tr) - tak jak w przykladzie "2D Image" z dokumentacji.
    # TRI_FAN i 3-skladnikowe (x,y,0) psuja sie na Vulkan/Metal.
    batch = batch_for_shader(state["image_shader"], "TRI_STRIP", {
        "pos": ((x, y), (x + _PREVIEW_W, y),
                (x, y + _PREVIEW_H), (x + _PREVIEW_W, y + _PREVIEW_H)),
        "texCoord": ((0, 0), (1, 0), (0, 1), (1, 1)),  # ktory rog tekstury w ktory rog quada
    })
    state["preview_batch"] = batch
    state["preview_key"] = key
    return batch


def _draw_hud(state):
    # Handler POST_PIXEL: wyswietl teksture jako obrazek HUD + podpis.
    region = bpy.context.region
    if region is None:
        return
    margin = 24  # odstep od krawedzi
    top_gap = 40  # odstep od gornej belki
    x = margin
    y_top = region.height - top_gap  # gora ekranu (rosnie razem z oknem)
    y = max(160, y_top - _PREVIEW_H)  # nie zjezdzaj za nisko na male okna
    old_blend = gpu.state.blend_get()
    old_depth = gpu.state.depth_test_get()
    try:
        gpu.state.blend_set("NONE")
        gpu.state.depth_test_set("NONE")
        image_shader = state["image_shader"]  # wbudowany shader do wyswietlania tekstur
        image_shader.bind()
        # Podaj teksture offscreen jako sampler "image". ZERO kopiowania do CPU!
        image_shader.uniform_sampler("image", state["offscreen"].texture_color)
        _preview_batch(state, x, y).draw(image_shader)
    finally:
        gpu.state.blend_set(old_blend)
        gpu.state.depth_test_set(old_depth)
    # Podpis nad podgladem.
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
        blf.position(0, x, y + _PREVIEW_H + 10, 0)
        blf.draw(0, "GPU OFFSCREEN  |  render-do-tekstury HUD")
    finally:
        try:
            blf.disable(0, blf.SHADOW)
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


def _make_timer(state):
    def tick():
        if bpy.app.driver_namespace.get(_KEY) is not state:
            return None
        state["tick"] += 1  # zwieksz licznik klatek animacji
        _tag_redraw()
        return 1.0 / 30.0
    return tick


def main():
    if _remove_previous():
        _tag_redraw()
        print("GPUOffScreen HUD wylaczony (przelacznik). Uruchom znow zeby pokazac.")
        return
    offscreen = _create_offscreen()  # stworz teksture 512x320 na GPU
    # Wlasny shader do wypelniania tekstury (przepis jak w 03, ale bez viewportSize).
    interface = gpu.types.GPUStageInterfaceInfo("offscreen_interface")
    interface.smooth("VEC2", "v_uv")
    info = gpu.types.GPUShaderCreateInfo()
    info.push_constant("FLOAT", "time")
    info.vertex_in(0, "VEC2", "pos")
    info.vertex_out(interface)
    info.fragment_out(0, "VEC4", "FragColor")
    info.vertex_source(_VERTEX)
    info.fragment_source(_FRAGMENT)
    shader = gpu.shader.create_from_info(info)
    quad = batch_for_shader(shader, "TRI_STRIP", {
        "pos": ((-1.0, -1.0), (1.0, -1.0), (-1.0, 1.0), (1.0, 1.0)),
    })

    # Gotowy shader do pokazania tekstury na ekranie (jak "drukarka zdjec").
    image_shader = gpu.shader.from_builtin("IMAGE")

    state = {
        "offscreen": offscreen,
        "shader": shader,
        "quad": quad,
        "image_shader": image_shader,
        "preview_batch": None,
        "preview_key": None,
        "started": time.perf_counter(),
        "tick": 0,
        "rendered_tick": -1,  # ktory tick juz wyrenderowano do tekstury
        "handles": [],
    }
    state["handles"].append(bpy.types.SpaceView3D.draw_handler_add(
        _draw_view, (state,), "WINDOW", "POST_VIEW"  # tu mamy kontekst GPU do renderu
    ))
    state["handles"].append(bpy.types.SpaceView3D.draw_handler_add(
        _draw_hud, (state,), "WINDOW", "POST_PIXEL"  # tu wyswietlamy wynik
    ))
    state["timer"] = _make_timer(state)
    bpy.app.timers.register(state["timer"], first_interval=1.0 / 30.0)
    bpy.app.driver_namespace[_KEY] = state
    print("GPUOffScreen HUD dziala. Tekstura wyswietlana bez odczytu do CPU. Re-run wylacza.")


if __name__ == "__main__":
    main()
