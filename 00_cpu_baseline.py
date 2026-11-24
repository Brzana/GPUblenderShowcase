"""00 — CPU baseline: dlaczego w ogole potrzebujemy GPU?

KROK 00/6 — "Jaki problem rozwiazujemy?"
CEL: Zmierzyc czysta symulacje w Pythonie (bez rysowania), zeby w kroku 06
     miec liczbe do porownania: CPU vs GPU.
JAK POKAZAC: Text Editor > Open > Run Script, potem
  Window > Toggle System Console. Liczbe "ms per frame" przeczytaj na glos.
POJECIA: petla w Pythonie robi sie wolna przy wielu czasteczkach; GIL +
  narzut Pythona dominuja; rysowanie celowo NIE jest tu liczone.
SPROBUJ: zmien PARTICLE_COUNT na 5_000, uruchom ponownie — czas rosnie liniowo.
Nastepny: 01 rysuje na GPU nie dotykajac sceny w ogole.

Uruchom w Blenderze przez Text Editor > Run Script. Wynik pojawia sie
w konsoli. Ten skrypt nic nie tworzy i nic nie modyfikuje w scenie.
UWAGA: na chwile zawiesi UI (jedna synchroniczna petla pomiarowa).
"""

import math  # potrzebne do sin/cos/sqrt przy ukladaniu spirali i fizyce
import time  # stoper do mierzenia czasu (perf_counter ma wysoka dokladnosc)


# --- Ustawienia symulacji (zmien je na zajeciach, to dobry eksperyment) ---
PARTICLE_COUNT = 50_000  # ile czasteczek calkujemy w Pythonie
FRAME_COUNT = 24  # ile klatek mierzymy, potem liczymy srednia
DT = 1.0 / 60.0  # krok czasu: zakladamy 60 FPS, jak w grach
BOUND = 5.5  # scianki pudelka: jak czasteczka wyleci poza +-BOUND, odbija sie


def make_particles(count):
    # Uklada czasteczki w spirale na dysku (ladny start, deterministyczny).
    # Kazda czasteczka to lista: [x, y, vx, vy] czyli pozycja + predkosc.
    particles = []
    golden_angle = 2.399963229728653  # "zloty kat" - daje rownomierne rozlozenie punktow
    for i in range(count):
        # Pierwiastek ze (i+0.5)/count zeby gestosc byla rowna na calej powierzchni kola.
        radius = 4.0 * math.sqrt((i + 0.5) / count)
        angle = i * golden_angle  # kazda kolejna obrocona o ten sam kat
        x = radius * math.cos(angle)
        y = radius * math.sin(angle)
        # Poczatkowa predkosc styczna (prostopadla do promienia) - beda wirowac.
        particles.append([x, y, -0.15 * math.sin(angle), 0.15 * math.cos(angle)])
    return particles


def step_python(particles, dt):
    # Jeden krok fizyki - TO SAMO rownanie co w finale 06 na GPU (porownanie 1:1).
    # Robimy update "w miejscu" (p[0] = ...) zeby nie tworzyc nowych list
    # i mierzyc uczciwie sama matematyke, a nie alokacje pamieci.
    for p in particles:
        x, y, vx, vy = p
        # 1/r - im blizej srodka, tym mocniejszy wirowy "tornado force".
        # +0.2 zeby nie dzielic przez zero w samym srodku.
        inv_r = 1.0 / math.sqrt(x * x + y * y + 0.2)
        # ax, ay: skladowa wirowa (-y, x) + sciaganie do srodka (-x, -y) + opor (-v).
        ax = -y * inv_r * 0.45 - x * 0.08 - vx * 0.12
        ay = x * inv_r * 0.45 - y * 0.08 - vy * 0.12
        # Calka Eulera: najpierw predkosc, potem pozycja.
        vx += ax * dt
        vy += ay * dt
        x += vx * dt
        y += vy * dt
        # Odbicie od scianek: przytnij pozycje i odwroc predkosc.
        # (06 robi DOKLADNIE to samo w shaderze compute - porownaj!)
        if x < -BOUND or x > BOUND:
            x = min(BOUND, max(-BOUND, x))
            vx = -vx
        if y < -BOUND or y > BOUND:
            y = min(BOUND, max(-BOUND, y))
            vy = -vy
        p[0], p[1], p[2], p[3] = x, y, vx, vy
    return particles


def main():
    # 1. Zbuduj czasteczki raz.
    particles = make_particles(PARTICLE_COUNT)
    # 2. Zmierz czas N krokow pod rzad (bez rysowania!).
    start = time.perf_counter()
    for _ in range(FRAME_COUNT):
        step_python(particles, DT)
    elapsed = time.perf_counter() - start
    # 3. Policz sredni czas jednej klatki i teoretyczne FPS samej symulacji.
    ms_per_frame = elapsed * 1000.0 / FRAME_COUNT

    print("\n=== CPU baseline: czysty Python ===")
    print(f"Czasteczki: {PARTICLE_COUNT:,} | kroki: {FRAME_COUNT}")
    print(f"Sredni czas kroku: {ms_per_frame:.2f} ms")
    print(f"Teoretyczne FPS samej symulacji: {1000.0 / ms_per_frame:.1f}")
    print("Wynik NIE zawiera rysowania ani aktualizacji obiektow Blendera.")
    print("Porownaj z 06 (102,400 czasteczek na GPU, bez odczytu do RAM).")


if __name__ == "__main__":
    # Ten warunek znaczy: "uruchom main() tylko gdy puszczam plik, nie gdy importuje".
    main()
