// Horizon Aurora Lite 2.0: helpers and tuning shared by every stage.
//
// This is Aurora 2.0's shared block with the screen-space effects taken out:
// Lite runs no reflection, contact-shading, sun-shaft or bloom pass, so its
// constants and the depth-reconstruction helpers those passes need are not
// here either. Nothing in this file is unused.
//
// Aurora 2.0 adds the effects a Minecraft shader pack is known for that the
// post stage can honestly do: screen-space reflections on water, screen-space
// contact shading (SSAO), volumetric sun shafts and bloom. All four are driven
// by the depth buffer and the camera matrices the post stage is given, so they
// are real light-transport approximations on the picture, not textures painted
// over it.
//
// They are NOT shadow maps. A shadow map needs the world drawn again from the
// sun's point of view, and Horizon's shader API has no stage that runs inside a
// second render pass (`docs/api/shaders.md`, "Not there yet"). Nothing here
// pretends otherwise: the shadows you see are contact shadows from SSAO, which
// darken creases, corners and the base of every object. Cast shadows on the
// ground from a tree or a mob are not in this pack.
//
// Tuning lives here as constants because Horizon builds every pack's pipelines
// with its declared options at their defaults (game/native_shaders.rs), so a
// declared option would be a setting that does nothing. Save this file with the
// game running and it reloads within half a second.

// --- colour ----------------------------------------------------------------
const AURORA_SATURATION: f32 = 1.085;
const AURORA_CONTRAST: f32 = 0.16;
const AURORA_ORANGE_PULL: f32 = 0.34;
const AURORA_SHADOW_LIFT: f32 = 0.011;
const AURORA_SHOULDER: f32 = 0.85;
const AURORA_VIGNETTE: f32 = 0.11;

// --- light and air ---------------------------------------------------------
const AURORA_SKY_DEPTH: f32 = 0.52;
const AURORA_WARMTH: f32 = 0.78;
const AURORA_HAZE: f32 = 0.24;
const AURORA_SUN_GLARE: f32 = 0.055;

// --- material --------------------------------------------------------------
const AURORA_FOLIAGE: f32 = 0.55;
const AURORA_WATER: f32 = 0.70;
const AURORA_LIGHTMAP_CURVE: f32 = 0.34;
const AURORA_WAVES: f32 = 1.0; // animated ripple highlights on water, 0 = still

// --- colour helpers --------------------------------------------------------
fn aurora_luma(c: vec3<f32>) -> f32 {
    return dot(c, vec3<f32>(0.2126, 0.7152, 0.0722));
}

fn aurora_saturate(c: vec3<f32>, amount: f32) -> vec3<f32> {
    return mix(vec3<f32>(aurora_luma(c)), c, amount);
}

fn aurora_daylight() -> f32 {
    return select(0.0, smoothstep(-0.12, 0.10, frame.sun_direction.y), frame.dimension == 0);
}

fn aurora_sun_low() -> f32 {
    return 1.0 - smoothstep(0.0, 0.34, abs(frame.sun_direction.y));
}

fn aurora_golden() -> f32 {
    return aurora_sun_low() * aurora_daylight() * (1.0 - frame.rain * 0.8) * AURORA_WARMTH;
}

fn aurora_shoulder(c: vec3<f32>) -> vec3<f32> {
    let knee = vec3<f32>(AURORA_SHOULDER);
    let room = 1.0 - AURORA_SHOULDER;
    let over = max(c - knee, vec3<f32>(0.0));
    return min(c, knee) + room - (room * room) / (over + vec3<f32>(room));
}

fn aurora_contrast(c: vec3<f32>, amount: f32) -> vec3<f32> {
    let curve = smoothstep(vec3<f32>(0.0), vec3<f32>(1.0), c);
    return mix(c, curve, clamp(amount, 0.0, 1.0));
}

fn aurora_lift(c: vec3<f32>) -> vec3<f32> {
    let weight = 1.0 - smoothstep(0.0, 0.30, aurora_luma(c));
    return c + AURORA_SHADOW_LIFT * weight * weight * vec3<f32>(0.60, 0.78, 1.00);
}

fn aurora_vignette(uv: vec2<f32>) -> f32 {
    let aspect = frame.resolution.x / max(frame.resolution.y, 1.0);
    let far = length(vec2<f32>(aspect, 1.0) * 0.5);
    let r = length((uv - vec2<f32>(0.5)) * vec2<f32>(aspect, 1.0)) / far;
    return 1.0 - AURORA_VIGNETTE * smoothstep(0.55, 1.05, r);
}

fn aurora_hash(p: vec2<f32>) -> f32 {
    let q = floor(p);
    return fract(sin(q.x + q.y * 127.1) * 43758.5453);
}

fn aurora_dither(pixel: vec2<f32>) -> f32 {
    return aurora_hash(pixel);
}

fn aurora_blue_mask(albedo: vec3<f32>) -> f32 {
    return smoothstep(0.012, 0.115, albedo.b - albedo.r);
}

fn aurora_green_mask(albedo: vec3<f32>) -> f32 {
    return smoothstep(0.02, 0.14, albedo.g - max(albedo.r, albedo.b));
}

// --- geometry the post passes rebuild from the depth buffer ----------------
//
// The post stage reads the world's depth (reversed: 1 at the near plane, 0 at
// the far plane and in the sky) and `view_position`, which turns a pixel and a
// depth back into a camera-relative world position in blocks. Everything below
// is built from those two things and the frame's matrices, which is why the
// effects that follow are geometry, not guesswork.

// A pale sun colour that follows the light: white at noon, golden when low.
fn aurora_sun_tint() -> vec3<f32> {
    let low = aurora_sun_low();
    return mix(vec3<f32>(1.00, 0.97, 0.90), vec3<f32>(1.00, 0.72, 0.42),
        low * (0.55 + 0.45 * aurora_daylight()));
}
