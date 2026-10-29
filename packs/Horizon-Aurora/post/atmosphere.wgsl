// Horizon Aurora: air.
//
// Vanilla fogs by distance with one flat colour, and only near the render
// distance. Aurora adds aerial perspective over the whole view: the further a
// pixel is, the more its colour is replaced by the air in front of it, and that
// air is the sky's own colour warmed toward a low sun. Near the camera nothing
// changes, so the ground you are standing on stays crisp.
//
// The pass needs the world's depth, which is reversed: 1 at the near plane,
// 0 at the far plane and in the sky.

fn post(input: PostInput) -> vec4<f32> {
    // Sky pixels, the other dimensions, and the view from inside water, lava or
    // powder snow: vanilla's picture is already right there.
    if (input.depth <= 0.0 || frame.dimension != 0 || frame.eye_in != 0u) {
        return input.color;
    }

    // The point this pixel sees, camera-relative: its length is the distance,
    // its direction is the view ray.
    let pos = view_position(input.uv, input.depth);
    let dist = length(pos);
    let dir = pos / max(dist, 0.001);
    let sun = normalize(frame.sun_direction);
    let toward_sun = max(dot(dir, sun), 0.0);
    let golden = aurora_golden();

    // How much air there is between the camera and this point. Tuned against
    // the render distance, so the effect travels with the view distance
    // instead of vanishing when a player raises it.
    let reach = max(frame.render_distance, 64.0);
    let falloff = 2.4 / reach;
    // Squared-then-rooted: the haze stays out of the near ground and only
    // gathers over the far half of the view (x^1.5, without a pow()).
    let haze = 1.0 - exp(-dist * falloff);
    let amount = haze * sqrt(haze) * AURORA_HAZE * (1.0 + frame.rain * 0.30);

    // The air's colour: the sky above mixed into vanilla's fog colour, warmed
    // where it is between the camera and a low sun.
    var air = mix(frame.fog_color, frame.sky_color, 0.35);
    air = mix(air, vec3<f32>(1.00, 0.80, 0.58), golden * pow(toward_sun, 3.0) * 0.30);
    air = mix(air, air * vec3<f32>(0.96, 0.99, 1.06), clamp(dir.y, 0.0, 1.0) * 0.40);
    let c = mix(input.color.rgb, air, amount);

    // A hint of the sun itself in the air it lights, brightest in clear weather
    // and gone with distance: light scatter, not a bloom.
    let glare = AURORA_SUN_GLARE * amount * pow(toward_sun, 9.0)
        * (0.40 + 0.60 * golden + 0.50 * aurora_daylight());
    return vec4<f32>(c + vec3<f32>(1.00, 0.86, 0.66) * glare, input.color.a);
}
