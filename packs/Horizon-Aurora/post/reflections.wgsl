// Horizon Aurora 2.0: screen-space reflections on water.
//
// Every block in the world is drawn with the colour its texture gives it; water
// is a flat translucent blue with nothing in it. A shader pack cannot ask for a
// reflection buffer, but it *can* ray-march the picture it already has: the
// depth buffer says where every other pixel's geometry is, so a ray leaving the
// water surface can be walked through the scene and tested against real depths.
// When it passes behind something, the colour at that pixel is what the eye
// would have seen reflected.
//
// This is a screen-space reflection: it only sees what the camera can see. A
// bank behind the camera cannot be reflected, the ray fades out near the edge
// of the picture, and when it finds only sky it takes the sky's own colour.
// Those are the honest limits of the technique, and the fades below make them
// soft instead of obvious.
//
// Which pixels are water: the material stage is not told which block it shades,
// so this pass asks two questions — is the pixel blue, and is its recovered
// normal lying flat? Water is both. Blue wool on a wall is not.

// The surface normal at a pixel, from its neighbours' depths, oriented toward
// the camera. Silhouettes are handled by taking the nearer neighbour on each
// axis (reversed depth: greater is nearer), so an object's edge does not bend
// its own normal outward.
fn aurora_normal(uv: vec2<f32>, depth: f32) -> vec3<f32> {
    let texel = 1.0 / max(frame.resolution, vec2<f32>(1.0));
    let left = depth_at(uv - vec2<f32>(texel.x, 0.0));
    let right = depth_at(uv + vec2<f32>(texel.x, 0.0));
    let up = depth_at(uv - vec2<f32>(0.0, texel.y));
    let down = depth_at(uv + vec2<f32>(0.0, texel.y));
    let p = view_position(uv, depth);
    let pl = view_position(uv - vec2<f32>(texel.x, 0.0), max(left, depth));
    let pr = view_position(uv + vec2<f32>(texel.x, 0.0), max(right, depth));
    let pu = view_position(uv - vec2<f32>(0.0, texel.y), max(up, depth));
    let pd = view_position(uv + vec2<f32>(0.0, texel.y), max(down, depth));
    // A degenerate cross product (a perfectly flat patch read twice, or two
    // depths that round together) would normalise to NaN and poison the pixel.
    let face = cross(pr - pl, pd - pu);
    let n = face / max(length(face), 1e-6);
    // The camera sits at the origin; a visible surface faces back toward it.
    return select(n, -n, dot(n, p) > 0.0);
}

fn post(input: PostInput) -> vec4<f32> {
    if (input.depth <= 0.0 || frame.dimension != 0 || frame.eye_in != 0u || AURORA_REFLECT <= 0.0) {
        return input.color;
    }

    let p = view_position(input.uv, input.depth);
    let n = aurora_normal(input.uv, input.depth);
    let water = aurora_water(input.color.rgb, n);
    if (water <= 0.002) {
        return input.color;
    }

    // The camera sits at the origin; guard the case where the surface is at it.
    let eye = p / max(length(p), 1e-4);
    let ray = reflect(eye, n);
    if (ray.z > 0.0) {
        // The reflection would travel behind the camera, where nothing is known.
        return input.color;
    }

    let steps = i32(clamp(AURORA_REFLECT_STEPS, 4.0, 48.0));
    var hit = 0.0;
    var hit_uv = vec2<f32>(0.0);
    var travelled = 0.15;
    for (var i = 0; i < steps; i++) {
        // Steps grow with distance: fine detail near the surface, cheap reach far.
        travelled += 0.30 + f32(i) * 0.18;
        let q = p + ray * travelled;
        let proj = aurora_project(q);
        if (proj.z <= 0.0 || proj.x < 0.0 || proj.x > 1.0 || proj.y < 0.0 || proj.y > 1.0) {
            break;
        }
        let there = depth_at(proj.xy);
        if (there <= 0.0) {
            // Only sky beyond this point: reflect the sky, more faintly.
            hit_uv = proj.xy;
            hit = 0.55;
            break;
        }
        if (proj.z > length(view_position(proj.xy, there)) + 0.15) {
            hit_uv = proj.xy;
            hit = 1.0;
            break;
        }
    }
    if (hit <= 0.0) {
        return input.color;
    }

    // Fresnel: water reflects little when looked at from above and almost
    // everything at a grazing angle, which is why reflections live near the
    // horizon. Edges of the picture fade out for the reason above.
    let facing = clamp(dot(-eye, n), 0.0, 1.0);
    let fresnel = 0.30 + 0.70 * pow(1.0 - facing, 4.0);
    let edge = smoothstep(0.0, 0.10, hit_uv.x) * (1.0 - smoothstep(0.90, 1.0, hit_uv.x))
        * smoothstep(0.0, 0.10, hit_uv.y) * (1.0 - smoothstep(0.90, 1.0, hit_uv.y));

    let reflected = textureSampleLevel(scene_color, linear_sampler, hit_uv, 0.0).rgb;
    let amount = clamp(AURORA_REFLECT * water * hit * edge * fresnel, 0.0, 0.85);
    return vec4<f32>(mix(input.color.rgb, reflected, amount), input.color.a);
}
