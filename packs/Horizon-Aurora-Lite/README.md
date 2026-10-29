# Horizon Aurora Lite

The look of **Horizon Aurora** on a lighter budget. It is the same pack with
the `Air` pass removed: one full-screen pass fewer per frame, so pick this one
on integrated graphics, a laptop, or an older GPU.

| Stage | File | What changes |
| --- | --- | --- |
| Sky | `sky.wgsl` | Deeper noon blue, golden light around a low sun, bluer evening sky, clean nights. |
| Terrain | `material.wgsl` | Softer shading on lit faces, richer greens, deeper water and ice. |
| Grade | `post/grade.wgsl` | Highlight roll-off, gentle contrast, saturation, orange correction, split toning, readable darks, vignette, dither. |

What you give up is the **aerial perspective**: distant land no longer takes on
the colour of the air in front of it, so the far view falls off toward vanilla's
flatter fog. Everything else is identical, and because both packs share the same
`common.wgsl` constants, tuning one tunes the other's look the same way.

Written against **shader API 0.1, manifest schema 1**. Install it exactly like
Horizon Aurora: `shaderpacks/`, then **Options → Horizon Settings → Shader
Packs**. See [docs/INSTALL.md](../../docs/INSTALL.md).

`[budget] gpu_ms = 0.8`.

Options are not selectable in Horizon yet (the game builds every pack with its
options at their defaults), so the tuning lives in `common.wgsl` as named
constants, live-reloaded when you save the file.

Licensed under the MIT License; see [LICENSE](LICENSE).
