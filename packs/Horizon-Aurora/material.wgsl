// Horizon Aurora 2.0: block surfaces.
//
// Vanilla's colour for a point of terrain is `albedo * tint * lightmap`. That
// product is already right for most blocks, so Aurora keeps it and changes four
// things:
//   * the shading curve: block and sky light get a soft S where the surface is
//     well lit, so sunlit faces read brighter and keep their shape (this is the
//     pack's lighting change on terrain; caves and nights are left untouched),
//   * green: grass, leaves and crops keep more of their own colour,
//   * blue translucent surfaces (water, ice, blue glass) take a deeper, colder
//     tone,
//   * water gets moving ripples: a real sun highlight, computed per pixel from
//     the surface slope, the sun's direction and the eye, so a lake glitters
//     where it faces the sun and goes quiet when it faces away.
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

        // Ripples. Two wave trains crossing at an angle in world space, scrolling
        // with the frame's clock; their gradients give the surface slope, the
        // slope gives a normal, and the highlight is the sun reflected off that
        // normal toward the eye. The eye is the camera, so it is simply the
        // direction from the surface to the origin of `input.position`.
        if (AURORA_WAVES > 0.0 && blue > 0.01) {
            let p = input.position;
            let t = frame.time;
            let wave_a = p.xz * 0.85 + vec2<f32>(t * 0.55, t * 0.31);
            let wave_b = p.xz * 1.45 + vec2<f32>(-t * 0.42, t * 0.67);
            let slope = vec2<f32>(
                cos(wave_a.x) * 0.36 + cos(wave_b.x) * 0.29,
                cos(wave_a.y) * 0.36 + cos(wave_b.y) * 0.29);
            let ripple_normal = normalize(vec3<f32>(-slope.x, 1.0, -slope.y));
            let to_eye = -p / max(length(p), 1e-4);
            let to_sun = normalize(frame.sun_direction);
            let half = normalize(to_eye + to_sun);
            let sparkle = pow(max(dot(ripple_normal, half), 0.0), 120.0);
            let daylight = clamp(aurora_luma(light), 0.0, 1.0);
            c += aurora_sun_tint() * sparkle * daylight * blue * AURORA_WAVES * 0.50;
        }
    }

    return Surface(vec4<f32>(clamp(c, vec3<f32>(0.0), vec3<f32>(1.0)), input.albedo.a));
}
