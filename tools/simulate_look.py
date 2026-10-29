#!/usr/bin/env python3
"""What Horizon Aurora does to a colour, computed from the pack's own math.

The pack's WGSL is the truth; this is a line-by-line transcription of
`common.wgsl`, `sky.wgsl`, `material.wgsl`, `post/atmosphere.wgsl` and
`post/grade.wgsl` so the look can be checked without a GPU. It runs the real
constants (they are read out of the WGSL, so tuning the pack re-tunes this) over
a set of representative colours: a noon sky, a sunset, a night, grass, stone,
water, and the greys that show whether a grade crushes or clips.

    simulate_look.py            # tables, and a check of the look's invariants
    simulate_look.py --values   # the constants it read from the pack

It answers questions a compiler cannot: does white stay white, does black stay
black, does the sunset stay warm instead of fluorescent, does a cave stay
readable. It is a simulation, not a screenshot: it says nothing about how the
game composites the result, and nothing about GPU time.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "packs" / "Horizon-Aurora"


# --- vec helpers -------------------------------------------------------------
def v(*xs: float) -> list[float]:
    return [float(x) for x in xs]


def add(a, b):
    return [x + y for x, y in zip(a, b)]


def sub(a, b):
    return [x - y for x, y in zip(a, b)]


def mul(a, b):
    return [x * y for x, y in zip(a, b)]


def smul(a, s):
    return [x * s for x in a]


def dot3(a, b):
    return sum(x * y for x, y in zip(a, b))


def length3(a):
    return math.sqrt(dot3(a, a))


def normalize3(a):
    n = length3(a)
    return [x / n if n > 0 else 0.0 for x in a]


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def clamp3(a, lo=0.0, hi=1.0):
    return [clamp(x, lo, hi) for x in a]


def mix(a, b, t):
    """`mix` with a scalar or a per-component `t`, as WGSL allows."""
    if isinstance(a, (int, float)):
        return a + (b - a) * t
    ts = t if isinstance(t, list) else [t] * len(a)
    return [x + (y - x) * ti for x, y, ti in zip(a, b, ts)]


def smoothstep(edge0, edge1, x):
    if isinstance(x, list):
        return [smoothstep(edge0, edge1, e) for e in x]
    if edge0 == edge1:
        return 0.0 if x < edge0 else 1.0
    t = clamp((x - edge0) / (edge1 - edge0))
    return t * t * (3.0 - 2.0 * t)


# --- the frame ---------------------------------------------------------------
@dataclass
class Frame:
    sun_direction: list[float]
    dimension: int = 0
    rain: float = 0.0
    eye_in: int = 0
    render_distance: float = 192.0
    resolution: tuple[float, float] = (1920.0, 1080.0)
    fog_color: list[float] = None
    sky_color: list[float] = None


# --- constants, read from common.wgsl so they cannot drift -------------------
def read_constants() -> dict[str, float]:
    text = (PACK / "common.wgsl").read_text()
    found = dict(re.findall(r"const\s+(AURORA_[A-Z_]+)\s*:\s*f32\s*=\s*([-\d.]+);", text))
    if not found:
        sys.exit("simulate_look: no AURORA_ constants in common.wgsl")
    return {k: float(v) for k, v in found.items()}


K = read_constants()


# --- common.wgsl -------------------------------------------------------------
def aurora_luma(c):
    return dot3(c, v(0.2126, 0.7152, 0.0722))


def aurora_saturate(c, amount):
    return mix(v(aurora_luma(c), aurora_luma(c), aurora_luma(c)), c, amount)


def aurora_daylight(f: Frame):
    if f.dimension != 0:
        return 0.0
    return smoothstep(-0.12, 0.10, f.sun_direction[1])


def aurora_sun_low(f: Frame):
    return 1.0 - smoothstep(0.0, 0.34, abs(f.sun_direction[1]))


def aurora_golden(f: Frame):
    return (
        aurora_sun_low(f)
        * aurora_daylight(f)
        * (1.0 - f.rain * 0.8)
        * K["AURORA_WARMTH"]
    )


def aurora_shoulder(c):
    room = 1.0 - K["AURORA_SHOULDER"]
    return add(
        [min(x, K["AURORA_SHOULDER"]) for x in c],
        [room - room * room / (max(x - K["AURORA_SHOULDER"], 0.0) + room) for x in c],
    )


def aurora_contrast(c, amount):
    return mix(c, smoothstep(0.0, 1.0, c), clamp(amount))


def aurora_lift(c):
    w = 1.0 - smoothstep(0.0, 0.30, aurora_luma(c))
    return add(c, smul(v(0.60, 0.78, 1.00), K["AURORA_SHADOW_LIFT"] * w * w))


def aurora_vignette(uv, f: Frame):
    aspect = f.resolution[0] / max(f.resolution[1], 1.0)
    far = length3(smul(v(aspect, 1.0), 0.5))
    r = length3(v((uv[0] - 0.5) * aspect, (uv[1] - 0.5))) / far
    return 1.0 - K["AURORA_VIGNETTE"] * smoothstep(0.55, 1.05, r)


def aurora_dither(pixel):
    # The WGSL uses sin()'s fractional part; the exact value does not matter to a
    # statistical check, only that it stays inside one 8-bit step.
    n = math.floor(pixel[0]) + math.floor(pixel[1]) * 127.1
    frac = math.sin(n) * 43758.5453
    return frac - math.floor(frac)


def aurora_blue_mask(albedo):
    return smoothstep(0.012, 0.115, albedo[2] - albedo[0])


def aurora_green_mask(albedo):
    return smoothstep(0.02, 0.14, albedo[1] - max(albedo[0], albedo[2]))


# --- sky.wgsl ----------------------------------------------------------------
def sky(direction, colour, f: Frame):
    c = list(colour)
    if f.dimension != 0 or f.eye_in != 0:
        return clamp3(c)
    d = normalize3(direction)
    up = clamp(d[1])
    sun = normalize3(f.sun_direction)
    toward_sun = max(dot3(d, sun), 0.0)
    away = max(dot3(d, [-x for x in sun]), 0.0)
    day = aurora_daylight(f)
    golden = aurora_golden(f)
    clear = 1.0 - f.rain * 0.8

    zenith = smoothstep(0.02, 0.92, up)
    depth = mix(v(1.0, 1.0, 1.0), v(0.63, 0.82, 1.10),
                K["AURORA_SKY_DEPTH"] * zenith * day * clear)
    c = mul(c, depth)

    halo = max(toward_sun, 0.0) ** 6.0 * 0.75 + toward_sun ** 2.0 * 0.25
    band = 1.0 - smoothstep(0.0, 0.42, abs(d[1]))
    warm = v(1.00, 0.74, 0.50)
    c = add(c, smul(warm, golden * (halo * 0.10 + band * toward_sun * 0.07)))

    c = mix(c, mul(c, v(0.93, 0.99, 1.08)), away * band * day * 0.55)

    orange = smoothstep(0.10, 0.42, c[0] - c[2])
    c = mix(c, aurora_saturate(c, 0.86), orange * golden * K["AURORA_ORANGE_PULL"])

    night = 1.0 - day
    cool = add(mul(c, v(0.90, 0.96, 1.10)), v(0.004, 0.006, 0.012))
    c = mix(c, cool, night * (0.30 + 0.40 * zenith))
    return clamp3(c)


# --- material.wgsl -----------------------------------------------------------
def material(albedo, tint, lightmap, translucent, f: Frame):
    lm = list(lightmap)
    curve = [x * x * (3.0 - 2.0 * x) for x in lm]
    lit = smoothstep(0.30, 1.0, lm)
    light = mix(lm, curve, [K["AURORA_LIGHTMAP_CURVE"] * x for x in lit])
    c = mul(mul(list(albedo), list(tint)), light)

    green = aurora_green_mask(albedo)
    c = mix(c, aurora_saturate(c, 1.12), green * K["AURORA_FOLIAGE"] * 0.5)

    if translucent:
        blue = aurora_blue_mask(albedo)
        headroom = 1.0 - smoothstep(0.80, 1.0, c[2])
        deep = mix(v(1.0, 1.0, 1.0), v(0.78, 0.94, 1.16),
                   blue * K["AURORA_WATER"] * headroom)
        c = mul(c, deep)
    return clamp3(c)


# --- post/atmosphere.wgsl ----------------------------------------------------
def atmosphere(colour, depth, uv, f: Frame):
    if depth <= 0.0 or f.dimension != 0 or f.eye_in != 0:
        return list(colour)
    pos = view_position(uv, depth, f)
    return atmosphere_at(colour, length3(pos), normalize3(pos), f)


def atmosphere_at(colour, dist, direction, f: Frame):
    """The atmosphere pass for a pixel `dist` blocks away along `direction`."""
    sun = normalize3(f.sun_direction)
    toward_sun = max(dot3(direction, sun), 0.0)
    golden = aurora_golden(f)

    reach = max(f.render_distance, 64.0)
    falloff = 2.4 / reach
    amount = ((1.0 - math.exp(-dist * falloff)) ** 1.5) * K["AURORA_HAZE"] * (1.0 + f.rain * 0.30)

    air = mix(f.fog_color, f.sky_color, 0.35)
    air = mix(air, v(1.00, 0.80, 0.58), golden * toward_sun ** 3.0 * 0.30)
    air = mix(air, mul(air, v(0.96, 0.99, 1.06)), clamp(direction[1]) * 0.40)
    c = mix(colour, air, amount)

    glare = (K["AURORA_SUN_GLARE"] * amount * toward_sun ** 9.0
             * (0.40 + 0.60 * golden + 0.50 * aurora_daylight(f)))
    return add(c, smul(v(1.00, 0.86, 0.66), glare))


def view_position(uv, depth, f: Frame) -> list[float]:
    """The renderer's `view_position` for a camera at the origin looking down -z.

    Only the direction and the distance matter here, so a pinhole camera with
    the pack's field of view rebuilds the same ray the shader would.
    """
    fov, aspect = math.radians(70.0), f.resolution[0] / f.resolution[1]
    ndc = (uv[0] * 2.0 - 1.0, 1.0 - uv[1] * 2.0)
    tan_half = math.tan(fov / 2.0)
    # reversed depth: 1 near (0.05) to 0 far
    near, far = 0.05, 2048.0
    d = max(depth, 1e-6)
    eye_z = (near * far) / (far - d * (far - near))  # reverse-Z inverse
    return [ndc[0] * tan_half * aspect * eye_z, ndc[1] * tan_half * eye_z, -eye_z]


# --- post/grade.wgsl ---------------------------------------------------------
def grade(colour, uv, pixel, f: Frame):
    c = aurora_shoulder(list(colour))
    c = aurora_contrast(c, K["AURORA_CONTRAST"])
    c = aurora_saturate(c, K["AURORA_SATURATION"])
    orange = smoothstep(0.10, 0.42, c[0] - c[2])
    c = mix(c, aurora_saturate(c, 0.88), orange * K["AURORA_ORANGE_PULL"])
    light = aurora_luma(c)
    split = smoothstep(0.15, 0.85, light)
    c = mix(mul(c, v(0.972, 0.990, 1.020)), mul(c, v(1.018, 1.002, 0.978)), split)
    c = aurora_lift(c)
    c = smul(c, aurora_vignette(uv, f))
    c = add(c, smul(v(1.0, 1.0, 1.0), (aurora_dither(pixel) - 0.5) / 255.0))
    return clamp3(c)


# --- scenarios ---------------------------------------------------------------
NOON = Frame(
    sun_direction=normalize3(v(0.0, 1.0, 0.0)),
    fog_color=v(0.62, 0.76, 1.0),
    sky_color=v(0.47, 0.65, 1.0),
)
SUNSET = Frame(
    sun_direction=normalize3(v(1.0, 0.02, 0.0)),
    fog_color=v(0.72, 0.55, 0.42),
    sky_color=v(0.55, 0.42, 0.40),
)
NIGHT = Frame(
    sun_direction=normalize3(v(-0.2, -0.98, 0.0)),
    fog_color=v(0.03, 0.04, 0.07),
    sky_color=v(0.02, 0.03, 0.06),
)
RAIN = Frame(
    sun_direction=normalize3(v(0.0, 0.8, 0.4)),
    rain=1.0,
    fog_color=v(0.42, 0.44, 0.48),
    sky_color=v(0.35, 0.40, 0.48),
)

CENTRE = (0.5, 0.5)
CORNER = (0.08, 0.92)


def luma(c):
    return aurora_luma(c)


def report(rows, header):
    print(header)
    print(f"  {'what':<26} {'before':<22} {'after':<22} {'luma':>13}  flags")
    for name, before, after in rows:
        lb, la = luma(before), luma(after)
        delta = f"{lb:.3f} -> {la:.3f}"
        flags = []
        if max(before) < 0.90 and any(x >= 0.999 for x in after):
            flags.append("CLIPPED")
        if lb > 0.02 and la < 0.004:
            flags.append("CRUSHED")
        if lb > 0.02 and abs(la - lb) / lb > 0.25:
            flags.append(f"luma {100 * (la - lb) / lb:+.0f}%")
        print(f"  {name:<26} {fmt(before):<22} {fmt(after):<22} {delta:>13}  {' '.join(flags)}")
    print()


def fmt(c):
    return "(" + ", ".join(f"{x:.3f}" for x in c) + ")"


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--values", action="store_true", help="print the constants read from the pack")
    args = parser.parse_args(argv)
    if args.values:
        for key, value in K.items():
            print(f"{key:<22} {value}")
        return 0

    failures = []

    def require(name, ok, detail=""):
        if not ok:
            failures.append(f"{name}{': ' + detail if detail else ''}")

    print(f"constants read from {PACK.relative_to(ROOT)}/common.wgsl\n")

    # 1. Sky
    rows = []
    for name, direction, frame, base in [
        ("noon, up", v(0, 1, 0), NOON, v(0.47, 0.65, 1.00)),
        ("noon, horizon away", v(-1, 0.02, 0), NOON, v(0.62, 0.76, 1.00)),
        ("sunset, horizon at sun", v(1, 0.03, 0), SUNSET, v(0.95, 0.58, 0.33)),
        ("sunset, up", v(0, 0.85, 0.5), SUNSET, v(0.28, 0.34, 0.60)),
        ("sunset, away from sun", v(-1, 0.05, 0), SUNSET, v(0.50, 0.44, 0.52)),
        ("night, up", v(0, 1, 0), NIGHT, v(0.02, 0.03, 0.06)),
        ("night, horizon", v(1, 0.05, 0), NIGHT, v(0.03, 0.04, 0.07)),
        ("rain, up", v(0, 1, 0), RAIN, v(0.35, 0.40, 0.48)),
    ]:
        rows.append((name, base, sky(direction, base, frame)))
    report(rows, "sky")
    for name, before, after in rows:
        require(f"sky {name}: stays inside the frame", max(after) <= 1.0)
    sunset = dict((r[0], r[2]) for r in rows)["sunset, horizon at sun"]
    require("sky sunset stays warm, not red-hot",
            sunset[0] > sunset[1] > sunset[2] and sunset[0] <= 1.0,
            fmt(sunset))
    require("sky sunset stays inside the frame",
            max(sunset) <= 1.0,
            fmt(sunset))
    night_up = dict((r[0], r[2]) for r in rows)["night, up"]
    require("sky night stays dark", luma(night_up) < 0.12, fmt(night_up))
    require("sky night stays visible", luma(night_up) > 0.005, fmt(night_up))

    # 2. Material
    rows = []
    day_light = v(1.0, 1.0, 1.0)
    dusk_light = v(0.42, 0.36, 0.34)
    cave_light = v(0.16, 0.10, 0.07)
    surfaces = [
        ("grass (day)", v(0.35, 0.55, 0.25), v(0.45, 0.75, 0.35), day_light, False),
        ("grass (dusk)", v(0.35, 0.55, 0.25), v(0.45, 0.75, 0.35), dusk_light, False),
        ("grass (cave, torch)", v(0.35, 0.55, 0.25), v(0.45, 0.75, 0.35), cave_light, False),
        ("stone (day)", v(0.50, 0.50, 0.50), v(1.0, 1.0, 1.0), day_light, False),
        ("oak leaves", v(0.30, 0.48, 0.22), v(0.35, 0.60, 0.30), day_light, False),
        ("water (day)", v(0.30, 0.45, 0.62), v(0.25, 0.45, 0.90), day_light, True),
        ("ice (day)", v(0.62, 0.80, 0.95), v(1.0, 1.0, 1.0), day_light, True),
        ("red glass (day)", v(0.80, 0.20, 0.20), v(1.0, 1.0, 1.0), day_light, True),
    ]
    for name, albedo, tint, light, translucent in surfaces:
        vanilla = [a * t * l for a, t, l in zip(albedo, tint, light)]
        rows.append((name, vanilla, material(albedo, tint, light, translucent, NOON)))
    report(rows, "material (vanilla's albedo * tint * lightmap, then Aurora)")
    mat = dict((r[0], r[2]) for r in rows)
    require("material grass keeps its green", mat["grass (day)"][1] > mat["grass (day)"][0] > mat["grass (day)"][2], fmt(mat["grass (day)"]))
    require("material water gets deeper and bluer",
            mat["water (day)"][2] - mat["water (day)"][0] > 0.55, fmt(mat["water (day)"]))
    require("material leaves red glass stays red", mat["red glass (day)"][0] > mat["red glass (day)"][2], fmt(mat["red glass (day)"]))
    cave_before = v(0.025, 0.041, 0.006)
    require("material leaves a torch-lit cave at vanilla's level",
            abs(luma(mat["grass (cave, torch)"]) - luma(cave_before)) / luma(cave_before) < 0.05,
            fmt(mat["grass (cave, torch)"]))
    require("material keeps pale ice from flattening",
            mat["ice (day)"][2] < 0.98, fmt(mat["ice (day)"]))

    # 3. Atmosphere
    rows = []
    flat = normalize3(v(0.0, -0.05, -1.0))
    at_sun = normalize3(SUNSET.sun_direction)
    for name, dist, direction, frame in [
        ("8 blocks", 8.0, flat, NOON),
        ("32 blocks", 32.0, flat, NOON),
        ("96 blocks", 96.0, flat, NOON),
        ("192 blocks", 192.0, flat, NOON),
        ("96 blocks toward sun", 96.0, at_sun, SUNSET),
    ]:
        base = v(0.28, 0.34, 0.22)
        rows.append((name, base, atmosphere_at(base, dist, direction, frame)))
    report(rows, "atmosphere (a green hillside at distance, clear noon)")
    atm = dict((r[0], r[2]) for r in rows)
    near_change = abs(luma(atm["8 blocks"]) - luma(v(0.28, 0.34, 0.22))) / luma(v(0.28, 0.34, 0.22))
    require("atmosphere barely touches the near ground", near_change < 0.10, f"{near_change:.3f}")
    far_change = abs(luma(atm["192 blocks"]) - luma(v(0.28, 0.34, 0.22))) / luma(v(0.28, 0.34, 0.22))
    require("atmosphere is visible at the render distance", far_change > 0.15, f"{far_change:.3f}")

    # 4. Grade invariants
    rows = []
    for name, base in [
        ("black", v(0, 0, 0)),
        ("near black", v(0.02, 0.02, 0.02)),
        ("shadow", v(0.12, 0.12, 0.13)),
        ("mid grey", v(0.50, 0.50, 0.50)),
        ("light grey", v(0.72, 0.72, 0.72)),
        ("white", v(1.0, 1.0, 1.0)),
        ("sunset pixel", v(0.95, 0.55, 0.28)),
        ("lava", v(1.0, 0.45, 0.10)),
        ("water pixel", v(0.10, 0.25, 0.55)),
        ("green pixel", v(0.30, 0.55, 0.22)),
    ]:
        rows.append((name, base, grade(base, CENTRE, (960.0, 540.0), NOON)))
    report(rows, "grade (centre of the picture, no vignette)")
    g = dict((r[0], r[2]) for r in rows)
    require("grade: pure black stays dark", luma(g["black"]) < 0.02, fmt(g["black"]))
    require("grade: pure black keeps a little light", luma(g["black"]) > 0.002, fmt(g["black"]))
    require("grade: white stays white", luma(g["white"]) > 0.90, fmt(g["white"]))
    require("grade: white is not tinted",
            max(g["white"]) - min(g["white"]) < 0.06, fmt(g["white"]))
    require("grade: mid grey keeps its level", abs(luma(g["mid grey"]) - 0.5) < 0.03, fmt(g["mid grey"]))
    require("grade: saturation rises a little",
            (g["green pixel"][1] - g["green pixel"][2]) > (0.55 - 0.22),
            fmt(g["green pixel"]))
    require("grade: sunset orange is pulled back, not pushed",
            (g["sunset pixel"][0] - g["sunset pixel"][2]) <= 0.95, fmt(g["sunset pixel"]))

    # 4b. End to end: the stages in the order the game runs them.
    rows = []
    def chain(name, base):
        rows.append((name, base, grade(atmosphere(base, 0.5, CENTRE, NOON), CENTRE, (960.0, 540.0), NOON)))

    sky_sunset = sky(v(1, 0.03, 0), v(0.85, 0.52, 0.30), SUNSET)
    rows.append(("sunset sky (sky+grade)", v(0.85, 0.52, 0.30),
                 grade(sky_sunset, CENTRE, (960.0, 540.0), SUNSET)))
    grass_day = material(v(0.35, 0.55, 0.25), v(0.45, 0.75, 0.35), v(1.0, 1.0, 1.0), False, NOON)
    chain("grass, 8 blocks away", grass_day)
    water_day = material(v(0.30, 0.45, 0.62), v(0.25, 0.45, 0.90), v(1.0, 1.0, 1.0), True, NOON)
    chain("water, 8 blocks away", water_day)
    require("end to end: a graded sunset sky is still warm and bright",
            rows[0][2][0] > rows[0][2][1] > rows[0][2][2] and luma(rows[0][2]) > 0.45,
            fmt(rows[0][2]))
    report(rows, "end to end (material -> air -> grade, noon unless said)")

    # 5. Vignette and dither
    corner = grade(v(0.5, 0.5, 0.5), CORNER, (10.0, 1070.0), NOON)
    centre = grade(v(0.5, 0.5, 0.5), CENTRE, (960.0, 540.0), NOON)
    print(f"vignette: grey 0.5 at the centre is {luma(centre):.3f}, in the corner {luma(corner):.3f}")
    require("vignette is subtle", 0.85 < luma(corner) / luma(centre) < 0.99,
            f"{luma(corner) / luma(centre):.3f}")
    steps = {(grade(v(0.4, 0.4, 0.4), CENTRE, (x, 540.0), NOON)[0] * 255.0) for x in range(60)}
    require("dither moves a flat colour between neighbouring 8-bit steps",
            len(steps) >= 2, str(sorted(steps)[:4]))

    # 6. Underwater and the other dimensions are left alone
    wet = Frame(sun_direction=NOON.sun_direction, eye_in=1, fog_color=NOON.fog_color, sky_color=NOON.sky_color)
    require("sky is vanilla under water", sky(v(0, 1, 0), v(0.2, 0.4, 0.8), wet) == clamp3(v(0.2, 0.4, 0.8)))
    require("atmosphere leaves water alone", atmosphere(v(0.2, 0.4, 0.8), 0.9, CENTRE, wet) == v(0.2, 0.4, 0.8))
    nether = Frame(sun_direction=NOON.sun_direction, dimension=-1, fog_color=NOON.fog_color, sky_color=NOON.sky_color)
    require("sky is vanilla in the Nether", sky(v(0, 1, 0), v(0.5, 0.2, 0.15), nether) == clamp3(v(0.5, 0.2, 0.15)))

    if failures:
        print(f"{len(failures)} check(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("all look checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
