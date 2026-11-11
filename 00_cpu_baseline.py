"""Punkt odniesienia: niewielki benchmark integracji czastek w czystym Pythonie.

Uruchom w Blenderze przez Text Editor > Run Script. Wynik pojawi sie w konsoli.
Skrypt nie tworzy ani nie modyfikuje obiektow sceny.
"""

import math
import time


PARTICLE_COUNT = 50_000
FRAME_COUNT = 24
DT = 1.0 / 60.0


def make_particles(count):
    # (x, y, vx, vy) -- deterministyczny rozklad spiralny.
    particles = []
    golden_angle = 2.399963229728653
    for i in range(count):
        radius = 4.0 * math.sqrt((i + 0.5) / count)
        angle = i * golden_angle
        x = radius * math.cos(angle)
        y = radius * math.sin(angle)
        particles.append((x, y, -0.15 * math.sin(angle), 0.15 * math.cos(angle)))
    return particles


def step_python(particles, dt):
    # Ten sam typ pracy co w przykladzie GPU: pole wirowe, opor i integracja.
    updated = []
    for x, y, vx, vy in particles:
        inv_r = 1.0 / math.sqrt(x * x + y * y + 0.2)
        ax = -y * inv_r * 0.45 - x * 0.08 - vx * 0.12
        ay =  x * inv_r * 0.45 - y * 0.08 - vy * 0.12
        vx += ax * dt
        vy += ay * dt
        x += vx * dt
        y += vy * dt
        if x < -5.5 or x > 5.5:
            vx = -vx
        if y < -5.5 or y > 5.5:
            vy = -vy
        updated.append((x, y, vx, vy))
    return updated


particles = make_particles(PARTICLE_COUNT)
start = time.perf_counter()
for _ in range(FRAME_COUNT):
    particles = step_python(particles, DT)
elapsed = time.perf_counter() - start
ms_per_frame = elapsed * 1000.0 / FRAME_COUNT

print("\n=== CPU baseline: czysty Python ===")
print(f"Czastek: {PARTICLE_COUNT:,} | krokow: {FRAME_COUNT}")
print(f"Sredni czas kroku: {ms_per_frame:.2f} ms")
print(f"Teoretyczne FPS samej symulacji: {1000.0 / ms_per_frame:.1f}")
print("Wynik nie obejmuje rysowania ani aktualizacji obiektow Blenderowych.\n")
