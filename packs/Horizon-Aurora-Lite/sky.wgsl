// Horizon Aurora: the sky.
//
// Vanilla hands over the colour along each view ray (sky, sky fog and the
// sunrise fan already mixed in). Aurora keeps that as the base, then:
//   * deepens the dome overhead, so noon is a real blue instead of a pale wash,
//   * adds the sun's warmth to the air around it at sunrise and sunset,
//   * cools the air away from the sun, so the blue survives the evening,
//   * gives back some of vanilla's excess orange when the sun is on the horizon,
//   * keeps nights cold and clean.
// The sun, moon, stars and clouds are drawn over this by the game.

fn sky(input: SkyInput) -> vec4<f32> {
    var c = input.color.rgb;

    // Only the Overworld has this sky, and none of it belongs behind a wall of
    // water, lava or powder snow: those keep vanilla's fogged dome.
    if (frame.dimension != 0 || frame.eye_in != 0u) {
        return vec4<f32>(clamp(c, vec3<f32>(0.0), vec3<f32>(1.0)), 1.0);
    }

    let d = normalize(input.direction);
    let up = clamp(d.y, 0.0, 1.0);
    let sun = normalize(frame.sun_direction);
    let toward_sun = max(dot(d, sun), 0.0);
    let away_from_sun = max(dot(d, -sun), 0.0);
    let day = aurora_daylight();
    let golden = aurora_golden();
    let clear = 1.0 - frame.rain * 0.8;

    // 1. The dome. A clear noon sky is richest straight up and palest at the
    //    horizon; vanilla is closer to one flat colour. Shading toward a clean
    //    blue by height gives the gradient depth without moving its hue.
    let zenith = smoothstep(0.02, 0.92, up);
    let depth = mix(vec3<f32>(1.0), vec3<f32>(0.63, 0.82, 1.10),
        AURORA_SKY_DEPTH * zenith * day * clear);
    c *= depth;

    // 2. Golden air. Warm light spreads through the lower sky around a low sun;
    //    added, not multiplied, so an already-orange sunset is not pushed
    //    further into red.
    let halo = pow(toward_sun, 6.0) * 0.75 + pow(toward_sun, 2.0) * 0.25;
    let band = 1.0 - smoothstep(0.0, 0.42, abs(d.y));
    let warm = vec3<f32>(1.00, 0.74, 0.50);
    c += warm * golden * (halo * 0.050 + band * toward_sun * 0.033);

    // 3. Cool air everywhere else, so the evening sky keeps its blue in the
    //    half of the sky the sun is not in.
    c = mix(c, c * vec3<f32>(0.93, 0.99, 1.08), away_from_sun * band * day * 0.55);

    // 4. Sunset orange is easy to overshoot. Where the sky is already strongly
    //    orange, pull the saturation back a little instead of adding to it.
    let orange = smoothstep(0.10, 0.42, c.r - c.b);
    c = mix(c, aurora_saturate(c, 0.86), orange * golden * AURORA_ORANGE_PULL);

    // 5. Night. Vanilla's night dome is almost black; a cool lift and a touch of
    //    blue keeps it readable and stops the moonlit haze looking muddy.
    let night = 1.0 - day;
    c = mix(c, c * vec3<f32>(0.90, 0.96, 1.10) + vec3<f32>(0.004, 0.006, 0.012),
        night * (0.30 + 0.40 * zenith));

    // 6. The sky is a picture, not a light source: keep it inside the frame.
    return vec4<f32>(clamp(c, vec3<f32>(0.0), vec3<f32>(1.0)), 1.0);
}
