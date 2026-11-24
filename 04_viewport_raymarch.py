"""04 — Raymarchowany Mandelbulb: ten sam szkielet co 03, ciezsza matematyka.

KROK 04/6 — "Co daje mi pelna kontrola GLSL?"
CEL: Pokazac ze wzorzec fullscreen-quad + GPUShaderCreateInfo z 03 skaluje sie
     do 58-krokowego raymarchera SDF z oswietleniem. Porownaj 03 vs 04 na zajeciach.
POJECIA:
  1. Fragment shader = petla raymarch (sphere tracing na mandelbulb()),
     normalna z roznic skonczonych, swiatlo diffuse + rim.
  2. Nietrafione promienie daja alpha 0 (przezroczyste) wiec scena przechodzi spod spodu.
  3. Koszt jest per-piksel: zmniejsz viewport - przyspieszy. Dobra zywa demonstracja
     limitu fill-rate GPU. Obrot myszka NIE rusza kamery shadera (to overlay, nie material).
WYMAGANE: najpierw uruchom 03 zeby uczniowie poznali otaczajacy Python.
NASTEPNY: 05 zostawia wlasny GLSL ale renderuje najpierw do tekstury.

To jest nakladka ekranowa (nie material ani post-process calej sceny).
Wynik shadera jest rysowany wprost do viewportu przez draw handler.
Zmniejsz STEP_COUNT jesli maszyna jest slaba (sprobuj 32).
"""

import bpy  # handlery, timery
import blf  # napisy
import gpu  # wlasny shader
import time  # animacja time
from gpu_extras.batch import batch_for_shader


_KEY = "gpu_showcase_raymarch_v1"
# Slot HUD 3: tytul y=162, podtytul y=142 (powyzej 03: 122/102).
STEP_COUNT = 58  # ile krokow marszu ma zrobic promien. Mniej = szybciej, brzydziej.
# Vertex identyczny jak w 03 - quad na caly ekran.
_VERTEX = r"""
void main()
{
    v_uv = pos * 0.5 + 0.5;
    gl_Position = vec4(pos, 0.0, 1.0);
}
"""

# Fragment: odleglosc do fraktala + marsz promieniem + swiatlo.
# Python wstawia STEP_COUNT w miejsce STEP_COUNT_PLACEHOLDER (GLSL wymaga stalej w petli).
_FRAGMENT = r"""
float mandelbulb(vec3 p)
{
    // Klasyczny fraktal Mandelbulb potegi 7. Zwraca SDF = "jak daleko do powierzchni".
    vec3 z = p;
    float dr = 1.0;  // pochodna do korekty odleglosci (trik Hart'a)
    float r = 0.0;
    for (int i = 0; i < 7; ++i) {
        r = length(z);
        if (r > 2.2) break;  // uciekl daleko - nie jest w fraktalu, przerwij
        float safe_r = max(r, 0.0001);  // zabezpieczenie przed dzieleniem przez zero
        float theta = acos(clamp(z.z / safe_r, -1.0, 1.0));  // kat od osi Z
        float phi = atan(z.y, z.x);  // kat wokol osi Z
        dr = pow(safe_r, 6.0) * 7.0 * dr + 1.0;
        float zr = pow(safe_r, 7.0);
        theta *= 7.0;  // potega fraktala: pomnoz katy x7
        phi *= 7.0;
        z = zr * vec3(sin(theta) * cos(phi), sin(phi) * sin(theta), cos(theta)) + p;
    }
    return 0.5 * log(max(r, 0.0001)) * r / max(dr, 0.0001);  // estymata odleglosci
}

vec3 rotate_y(vec3 p, float a)
{
    // Obrot wokol osi Y o kat a (zeby fraktal sie krecil w czasie).
    float c = cos(a), s = sin(a);
    return vec3(c * p.x + s * p.z, p.y, -s * p.x + c * p.z);
}

void main()
{
    vec2 uv = v_uv * 2.0 - 1.0;  // ekran [-1,1]
    uv.x *= viewportSize.x / max(viewportSize.y, 1.0);  // fix proporcji
    vec3 ro = vec3(0.0, 0.0, 4.2);  // origin promienia = pozycja kamery
    vec3 rd = normalize(vec3(uv * 0.78, -1.45));  // direction promienia przez piksel
    float t = 0.0;  // przebyty dystans wzdluz promienia
    float d = 0.0;  // odleglosc do powierzchni w danym kroku
    bool hit = false;

    // Sphere tracing: idz o tyle ile mowi SDF, bo tyle na pewno jest pusto.
    for (int i = 0; i < STEP_COUNT_PLACEHOLDER; ++i) {
        vec3 p = rotate_y(ro + rd * t, time * 0.22);  // punkt + obrot fraktala w czasie
        p.xy = mat2(cos(time * 0.13), -sin(time * 0.13), sin(time * 0.13), cos(time * 0.13)) * p.xy;
        d = mandelbulb(p);
        if (d < 0.0015) { hit = true; break; }  // jestesmy wystarczajaco blisko powierzchni
        t += max(d * 0.72, 0.001);  // krok z malym niedoszacowaniem (bezpieczniej)
        if (t > 9.0) break;  // za daleko - poddaj sie
    }

    if (!hit) {
        FragColor = vec4(0.0, 0.0, 0.0, 0.0);  // pudlo = przezroczyste, widac scene spod spodu
        return;
    }

    // Trafienie: policz normalna metoda roznic skonczonych (probki +/- e w 3 osiach).
    vec3 p = rotate_y(ro + rd * t, time * 0.22);
    float e = 0.002;
    vec3 n = normalize(vec3(
        mandelbulb(p + vec3(e,0,0)) - mandelbulb(p - vec3(e,0,0)),
        mandelbulb(p + vec3(0,e,0)) - mandelbulb(p - vec3(0,e,0)),
        mandelbulb(p + vec3(0,0,e)) - mandelbulb(p - vec3(0,0,e))));
    vec3 light_dir = normalize(vec3(-0.45, 0.7, 0.55));  // kierunek swiatla
    float diffuse = max(dot(n, light_dir), 0.0);  // klasyczne rozproszone
    float rim = pow(1.0 - max(dot(-rd, n), 0.0), 2.5);  // poswiata na krawedziach
    float bands = 0.5 + 0.5 * sin(11.0 * t - time * 2.0 + p.y * 2.0);  // pregi na powierzchni
    vec3 base = mix(vec3(0.04, 0.18, 0.55), vec3(0.05, 0.95, 0.8), bands);
    vec3 color = base * (0.25 + 0.85 * diffuse) + vec3(0.45, 0.12, 0.9) * rim;
    FragColor = vec4(color, 0.96);  // prawie nieprzezroczyste
}
""".replace("STEP_COUNT_PLACEHOLDER", str(STEP_COUNT))


def _remove_previous():
    # Standardowy toggle: zdepnij handlery + timer poprzedniego uruchomienia.
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
    # Identyczne jak w 03: podaj time + rozmiar, narysuj quad, dopisz HUD.
    region = bpy.context.region
    if region is None:
        return
    shader = state["shader"]
    old_blend = gpu.state.blend_get()
    old_depth = gpu.state.depth_test_get()
    try:
        gpu.state.blend_set("ALPHA")  # musi byc ALPHA zeby pudla (alpha 0) przepuszczaly scene
        gpu.state.depth_test_set("NONE")
        shader.bind()
        shader.uniform_float("time", time.perf_counter() - state["started"])
        shader.uniform_float("viewportSize", (region.width, region.height))
        state["batch"].draw(shader)
    finally:
        gpu.state.blend_set(old_blend)
        gpu.state.depth_test_set(old_depth)

    # Napis z cieniem dla czytelnosci na jasnym fraktalu.
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
        blf.draw(0, "Nakladka ekranowa; obrot myszka nie rusza kamery shadera")
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
        print("Nakladka raymarch wylaczona (przelacznik). Uruchom znow zeby pokazac.")
        return
    if not hasattr(gpu.types, "GPUShaderCreateInfo"):
        raise RuntimeError("Ten przyklad potrzebuje GPUShaderCreateInfo (Blender 3.x+ z modulem GPU).")

    # Ten blok jest KOPIA z 03 - specjalnie, zeby pokazac ze Python sie nie zmienia.
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
    print("Nakladka raymarch dziala. Re-run wylacza.")


if __name__ == "__main__":
    main()
