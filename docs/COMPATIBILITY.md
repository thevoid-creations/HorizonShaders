# What Horizon's renderer can and cannot do for a shader pack

Read out of the Horizon source at `main` @ `a491181` (2026-10-29), not out
of its documentation — where the two disagree, the code is quoted. Every claim
below has the file it comes from, so you can check it against whatever Horizon
you have.

The short version: a Horizon pack can change **the sky, block surfaces and the
final picture**, and nothing else. Aurora is built to that boundary and claims
nothing across it.

## The stages that exist

`crates/horizon-shader-api/src/stages.rs` defines exactly three, and
`crates/horizon-shader-api/src/check.rs` refuses anything else.

### `[sky]` — `fn sky(input: SkyInput) -> vec4<f32>`

| | |
| --- | --- |
| Called for | each pixel of the Overworld's sky dome, per view ray |
| Receives | `direction` (unit ray) and `color` (vanilla's colour along that ray: sky, sky fog and the sunrise fan already mixed) |
| Drawn over it by Horizon | the sun, moon, stars, the End's sky and the cloud plane |
| Limits | returns an opaque colour; alpha is ignored; **does not apply to the Nether or the End** (guarded by `frame.dimension`) |
| Source | `gfx/native_sky.rs`; call site `gfx.rs` ("native_sky_pass", and the in-pass `sky.draw`) |

What the stage can therefore do: recolour the dome, add atmospheric glow,
change night, react to rain and to the sun's height. What it cannot do: move the
sun, add clouds, or change another dimension's sky.

### `[material]` — `fn material(input: MaterialInput) -> Surface`

| | |
| --- | --- |
| Called for | terrain: solid, cutout and **translucent** (water, ice, stained glass), instanced and flat/distant draws |
| Receives | `albedo` (atlas colour), `tint` (biome tint × face shade × AO), `light` (block/sky 0..1), `lightmap` (vanilla's light colour this frame), `position`, `uv`, and `translucent` (which pass) |
| Returns only | `color` — the lit colour, alpha included |
| Applied after it returns | the alpha test (`< 0.5` cutout, `< 0.01` translucent), then fog |
| Does **not** cover | entities, block entities, particles, the hand, weather, clouds |
| Source | `gfx/native_material.rs`; pipelines swapped in `gfx.rs` (`solid_pipeline` / `translucent_pipeline`) |

Consequences worth knowing:

- **Not told which block it is looking at.** There is no block id, no normal
  and no material tag in `MaterialInput` (`horizon-shader-api/src/inputs.rs`).
  Anything block-specific must be inferred from `albedo`/`tint`/`translucent`.
  Aurora's water treatment is a hue test for exactly this reason, and it is
  deliberately small so that ice and blue glass — which share the hue — do not
  look wrong.
- **Lighting is already baked.** `lightmap` is vanilla's colour, so a pack can
  reshape existing light but cannot add a new light: there is no sun direction
  per surface and no shadow term to attenuate it.
- **Alpha is the game's.** Changing `color.a` changes what is cut out and how
  water blends. Aurora passes alpha through untouched.

### `[[post]]` — `fn post(input: PostInput) -> vec4<f32>`

| | |
| --- | --- |
| Called for | a full-screen pass over the world's picture; up to 8 in order |
| Receives | `uv`, `pixel`, `color` (previous pass, or the world for the first) and `depth` (reversed: 0 sky/far), plus `frame.scene_color`, `frame.scene_depth`, `previous`, samplers 4/5 and the helpers `depth_at`, `view_position` |
| Draws onto | the world's colour target for all but the last pass; the screen for the last |
| Covers | the whole world picture: terrain, entities, block entities, particles, clouds, weather, sky, sun/moon/stars |
| Does **not** cover | the first-person hand and the HUD, which are drawn after the passes (`gfx.rs`: `hud.draw_range` follows `post.run`) |
| Precision | intermediate targets are `Rgba16Float` (`native_post.rs`), so values above 1.0 survive between passes; the final pass writes the 8-bit window format |
| Source | `gfx/native_post.rs`; call site `gfx.rs` (`native_post` branch) |

## What the post stage's depth buffer *does* buy you

The post stage gets `scene_depth` (reversed: 0 is sky and the far plane), the
camera's `view`/`projection` and their inverses, and the helper
`view_position(uv, depth)` that turns a pixel and a depth back into a
camera-relative world position. That is a full per-pixel reconstruction of the
visible surface, and it is enough to do real screen-space light transport:

| Effect | How Aurora 2.0 does it | Honest limit |
| --- | --- | --- |
| Contact shading (SSAO) | Normals rebuilt from neighbouring depths; 16 hemisphere samples tested against the depth buffer | Local: it darkens creases and where objects meet, not ground a tree shadows from afar |
| Reflections on water | Reflected ray marched through the screen, tested against depths, colour taken from `scene_color` | Screen-space: only reflects what the camera can see; fades at the picture's edge and falls back to the sky |
| Volumetric sun shafts | March from each pixel toward the sun's projected position, counting open-sky samples | A screen-space approximation: shafts are occluded only by geometry in view |
| Bloom | Thresholded bright pass, twelve taps | None beyond cost |
| Water ripples | Slope from two crossing wave trains; specular from the sun and the eye | A shading effect, not displaced geometry |

One detail makes the reflection pass possible at all: Horizon's **translucent
terrain pipeline writes depth** (`gfx.rs`, the `translucent` pipeline built with
`depth_write: true` and alpha blending). A water pixel therefore carries the
water *surface's* depth, so the normal rebuilt from the depth buffer is the flat
surface normal a reflection needs — not the lake bed's. Where a renderer does not
write depth for water, the same pass would read the bed and the flatness test
would (correctly) refuse to draw a reflection into it.

What depth still cannot give: anything **behind** the camera, anything **off
screen**, and any **second** view of the world — which is exactly why shadows are
out of reach.

## What does not exist (and so is not in the pack)

| Effect you might expect from a Minecraft shader pack | Status in Horizon today |
| --- | --- |
| Shadow maps | No shadow stage, and the API's own docs list shadows as "not there yet" (`docs/api/shaders.md`). Nothing in `stages.rs` can receive a shadow map. **This cannot be faked**: a cast shadow needs geometry rendered from the light, and no stage runs in a second pass. Aurora 2.0 substitutes screen-space contact shading and says so. |
| A lighting/deferred pass | Same: no stage. |
| Entity / particle / hand materials | No stage. Graded only as part of the post picture. |
| Bloom, DOF, motion blur, screen-space reflections | No dedicated pass; a pack could blur within its own hand-written post pass, but there is no scene history, no exposed sun buffer and no depth-aware helper beyond `depth_at`/`view_position`. Aurora deliberately does none of this. |
| Cloud, weather, water-specific hooks | None. Weather and clouds are drawn by the renderer. |
| Setting an option's value at runtime | **Parsed, validated, shown in the tooling — but not selectable in the game.** `NativeShaders::tick_native_shader_pack` builds every pipeline with `o.kind.default_constant()` (`crates/horizon-client/src/game/native_shaders.rs`), and no screen writes any other value. See below. |

## The option limitation, precisely

`[[options]]` is fully part of the format: `check` validates each one, requires
it to be used as an `override` of the right type, and translates the pack with
every option at its default, its minimum and its maximum
(`horizon-shader-api/src/check.rs::translate`). What is missing is the *game's*
side of it — one line in one file:

```rust
// crates/horizon-client/src/game/native_shaders.rs
let constants = pack
    .manifest
    .options
    .iter()
    .map(|o| (o.id.clone(), o.kind.default_constant()))
    .collect();
```

Aurora therefore declares **no options at all**. Declaring options that the
game runs at their defaults would be exactly the "setting that does nothing"
this project promises not to ship. The look is tuned through named constants in
`common.wgsl`, which Horizon's hot reload applies the moment you save the file —
real, live, and honest.

If Horizon later ships the override screen, adding it to Aurora is additive: the
constants become the defaults of options of the same names, and every stage that
reads `AURORA_*` keeps working.

## Two interactions worth knowing

- **TAA is switched off while a pack has post passes.** In `gfx.rs`,
  `let taa = !frame.title && self.pack_post... && self.native...is_none_or(|n| n.post.is_none())`.
  Aurora has two, so Horizon's temporal anti-aliasing does not run under it (a
  world target is still allocated for the pack to read). If you prefer TAA,
  Aurora Lite is one pass lighter but still disables it; only a sky+material-only
  pack keeps TAA.
- **The hand and HUD are never graded.** `hud.draw_range` runs after
  `post.run`, and the first-person hand is drawn in the hand pass afterwards, so
  the pack cannot tint your crosshair, inventory or hotbar.

## Where this leaves the design

Aurora does, in its four stages, everything the boundary allows without
resorting to fakery:

1. sky colour and atmospheric glow (sky stage),
2. a shading curve, colour, water treatment and sun glints for terrain
   (material stage),
3. aerial perspective, which needs depth and so lives in a post pass,
4. contact shading, reflections, sun shafts and bloom, all rebuilt from depth,
5. the grade: highlight roll-off, contrast, saturation, split toning, lift,
   vignette, dither.

No stage pretends to do shadows, no screenshot is claimed from a machine that
never ran the game, and `docs/TESTING.md` is the list of things only you,
with a GPU, can confirm.
