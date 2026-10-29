# Validation harness

Horizon's authority for shader packs is `horizon-shader check` in
`crates/horizon-shader-api`. These tools let the same questions be asked on a
machine with no Rust toolchain:

| File | What it does |
| --- | --- |
| `validate_pack.py` | Reads, checks and packages packs. Mirrors `horizon_shader_api::{manifest,package,stages,check}` rule for rule, validates every stage with the *same* naga (30.0.1, via `naga-wasm`), builds the runtime modules the renderer really compiles (splicing in Horizon's own `terrain.wgsl`), and translates for SPIR-V, MSL and HLSL. |
| `naga.mjs` | The JSON pipe to naga-wasm: parse, validate, translate. |
| `simulate_look.py` | A line-by-line transcription of the pack's WGSL, run over representative colours to check the look's invariants (white stays white, darks stay readable, water does not clip, distant air is visible but near ground is untouched). |

## Setup

```sh
cd tools && npm install          # naga-wasm 30.2.0 (bundles naga 30.0.1)
```

Node 22 or newer. Python 3.11 or newer (for `tomllib`).

## Use

```sh
python3 tools/validate_pack.py self-test --horizon ../horizon
python3 tools/validate_pack.py check packs/Horizon-Aurora --translate --horizon ../horizon
python3 tools/validate_pack.py pack  packs/Horizon-Aurora --out dist/Horizon-Aurora.hshader
python3 tools/simulate_look.py
```

`--horizon PATH` is what makes the check complete: it splices the pack's `sky`
and `material` into the renderer's real modules, using `terrain.wgsl` from that
checkout, exactly as `native_sky.rs` and `native_material.rs` do.

## Limits, stated plainly

- The check's expression count and its `process_overrides` option step need
  naga's IR, which naga-wasm does not expose. Texture reads are counted at call
  sites instead (an upper bound), and option sets are applied by rewriting each
  `override` to a `const` with the same value — which is what the override step
  computes. A pack with no options (Horizon Aurora) has no difference at all.
- Read `docs/VALIDATION.md` before treating a green run as proof that a pack
  looks right in the game.
