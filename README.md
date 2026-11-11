# Blender GPU Showcase

Krótki zestaw demonstracyjny: viewport draw handlers, własne shadery GLSL,
compute shader oraz tekstura offscreen. Skrypty nie dodają geometrii cząstek do
sceny ani nie modyfikują siatek.

## Wymagania i uruchomienie

- Zalecany Blender **4.5+** z backendem GPU obsługującym compute. Compute API
  zależy od wersji Blendera, sterownika i backendu; jeśli `gpu.compute` nie jest
  dostępne, pozostałe przykłady nadal można uruchamiać osobno.
- Otwórz plik `.py` w Blenderze: **Scripting > Text Editor > Open > Run Script**.
- Najpierw uruchom `01_viewport_normal_overlay.py` z aktywnym obiektem Mesh.
  Kolejne przykłady uruchamiaj osobno; ponowne uruchomienie tego samego skryptu
  usuwa jego poprzednie draw handlery i timer.
- `00_cpu_baseline.py` wypisuje pomiar do konsoli systemowej (Windows:
  **Window > Toggle System Console**). Nie tworzy obiektów.

## Kolejność prezentacji

1. **CPU baseline** — uruchom `00_cpu_baseline.py`, pokaż czas aktualizacji
   50 tys. stanów cząstek w Pythonie. To pomiar obliczeń, bez rysowania.
2. **Overlay** — zaznacz siatkę i uruchom `01_viewport_normal_overlay.py`.
   Pole przepływu i strzałki normalnych są jedną paczką GPU; nie pojawiają się
   w Outlinerze.
3. **Custom GLSL** — `02_viewport_raymarch.py` rysuje animowany Mandelbulb
   bezpośrednio jako overlay ekranowy. To raymarch shader, nie materiał ani
   pełny post-process renderu sceny.
4. **Offscreen** — `04_offscreen_hud.py` renderuje animowaną teksturę do
   `GPUOffScreen`, a potem wyświetla ją w HUD bez kopiowania pikseli do CPU.
5. **Compute** — `03_compute_particle_flow.py` symuluje 102 400 cząstek
   w compute shaderze i pobiera pozycje w vertex shaderze z tekstury.

### Porównanie backendów

Uruchom dwie osobne instancje Blendera i w każdej odtwórz ten sam przykład:

```text
blender --gpu-backend opengl
blender --gpu-backend vulkan
```

Dostępność backendu zależy od kompilacji Blendera. Wersja z Metalem wymaga
kompilacji obsługującej Metal; sprawdź `blender --help` na maszynie pokazowej.

## Uczciwe zastrzeżenia techniczne

- W aktualnym publicznym Python API Blendera dostępny jest `gpu.compute` i
  zapis/odczyt obrazów w compute shaderach; `gpu.types.GPUStorageBuf` nie jest
  standardowym publicznym typem. Dlatego demo cząstek używa dwóch tekstur
  `RGBA32F` (ping-pong), a nie SSBO. Początkowe stany i stałe UV-y są wysyłane
  z CPU tylko raz; po inicjalizacji pozycje nie wracają do RAM.
- 102 400 cząstek to liczba stanów symulacji, nie gwarancja określonego FPS.
  Wynik zależy m.in. od GPU, sterownika, rozdzielczości viewportu i backendu.
- Blender nie gwarantuje identycznego wsparcia funkcji compute na wszystkich
  platformach i wersjach. Najpierw sprawdź demo na docelowej maszynie; dostępność
  OpenGL/Vulkan/Metal zależy od konkretnej kompilacji i sterowników.
- Skrypty nie obiecują „60+ FPS” — pokazuj licznik FPS/Profiler Blenderowy na
  docelowym sprzęcie i porównuj ten sam viewport oraz ustawienia.

## Zatrzymanie

Uruchom ponownie ten sam plik, by usunąć jego handler/timer. Możesz też zamknąć
Blendera; zasoby GPU skryptów są zwalniane przy zamykaniu.
