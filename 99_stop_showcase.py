"""Wylacza wszystkie demka GPU (01-06).

Uruchom gdy teksty HUD na siebie nachodza - np. po odpaleniu kilku dem naraz.
Pojedyncze demo tez wylaczysz re-runem tego samego pliku, ale ten skrypt czysci wszystko.
00 nie ma handlera viewportu, wiec nie ma tu nic do czyszczenia dla niego.
"""

import bpy


# Wszystkie klucze ze schowka driver_namespace - po jednym na kazde demo 01-06.
_KEYS = (
    "gpu_showcase_hello_v1",  # 01 trojkat
    "gpu_showcase_normal_overlay_v1",  # 02 nakladka na mesh
    "gpu_showcase_shader_toy_v1",  # 03 gradient
    "gpu_showcase_raymarch_v1",  # 04 mandelbulb
    "gpu_showcase_offscreen_v1",  # 05 offscreen
    "gpu_showcase_compute_particles_v1",  # 06 compute
)


def _stop_one(key):
    # Wylacz jedno demo po kluczu. Zwraca True jesli cos faktycznie dzialalo.
    state = bpy.app.driver_namespace.pop(key, None)  # wyjmij ze schowka (pop = pobierz i usun)
    if not state:
        return False  # to demo nie dzialalo
    handles = []
    if isinstance(state, dict):
        # 02 w starszej wersji uzywalo view_handle/hud_handle;
        # 01/03/04/05/06 uzywaja listy "handles". Obslugujemy oba dla bezpieczenstwa.
        for single in ("view_handle", "hud_handle"):
            handle = state.get(single)
            if handle is not None:
                handles.append(handle)
        listed = state.get("handles")
        if isinstance(listed, (list, tuple)):
            handles.extend(listed)
        # Wylacz timer animacji zeby nie prosil o redraw po smierci demka.
        timer = state.get("timer")
        if timer is not None:
            try:
                if bpy.app.timers.is_registered(timer):
                    bpy.app.timers.unregister(timer)
            except (ReferenceError, ValueError, RuntimeError):
                pass
        # Zwolnij offscreen z 05 (ma jawna metode free()).
        offscreen = state.get("offscreen")
        if offscreen is not None:
            try:
                offscreen.free()
            except (ReferenceError, RuntimeError):
                pass
        # 06 trzyma tekstury ping-pong; puszczenie referencji zwalnia pamiec GPU.
        for tex in state.get("textures", ()):
            try:
                del tex
            except (ReferenceError, RuntimeError):
                pass
    # Odepnij funkcje rysujace od viewportu.
    for handle in handles:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(handle, "WINDOW")
        except (ReferenceError, ValueError, RuntimeError):
            pass
    return True


def main():
    # Wylacz wszystko po kolei i zbierz co faktycznie dzialalo.
    stopped = [key for key in _KEYS if _stop_one(key)]

    # Wymus przerysowanie zeby nie zostaly "duchy" po nakladkach.
    try:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()
    except (AttributeError, ReferenceError, RuntimeError):
        pass

    print("Wylaczono: " + (", ".join(stopped) if stopped else "nic nie dzialalo"))


if __name__ == "__main__":
    main()
