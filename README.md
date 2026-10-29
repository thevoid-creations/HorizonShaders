# Horizon Aurora

A shader pack for [Horizon](https://github.com/horizon-rust/horizon), the Rust
rewrite of Minecraft: Java Edition. Horizon keeps vanilla's world, mobs and
rules and draws them itself; a **Horizon shader pack** is WGSL that plugs into
the stages of that renderer. Aurora is one of the first packs written for it.

![Horizon Aurora](packs/Horizon-Aurora/icon.png)

**2.0 adds the screen-space effects**, built from the depth buffer the post
stage is handed:

- **Reflections on water** — a ray marched through the scene and tested against real depths.
- **Contact shading (SSAO)** — creases, corners and the base of every object sit in their own shadow.
- **Volumetric sun shafts** — light that takes the shape of whatever stands in front of the sun.
- **Bloom** — only above a threshold, so the sun and lava glow and grass does not.
- **Moving water** — real sun glints on a rippling surface.

Underneath: natural blue skies, warm low sun, air with depth, richer greens and a
gentle cinematic grade.

**What it is not:** there are still no cast shadows. A shadow map needs the
world drawn again from the sun's point of view, and Horizon's shader API has no
stage inside a second render pass. The shadows you get are contact shadows from
SSAO — real, but local. Nothing here is a setting that does nothing, and nothing
here is claimed without saying how it was checked.

## Install

1. In Horizon, open **Options → Horizon Settings → Shader Packs → Open Pack Folder**.
2. Drop `Horizon-Aurora.hshader` (or the `Horizon-Aurora` folder) into the folder that opens.
3. Reopen the page and click **Horizon Aurora (Horizon): OFF**.

Full instructions, per operating system: [docs/INSTALL.md](docs/INSTALL.md).

## Downloads

| File | What it is |
| --- | --- |
| `dist/Horizon-Aurora.hshader` | The pack (2.0, six passes), in Horizon's `.hshader` format — install this. |
| `dist/Horizon-Aurora-Lite.hshader` | The lighter variant: two passes, no screen-space effects. |
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
at commit `a491181` (2026-10-29). A Horizon that serves another API line
refuses the pack with a message in chat rather than drawing something wrong.

What the renderer can and cannot do, with the source references behind every
claim: [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md).

## Licence

MIT. Not an official Minecraft product; no Minecraft assets are included.
