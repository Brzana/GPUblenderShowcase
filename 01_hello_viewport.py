"""01 — Hello Viewport: twoje pierwsze rysowanie na GPU (OD TEGO ZACZNIJ GPU).

KROK 01/6 — "Jak dziala skryptowanie GPU?"
CEL: Narysuj jeden trojkat w widoku 3D nie dodajac zadnego obiektu
     do sceny i zrozum 3-stopniowy wzorzec GPU.
POJECIA:
  1. draw_handler = "wolaj moja funkcje za kazdym razem gdy viewport sie przerysuje".
     POST_VIEW rysuje w swiecie 3D, POST_PIXEL rysuje HUD 2D na wierzchu.
  2. Gotowy shader + batch = najmniejszy program GPU.
     CPU wysyla 3 pozycje RAZ, GPU przerysowuje je co klatke za darmo.
  3. driver_namespace przechowuje uchwyty, zeby re-run skryptu go wylaczal.
SPROBUJ NA ZAJECIACH:
  - Uruchom, orbituj widokiem: trojkat stoi w miejscu w 3D.
  - Uruchom ponownie: znika (przelacznik). Uruchom znow zeby pokazac. 99 wylacza wszystko.
NASTEPNY: 02 pokazuje ten sam wzorzec na prawdziwych danych z mesha.
"""

import bpy  # dostep do sceny, okien, timerow i driver_namespace
import blf  # rysowanie tekstu 2D (HUD) na wierzchu viewportu
import gpu  # modul GPU Blendera: shadery, stan mieszania itp.
from gpu_extras.batch import batch_for_shader  # pomocnik: "z tych wierzcholkow zrob paczke do rysowania"


_KEY = "gpu_showcase_hello_v1"  # unikalna nazwa w schowku - po niej poznajemy "nasz" pokaz
# Slot HUD 0 (dol ekranu): tytul y=42, podtytul y=22. Inne demka uzywaja wyzszych slotow.


def _remove_previous():
    # Sprobuj wylaczyc poprzednie uruchomienie tego samego skryptu.
    # Zwraca True jesli cos wylaczylismy (czyli to byl re-run = przelacznik OFF).
    state = bpy.app.driver_namespace.pop(_KEY, None)
    if not state:
        return False  # nic nie dzialalo, czyli startujemy od nowa
    for handle in state.get("handles", ()):
        try:
            # Odpinamy funkcje rysujace od viewportu.
            bpy.types.SpaceView3D.draw_handler_remove(handle, "WINDOW")
        except (ReferenceError, ValueError, RuntimeError):
            pass  # okno moglo zniknac w miedzyczasie - ignorujemy
    return True


def _draw_3d():
    # Ta funkcja leci przy KAZDYM przerysowaniu viewportu. Zero ciezkiej matematyki -
    # tylko "narysuj to co GPU juz ma w pamieci".
    shader = _draw_3d.shader  # shader podpiety nizej jako atrybut funkcji (trik na przekazanie danych)
    batch = _draw_3d.batch  # paczka wierzcholkow podpieta tak samo
    shader.bind()  # wlacz ten program GPU ("teraz rysujemy tym")
    # Jednolity kolor RGBA dla calego trojkata. GPU wypelni nim kazdy piksel.
    shader.uniform_float("color", (0.15, 0.8, 1.0, 0.9))
    batch.draw(shader)  # faktyczne polecenie rysowania


def _draw_hud():
    # Napisy w rogu ekranu - to jest 2D, zawsze w tym samym miejscu ekranu.
    font_id = 0
    blf.size(font_id, 14)  # rozmiar czcionki
    blf.color(font_id, 0.35, 0.95, 1.0, 1.0)  # cyjan
    blf.position(font_id, 22, 42, 0)  # x=22, y=42 piksele od dolu
    blf.draw(font_id, "01 HELLO  |  jeden trojkat GPU, zero obiektow sceny")
    blf.color(font_id, 0.9, 0.92, 0.95, 0.9)  # jasnoszary podtytul
    blf.position(font_id, 22, 22, 0)
    blf.draw(font_id, "POST_VIEW = swiat 3D  |  uruchom ponownie zeby wylaczyc")


def _tag_redraw():
    # Popros wszystkie okna 3D o przerysowanie (inaczej obraz stoi w miejscu).
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
    # Najpierw sprawdz czy to re-run - jesli tak, to wlasnie wylaczylismy i koniec.
    if _remove_previous():
        _tag_redraw()  # odswiez zeby zniknal slad po trojkacie
        print("01 hello viewport wylaczony (przelacznik). Uruchom znow zeby pokazac.")
        return

    # KROK 1: opisz geometrie (CPU, raz).
    # Trzy punkty 3D. To jedyne dane jakie kiedykolwiek wyslemy na GPU.
    positions = (
        (0.0, 0.0, 0.0),
        (1.5, 0.0, 0.0),
        (0.75, 1.2, 0.0),
    )

    # KROK 2: wybierz gotowy program GPU.
    # UNIFORM_COLOR to wbudowany shader: pozycja wchodzi, plaski kolor wychodzi.
    # (Przed Blenderem 4.0 nazywal sie 3D_UNIFORM_COLOR.)
    # W tym kroku nie piszemy ani linijki GLSL.
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    batch = batch_for_shader(shader, "TRIS", {"pos": positions})  # TRIS = trojkaty

    # Przypnij shader i batch do funkcji rysujacej, zeby miala je co klatke.
    _draw_3d.shader = shader
    _draw_3d.batch = batch

    # KROK 3: popros Blendera zeby wolal nas przy kazdym rysowaniu.
    state = {"handles": []}
    state["handles"].append(bpy.types.SpaceView3D.draw_handler_add(
        _draw_3d, (), "WINDOW", "POST_VIEW"  # trojkat w swiecie 3D
    ))
    state["handles"].append(bpy.types.SpaceView3D.draw_handler_add(
        _draw_hud, (), "WINDOW", "POST_PIXEL"  # napis jako HUD 2D na wierzchu
    ))
    bpy.app.driver_namespace[_KEY] = state  # zapamietaj uchwyty do pozniejszego wylaczenia
    print("01 hello viewport dziala: jeden trojkat, zero obiektow sceny. Re-run wylacza.")


if __name__ == "__main__":
    main()
