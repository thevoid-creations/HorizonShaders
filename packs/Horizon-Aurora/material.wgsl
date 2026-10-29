// Horizon Aurora: block surfaces.
//
// Vanilla's colour for a point of terrain is `albedo * tint * lightmap`. That
// product is already right for most blocks, so Aurora keeps it and changes only
// three things:
//   * the shading curve: block and sky light get a soft S, so faces that face
//     the light read brighter and the shade keeps some depth instead of
//     flattening into the same grey (this is the pack's lighting change),
//   * green: grass, leaves and crops keep more of their own colour,
//   * blue translucent surfaces (water, ice, blue glass) take a deeper, colder
//     tone, the pack's water change.
// The alpha channel is passed through untouched: it is what vanilla's cutout
// test and the translucent blend use, so leaves, glass and water stay exactly
// as transparent as they were.
//
// Horizon applies fog and the alpha test after this function returns.

fn material(input: MaterialInput) -> Surface {
    let lm = input.lightmap;

    // Soft S-curve on the lighting: `lm * lm * (3 - 2 * lm)` is the smoothstep
    // curve, unchanged at 0 and 1 and a little brighter through the upper half.
    // It is faded out where there is little light, so caves, nights and torchlight
    // keep vanilla's falloff exactly and stay as readable as they were: only
    // sunlit and well-lit faces gain separation.
    let curve = lm * lm * (vec3<f32>(3.0) - 2.0 * lm);
    let lit = smoothstep(vec3<f32>(0.30), vec3<f32>(1.0), lm);
    let light = mix(lm, curve, AURORA_LIGHTMAP_CURVE * lit);

    var c = input.albedo.rgb * input.tint.rgb * light;

    // Greens: grass, leaves and crops. A touch more saturation in the leaf's own
    // colour reads as richer terrain; the mask keeps sand, stone and dirt out.
    let green = aurora_green_mask(input.albedo.rgb);
    c = mix(c, aurora_saturate(c, 1.12), green * AURORA_FOLIAGE * 0.5);

    // Water and the other blue translucent surfaces: deeper, colder, a little
    // richer. The material stage is not told which block it is shading, so the
    // test is the texture's own hue; ice and blue stained glass share it, which
    // is why the change is small and takes its colour from what is already there.
    if (input.translucent) {
        let blue = aurora_blue_mask(input.albedo.rgb);
        // Bright blue already has nowhere to go: fade the change out near white
        // so pale ice keeps its highlights instead of flattening into 1.0.
        let headroom = 1.0 - smoothstep(0.80, 1.0, c.b);
        let deep = mix(vec3<f32>(1.0), vec3<f32>(0.78, 0.94, 1.16),
            blue * AURORA_WATER * headroom);
        c *= deep;
    }

    return Surface(vec4<f32>(clamp(c, vec3<f32>(0.0), vec3<f32>(1.0)), input.albedo.a));
}
