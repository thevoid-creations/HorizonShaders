#!/usr/bin/env python3
"""Validate and package Horizon shader packs without a Rust toolchain.

`horizon-shader check` is the authority: it lives in `crates/horizon-shader-api`
and the game, the launcher and the registry all run it. This script mirrors it
rule for rule (manifest, package, stage composition, signatures, API rules,
options, budgets) and runs the *same* validator through naga 30.0.1 compiled to
WebAssembly (`naga-wasm`), so a pack can be checked on a machine that has no
Rust compiler. It is a mirror, not a substitute: run the official CLI when you
build Horizon itself (docs/VALIDATION.md says which claims rest on which).

Usage:
    validate_pack.py check <pack-or-.hshader>... [--json] [--translate]
    validate_pack.py pack <pack-dir> [--out FILE.hshader]
    validate_pack.py self-test [--horizon PATH]

`--translate` also translates every entry point for Vulkan (SPIR-V), Metal
(MSL) and DirectX 12 (HLSL), as step 6 of the check does.
`--horizon PATH` points at a Horizon checkout; its `terrain.wgsl` is then used
to build and validate the *runtime* sky and material modules exactly as
`native_sky.rs` and `native_material.rs` do. Nothing else is read from it.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

# --- limits, from crates/horizon-shader-api/src/manifest.rs and package.rs ----
SCHEMA = 1
API = "0.1"
MANIFEST = "horizon-shaders.toml"
EXTENSION = "hshader"
MAX_POST_PASSES = 8
MAX_OPTIONS = 64
MAX_GPU_MS = 16.0
MAX_EXPRESSIONS = 20_000
MAX_TEXTURE_READS = 64
MAX_WGSL = 256 << 10
MAX_OTHER = 1 << 20
MAX_TOTAL = 8 << 20
MAX_ENTRIES = 512
EXTRAS = ("README.md", "LICENSE", "LICENSE.md", "LICENSE.txt", "icon.png")
GROUP = 3

# --- the prelude, from crates/horizon-shader-api/src/{inputs,stages}.rs ------
# Every struct below is `Struct::wgsl()`'s output for the Rust definition in
# inputs.rs; `self-test` re-derives Frame's field offsets and compares them with
# the table in docs/api/shaders-reference.md, so a transcription slip fails loudly.
FRAME_FIELDS = [
    ("view", "mat4x4<f32>"),
    ("projection", "mat4x4<f32>"),
    ("view_inverse", "mat4x4<f32>"),
    ("projection_inverse", "mat4x4<f32>"),
    ("camera_position", "vec3<f32>"),
    ("time", "f32"),
    ("sun_direction", "vec3<f32>"),
    ("day_time", "f32"),
    ("moon_direction", "vec3<f32>"),
    ("game_time", "f32"),
    ("sky_color", "vec3<f32>"),
    ("rain", "f32"),
    ("fog_color", "vec3<f32>"),
    ("thunder", "f32"),
    ("resolution", "vec2<f32>"),
    ("eye_light", "vec2<f32>"),
    ("fog_start", "f32"),
    ("fog_end", "f32"),
    ("render_distance", "f32"),
    ("far", "f32"),
    ("night_vision", "f32"),
    ("blindness", "f32"),
    ("darkness", "f32"),
    ("brightness", "f32"),
    ("eye_in", "u32"),
    ("dimension", "i32"),
    ("frame_index", "u32"),
    ("hide_gui", "u32"),
]
# docs/api/shaders-reference.md, "The frame" table: (field, byte offset).
FRAME_OFFSETS_DOC = [
    ("view", 0), ("projection", 64), ("view_inverse", 128),
    ("projection_inverse", 192), ("camera_position", 256), ("time", 268),
    ("sun_direction", 272), ("day_time", 284), ("moon_direction", 288),
    ("game_time", 300), ("sky_color", 304), ("rain", 316), ("fog_color", 320),
    ("thunder", 332), ("resolution", 336), ("eye_light", 344),
    ("fog_start", 352), ("fog_end", 356), ("render_distance", 360),
    ("far", 364), ("night_vision", 368), ("blindness", 372), ("darkness", 376),
    ("brightness", 380), ("eye_in", 384), ("dimension", 388),
    ("frame_index", 392), ("hide_gui", 396),
]

POST_INPUT_FIELDS = [
    ("uv", "vec2<f32>"),
    ("pixel", "vec2<f32>"),
    ("color", "vec4<f32>"),
    ("depth", "f32"),
]
MATERIAL_INPUT_FIELDS = [
    ("albedo", "vec4<f32>"),
    ("tint", "vec4<f32>"),
    ("light", "vec2<f32>"),
    ("lightmap", "vec3<f32>"),
    ("position", "vec3<f32>"),
    ("uv", "vec2<f32>"),
    ("translucent", "bool"),
]
SURFACE_FIELDS = [("color", "vec4<f32>")]
SKY_INPUT_FIELDS = [("direction", "vec3<f32>"), ("color", "vec4<f32>")]

RESOURCES = {
    "post": [
        (0, "var<uniform> frame: Frame"),
        (1, "var scene_color: texture_2d<f32>"),
        (2, "var scene_depth: texture_depth_2d"),
        (3, "var previous: texture_2d<f32>"),
        (4, "var linear_sampler: sampler"),
        (5, "var nearest_sampler: sampler"),
    ],
    "sky": [(0, "var<uniform> frame: Frame")],
    "material": [(0, "var<uniform> frame: Frame")],
}

POST_HELPERS = """\
// The world's depth at `uv` (reversed: 0 is the sky).
fn depth_at(uv: vec2<f32>) -> f32 {
    let size = vec2<f32>(textureDimensions(scene_depth));
    let texel = vec2<i32>(clamp(uv * size, vec2<f32>(0.0), size - 1.0));
    return textureLoad(scene_depth, texel, 0);
}
// The camera-relative world position, in blocks, of the point at `uv` and `depth`.
fn view_position(uv: vec2<f32>, depth: f32) -> vec3<f32> {
    let clip = vec4<f32>(uv.x * 2.0 - 1.0, 1.0 - uv.y * 2.0, depth, 1.0);
    let view = frame.projection_inverse * clip;
    return (frame.view_inverse * vec4<f32>(view.xyz / view.w, 0.0)).xyz;
}
"""

POST_ENTRIES = """\
struct HorizonPostOut {
    @builtin(position) position: vec4<f32>,
    @location(0) uv: vec2<f32>,
}
@vertex fn horizon_vs_post(@builtin(vertex_index) i: u32) -> HorizonPostOut {
    let p = vec2<f32>(f32((i << 1u) & 2u), f32(i & 2u));
    var out: HorizonPostOut;
    out.position = vec4<f32>(p * 2.0 - 1.0, 0.0, 1.0);
    out.uv = vec2<f32>(p.x, 1.0 - p.y);
    return out;
}
@fragment fn horizon_fs_post(in: HorizonPostOut) -> @location(0) vec4<f32> {
    let color = textureSampleLevel(previous, linear_sampler, in.uv, 0.0);
    return post(PostInput(in.uv, in.position.xy, color, depth_at(in.uv)));
}
"""

MATERIAL_ENTRIES = """\
struct HorizonMaterialIn {
    @builtin(position) position: vec4<f32>,
    @location(0) albedo: vec4<f32>,
    @location(1) tint: vec4<f32>,
    @location(2) light: vec2<f32>,
    @location(3) lightmap: vec3<f32>,
    @location(4) world: vec3<f32>,
    @location(5) uv: vec2<f32>,
    @location(6) @interpolate(flat) translucent: u32,
}
@fragment fn horizon_fs_material(in: HorizonMaterialIn) -> @location(0) vec4<f32> {
    let input = MaterialInput(in.albedo, in.tint, in.light, in.lightmap, in.world, in.uv, in.translucent != 0u);
    return material(input).color;
}
"""

SKY_ENTRIES = """\
struct HorizonSkyIn {
    @builtin(position) position: vec4<f32>,
    @location(0) direction: vec3<f32>,
    @location(1) color: vec4<f32>,
}
@fragment fn horizon_fs_sky(in: HorizonSkyIn) -> @location(0) vec4<f32> {
    return sky(SkyInput(normalize(in.direction), in.color));
}
"""

# The entry points the renderer actually builds for the sky and material
# stages (native_sky.rs, native_material.rs), used only with --horizon.
SKY_PACK_ENTRY = """
@fragment fn horizon_sky_fs_pack(in: horizon_sky_SkyOut) -> @location(0) vec4<f32> {
    let d = horizon_sky_view_ray(in.ndc);
    return vec4(sky(SkyInput(d, vec4(horizon_sky_sky_along_ray(d), 1.0))).rgb, 1.0);
}
"""

MATERIAL_ENTRIES_RUNTIME = """
struct HorizonMaterialOut {
    @builtin(position) clip: vec4<f32>,
    @location(0) uv: vec2<f32>,
    @location(1) @interpolate(flat) layer: u32,
    @location(2) tint: vec4<f32>,
    @location(3) light: vec2<f32>,
    @location(4) lightmap: vec3<f32>,
    @location(5) position: vec3<f32>,
    @location(6) spherical: f32,
    @location(7) cylindrical: f32,
}
fn horizon_material_vertex(position: vec3<f32>, uv: vec2<f32>, layer: u32, color: vec4<f32>,
    light: vec2<u32>, origin: vec3<f32>) -> HorizonMaterialOut {
    let pos = position + origin;
    var out: HorizonMaterialOut;
    out.clip = horizon_terrain_globals.view_proj * vec4(pos, 1.0);
    out.uv = uv;
    out.layer = layer;
    out.tint = vec4(color.rgb, 1.0);
    let block = max(f32(light.y), horizon_terrain_dynamic_block_light(pos));
    let sky = f32(light.x);
    // 16 per level, 15 levels.
    out.light = min(vec2(block, sky) / 240.0, vec2(1.0));
    out.lightmap = horizon_terrain_sample_lightmap(sky / 16.0, block / 16.0).rgb;
    out.position = pos;
    out.spherical = length(pos);
    out.cylindrical = max(length(pos.xz), abs(pos.y));
    return out;
}
@vertex fn horizon_material_vs(
    @location(0) position: vec3<f32>, @location(1) uv: vec2<u32>,
    @location(2) layer: u32, @location(3) color: vec4<f32>, @location(4) light: vec2<u32>,
    @location(5) origin: vec4<f32>) -> HorizonMaterialOut {
    return horizon_material_vertex(position, horizon_terrain_terrain_uv(uv, origin.w), layer,
        color, light, origin.xyz);
}
@vertex fn horizon_material_vs_flat(
    @builtin(vertex_index) vertex: u32,
    @location(0) position: vec3<f32>, @location(1) uv: vec2<u32>,
    @location(2) layer: u32, @location(3) color: vec4<f32>, @location(4) light: vec2<u32>
) -> HorizonMaterialOut {
    let origin = horizon_terrain_slot_origins[horizon_terrain_block_slots[vertex >> 8u]];
    return horizon_material_vertex(position, horizon_terrain_terrain_uv(uv, origin.w), layer,
        color, light, origin.xyz);
}
fn horizon_material_color(in: HorizonMaterialOut, translucent: bool) -> vec4<f32> {
    let albedo = horizon_terrain_sprite(in.uv, in.layer & 0x7fffu);
    return material(MaterialInput(albedo, in.tint, in.light, in.lightmap, in.position, in.uv,
        translucent)).color;
}
@fragment fn horizon_material_fs_solid(in: HorizonMaterialOut) -> @location(0) vec4<f32> {
    let color = horizon_material_color(in, false);
    // Bit 15 of the layer marks opaque leaves (forceOpaque): no alpha cutout.
    if color.a < 0.5 && (in.layer & 0x8000u) == 0u { discard; }
    return horizon_terrain_apply_fog(vec4(color.rgb, 1.0), in.spherical, in.cylindrical);
}
@fragment fn horizon_material_fs_translucent(in: HorizonMaterialOut) -> @location(0) vec4<f32> {
    let color = horizon_material_color(in, true);
    if color.a < 0.01 { discard; }
    return horizon_terrain_apply_fog(color, in.spherical, in.cylindrical);
}
"""


def struct_wgsl(name: str, fields) -> str:
    out = f"struct {name} {{\n"
    out += "".join(f"    {f}: {t},\n" for f, t in fields)
    return out + "}\n"


def stage_input(kind: str) -> list:
    return {"sky": SKY_INPUT_FIELDS, "material": MATERIAL_INPUT_FIELDS, "post": POST_INPUT_FIELDS}[kind]


def stage_output_name(kind: str) -> str:
    return "Surface" if kind == "material" else "vec4<f32>"


def prelude(kind: str) -> str:
    out = "// Horizon shader API prelude (docs/api/shaders-reference.md)\n"
    out += struct_wgsl("Frame", FRAME_FIELDS)
    out += struct_wgsl(
        {"sky": "SkyInput", "material": "MaterialInput", "post": "PostInput"}[kind],
        stage_input(kind),
    )
    if kind == "material":
        out += struct_wgsl("Surface", SURFACE_FIELDS)
    for binding, decl in RESOURCES[kind]:
        out += f"@group({GROUP}) @binding({binding}) {decl};\n"
    if kind == "post":
        out += POST_HELPERS
    return out


def entries(kind: str) -> str:
    return {"sky": SKY_ENTRIES, "material": MATERIAL_ENTRIES, "post": POST_ENTRIES}[kind]


# --- problems ---------------------------------------------------------------
@dataclass
class Problem:
    file: str
    message: str
    line: int = 0
    column: int = 0

    def __str__(self) -> str:
        if self.line == 0:
            return f"{self.file}: {self.message}"
        return f"{self.file}:{self.line}:{self.column}: {self.message}"


@dataclass
class Stage:
    kind: str
    file: str
    label: str
    source: str


@dataclass
class Pack:
    path: Path
    manifest: dict
    files: dict[str, bytes] = field(default_factory=dict)

    def source(self, name: str) -> str | None:
        b = self.files.get(name)
        return b.decode("utf-8") if b is not None else None


# --- package.rs -------------------------------------------------------------
PLAIN_PART = re.compile(r"^[A-Za-z0-9._-]+$")


def plain_path(path: str) -> bool:
    if not path:
        return False
    return all(p and not p.startswith(".") and PLAIN_PART.match(p) for p in path.split("/"))


def is_pack(path: Path) -> bool:
    return (path / MANIFEST).is_file() or (
        path.is_file() and path.suffix == f".{EXTENSION}"
    )


def read_pack(path: Path) -> tuple[Pack | None, list[Problem]]:
    files: dict[str, bytes] = {}
    if path.is_dir():
        for root, dirs, names in os.walk(path):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            rel_root = os.path.relpath(root, path)
            for name in sorted(names):
                if name.startswith("."):
                    continue
                rel = name if rel_root == "." else f"{Path(rel_root).as_posix()}/{name}"
                data = (Path(root) / name).read_bytes()
                if len(data) > MAX_TOTAL:
                    return None, [Problem(str(path), f"{rel} is over {MAX_TOTAL >> 20} MiB")]
                files[rel] = data
    else:
        try:
            with zipfile.ZipFile(path) as z:
                if len(z.infolist()) > MAX_ENTRIES:
                    return None, [Problem(str(path), f"over {MAX_ENTRIES} files in the package")]
                for info in z.infolist():
                    if info.is_dir():
                        continue
                    if info.filename in files:
                        return None, [Problem(str(path), f"{info.filename} is in the package twice")]
                    files[info.filename] = z.read(info)
        except zipfile.BadZipFile as e:
            return None, [Problem(str(path), f"not a .{EXTENSION} (zip): {e}")]
    pack, problems = from_files(files)
    if pack is not None:
        pack.path = path
    return pack, problems


def from_files(files: dict[str, bytes]) -> tuple[Pack | None, list[Problem]]:
    if MANIFEST not in files:
        return None, [Problem(MANIFEST, "missing at the pack's root")]
    try:
        text = files[MANIFEST].decode("utf-8")
    except UnicodeDecodeError:
        return None, [Problem(MANIFEST, "not UTF-8")]
    manifest, problems = parse_manifest(text)
    if manifest is None:
        return problems and (None, problems) or (None, [Problem(MANIFEST, "unreadable")])
    used = manifest_files(manifest)
    total = 0
    for name in sorted(files):
        if not plain_path(name):
            return None, [Problem(name, "is not a plain path")]
        data = files[name]
        total += len(data)
        if name.endswith(".wgsl"):
            if name not in used:
                return None, [Problem(name, "is not used by any stage or in shared")]
            try:
                data.decode("utf-8")
            except UnicodeDecodeError:
                return None, [Problem(name, "not UTF-8")]
            limit = MAX_WGSL
        elif name == MANIFEST or name in EXTRAS:
            limit = MAX_OTHER
        else:
            return None, [Problem(
                name,
                f"a pack holds only {MANIFEST}, .wgsl files and {', '.join(EXTRAS)}",
            )]
        if len(data) > limit:
            return None, [Problem(name, f"is over {limit >> 10} KiB")]
    if total > MAX_TOTAL:
        return None, [Problem(MANIFEST, f"the pack is over {MAX_TOTAL >> 20} MiB")]
    for name in used:
        if name not in files:
            return None, [Problem(name, f"named in {MANIFEST} but missing")]
    return Pack(Path("."), manifest, files), []


def manifest_files(m: dict) -> list[str]:
    out: list[str] = []
    stages = ([] if m["sky"] is None else [m["sky"]]) + (
        [] if m["material"] is None else [m["material"]]
    ) + m["post"]
    for name in list(m["shared"]) + [s["file"] for s in stages]:
        if name not in out:
            out.append(name)
    return out


# --- manifest.rs ------------------------------------------------------------
ID_RE = re.compile(r"^[a-z0-9_]{1,64}$")
IDENT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


def is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def parse_manifest(text: str) -> tuple[dict | None, list[Problem]]:
    problems: list[Problem] = []

    def bad(msg: str):
        return None, problems + [Problem(MANIFEST, msg)]

    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        return bad(str(e))

    known = {"schema", "id", "name", "version", "api", "description", "authors",
             "license", "shared", "sky", "material", "post", "options", "budget"}
    for key in raw:
        if key not in known:
            return bad(f"unknown field `{key}`")
    for key in ("schema", "id", "name", "version", "api"):
        if key not in raw:
            return bad(f"missing field `{key}`")
    if raw["schema"] != SCHEMA:
        return bad(f"schema {raw['schema']}; this Horizon reads {SCHEMA}")
    if raw["api"] != API:
        return bad(f"written for shader API {raw['api']}; this Horizon serves {API}")
    if not ID_RE.match(raw["id"]):
        return bad(f"id {raw['id']!r} is not [a-z0-9_]{{1,64}}")
    if not str(raw["name"]).strip() or not str(raw["version"]).strip():
        return bad("name and version can't be empty")

    def stage_value(obj, where: str):
        if not isinstance(obj, dict):
            return None, [Problem(MANIFEST, f"{where} is not a table")]
        unknown = set(obj) - {"file", "name"}
        if unknown:
            return None, [Problem(MANIFEST, f"{where}: unknown field `{sorted(unknown)[0]}`")]
        if "file" not in obj:
            return None, [Problem(MANIFEST, f"{where}: missing field `file`")]
        return {"file": obj["file"], "name": obj.get("name")}, []

    sky = material = None
    if "sky" in raw:
        sky, p = stage_value(raw["sky"], "sky")
        problems.extend(p)
    if "material" in raw:
        material, p = stage_value(raw["material"], "material")
        problems.extend(p)
    post = []
    for i, obj in enumerate(raw.get("post", []) or []):
        s, p = stage_value(obj, f"post[{i}]")
        problems.extend(p)
        if s is not None:
            post.append(s)
    if problems:
        return None, problems

    if sky is None and material is None and not post:
        return bad("no stage: give it a [sky], a [material] or a [[post]]")
    if len(post) > MAX_POST_PASSES:
        return bad(f"{len(post)} post passes; a pack may chain {MAX_POST_PASSES}")
    stages = ([sky] if sky else []) + ([material] if material else []) + post
    for s in list(raw.get("shared", []) or []) + stages:
        name = s if isinstance(s, str) else s["file"]
        if not isinstance(name, str) or not plain_path(name) or not name.endswith(".wgsl"):
            return bad(f"{name!r} is not a plain path to a .wgsl file")

    options = []
    for i, o in enumerate(raw.get("options", []) or []):
        opt, p = parse_option(o, i)
        problems.extend(p)
        if opt is not None:
            if any(prev["id"] == opt["id"] for prev in options):
                return bad(f"option {opt['id']!r} is declared twice")
            options.append(opt)
    if problems:
        return None, problems
    if len(options) > MAX_OPTIONS:
        return bad(f"{len(options)} options; a pack may declare {MAX_OPTIONS}")

    budget = raw.get("budget", {}) or {}
    if not isinstance(budget, dict) or set(budget) - {"gpu_ms"}:
        return bad("budget: unknown field")
    gpu_ms = budget.get("gpu_ms")
    if gpu_ms is not None:
        if not is_number(gpu_ms) or not (0.0 < float(gpu_ms) <= MAX_GPU_MS):
            return bad(f"budget.gpu_ms {gpu_ms} is not in (0, {MAX_GPU_MS:g}]")

    return {
        "schema": raw["schema"],
        "id": raw["id"],
        "name": raw["name"],
        "version": raw["version"],
        "api": raw["api"],
        "description": raw.get("description", ""),
        "authors": raw.get("authors", []) or [],
        "license": raw.get("license"),
        "shared": raw.get("shared", []) or [],
        "sky": sky,
        "material": material,
        "post": post,
        "options": options,
        "budget": {"gpu_ms": None if gpu_ms is None else float(gpu_ms)},
    }, []


def parse_option(o, index: int) -> tuple[dict | None, list[Problem]]:
    where = f"option #{index + 1}"

    def bad(msg):
        return None, [Problem(MANIFEST, f"{where}: {msg}")]

    if not isinstance(o, dict):
        return bad("is not a table")
    unknown = set(o) - {"id", "name", "description", "type", "default", "min", "max", "step", "values"}
    if unknown:
        return bad(f"unknown field `{sorted(unknown)[0]}`")
    for key in ("id", "name", "type"):
        if key not in o:
            return bad(f"missing field `{key}`")
    if "default" not in o:
        return bad("missing field `default`")
    oid = o["id"]
    if not isinstance(oid, str) or not IDENT_RE.match(oid) or oid.startswith("horizon_"):
        return bad(
            "the id must be a WGSL identifier: a letter, then letters, digits or _, "
            "up to 64, not starting with horizon_"
        )
    kind = o["type"]
    out = {"id": oid, "name": o["name"], "description": o.get("description", ""), "type": kind}
    if kind == "bool":
        if any(k in o for k in ("min", "max", "step", "values")):
            return bad("min/max/step/values don't apply to type = \"bool\"")
        if not isinstance(o["default"], bool):
            return bad("default must be true or false")
        out["wgsl_type"], out["default"] = "bool", o["default"]
    elif kind == "float":
        if "values" in o:
            return bad("values doesn't apply to type = \"float\"")
        for key in ("min", "max"):
            if key not in o:
                return bad(f"needs {key}")
            if not is_number(o[key]):
                return bad(f"{key} is not a number")
        if not is_number(o["default"]):
            return bad(f"{o['default']} is not a number")
        lo, hi, default = float(o["min"]), float(o["max"]), float(o["default"])
        step = float(o["step"]) if "step" in o else (hi - lo) / 100.0
        if not (lo < hi and lo <= default <= hi):
            return bad(f"needs min < max and default in [{lo}, {hi}]")
        if not (step > 0.0 and step <= hi - lo):
            return bad(f"step {step} is not in (0, {hi - lo}]")
        out |= {"wgsl_type": "f32", "default": default, "min": lo, "max": hi, "step": step}
    elif kind == "int":
        if any(k in o for k in ("step", "values")):
            return bad("step/values don't apply to type = \"int\"")
        for key in ("min", "max", "default"):
            if key not in o:
                return bad(f"needs {key}")
            if not isinstance(o[key], int) or isinstance(o[key], bool):
                return bad(f"{o[key]} is not a 32-bit integer")
        lo, hi, default = o["min"], o["max"], o["default"]
        if not (-(2**31) <= lo < 2**31 and -(2**31) <= hi < 2**31):
            return bad("min/max must be 32-bit")
        if not (lo < hi and lo <= default <= hi):
            return bad(f"needs min < max and default in [{lo}, {hi}]")
        out |= {"wgsl_type": "i32", "default": default, "min": lo, "max": hi}
    elif kind == "choice":
        if any(k in o for k in ("min", "max", "step")):
            return bad("min/max/step don't apply to type = \"choice\"")
        values = o.get("values")
        if not isinstance(values, list):
            return bad("needs values")
        if not (2 <= len(values) <= 32):
            return bad("needs 2 to 32 values")
        for i, v in enumerate(values):
            if not isinstance(v, str) or not v.strip() or v in values[:i]:
                return bad("values must be distinct and not empty")
        if not isinstance(o["default"], str) or o["default"] not in values:
            return bad("default must be one of the values")
        out |= {"wgsl_type": "u32", "default": values.index(o["default"]), "values": values}
    else:
        return bad(f"type {kind!r} is not bool, float, int or choice")
    return out, []


# --- stages.rs --------------------------------------------------------------
def compose(pack: Pack, kind: str, file: str) -> str:
    parts: list[str] = []

    def push(text: str):
        parts.append(text if text.endswith("\n") else text + "\n")

    push(prelude(kind))
    for shared in pack.manifest["shared"]:
        if shared != file:
            push(pack.source(shared) or "")
    push(pack.source(file) or "")
    return "".join(parts)


def compose_with_entries(pack: Pack, kind: str, file: str) -> str:
    text = compose(pack, kind, file)
    return text + entries(kind)


# --- check.rs ---------------------------------------------------------------
STAGE_FN = {
    "sky": ("sky", "SkyInput", "vec4<f32>"),
    "material": ("material", "MaterialInput", "Surface"),
    "post": ("post", "PostInput", "vec4<f32>"),
}
TEXTURE_READ = re.compile(r"\btexture(Sample|SampleLevel|SampleBias|SampleGrad|Load|Gather|GatherCompare|SampleCompare|SampleCompareLevel)\w*\s*\(")


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def check_pack(pack: Pack, translate: bool, horizon: Path | None) -> dict:
    manifest = pack.manifest
    problems: list[Problem] = []
    stages: list[Stage] = []
    ordered = ([("sky", manifest["sky"])] if manifest["sky"] else []) + (
        [("material", manifest["material"])] if manifest["material"] else []
    ) + [("post", s) for s in manifest["post"]]

    own_files = list(manifest["shared"]) + [s["file"] for _, s in ordered]
    for name in own_files:
        code = strip_comments(pack.source(name) or "")
        for m in re.finditer(r"@(vertex|fragment|compute)\b", code):
            problems.append(Problem(name, f"declares the entry point (`@{m.group(1)}`): a stage is a function, Horizon adds the entry points"))
            break
        if re.search(r"@group\s*\(", code) or re.search(r"@binding\s*\(", code):
            problems.append(Problem(name, "declares a binding: a stage reads only the resources of its prelude"))
        for m in re.finditer(r"\bhorizon_[A-Za-z0-9_]*", code):
            problems.append(Problem(name, f"`{m.group(0)}`: names starting with horizon_ are Horizon's"))
            break

    parsed: list[tuple[str, dict, str]] = []
    for kind, stage in ordered:
        file = stage["file"]
        label = stage.get("name") or file
        module, naga_error = naga_run([{"name": f"{kind}:{file}", "source": compose(pack, kind, file)}])
        if not module["ok"]:
            problems.append(Problem(file, module.get("error", naga_error or "invalid")))
            continue
        fn, arg, ret = STAGE_FN[kind]
        own = compose(pack, kind, file)
        pattern = re.compile(
            rf"\bfn\s+{fn}\s*\(\s*\w+\s*:\s*{re.escape(arg)}\s*\)\s*->\s*{re.escape(ret)}\s*\{{"
        )
        if not pattern.search(strip_comments(own)):
            problems.append(
                Problem(file, f"`fn {fn}(input: {arg}) -> {ret}` is missing, or declares another signature")
            )
            continue
        # overrides must be options of their type, or carry their own default
        code = strip_comments(own)
        for m in re.finditer(r"\boverride\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([A-Za-z0-9_<>]+)\s*(=\s*[^;]*)?;", code):
            name, ty, default = m.group(1), m.group(2), m.group(3)
            option = next((o for o in manifest["options"] if o["id"] == name), None)
            if option and ty != option["wgsl_type"]:
                problems.append(Problem(
                    file, f"`override {name}: {ty}`: option {name!r} is a {option['type']}, "
                          f"so its override is `{option['wgsl_type']}`"))
            elif option is None and default is None:
                problems.append(Problem(file, f"`override {name}` has no default and no [[options]] entry"))
        reads = len(TEXTURE_READ.findall(strip_comments(own)))
        if reads > MAX_TEXTURE_READS:
            problems.append(Problem(file, f"{reads} texture reads; a stage may write {MAX_TEXTURE_READS}"))
        stages.append(Stage(kind, file, label, own))
        parsed.append((kind, stage, label))

    if not problems:
        for option in manifest["options"]:
            used = any(
                re.search(rf"\boverride\s+{re.escape(option['id'])}\s*:", strip_comments(s.source))
                for s in stages
            )
            if not used:
                problems.append(Problem(
                    MANIFEST,
                    f"option {option['id']!r}: no stage declares `override {option['id']}: "
                    f"{option['wgsl_type']}`"))

    # The runtime modules the renderer composes for the sky and material
    # stages (native_sky.rs, native_material.rs), and every entry point's
    # translation for the three backends.
    runtime = []
    if not problems:
        for kind, stage, _label in parsed:
            file = stage["file"]
            own = compose(pack, kind, file)
            # 1. The module `check` validates: prelude, shared, the file, Horizon's entries.
            module, _ = naga_run([{"name": f"{kind}:{file}", "source": compose_with_entries(pack, kind, file)}])
            if not module["ok"]:
                problems.append(Problem(file, module.get("error", "invalid")))
                continue
            # 2. The module the renderer really compiles (native_sky.rs, native_material.rs).
            if horizon is not None and kind in ("sky", "material"):
                built = runtime_module(kind, own, horizon)
                if built is None:
                    runtime.append({"stage": kind, "file": file, "ok": False,
                                    "error": "terrain.wgsl is missing in the Horizon checkout"})
                    # A --horizon run that cannot build the runtime module has not
                    # checked the thing it was asked to check: that is a failure.
                    problems.append(Problem(file, "terrain.wgsl is missing in the Horizon checkout"))
                else:
                    module, _ = naga_run([{"name": f"runtime:{kind}:{file}", "source": built}])
                    runtime.append({"stage": kind, "file": file, "ok": module["ok"],
                                    "error": module.get("error")})
                    if not module["ok"]:
                        problems.append(Problem(file, "the runtime module is refused: " + module.get("error", "")))
                        continue
            # 3. Translation for Vulkan, Metal and DirectX 12, as step 6 of the check.
            if translate:
                result, _ = naga_run(translate_variants(pack, stage, kind))
                runtime.append({"stage": kind, "file": file, "translate": result.get("translate")})
                if not result["ok"]:
                    problems.append(Problem(file, result.get("error", "translation failed")))

    out = {
        "path": str(pack.path),
        "ok": not problems,
        "id": manifest["id"],
        "version": manifest["version"],
        "api": manifest["api"],
        "sha256": pack_sha256(pack) if pack.path.is_dir() else sha256_file(pack.path),
        "stages": [
            {
                "stage": s.kind,
                "file": s.file,
                "label": s.label,
                # naga-wasm exposes no IR, so the CLI's expression count is not
                # available here; texture reads are counted at call sites.
                "texture_reads": len(TEXTURE_READ.findall(strip_comments(s.source))),
            }
            for s in stages
        ],
        "runtime": runtime,
        "problems": [
            {"file": p.file, "line": p.line, "column": p.column, "message": p.message}
            for p in problems
        ],
    }
    return out


def translate_variants(pack: Pack, stage: dict, kind: str) -> list[dict]:
    """The stage with its options at their defaults, minimums and maximums.

    `check::translate` runs naga's `process_overrides` for each set; naga-wasm
    exposes no override step, so each `override` is rewritten to a `const` of
    the same type and value, which is the same module after substitution.
    """
    options = pack.manifest["options"]
    sets = {"defaults": {}, "minimums": {}, "maximums": {}}
    for o in options:
        sets["defaults"][o["id"]] = o["default"]
        if o["type"] == "float":
            sets["minimums"][o["id"]] = o["min"]
            sets["maximums"][o["id"]] = o["max"]
        elif o["type"] == "int":
            sets["minimums"][o["id"]] = o["min"]
            sets["maximums"][o["id"]] = o["max"]
        elif o["type"] == "bool":
            sets["minimums"][o["id"]] = False
            sets["maximums"][o["id"]] = True
        else:
            sets["minimums"][o["id"]] = 0
            sets["maximums"][o["id"]] = len(o["values"]) - 1
    source = compose_with_entries(pack, kind, stage["file"])
    out = []
    for name, values in sets.items():
        text = source
        for oid, value in values.items():
            literal = (
                "true" if value is True else "false" if value is False
                else f"{float(value):.9g}" if isinstance(value, float) else f"{value}"
            )
            text = re.sub(
                rf"\boverride\s+{re.escape(oid)}\s*:\s*[A-Za-z0-9_<>]+\s*=[^;]*;",
                f"const {oid}: {next(o['wgsl_type'] for o in options if o['id'] == oid)} = {literal};",
                text,
            )
        if "override" in strip_comments(text):
            continue  # a stray override with its own default is fine at runtime only
        out.append({"name": f"{kind}:{stage['file']}:{name}", "source": text, "translate": True})
    return out


def runtime_module(kind: str, source: str, horizon: Path) -> str | None:
    terrain = horizon / "crates/horizon-client-render/src/terrain.wgsl"
    if not terrain.is_file():
        return None
    text = terrain.read_text()
    if kind == "material":
        return (
            source
            + "\n// Horizon's terrain (terrain.wgsl)\n"
            + prefixed(section(text, "struct Globals {", "// Sky (SkyRenderer)"), "horizon_terrain_")
            + MATERIAL_ENTRIES_RUNTIME
        )
    sky = "".join(
        [
            section(text, "struct Globals {", "@group(0) @binding(1)"),
            section(text, "fn linear_fog(", "fn apply_fog("),
            section(text, "struct SkyOut {", "// rendertype_lines"),
        ]
    )
    return source + "\n// Horizon's sky (terrain.wgsl)\n" + prefixed(sky, "horizon_sky_") + SKY_PACK_ENTRY


def section(source: str, start: str, end: str) -> str:
    from_at = source.index(f"\n{start}") + 1
    to_at = from_at + source[from_at:].index(f"\n{end}") + 1
    return source[from_at:to_at]


def declared(text: str) -> list[str]:
    names = []
    for line in text.splitlines():
        if not line or line[0].isspace():
            continue
        rest = line
        while rest.startswith("@"):
            cut = rest.find(" ")
            rest = rest[cut:].lstrip() if cut != -1 else ""
        found = None
        for key in ("fn ", "struct ", "const ", "override ", "var "):
            if rest.startswith(key):
                found = rest[len(key):]
                break
        if found is None and rest.startswith("var<"):
            after = rest[4:]
            gt = after.find(">")
            found = after[gt + 1:].lstrip() if gt != -1 else None
        if found is not None:
            cut = len(found)
            for i, ch in enumerate(found):
                if not (ch.isascii() and (ch.isalnum() or ch == "_")):
                    cut = i
                    break
            names.append(found[:cut])
    return names


def prefixed(text: str, prefix: str) -> str:
    names = set(declared(text))
    out = []
    word = ""

    def flush():
        nonlocal word
        if word in names:
            out.append(prefix)
        out.append(word)
        word = ""

    for ch in text:
        if ch.isascii() and (ch.isalnum() or ch == "_"):
            word += ch
        else:
            flush()
            out.append(ch)
    flush()
    return "".join(out)


# --- naga bridge ------------------------------------------------------------
def naga_run(modules: list[dict]) -> tuple[dict, str | None]:
    tools = Path(__file__).resolve().parent
    node = shutil.which("node")
    if node is None:
        return {"ok": False, "error": "node is not installed, so naga cannot run"}, "no node"
    proc = subprocess.run(
        [node, str(tools / "naga.mjs")],
        input=json.dumps({"modules": modules}),
        text=True,
        capture_output=True,
        cwd=tools,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()[:2000]
        return {"ok": False, "error": f"naga bridge failed: {detail}"}, detail
    results = json.loads(proc.stdout)["results"]
    failed = next((r for r in results if not r["ok"]), None)
    if failed is not None:
        return failed, None
    return results[-1] if results else {"ok": True}, None


# --- packaging --------------------------------------------------------------
def pack_bytes(pack: Pack) -> bytes:
    """`Pack::package`: the files in path order, fixed dates, 0o644."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(pack.files):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            info.create_system = 3
            z.writestr(info, pack.files[name])
    return buf.getvalue()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def pack_sha256(pack: Pack) -> str:
    return sha256_bytes(pack_bytes(pack))


# --- self-test --------------------------------------------------------------
def self_test(horizon: Path | None) -> int:
    failures = 0

    def check(name: str, ok: bool, detail: str = ""):
        nonlocal failures
        print(f"  {'ok  ' if ok else 'FAIL'} {name}{'' if ok else ': ' + detail}")
        if not ok:
            failures += 1

    print("prelude transcription")
    # WGSL uniform layout: verify the field list against the published offsets.
    align = {"f32": (4, 4), "u32": (4, 4), "i32": (4, 4), "vec2<f32>": (8, 8),
             "vec3<f32>": (16, 12), "vec4<f32>": (16, 16), "mat4x4<f32>": (16, 64)}
    offset = 0
    computed = []
    for name, ty in FRAME_FIELDS:
        a, size = align[ty]
        offset = (offset + a - 1) // a * a
        computed.append((name, offset))
        offset += size
    total = (offset + 15) // 16 * 16
    check("Frame has 28 fields", len(FRAME_FIELDS) == 28, str(len(FRAME_FIELDS)))
    check("Frame offsets match docs/api/shaders-reference.md",
          computed == FRAME_OFFSETS_DOC,
          f"{[(a, b) for a, b in zip(computed, FRAME_OFFSETS_DOC) if a != b]}")
    check("Frame size is 400 bytes", total == 400, str(total))
    trivial = "\nfn post(input: PostInput) -> vec4<f32> { return input.color; }\n"
    check("the post prelude validates", naga_run([{"name": "prelude", "source": prelude("post") + trivial + POST_ENTRIES}])[0]["ok"])
    trivial_sky = "\nfn sky(input: SkyInput) -> vec4<f32> { return input.color; }\n"
    check("the sky prelude validates", naga_run([{"name": "prelude-sky", "source": prelude("sky") + trivial_sky + SKY_ENTRIES}])[0]["ok"])
    trivial_mat = "\nfn material(input: MaterialInput) -> Surface { return Surface(input.albedo); }\n"
    check("the material prelude validates", naga_run([{"name": "prelude-mat", "source": prelude("material") + trivial_mat + MATERIAL_ENTRIES}])[0]["ok"])

    print("known-good packs from the Horizon tree")
    samples = [
        Path("crates/horizon-shader-api/packs/golden_hour"),
        Path("crates/horizon-shader-api/tests/samples/schema-1"),
        Path("crates/horizon-shader-api/templates/post"),
        Path("crates/horizon-shader-api/templates/sky"),
        Path("crates/horizon-shader-api/templates/material"),
    ]
    if horizon is None:
        print("  (skipped: pass --horizon PATH for the Horizon checkout)")
    else:
        for sample in samples:
            path = horizon / sample
            if not path.is_dir():
                check(str(sample), False, "missing")
                continue
            # the templates hold {{id}} placeholders, which are not a pack yet
            if "{{" in (path / MANIFEST).read_text():
                continue
            pack, problems = read_pack(path)
            if pack is None:
                check(str(sample), False, "; ".join(str(p) for p in problems))
                continue
            report = check_pack(pack, translate=True, horizon=horizon)
            check(str(sample), report["ok"], "; ".join(p["message"] for p in report["problems"]))

        print("known-bad packs are refused")
        import tempfile
        ok_post = "fn post(input: PostInput) -> vec4<f32> { return input.color; }\n"
        cases = {
            "no stage": "schema = 1\nid='x'\nname='X'\nversion='1'\napi='0.1'\n",
            "wrong api": "schema = 1\nid='x'\nname='X'\nversion='1'\napi='0.2'\n[[post]]\nfile='p.wgsl'\n",
            "bad id": "schema = 1\nid='X y'\nname='X'\nversion='1'\napi='0.1'\n[[post]]\nfile='p.wgsl'\n",
            "nine passes": "schema = 1\nid='x'\nname='X'\nversion='1'\napi='0.1'\n"
            + "".join(f"[[post]]\nfile='p{i}.wgsl'\n" for i in range(9)),
            "unused option": "schema = 1\nid='x'\nname='X'\nversion='1'\napi='0.1'\n[[post]]\nfile='p.wgsl'\n"
            "[[options]]\nid='k'\nname='K'\ntype='float'\ndefault=1.0\nmin=0.0\nmax=2.0\n",
        }
        # Packs whose manifest is fine but whose WGSL is not: the check has to
        # reach naga, not stop at the manifest.
        manifest_ok = (
            "schema = 1\nid='x'\nname='X'\nversion='1'\napi='0.1'\n"
            "[[post]]\nfile='p.wgsl'\n")
        code_cases = {
            # The exact bug this harness caught in the pack during development.
            "a vec3 passed to scalar smoothstep":
                "fn post(input: PostInput) -> vec4<f32> {\n"
                "    let x = smoothstep(0.3, 1.0, vec3<f32>(0.5));\n"
                "    return vec4<f32>(x);\n}\n",
            "a wrong return type":
                "fn post(input: PostInput) -> vec4<f32> { return input.color.rgb; }\n",
            "a missing stage function":
                "fn grade(input: PostInput) -> vec4<f32> { return input.color; }\n",
            "an entry point of its own":
                ok_post + "@fragment fn mine() -> @location(0) vec4<f32> { return vec4(1.0); }\n",
            "a binding of its own":
                ok_post + "@group(3) @binding(9) var extra: vec4<f32>;\n",
            "an undeclared option override":
                "override gain: f32;\n" + ok_post,
            # 70 distinct reads: naga counts IR expressions, so a read inside a
            # loop is one of them and would not exceed the limit.
            "a texture read past the limit":
                "fn post(input: PostInput) -> vec4<f32> {\n"
                "    var c = input.color;\n"
                + "".join(
                    f"    c += textureSampleLevel(previous, linear_sampler, input.uv + vec2<f32>({i}.0, 0.0), 0.0);\n"
                    for i in range(70))
                + "    return c;\n}\n",
        }
        for name, code in code_cases.items():
            with tempfile.TemporaryDirectory() as tmp:
                d = Path(tmp)
                (d / MANIFEST).write_text(manifest_ok.replace("id='x'", "id='bad'"))
                (d / "p.wgsl").write_text(code)
                pack, _ = read_pack(d)
                report = None if pack is None else check_pack(pack, translate=False, horizon=None)
                check(name, pack is None or not report["ok"])

        for name, text in cases.items():
            with tempfile.TemporaryDirectory() as tmp:
                d = Path(tmp)
                (d / MANIFEST).write_text(text)
                for i in range(9):
                    (d / f"p{i}.wgsl").write_text(ok_post)
                pack, _ = read_pack(d)
                report = None if pack is None else check_pack(pack, translate=False, horizon=None)
                check(name, pack is None or not report["ok"])

    print(f"\n{failures} failure(s)")
    return 1 if failures else 0


# --- CLI --------------------------------------------------------------------
def print_report(r: dict):
    what = f"{r['id']} {r['version']} (shader API {r['api']})" if r["id"] else r["path"]
    if not r["ok"]:
        print(f"{what}: FAILED")
        for p in r["problems"]:
            loc = f"{p['file']}:{p['line']}:{p['column']}" if p["line"] else p["file"]
            print(f"  {loc}: {p['message']}")
        return
    print(f"{what}: ok")
    for s in r["stages"]:
        print(f"  {s['stage']:<9} {s['label']:<28} {s['texture_reads']:>6} texture reads")
    for rt in r["runtime"]:
        if rt.get("ok") is False:
            print(f"  runtime {rt['stage']}: FAILED {rt['error']}")
        elif "translate" in rt:
            backends = rt["translate"] or {}
            ok = all(v["ok"] for v in backends.values())
            print(f"  {rt['stage']:<9} {rt['file']:<28} translate {'ok' if ok else 'FAILED'}")
    if r["sha256"]:
        print(f"  sha256 {r['sha256']}")


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    command, rest = argv[0], argv[1:]
    horizon = None
    if "--horizon" in rest:
        horizon = Path(rest[rest.index("--horizon") + 1]).resolve()
        i = rest.index("--horizon")
        del rest[i:i + 2]

    if command == "self-test":
        return self_test(horizon)
    if command in ("check", "pack"):
        positional = [a for a in rest if not a.startswith("--")]
        flags = {a for a in rest if a.startswith("--")}
        if not positional:
            print(__doc__)
            return 2
        if command == "pack":
            out = None
            if "--out" in rest:
                out = Path(rest[rest.index("--out") + 1])
            pack, problems = read_pack(Path(positional[0]).resolve())
            if pack is None:
                for p in problems:
                    print(p, file=sys.stderr)
                return 1
            report = check_pack(pack, translate=True, horizon=horizon)
            if not report["ok"]:
                print_report(report)
                print(f"error: {positional[0]} failed the check", file=sys.stderr)
                return 1
            data = pack_bytes(pack)
            target = out or Path(positional[0]).with_name(
                f"{pack.manifest['id']}-{pack.manifest['version']}.{EXTENSION}")
            target.write_bytes(data)
            print_report(report)
            print(f"Wrote {target} (sha256 {sha256_bytes(data)})")
            return 0
        results = []
        for path in positional:
            pack, problems = read_pack(Path(path).resolve())
            if pack is None:
                results.append({
                    "path": path, "ok": False, "id": None, "version": None, "api": None,
                    "sha256": None, "stages": [], "runtime": [],
                    "problems": [{"file": p.file, "line": p.line, "column": p.column,
                                  "message": p.message} for p in problems],
                })
            else:
                results.append(check_pack(pack, translate="--translate" in flags, horizon=horizon))
        if "--json" in flags:
            print(json.dumps(results, indent=2))
        else:
            for r in results:
                print_report(r)
        failed = sum(1 for r in results if not r["ok"])
        if failed:
            print(f"error: {failed} of {len(results)} packs failed the check", file=sys.stderr)
            return 1
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
