// Horizon Aurora: the colour grade.
//
// The last pass of the pack, and the one that decides its look. In order:
//   1. highlights roll off instead of clipping, so lava, the sun and torches
//      keep their shape,
//   2. a gentle S-curve for cinematic contrast around the midtones,
//   3. saturation up a little, then sunset's excess orange given back,
//   4. cool shade and warm light, very slight (split toning),
//   5. the darkest pixels lifted a hair so caves and nights stay readable,
//   6. a soft vignette, and dither so clouds and fog do not band at 8 bits.
//
// Horizon's world target and this pass's output are display-referred (the
// renderer's pipeline is not linear-light), so these are photographic
// operations on the picture, not radiometric ones.

fn post(input: PostInput) -> vec4<f32> {
    var c = input.color.rgb;

    // 1. Highlight roll-off. Below the shoulder nothing changes at all.
    c = aurora_shoulder(c);

    // 2. Contrast. A small blend toward an S-curve; blacks and whites stay put.
    c = aurora_contrast(c, AURORA_CONTRAST);

    // 3. Colour. Richer overall, then cooler *hues* are left alone while an
    //    over-orange sunset is pulled back toward warm sunlight.
    c = aurora_saturate(c, AURORA_SATURATION);
    let orange = smoothstep(0.10, 0.42, c.r - c.b);
    c = mix(c, aurora_saturate(c, 0.88), orange * AURORA_ORANGE_PULL);

    // 4. Split tone: shade leans a little cool, light a little warm. Both are
    //    within a couple of percent, which is what keeps it from looking tinted.
    let light = aurora_luma(c);
    let split = smoothstep(0.15, 0.85, light);
    c = mix(c * vec3<f32>(0.972, 0.990, 1.020), c * vec3<f32>(1.018, 1.002, 0.978), split);

    // 5. Readable darks.
    c = aurora_lift(c);

    // 6. Vignette, then 8-bit dither.
    c *= aurora_vignette(input.uv);
    c += vec3<f32>((aurora_dither(input.pixel) - 0.5) / 255.0);

    return vec4<f32>(clamp(c, vec3<f32>(0.0), vec3<f32>(1.0)), input.color.a);
}
