"""00 — CPU baseline: why bother with the GPU?

LECTURE STEP 0/6 — "What problem are we solving?"
GOAL: Measure pure-Python particle integration (no drawing) so the
      GPU payoff in step 06 has a number attached to it.
HOW TO PRESENT: Text Editor > Open > Run Script, then
  Window > Toggle System Console. Read the "ms per frame" line aloud.
CONCEPTS: per-frame CPU loop cost grows with particle count; GIL +
  Python overhead dominate; drawing is NOT included here on purpose.
TRY: Lower PARTICLE_COUNT to 5_000, re-run — roughly linear scaling.
NEXT: 01 draws on the GPU without touching the scene at all.

Run in Blender via Text Editor > Run Script. Output appears in the
console. This script creates and modifies no scene objects.
NOTE: it blocks the UI briefly while measuring (one synchronous loop).
"""

import math
import time


PARTICLE_COUNT = 50_000
FRAME_COUNT = 24
DT = 1.0 / 60.0
BOUND = 5.5


def make_particles(count):
    # (x, y, vx, vy) — deterministic spiral layout.
    particles = []
    golden_angle = 2.399963229728653
    for i in range(count):
        radius = 4.0 * math.sqrt((i + 0.5) / count)
        angle = i * golden_angle
        x = radius * math.cos(angle)
        y = radius * math.sin(angle)
        particles.append([x, y, -0.15 * math.sin(angle), 0.15 * math.cos(angle)])
    return particles


def step_python(particles, dt):
    # Same force field as the 06 GPU demo: swirl + drag + integration.
    # Updated in place to avoid per-frame list allocation (fairer timing).
    # Bounce matches 06: clamp position, then flip velocity.
    for p in particles:
        x, y, vx, vy = p
        inv_r = 1.0 / math.sqrt(x * x + y * y + 0.2)
        ax = -y * inv_r * 0.45 - x * 0.08 - vx * 0.12
        ay = x * inv_r * 0.45 - y * 0.08 - vy * 0.12
        vx += ax * dt
        vy += ay * dt
        x += vx * dt
        y += vy * dt
        if x < -BOUND or x > BOUND:
            x = min(BOUND, max(-BOUND, x))
            vx = -vx
        if y < -BOUND or y > BOUND:
            y = min(BOUND, max(-BOUND, y))
            vy = -vy
        p[0], p[1], p[2], p[3] = x, y, vx, vy
    return particles


def main():
    particles = make_particles(PARTICLE_COUNT)
    start = time.perf_counter()
    for _ in range(FRAME_COUNT):
        step_python(particles, DT)
    elapsed = time.perf_counter() - start
    ms_per_frame = elapsed * 1000.0 / FRAME_COUNT

    print("\n=== CPU baseline: pure Python ===")
    print(f"Particles: {PARTICLE_COUNT:,} | steps: {FRAME_COUNT}")
    print(f"Average step time: {ms_per_frame:.2f} ms")
    print(f"Theoretical FPS of simulation alone: {1000.0 / ms_per_frame:.1f}")
    print("Result excludes drawing and Blender object updates.")
    print("Compare with 06 (102,400 particles on GPU, no readback).")


if __name__ == "__main__":
    main()
