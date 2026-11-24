"""06 — FINAL: 102 400 czasteczek, compute shader + tekstury ping-pong.

KROK 06/6 — "Jak symulowac I rysowac bez CPU?"
CEL: Spnij cala historie. Porownaj z liczba CPU z 00.
POJECIA:
  1. Tekstura stanu RGBA32F = (x, y, vx, vy). CPU wysyla startowa spirale
     RAZ; potem compute shader czyta state_in, pisze state_out.
  2. Ping-pong: dwie tekstury zamieniaja sie rolami co klatke. Bez odczytu do RAM.
  3. Vertex shader robi texelFetch() z biezacej tekstury - pozycja z UV.
     Rysowane jako gl_Points przez macierz viewProjectionMatrix.
  4. Jeden dispatch na tick timera (straznik dispatched_tick) zeby N viewportow
     nie przyspieszalo symulacji. To samo pole sil co w 00 dla porownania.
LINIJKA DEMO: "00 calkowalo 50k czasteczek na CPU w X ms. To calkuje
  102k na GPU bez wracania pozycji do RAM."
SPRZATANIE: re-run zeby wylaczyc, albo 99_stop_showcase.py.

UWAGA: dispatch compute jest w draw handlerze celowo - timery Blendera
nie maja kontekstu GPU, wiec dispatch musi byc tam gdzie GL jest aktywny.
Straznik tick pilnuje zeby byl jeden krok na tick timera.
"""

import bpy  # handlery, timery, macierz kamery region_data
import blf  # napisy HUD
import gpu  # shadery, tekstury, gpu.compute.dispatch
import math  # ukladanie spirali startowej jak w 00
from gpu_extras.batch import batch_for_shader


_KEY = "gpu_showcase_compute_particles_v1"
# Slot HUD 4: tytul y=202, podtytul y=182 (powyzej 04: 162/142; 05 jest przypiety do gory).
_SIZE = 320  # tekstura 320x320 = 102400 czasteczek (kazdy piksel = jedna czasteczka)
_LOCAL_SIZE = 16  # rozmiar grupy roboczej GPU (16x16 watkow na grupe)
_COUNT = _SIZE * _SIZE
_DT = 1.0 / 60.0  # krok fizyki jak w 00
_GROUPS = (_SIZE + _LOCAL_SIZE - 1) // _LOCAL_SIZE  # ile grup potrzeba: 320/16 = 20x20

# Shader liczacy fizyke. Leci RAZ na czasteczke, rownolegle na tysiacach rdzeni GPU.
# state_in: czyta stara pozycje+predkosc, state_out: zapisuje nowe.
_COMPUTE = r"""
void main()
{
    ivec2 cell = ivec2(gl_GlobalInvocationID.xy);  // "moj" piksel: ktora czasteczka mnie wolala
    ivec2 dims = imageSize(state_in);  // rozmiar tekstury (320x320)
    if (cell.x >= dims.x || cell.y >= dims.y) return;  // straznik na brzegi (przy niepodzielnych rozmiarach)

    vec4 state = imageLoad(state_in, cell);  // pobierz (x, y, vx, vy)
    vec2 p = state.xy;  // pozycja
    vec2 v = state.zw;  // predkosc
    // TO SAMO rownanie co w step_python w 00, tylko wektorowo i na GPU:
    float inv_r = inversesqrt(dot(p, p) + 0.2);  // 1/r
    vec2 tangent = vec2(-p.y, p.x) * inv_r;  // kierunek wirowy
    vec2 acceleration = tangent * 0.45 - p * 0.08 - v * 0.12;  // wirowanie + srodek + opor
    v += acceleration * delta_time;  // calka Eulera
    p += v * delta_time;

    // Odbicia od scianek +-5.5 - identyczne jak BOUND w 00.
    if (p.x < -5.5 || p.x > 5.5) { p.x = clamp(p.x, -5.5, 5.5); v.x = -v.x; }
    if (p.y < -5.5 || p.y > 5.5) { p.y = clamp(p.y, -5.5, 5.5); v.y = -v.y; }
    imageStore(state_out, cell, vec4(p, v));  // zapisz nowy stan do drugiej tekstury
}
"""

# Vertex shader do RYSOWANIA. Dla kazdego punktu pobiera pozycje z tekstury stanu.
_DRAW_VERTEX = r"""
void main()
{
    ivec2 dims = textureSize(state_tex, 0);  // rozmiar tekstury stanu
    ivec2 cell = clamp(ivec2(uv * vec2(dims)), ivec2(0), dims - ivec2(1));  // uv punktu -> ktory piksel
    vec4 state = texelFetch(state_tex, cell, 0);  // odczytaj (x,y,vx,vy) - TO jest pozycja czasteczki!
    v_speed = length(state.zw);  // predkosc przekaz do fragmentu zeby pokolorowac
    gl_Position = viewProjectionMatrix * vec4(state.xy, 0.0, 1.0);  // 2D symulacji -> ekran 3D
}
"""

# Fragment shader do RYSOWANIA. Z kwadratu punktu robi kolko i koloruje po predkosci.
_DRAW_FRAGMENT = r"""
void main()
{
    vec2 q = gl_PointCoord * 2.0 - 1.0;  // wspolrzedne wewnatrz punktu [-1,1]
    float r2 = dot(q, q);
    if (r2 > 1.0) discard;  // wytnij rogi kwadratu - zostaje kolko
    float speed = clamp(v_speed * 1.8, 0.0, 1.0);  // 0=wolno, 1=szybko
    vec3 color = mix(vec3(0.04, 0.45, 1.0), vec3(0.2, 1.0, 0.72), speed);  // niebieski -> zielony
    float glow = 1.0 - smoothstep(0.0, 1.0, r2);  // miekka krawedz kolka
    FragColor = vec4(color, 0.35 + glow * 0.65);
}
"""


def _remove_previous():
    # Toggle: zdepnij handlery + timer. Tekstury zwolnia sie same gdy puscimy referencje.
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
    for tex in state.get("textures", ()):
        try:
            # GPUTexture nie ma free(); wystarczy puscic referencje, GPU zwolni pamiec.
            # Czyscimy jawnie zeby re-runy nie zjadaly pamieci GPU.
            del tex
        except (ReferenceError, RuntimeError):
            pass
    return True


def _create_textures():
    # Jednorazowy upload startowy z CPU (~400k liczb). Moze na moment zawiesic UI.
    values = []  # plaska lista: x,y,vx,vy, x,y,vx,vy, ...
    golden_angle = 2.399963229728653  # ten sam trik co w 00 na rowna spirale
    for i in range(_COUNT):
        radius = 4.4 * math.sqrt((i + 0.5) / _COUNT)
        angle = i * golden_angle
        x = radius * math.cos(angle)
        y = radius * math.sin(angle)
        vx = -0.15 * math.sin(angle)  # predkosc styczna jak w 00
        vy = 0.15 * math.cos(angle)
        values.extend((x, y, vx, vy))
    total = _SIZE * _SIZE * 4
    assert len(values) == total, f"zly rozmiar danych: {len(values)} != {total}"
    initial_data = gpu.types.Buffer("FLOAT", total, values)  # bufor CPU -> GPU
    first = gpu.types.GPUTexture((_SIZE, _SIZE), format="RGBA32F", data=initial_data)  # tekstura ze spirala
    second = gpu.types.GPUTexture((_SIZE, _SIZE), format="RGBA32F")  # druga pusta do ping-ponga
    return (first, second), initial_data


def _draw_simulation(state):
    # Najwazniejsza funkcja: 1x compute (fizyka) + 1x rysowanie, co redraw.
    context = bpy.context
    if context.region_data is None:
        return  # nie jestesmy w widoku 3D (np. inny edytor) - nic nie rob

    # Kontekst GPU jest aktywny TYLKO tutaj (w handlerze), nie w timerze - dlatego dispatch jest tu.
    # Straznik zeby wiele otwartych viewportow nie liczylo fizyki wiele razy na tick.
    if state["dispatched_tick"] != state["tick"]:
        source_index = state["current"]  # z ktorej tekstury czytamy...
        target_index = 1 - source_index  # ...do ktorej piszemy (ping-pong 0<->1)
        compute = state["compute_shader"]
        compute.bind()
        compute.image("state_in", state["textures"][source_index])
        compute.image("state_out", state["textures"][target_index])
        compute.uniform_float("delta_time", _DT)
        gpu.compute.dispatch(compute, _GROUPS, _GROUPS, 1)  # odpal 20x20 grup = 320x320 watkow
        state["current"] = target_index  # zamien role tekstur
        state["dispatched_tick"] = state["tick"]

    # Rysowanie punktow z biezacej tekstury stanu.
    old_blend = gpu.state.blend_get()
    old_depth = gpu.state.depth_test_get()
    try:
        gpu.state.blend_set("ALPHA")
        gpu.state.depth_test_set("NONE")
        # UWAGA: rozmiar punktu bywa sciety do 1px na niektorych backendach (Vulkan/Metal).
        gpu.state.point_size_set(3.0)
        draw_shader = state["draw_shader"]
        draw_shader.bind()
        # Macierz kamery biezacego viewportu zeby punkty siedzialy w swiecie 3D.
        draw_shader.uniform_float("viewProjectionMatrix", context.region_data.perspective_matrix)
        # Podepnij biezaca teksture stanu jako sampler do odczytu w vertex shaderze.
        draw_shader.uniform_sampler("state_tex", state["textures"][state["current"]])
        state["batch"].draw(draw_shader)
    finally:
        gpu.state.blend_set(old_blend)
        gpu.state.depth_test_set(old_depth)
        gpu.state.point_size_set(1.0)  # przywroc domyslny rozmiar punktu


def _draw_hud(state):
    # Podpis licznika czasteczek.
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
        blf.position(0, 22, 202, 0)
        blf.draw(0, f"GPU COMPUTE  |  {state['count']:,} czasteczek  |  RGBA32F ping-pong")
        blf.color(0, 0.9, 0.92, 0.95, 0.9)
        blf.position(0, 22, 182, 0)
        blf.draw(0, "compute -> tekstura -> vertex shader -> viewport (bez odczytu)")
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
    # Timer tylko podbija licznik i prosi o redraw. Fizyka dzieje sie w handlerze (patrz wyzej).
    def tick():
        if bpy.app.driver_namespace.get(_KEY) is not state:
            return None
        state["tick"] += 1
        _tag_redraw()
        return _DT  # wroc za 1/60 s
    return tick


def main():
    if _remove_previous():
        _tag_redraw()
        print("Symulacja GPU wylaczona (przelacznik). Uruchom znow zeby zrestartowac.")
        return
    required = ("GPUShaderCreateInfo", "GPUTexture")
    if not all(hasattr(gpu.types, name) for name in required) or not hasattr(gpu, "compute"):
        raise RuntimeError("Demo compute potrzebuje nowego Blendera z gpu.compute (zalecany 4.x).")

    # 1. Shader liczacy (compute): jedno wejscie READ, jedno wyjscie WRITE + rozmiar grupy.
    compute_info = gpu.types.GPUShaderCreateInfo()
    compute_info.push_constant("FLOAT", "delta_time")  # krok czasu jako uniform
    compute_info.image(0, "RGBA32F", "FLOAT_2D", "state_in", qualifiers={"READ"})
    compute_info.image(1, "RGBA32F", "FLOAT_2D", "state_out", qualifiers={"WRITE"})
    compute_info.local_group_size(_LOCAL_SIZE, _LOCAL_SIZE, 1)  # 16x16 watkow na grupe
    compute_info.compute_source(_COMPUTE)
    compute_shader = gpu.shader.create_from_info(compute_info)

    # 2. Shader rysujacy: czyta teksture stanu, wystawia predkosc do kolorowania.
    draw_interface = gpu.types.GPUStageInterfaceInfo("particle_interface")
    draw_interface.smooth("FLOAT", "v_speed")  # varying: vertex -> fragment
    draw_info = gpu.types.GPUShaderCreateInfo()
    draw_info.push_constant("MAT4", "viewProjectionMatrix")  # macierz kamery
    draw_info.sampler(0, "FLOAT_2D", "state_tex")  # tekstura stanu do odczytu
    draw_info.vertex_in(0, "VEC2", "uv")  # ktora czasteczka (indeks jako UV)
    draw_info.vertex_out(draw_interface)
    draw_info.fragment_out(0, "VEC4", "FragColor")
    draw_info.vertex_source(_DRAW_VERTEX)
    draw_info.fragment_source(_DRAW_FRAGMENT)
    draw_shader = gpu.shader.create_from_info(draw_info)

    # 3. Tekstury startowe + batch punktow. Jeden wierzcholek POINTS = jedna czasteczka.
    textures, initial_data = _create_textures()
    # UV srodka kazdego piksela: (x+0.5)/SIZE - zeby texelFetch trafil idealnie w piksel.
    uvs = [((x + 0.5) / _SIZE, (y + 0.5) / _SIZE)
           for y in range(_SIZE) for x in range(_SIZE)]
    batch = batch_for_shader(draw_shader, "POINTS", {"uv": uvs})

    state = {
        "compute_shader": compute_shader,
        "draw_shader": draw_shader,
        "textures": textures,
        # Trzymaj Buffer przy zyciu: GPUTexture moze go potrzebowac az upload sie skonczy.
        "initial_data": initial_data,
        "batch": batch,
        "count": _COUNT,
        "tick": 0,
        "dispatched_tick": -1,  # ktory tick juz policzyl compute
        "current": 0,  # ktora tekstura jest biezaca (0 albo 1, ping-pong)
        "handles": [],
    }
    state["handles"].append(bpy.types.SpaceView3D.draw_handler_add(
        _draw_simulation, (state,), "WINDOW", "POST_VIEW"  # punkty w swiecie 3D
    ))
    state["handles"].append(bpy.types.SpaceView3D.draw_handler_add(
        _draw_hud, (state,), "WINDOW", "POST_PIXEL"  # licznik jako HUD
    ))
    state["timer"] = _make_timer(state)
    bpy.app.timers.register(state["timer"], first_interval=_DT)
    bpy.app.driver_namespace[_KEY] = state
    print(f"Symulacja GPU dziala: {_COUNT:,} czasteczek; stan nigdy nie wraca do CPU. Re-run wylacza.")


if __name__ == "__main__":
    main()
