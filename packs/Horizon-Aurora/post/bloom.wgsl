// Horizon Aurora 2.0: bloom.
//
// A soft halo around the few pixels that are genuinely brighter than the
// shoulder: the sun's disc, lava, fire, glowstone at night. The bright pass is
// thresholded first, so ordinary bright grass or stone contributes nothing —
// this is the opposite of the washed-out glow that gives bloom a bad name.
//
// Twelve taps on two rings, scaled by the picture's height so the halo looks
// the same at any resolution, sampled from `previous` so the pass before it is
// the one glowing.

fn post(input: PostInput) -> vec4<f32> {
    if (AURORA_BLOOM <= 0.0) {
        return input.color;
    }
    let texel = frame.resolution.y / 720.0 / max(frame.resolution, vec2<f32>(1.0));
    let knee = max(1.0 - AURORA_BLOOM_THRESHOLD, 0.001);
    var sum = vec3<f32>(0.0);
    for (var i = 0; i < 12; i++) {
        let angle = f32(i) * 0.5235988;
        let radius = select(3.5, 8.0, (i & 1) == 1);
        let offset = vec2<f32>(cos(angle), sin(angle)) * radius * texel;
        let c = textureSampleLevel(previous, linear_sampler, input.uv + offset, 0.0).rgb;
        // Only the part of the colour above the threshold glows, and it keeps
        // its own hue: lava glows orange, the sun glows white.
        let over = clamp((aurora_luma(c) - AURORA_BLOOM_THRESHOLD) / knee, 0.0, 1.0);
        sum += c * over * over;
    }
    return vec4<f32>(input.color.rgb + sum * (AURORA_BLOOM / 12.0), input.color.a);
}
