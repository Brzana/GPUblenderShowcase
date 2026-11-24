"""03 — Shader Toy: twoj pierwszy wlasny shader pikselowy w GLSL.

KROK 03/6 — "Jak przejac kontrole nad kazdym pikselem?"
CEL: Narysuj pelnoekranowy animowany gradient w ~15 linijkach GLSL.
POJECIA:
  1. GPUShaderCreateInfo opisuje wlasny shader: wejscia (vertex_in),
     wyjscia (fragment_out), mundury/uniformy (push_constant) + zrodla GLSL.
  2. Vertex shader leci 4x (raz na rog), fragment shader leci per-piksel.
     v_uv interpoluje sie po czworokacie: przestrzen UV 0..1 do obliczen.
  3. Uniform `time` animuje; `viewportSize` pilnuje proporcji.
     Nic nie wraca do CPU - piksele zostaja na GPU.
SPROBUJ NA ZAJECIACH:
  - Zmien `12.0 * r` na `30.0 * r`, re-run: petla live-edit GLSL.
  - Zmien dwa kolory w mix(), re-run.
NASTEPNY: 04 uzywa DOKLADNIE tego samego szkieletu, tylko matematyka
  fragmentu bedzie ciezsza (raymarch Mandelbulba). Porownaj pliki bok w bok.
"""

import bpy  # handlery, timery, driver_namespace
import blf  # napisy HUD
import gpu  # tworzenie wlasnego shadera
import time  # liczenie czasu animacji (perf_counter - started)
from gpu_extras.batch import batch_for_shader


_KEY = "gpu_showcase_shader_toy_v1"
# Slot HUD 2: tytul y=122, podtytul y=102 (powyzej 01: 42/22, 02: 82/62).

# Czworokat na caly ekran: pozycje w clip-space (-1..1).
# Vertex shader dostaje "pos" i musi wystawic v_uv + gl_Position.
_VERTEX = r"""
void main()
{
    v_uv = pos * 0.5 + 0.5;  // zamien [-1,1] na [0,1] zeby miec ladne UV
    gl_Position = vec4(pos, 0.0, 1.0);  // pozycja finalna na ekranie
}
"""

# Celowo malutki fragment shader. Czytaj od gory na zajeciach:
# uv -> poprawka aspektu -> odleglosc od srodka -> animowane pierscienie -> miks kolorow.
_FRAGMENT = r"""
void main()
{
    vec2 uv = v_uv * 2.0 - 1.0;  // wroc do [-1,1] zeby srodek byl w (0,0)
    uv.x *= viewportSize.x / max(viewportSize.y, 1.0);  // napraw rozciaganie przy szerokim oknie
    float r = length(uv);  // odleglosc od srodka ekranu
    float rings = 0.5 + 0.5 * sin(12.0 * r - time * 2.0);  // biegnace pierscienie
    float glow = exp(-3.0 * r);  // poswiata gasnaca od srodka
    vec3 deep = vec3(0.02, 0.05, 0.16);  // granat tla
    vec3 cyan = vec3(0.1, 0.85, 0.95);  // cyjan pierscieni
    vec3 color = mix(deep, cyan, rings * 0.45 + glow * 0.55);  // zmieszaj
    FragColor = vec4(color, 1.0);  // wynik: kolor pikselu, pelny alpha
}
"""


def _remove_previous():
    # Wylacz poprzednie uruchomienie + timer animacji.
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
    # Popros viewporty o przerysowanie (wywolywane z timera 30x na sekunde).
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
    # Rysowanie co klatke: ustaw blendowanie, podaj czas i rozmiar, narysuj quad.
    region = bpy.context.region
    if region is None:
        return
    shader = state["shader"]
    old_blend = gpu.state.blend_get()  # zapamietaj ustawienia Blendera...
    old_depth = gpu.state.depth_test_get()
    try:
        gpu.state.blend_set("ALPHA")  # ...wlacz przezroczystosc...
        gpu.state.depth_test_set("NONE")  # ...wylacz test glebokosci (HUD zawsze na wierzchu)
        shader.bind()
        # Jedyna rzecz wysylana z CPU co klatke: czas od startu + rozmiar okna.
        shader.uniform_float("time", time.perf_counter() - state["started"])
        shader.uniform_float("viewportSize", (region.width, region.height))
        state["batch"].draw(shader)
    finally:
        gpu.state.blend_set(old_blend)  # ...i przywroc jak bylo, zeby nie popsuc reszty UI
        gpu.state.depth_test_set(old_depth)

    # Napisy HUD rysowane w tym samym handlerze (prosciej, jeden handler mniej).
    blf.size(0, 14)
    blf.color(0, 0.35, 0.95, 1.0, 1.0)
    blf.position(0, 22, 122, 0)
    blf.draw(0, "03 SHADER TOY  |  wlasny GLSL gradient  |  edytuj + re-run")
    blf.color(0, 0.9, 0.92, 0.95, 0.9)
    blf.position(0, 22, 102, 0)
    blf.draw(0, "Ten sam szkielet co 04 raymarch — rozni sie tylko matematyka fragmentu")


def _make_timer(state):
    # Timer = metronom: co 1/30s prosi o przerysowanie, zeby animacja plynela.
    def tick():
        if bpy.app.driver_namespace.get(_KEY) is not state:
            return None  # ktos nas wylaczyl (np. 99) - zakoncz timer
        _tag_redraw()
        return 1.0 / 30.0  # wroc za 1/30 s (zwrocenie liczby = "powtorz")
    return tick


def main():
    if _remove_previous():
        _tag_redraw()
        print("03 shader toy wylaczony (przelacznik). Uruchom znow zeby pokazac.")
        return
    if not hasattr(gpu.types, "GPUShaderCreateInfo"):
        raise RuntimeError("Ten przyklad potrzebuje GPUShaderCreateInfo (Blender 3.x+ z modulem GPU).")

    # Przepis na shader, linijka po linijce - pokaz kazda na zajeciach:
    interface = gpu.types.GPUStageInterfaceInfo("toy_interface")
    interface.smooth("VEC2", "v_uv")          # zmienna przekazywana vertex -> fragment (interpolowana)
    info = gpu.types.GPUShaderCreateInfo()
    info.push_constant("FLOAT", "time")        # uniform co klatke: czas
    info.push_constant("VEC2", "viewportSize")  # uniform co klatke: rozmiar okna
    info.vertex_in(0, "VEC2", "pos")           # wejscie per-wierzcholek: pozycja quada
    info.vertex_out(interface)
    info.fragment_out(0, "VEC4", "FragColor")  # wyjscie per-piksel: kolor
    info.vertex_source(_VERTEX)
    info.fragment_source(_FRAGMENT)
    shader = gpu.shader.create_from_info(info)  # zbuduj gotowy program GPU z opisu

    # Quad na caly ekran jako TRI_STRIP: dol-lewy, dol-prawy, gora-lewy, gora-prawy.
    batch = batch_for_shader(shader, "TRI_STRIP", {
        "pos": ((-1.0, -1.0), (1.0, -1.0), (-1.0, 1.0), (1.0, 1.0)),
    })

    state = {"shader": shader, "batch": batch, "started": time.perf_counter(), "handles": []}
    state["handles"].append(bpy.types.SpaceView3D.draw_handler_add(
        _draw, (state,), "WINDOW", "POST_PIXEL"  # caly ekran 2D, na wierzchu sceny 3D
    ))
    state["timer"] = _make_timer(state)
    bpy.app.timers.register(state["timer"], first_interval=1.0 / 30.0)
    bpy.app.driver_namespace[_KEY] = state
    print("03 shader toy dziala. Edytuj _FRAGMENT, re-run zeby zobaczyc zmiane GLSL na zywo.")


if __name__ == "__main__":
    main()
