# Horizon Aurora

A shader pack for [Horizon](https://github.com/horizon-rust/horizon), the Rust
rewrite of Minecraft: Java Edition. It keeps Horizon's own renderer (its
culling, batching, meshing and LOD) and changes how the world *looks*: deeper
blue skies, golden sunset light, air with real depth, richer greens, deeper
water, and a gentle cinematic grade.

Written against **shader API 0.1, manifest schema 1**, the format Horizon
serves today. It uses all three stages the API gives a pack — `sky`,
`material` and `post` — so it needs no other software, no fork of the game and
no launcher mod.

## What it does

| Stage | File | What changes |
| --- | --- | --- |
| Sky | `sky.wgsl` | The dome is deepened toward a real noon blue, warm light gathers around a low sun, the half of the sky away from the sun stays blue, vanilla's excess sunset orange is given back, and nights go cold and clean instead of black. |
| Terrain | `material.wgsl` | A soft shading curve on lit faces (more shape on sunlit terrain, cave and torch light left exactly as vanilla), richer greens for grass, leaves and crops, deeper and colder water, ice and blue glass. |
| Air | `post/atmosphere.wgsl` | Aerial perspective over the whole view: distant land takes on the sky's colour, warmed toward a low sun. The near ground is untouched. |
| Grade | `post/grade.wgsl` | Highlights roll off instead of clipping, a gentle S-curve for contrast, a little more saturation, an orange correction, cool shade / warm light split toning, readable darks, a soft vignette and 8-bit dither. |

The sun, moon, stars, clouds, entities, the hand and the HUD are drawn by
Horizon itself and are unaffected — the pack changes the world's picture, not
the interface or the game.

## Performance

Four stages, one of them a per-pixel terrain shader and two full-screen passes.
No shadow maps, no extra render targets, no temporal accumulation, no blur
chains. `[budget] gpu_ms = 1.2` is the pack's own declared aim.

On a GPU that struggles, use **Horizon Aurora Lite** instead: the same skies,
terrain and grade with the air pass left out. Its budget is 0.8 ms.

## Changing the look

Options (`[[options]]`) are part of the format, but Horizon builds every pack
with its options at their **defaults** today — the game has no screen for
changing them yet (`crates/horizon-client/src/game/native_shaders.rs` passes
`OptionKind::default_constant`). This pack therefore declares none rather than
show settings that cannot be changed.

Its tuning lives in `common.wgsl` as constants with names that say what they do:

```wgsl
const AURORA_SATURATION: f32 = 1.085;   // colour richness, 1 = vanilla
const AURORA_CONTRAST: f32 = 0.16;      // midtone S-curve, 0 = vanilla
const AURORA_WARMTH: f32 = 0.78;        // golden light around a low sun
const AURORA_HAZE: f32 = 0.24;          // aerial perspective at the render distance
const AURORA_WATER: f32 = 0.70;         // how much deeper water goes
const AURORA_VIGNETTE: f32 = 0.11;      // corner darkening, 0 = off
```

Save the file while the game is running: Horizon checks the pack twice a second
and rebuilds it in place ("Shader pack Horizon Aurora reloaded" appears in the
chat). If an edit does not compile, the chat tells you the file, line and
column and the last good version keeps drawing.

## Installing

Put the `.hshader` file (or this folder) in Horizon's `shaderpacks` directory,
then choose it under **Options → Horizon Settings → Shader Packs**. Clicking it
again turns it off. Horizon checks the pack before it runs and refuses a broken
one with the reason in the chat, so a bad pack can never leave you with a black
screen.

The full walkthrough, including where `shaderpacks` is on Windows, macOS and
Linux, is in [docs/INSTALL.md](../../docs/INSTALL.md).

## Compatibility

- Manifest `schema = 1`, shader API `api = "0.1"`.
- Horizon refuses a pack written for another API line with a clear message
  rather than drawing something wrong; if a future version moves to API 0.2,
  this pack will say so in the chat instead of misbehaving.
- Tested against Horizon `main` at commit `0a95d1c047` (2026-10-29).

## Credit

Pack by thevoid-creations. Inspired by the look of Golden Hour, Horizon's own
example pack, and of the classic shader packs that made Minecraft's weather
feel like weather.

Licensed under the MIT License; see [LICENSE](LICENSE).
