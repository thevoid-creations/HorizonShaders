# Horizon Aurora

A shader pack for [Horizon](https://github.com/horizon-rust/horizon), the Rust
rewrite of Minecraft: Java Edition. Horizon keeps vanilla's world, mobs and
rules and draws them itself; a **Horizon shader pack** is WGSL that plugs into
the stages of that renderer. Aurora is one of the first packs written for it.

![Horizon Aurora](packs/Horizon-Aurora/icon.png)

- **Natural blue skies** that deepen overhead instead of washing out.
- **Warm sunlight** at sunrise and sunset, without the neon orange.
- **Air with depth**: distant land fades into the colour of the sky in front of it.
- **Richer greens**, natural terrain, **deeper water**.
- **A gentle cinematic grade**: soft highlight roll-off, subtle contrast, readable darks.
- **Two levels**: *Horizon Aurora* and *Horizon Aurora Lite*, one full-screen pass lighter.

No shadows are claimed, because Horizon's shader API has no shadow stage yet.
Nothing in this pack is a setting that does nothing.

## Install

1. In Horizon, open **Options → Horizon Settings → Shader Packs → Open Pack Folder**.
2. Drop `Horizon-Aurora.hshader` (or the `Horizon-Aurora` folder) into the folder that opens.
3. Reopen the page and click **Horizon Aurora (Horizon): OFF**.

Full instructions, per operating system: [docs/INSTALL.md](docs/INSTALL.md).

## Downloads

| File | What it is |
| --- | --- |
| `dist/Horizon-Aurora.hshader` | The pack, packaged in Horizon's `.hshader` format (install this). |
| `dist/Horizon-Aurora-Lite.hshader` | The lighter variant. |
| `dist/Horizon-Aurora-Source.zip` | Both packs as source, with this documentation. |

## What is in this repository

```
packs/Horizon-Aurora/        the pack: manifest, WGSL stages, icon, licence
packs/Horizon-Aurora-Lite/   the lighter variant
docs/                        install, validation, capabilities, in-game test plan
tools/                       the validation harness (naga 30.0.1 via WebAssembly)
dist/                        built .hshader files and their SHA-256 sums
```

## How it is checked

Horizon's own checker — `horizon-shader check` in
`crates/horizon-shader-api` — is the authority. This machine has no Rust
toolchain, so `tools/` mirrors that checker rule for rule and runs the *same*
validator (naga 30.0.1, the version Horizon pins) compiled to WebAssembly, plus
the **runtime** modules Horizon actually builds by splicing in its own
`terrain.wgsl`. What that does and does not prove: [docs/VALIDATION.md](docs/VALIDATION.md).

```sh
make check     # manifest, stages, naga, runtime modules, SPIR-V/Metal/HLSL
make look      # the pack's own maths over representative colours
make dist      # .hshader files + source zip
```

## Compatibility

Manifest `schema = 1`, shader API `api = "0.1"`, checked against Horizon `main`
at commit `0a95d1c047` (2026-10-29). A Horizon that serves another API line
refuses the pack with a message in chat rather than drawing something wrong.

What the renderer can and cannot do, with the source references behind every
claim: [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md).

## Licence

MIT. Not an official Minecraft product; no Minecraft assets are included.
