// Horizon Aurora 2.0: volumetric sun shafts.
//
// Light scattered by the air between you and the sun is invisible in a
// rasteriser, because nothing is drawn there. The usual trick is to build it
// from what the camera can see: march from this pixel toward the sun's position
// on screen and count how much of that path is open sky. Rays that pass through
// a canopy, a cave mouth or the edge of a cliff pick up fewer open samples, so
// the shafts fall across the world in the shape of whatever is blocking them.
//
// It reacts to the real sun: the shaft is drawn from `frame.sun_direction`
// projected through the camera's own matrices, tinted gold when the sun is low,
// and faded in rain.

fn post(input: PostInput) -> vec4<f32> {
    let sun = aurora_sun_screen();
    if (sun.z <= 0.0 || AURORA_RAYS <= 0.0 || frame.dimension != 0 || frame.eye_in != 0u) {
        return input.color;
    }

    // Only light *around* the sun's direction contributes.
    let to_sun = 1.0 - smoothstep(0.0, 0.90, length(sun.xy - input.uv));
    if (to_sun <= 0.001) {
        return input.color;
    }

    var uv = input.uv;
    let stride = (sun.xy - input.uv) * (0.94 / 24.0);
    var open = 0.0;
    var decay = 1.0;
    var total = 0.0;
    for (var i = 0; i < 24; i++) {
        uv += stride;
        if (depth_at(uv) <= 0.0) {
            // A reversed depth of 0 is the far plane or the sky: open air.
            open += decay;
        }
        total += decay;
        decay *= 0.965;
    }
    let density = open / max(total, 0.0001);

    // Sky pixels are already bright; shafts read over the ground and the shapes
    // in front of it, which is where the light actually falls.
    let over_geometry = smoothstep(0.0, 0.02, input.depth);
    let amount = AURORA_RAYS * density * to_sun * sun.z * over_geometry
        * (1.0 - frame.rain * 0.7) * (0.35 + 0.65 * aurora_daylight());
    return vec4<f32>(input.color.rgb + aurora_sun_tint() * amount * 0.40, input.color.a);
}
