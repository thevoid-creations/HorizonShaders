// Horizon Aurora: helpers and tuning shared by every stage.
//
// These constants are the pack's tuning knobs. The game checks the pack
// twice a second while it runs, so save this file and the picture changes
// within a moment ("Shader pack Horizon Aurora reloaded" in the chat); if a
// change does not compile, the chat says where and the last good version
// keeps drawing.
//
// Horizon 30.0.1 builds a pack's pipelines with its declared option values at
// their *defaults* only (crates/horizon-client/src/game/native_shaders.rs
// passes `OptionKind::default_constant`), and this pack declares no options
// rather than offer settings the game cannot change yet. Constants are the
// honest equivalent today: real, live, and applied on reload.

// Colour
const AURORA_SATURATION: f32 = 1.085; // colour richness, 1 = vanilla
const AURORA_CONTRAST: f32 = 0.16; // midtone S-curve strength, 0 = vanilla
const AURORA_ORANGE_PULL: f32 = 0.34; // how much of sunset's excess orange is given back
const AURORA_SHADOW_LIFT: f32 = 0.011; // keeps the darkest pixels readable
const AURORA_SHOULDER: f32 = 0.85; // where highlights start to roll off (0..1)
const AURORA_VIGNETTE: f32 = 0.11; // corner darkening, 0 = off

// Light and air
const AURORA_SKY_DEPTH: f32 = 0.52; // how much deeper the zenith goes
const AURORA_WARMTH: f32 = 0.78; // golden light around a low sun
const AURORA_HAZE: f32 = 0.24; // aerial perspective at the render distance
const AURORA_SUN_GLARE: f32 = 0.055; // the sun's own halo in the air

// Material
const AURORA_FOLIAGE: f32 = 0.55; // saturation added to greens
const AURORA_WATER: f32 = 0.70; // how much deeper water and blue glass go
const AURORA_LIGHTMAP_CURVE: f32 = 0.34; // shading contrast (block and sky light)

// Luminance as the eye weights it. Every stage measures brightness this way,
// so the pack stays consistent with itself.
fn aurora_luma(c: vec3<f32>) -> f32 {
    return dot(c, vec3<f32>(0.2126, 0.7152, 0.0722));
}

// `c` with its saturation scaled around its own luminance: 1 keeps it, 0 is grey.
fn aurora_saturate(c: vec3<f32>, amount: f32) -> vec3<f32> {
    return mix(vec3<f32>(aurora_luma(c)), c, amount);
}

// 1 while the sun is up in the Overworld, fading through the horizon.
fn aurora_daylight() -> f32 {
    return select(0.0, smoothstep(-0.12, 0.10, frame.sun_direction.y), frame.dimension == 0);
}

// 1 while the sun sits on the horizon, 0 once it is a third of the way up.
fn aurora_sun_low() -> f32 {
    return 1.0 - smoothstep(0.0, 0.34, abs(frame.sun_direction.y));
}

// How golden the light is: low sun, daytime, and clear enough to see it.
fn aurora_golden() -> f32 {
    return aurora_sun_low() * aurora_daylight() * (1.0 - frame.rain * 0.8) * AURORA_WARMTH;
}

// Highlight roll-off: everything below `AURORA_SHOULDER` is untouched, what is
// above it eases toward white instead of clipping. A burnt-out sky or a lava
// lake keeps its shape instead of turning into a flat white patch.
fn aurora_shoulder(c: vec3<f32>) -> vec3<f32> {
    let knee = vec3<f32>(AURORA_SHOULDER);
    let room = 1.0 - AURORA_SHOULDER;
    let over = max(c - knee, vec3<f32>(0.0));
    return min(c, knee) + room - (room * room) / (over + vec3<f32>(room));
}

// A gentle S-curve around the midtones; `amount` blends it with the original.
fn aurora_contrast(c: vec3<f32>, amount: f32) -> vec3<f32> {
    let curve = smoothstep(vec3<f32>(0.0), vec3<f32>(1.0), c);
    return mix(c, curve, clamp(amount, 0.0, 1.0));
}

// A little cool light in the deepest shade, strongest at black, gone by 0.3:
// the pack adds contrast without drowning the dark in ink.
fn aurora_lift(c: vec3<f32>) -> vec3<f32> {
    let weight = 1.0 - smoothstep(0.0, 0.30, aurora_luma(c));
    return c + AURORA_SHADOW_LIFT * weight * weight * vec3<f32>(0.60, 0.78, 1.00);
}

// Corner falloff, aspect-corrected so the shape is a circle on any window.
fn aurora_vignette(uv: vec2<f32>) -> f32 {
    let aspect = frame.resolution.x / max(frame.resolution.y, 1.0);
    let far = length(vec2<f32>(aspect, 1.0) * 0.5);
    let r = length((uv - vec2<f32>(0.5)) * vec2<f32>(aspect, 1.0)) / far;
    return 1.0 - AURORA_VIGNETTE * smoothstep(0.55, 1.05, r);
}

// A stable per-pixel value in 0..1, for dithering an 8-bit picture.
fn aurora_dither(pixel: vec2<f32>) -> f32 {
    let p = floor(pixel);
    return fract(sin(p.x + p.y * 127.1) * 43758.5453);
}

// How blue a surface is, 0..1: the water test, since the material stage is not
// told which block it is looking at. Water, ice and blue stained glass share
// it, which is why the change it drives is small.
fn aurora_blue_mask(albedo: vec3<f32>) -> f32 {
    return smoothstep(0.012, 0.115, albedo.b - albedo.r);
}

// How green a surface is, 0..1, for grass, leaves and crops.
fn aurora_green_mask(albedo: vec3<f32>) -> f32 {
    return smoothstep(0.02, 0.14, albedo.g - max(albedo.r, albedo.b));
}
