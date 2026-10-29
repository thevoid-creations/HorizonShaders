# Horizon Aurora Lite 2.0

**Horizon Aurora** with the screen-space passes left out, for integrated
graphics, laptops and older GPUs. Two full-screen passes instead of six.

| Stage | File | What changes |
| --- | --- | --- |
| Sky | `sky.wgsl` | Deeper noon blue, golden light around a low sun, bluer evenings, cold clean nights |
| Terrain | `material.wgsl` | Softer shading on lit faces, richer greens, deeper water, moving ripple highlights |
| Air | `post/atmosphere.wgsl` | Aerial perspective: distant land takes the colour of the sky in front of it |
| Grade | `post/grade.wgsl` | Highlight roll-off, gentle contrast, saturation, orange correction, split toning, readable darks, vignette, dither |

## What you give up

- **Water reflections** (screen-space ray march)
- **Contact shading** (SSAO from depth) — the biggest visual difference in 2.0
- **Volumetric sun shafts**
- **Bloom**

The colour, the sky, the terrain treatment and the water's own ripples and
sparkle are identical, because they cost nothing extra: they live in the stage
shaders Aurora runs anyway.

## Installing

Exactly like Horizon Aurora: `shaderpacks/`, then **Options → Horizon Settings →
Shader Packs**. See [docs/INSTALL.md](../../docs/INSTALL.md).

`[budget] gpu_ms = 0.9`. Manifest `schema = 1`, shader API `api = "0.1"`.

## Tuning

No options are declared — Horizon builds every pack with its options at their
defaults, so a declared option would do nothing. The look lives in
`common.wgsl` as named constants (Aurora's file with the screen-space block
removed, so nothing in it is unused) and reloads when you save it:

```wgsl
const AURORA_SATURATION: f32 = 1.085;
const AURORA_SKY_DEPTH: f32 = 0.52;
const AURORA_WATER: f32 = 0.70;
const AURORA_WAVES: f32 = 1.0;      // 0 = still water
const AURORA_VIGNETTE: f32 = 0.11;
```

Licensed under the MIT License; see [LICENSE](LICENSE).
