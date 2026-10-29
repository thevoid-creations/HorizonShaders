# Validation report

What was checked, with what, and — just as important — what that does **not**
prove. Every number below is a recorded run, not an estimate.

## The environment this was built in

| | |
| --- | --- |
| OS | Debian GNU/Linux 12 (bookworm), Linux 6.1, x86-64, 2 vCPU |
| Python | 3.11.2 (for `tomllib`) |
| Node | 22.22.3 |
| naga | **30.0.1**, via `naga-wasm` 30.2.0 (WebAssembly) |
| Rust toolchain | **none installed and not installable** (no route to `static.rust-lang.org` or `crates.io`) |
| GPU | **none** — no Vulkan loader, no Mesa, no `/dev/dri` |
| Horizon | `main` @ `0a95d1c047` (2026-10-29), cloned read-only for the runtime-module checks |

So `cargo test`, `cargo clippy`, `horizon-shader check` and the game itself
**could not be run here**. The sections below say exactly what replaced them and
where that substitute is weaker.

## A. Verified by automated checks

### A1. The harness is trustworthy — `make self-test`

A mirror of a checker is worthless if it does not agree with the original, so
the harness is first tested against Horizon's own material: 20 checks, 0 failures.

```
prelude transcription
  ok   Frame has 28 fields
  ok   Frame offsets match docs/api/shaders-reference.md
  ok   Frame size is 400 bytes
  ok   the post prelude validates
  ok   the sky prelude validates
  ok   the material prelude validates
known-good packs from the Horizon tree
  ok   crates/horizon-shader-api/packs/golden_hour
  ok   crates/horizon-shader-api/tests/samples/schema-1
known-bad packs are refused
  ok   a vec3 passed to scalar smoothstep
  ok   a wrong return type
  ok   a missing stage function
  ok   an entry point of its own
  ok   a binding of its own
  ok   an undeclared option override
  ok   a texture read past the limit
  ok   no stage
  ok   wrong api
  ok   bad id
  ok   nine passes
  ok   unused option

0 failure(s)
```

- The `Frame` WGSL struct in `tools/validate_pack.py` is transcribed from
  `crates/horizon-shader-api/src/inputs.rs`. The self-test recomputes WGSL
  uniform offsets from it and compares them with the table Horizon *generates*
  into `docs/api/shaders-reference.md`; all 28 fields and the 400-byte size
  agree, so the prelude the pack is compiled against is the real one.
- Horizon's own `golden_hour` pack and its `schema-1` sample pack pass this
  harness, including translation for SPIR-V, MSL and HLSL — it accepts what
  Horizon accepts.
- Seven packs with valid manifests but broken WGSL are each refused — a `vec3`
  handed to a scalar `smoothstep` (the exact bug this harness caught in Aurora
  while it was being written), a wrong return type, a stage function under the
  wrong name, an entry point of the pack's own, a binding of the pack's own, an
  `override` with no option and no default, and 70 texture reads against a limit
  of 64. Five malformed manifests are refused too. It rejects what Horizon
  rejects, for the same reasons.

### A2. The packs themselves — `make check`

```
horizon_aurora 1.0.0 (shader API 0.1): ok
  sky       Sky                               0 texture reads
  material  Terrain                           0 texture reads
  post      Air                               1 texture reads
  post      Grade                             1 texture reads
  sky       sky.wgsl                     translate ok
  material  material.wgsl                translate ok
  post      post/atmosphere.wgsl         translate ok
  post      post/grade.wgsl              translate ok
  sha256 5e2f6ca67c79088b3864765e0475e4b440c5b184745c2280b8335a2958eff02c
horizon_aurora_lite 1.0.0 (shader API 0.1): ok
  sky       Sky                               0 texture reads
  material  Terrain                           0 texture reads
  post      Grade                             1 texture reads
  ... translate ok for all three stages
  sha256 4fa13ad5211d9a66006bb70ce246e8fee720aa4d699fa4a0437d532038013515
```

Each line covers:

1. **Manifest** (`schema = 1`, `api = "0.1"`, id `[a-z0-9_]{1,64}`, stage files
   plain `.wgsl` paths, 8 post passes at most, ≤ 64 options, `budget.gpu_ms` in
   `(0, 16]`).
2. **Package** (only the manifest, the files it names, `README.md`, `LICENSE`,
   `icon.png`; 256 KiB per WGSL file, 8 MiB in total; every named file present
   and used).
3. **WGSL**, parsed and validated by **naga 30.0.1** — the same validator
   version Horizon pins in `Cargo.lock`.
4. **Signature and API rules**: `fn sky(input: SkyInput) -> vec4<f32>`,
   `fn material(input: MaterialInput) -> Surface`,
   `fn post(input: PostInput) -> vec4<f32>`; no entry points, no bindings, no
   `horizon_` names of the pack's own; every `override` matching its option's
   type.
5. **Budgets**: 0 texture reads in `sky` and `material`, 1 in each post pass
   (the limit is 64).
6. **The runtime modules.** This is the part that matters most and that a plain
   WGSL check misses. Horizon does not compile a pack's `sky` and `material`
   files on their own: it appends the stage's WGSL to a copy of its **own**
   `terrain.wgsl` and adds entry points
   (`native_sky.rs::shader_source`, `native_material.rs::shader_source`). The
   harness rebuilds those exact modules — sections of `terrain.wgsl` from the
   Horizon checkout, prefixed with `horizon_sky_` / `horizon_terrain_` by the
   same algorithm as `wgsl_prefix.rs` — and validates *those*. Verified by
   negative test: a stray `horizon_terrain_sprite` call in `material.wgsl` is
   caught as an unknown identifier in the composed module, i.e. the check is
   really compiling the shader the game will compile.
7. **Translation** for Vulkan (SPIR-V), Metal (MSL) and DirectX 12 (HLSL), as
   step 6 of `horizon_shader_api::check` does. Both packs declare no options, so
   the check's three option sets (defaults, minimums, maximums) coincide and
   there is nothing for naga's override step to substitute.

### A3. The look — `make look`

`tools/simulate_look.py` is a line-by-line transcription of the pack's WGSL
(its constants are read out of `common.wgsl`, so tuning the pack retunes the
test) run over representative colours. 26 invariants pass, including:

| Invariant | Result |
| --- | --- |
| White stays white, and is not tinted | `(1,1,1) → (0.950,0.935,0.912)`, channel spread `0.038` |
| Mid grey keeps its level | `0.500 → 0.497` |
| Pure black stays dark but is not crushed | `0.000 → 0.007` |
| Sunset horizon keeps its light instead of clipping | `(0.950,0.580,0.330) → (1.000,0.647,0.389)`, luma `0.641 → 0.704` |
| Night sky stays dark and readable | luma `0.030 → 0.034` |
| A torch-lit cave is left exactly as vanilla | luma `0.035 → 0.035` (`-0.2%`) |
| Pale ice is not flattened to white | luma `0.773 → 0.767`, blue `0.950 → 0.967` |
| Water goes deeper and bluer | `(0.075,0.203,0.558) → (0.063,0.194,0.620)` |
| Red stained glass stays red | unchanged |
| Air is invisible 8 blocks away | `8 blocks: +0.6%` luma |
| Air is visible at the render distance | `192 blocks: luma +25%` |
| Sky under water, and in the Nether, is untouched | exact equality |
| Vignette is subtle | centre `0.497`, corner `0.462` |

Three real bugs were found and fixed this way before packaging: pale ice and
water flattened to `b = 1.0`; a torch-lit cave was darkened 23% by the
lightmap curve (now the curve only applies to lit faces); and the sunset
horizon pushed red to clipping.

## B. Verified in an actual game

**No.** This machine has no GPU, no Vulkan/Mesa, and Horizon needs a Microsoft
account plus a Minecraft: Java Edition installation. Nothing in this report was
observed in a running game, and no screenshot is claimed to come from one.

`docs/TESTING.md` is the checklist for doing that on your own machine, in the
order that isolates one file at a time.

## C. Not verified, and why it matters

| Not verified | Why | What would settle it |
| --- | --- | --- |
| The pack renders | no GPU here | install and look (`docs/TESTING.md`, steps 1–3) |
| GPU cost against `budget.gpu_ms = 1.2` | no GPU | F3's per-pass timings, while the pack runs |
| The official `horizon-shader check` accepts it | needs a Rust toolchain | `cargo install --path crates/horizon-shader-api && horizon-shader check packs/Horizon-Aurora` |
| naga-wasm's validator flags equal `check`'s | naga-wasm exposes `validate()` with its own flag set; the Rust check passes `ValidationFlags::all()` | the CLI run above |
| The look on real vanilla colours | the simulation uses representative values, not a frame | eyes |

## D. Reproducting all of it

```sh
git clone https://github.com/horizon-rust/horizon ../horizon     # for the runtime checks
cd tools && npm install                                          # naga-wasm 30.2.0
cd .. && make self-test HORIZON=../horizon
make check  HORIZON=../horizon
make look
make dist   HORIZON=../horizon
```

`make dist` writes `dist/Horizon-Aurora.hshader`, `dist/Horizon-Aurora-Lite.hshader`,
`dist/Horizon-Aurora-Source.zip` and `dist/SHA256SUMS`. The `.hshader` bytes are
reproducible — files in path order, fixed timestamps, fixed permissions — so the
same pack always has the same SHA-256.
