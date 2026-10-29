# Horizon Aurora 2.0

A shader pack for [Horizon](https://github.com/horizon-rust/horizon), the Rust
rewrite of Minecraft: Java Edition. It keeps Horizon's renderer — its culling,
batching, meshing, LOD — and changes how the world looks, using the three stages
the game's shader API actually runs.

**2.0 is the version with the screen-space effects.** The post stage is handed
the world's depth buffer, the camera's matrices and the sun's direction, which
is enough to rebuild geometry per pixel. Aurora 2.0 uses that for:

- **Reflections on water.** A ray leaves the water surface, is walked through
  the scene and tested against real depths, and the colour it lands on is what
  the eye would have seen reflected. Screen-space: it reflects what the camera
  can see, and fades out where it cannot.
- **Contact shading (SSAO).** Normals rebuilt from depth, 16 samples per pixel,
  so creases, corners, cave mouths and the base of every object sit in their own
  shadow. This is what stops terrain looking like flat cardboard.
- **Volumetric sun shafts.** Light scattered by air, marched from each pixel
  toward the sun's real position on screen, so the shafts take the shape of
  whatever is in front of the sun.
- **Bloom, for the genuinely bright.** Above a threshold, so the sun, lava and
  glowstone glow and ordinary bright grass does not.
- **Moving water.** Two wave trains crossing in world space; the highlight is
  the sun reflected off that slope toward your eye, so a lake glitters when it
  faces the sun and goes quiet when it faces away.

Everything from 1.0 is underneath: deeper noon blue, golden low sun, air with
depth, richer greens, and a grade with highlight roll-off and readable darks.

## What it is not

**There are no cast shadows.** A tree does not lay a shadow across the ground,
because a shadow map needs the world drawn again from the sun's point of view,
and Horizon's shader API has no stage inside a second render pass
(`docs/api/shaders.md`, "Not there yet"). The shadows you do get are contact
shadows from SSAO: real, but local. Nothing in this pack pretends otherwise.

No entity textures, no block-specific materials, no screen-space GI, no
motion blur: the API has no hook for them.

Full map of the boundary, with source references: [docs/COMPATIBILITY.md](../../docs/COMPATIBILITY.md).

## The chain

| # | Pass | File | What it does |
| --- | --- | --- | --- |
| — | Sky | `sky.wgsl` | Dome colour, gold around a low sun, cold nights |
| — | Terrain | `material.wgsl` | Shading curve, greens, water tone, ripple highlights |
| 1 | Air | `post/atmosphere.wgsl` | Aerial perspective at distance |
| 2 | Contact shading | `post/ao.wgsl` | SSAO from depth |
| 3 | Water reflections | `post/reflections.wgsl` | Screen-space reflections |
| 4 | Sun shafts | `post/godrays.wgsl` | Volumetric light |
| 5 | Bloom | `post/bloom.wgsl` | Highlight glow |
| 6 | Grade | `post/grade.wgsl` | Roll-off, contrast, colour, vignette, dither |

Six full-screen passes and two stage shaders. `[budget] gpu_ms = 4.0`. On a GPU
that cannot afford that, **Horizon Aurora Lite** runs the same skies, terrain
and grade with two passes instead of six.

## Turning effects down

Horizon builds every pack's pipelines with its declared options at their
**defaults** — `game/native_shaders.rs` passes `OptionKind::default_constant()`
and no screen changes them — so this pack declares **no options**. A setting you
cannot change is a lie. Instead every effect has a constant in `common.wgsl`:

```wgsl
const AURORA_REFLECT: f32 = 0.55;          // reflections, 0 = off
const AURORA_AO_STRENGTH: f32 = 0.72;      // contact shading, 0 = off
const AURORA_RAYS: f32 = 0.42;             // sun shafts, 0 = off
const AURORA_BLOOM: f32 = 0.30;            // glow, 0 = off
const AURORA_WAVES: f32 = 1.0;             // ripples, 0 = still water
```

Save the file with the game running: Horizon re-checks the pack twice a second
and rebuilds it in place ("Shader pack Horizon Aurora reloaded" appears in the
chat). If an edit does not compile, the chat names the file, line and column and
the last good version keeps drawing.

## Installing

Put `Horizon-Aurora.hshader` (or this folder) in Horizon's `shaderpacks`
directory, then pick it under **Options → Horizon Settings → Shader Packs**.
Clicking it again turns it off. The game checks the pack before it runs and
refuses a broken one with the reason in chat.

Step by step, with the folder locations: [docs/INSTALL.md](../../docs/INSTALL.md).

## Compatibility

Manifest `schema = 1`, shader API `api = "0.1"`. Checked against Horizon `main`
at `a491181` (2026-10-29). A Horizon serving a different API line refuses the
pack with a message rather than drawing something wrong.

Licensed under the MIT License; see [LICENSE](LICENSE).
