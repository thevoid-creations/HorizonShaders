// Horizon Aurora 2.0: screen-space contact shading (SSAO).
//
// Horizon's material stage is handed a lightmap that vanilla baked from block
// light and sky light. It knows nothing about the shape of the world around a
// point, so a wall meeting a floor, the base of a tree and the inside of a
// corner are all lit as if the surface were alone in the open. That is why
// vanilla terrain looks flat.
//
// This pass recovers the missing shape from the depth buffer: for every pixel
// it rebuilds the surface normal and its neighbours from `view_position`, then
// scatters 16 samples through the hemisphere above the surface. A sample that
// lands behind something nearer to the camera is a ray that would have hit
// geometry, so the pixel is a little darker. That is screen-space ambient
// occlusion: real contact shadows where geometry crowds together.
//
// It is not a shadow map. It cannot darken ground that a tree casts on from a
// distance; it darkens creases, corners and where things meet the ground.

fn aurora_occlusion(uv: vec2<f32>, depth: f32) -> f32 {
    let radius = AURORA_AO_RADIUS;
    let p = view_position(uv, depth);
    let n = aurora_normal(uv, depth);
    let basis = aurora_basis(n);
    var occ = 0.0;
    var counted = 0.0;
    for (var i = 0; i < 16; i++) {
        // A golden-angle spiral spread through the hemisphere: even coverage
        // without a random number, so the result is stable frame to frame.
        let angle = f32(i) * 2.39996323;
        let radius01 = sqrt((f32(i) + 0.5) / 16.0);
        let dir = normalize(basis * vec3<f32>(
            cos(angle) * radius01,
            sin(angle) * radius01,
            0.30 + 0.70 * radius01));
        let q = p + dir * radius;
        let proj = aurora_project(q);
        if (proj.z <= 0.0 || proj.x < 0.002 || proj.x > 0.998 || proj.y < 0.002 || proj.y > 0.998) {
            continue;
        }
        let there = depth_at(proj.xy);
        if (there <= 0.0) {
            continue;
        }
        // How much nearer the geometry at that pixel is than the sample point.
        let gap = proj.z - length(view_position(proj.xy, there));
        counted += 1.0;
        if (gap > AURORA_AO_BIAS) {
            occ += 1.0 - smoothstep(0.0, radius * 1.6, gap);
        }
    }
    if (counted < 1.0) {
        return 1.0;
    }
    return clamp(1.0 - (occ / counted) * AURORA_AO_STRENGTH, 0.0, 1.0);
}

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
    // Sky has no surface to shade, the Nether and the End keep vanilla's look,
    // and the view from inside a fluid is not graded.
    if (input.depth <= 0.0 || frame.dimension != 0 || frame.eye_in != 0u || AURORA_AO_STRENGTH <= 0.0) {
        return input.color;
    }
    let shade = aurora_occlusion(input.uv, input.depth);
    return vec4<f32>(input.color.rgb * shade, input.color.a);
}
