// naga 30.0.1 (the exact validator Horizon's `horizon-shader check` uses,
// compiled to WebAssembly) behind a JSON pipe, so validate_pack.py can parse,
// validate and translate WGSL without a Rust toolchain.
//
// stdin:  { modules: [ { name, source, translate } ] }
// stdout: { naga, results: [ { name, ok, error, spirv_words, msl, hlsl } ] }
//
// `translate` writes the module for Vulkan (SPIR-V), Metal (MSL) and
// DirectX 12 (HLSL), as `horizon_shader_api::check::translate` does.
import { parseWgsl, validate, writeSpirv, writeMsl, writeHlsl, nagaVersion } from "naga-wasm";

const chunks = [];
for await (const chunk of process.stdin) chunks.push(chunk);
const input = JSON.parse(Buffer.concat(chunks).toString("utf8"));

const results = [];
for (const module of input.modules ?? []) {
  const out = { name: module.name, ok: false };
  let handle;
  try {
    handle = parseWgsl(module.source);
  } catch (e) {
    out.error = `parse: ${e.formatted ?? e.message}`;
    results.push(out);
    continue;
  }
  let info;
  try {
    info = validate(handle);
  } catch (e) {
    out.error = `validation: ${e.formatted ?? e.message}`;
    results.push(out);
    continue;
  }
  out.ok = true;
  if (module.translate) {
    out.translate = {};
    for (const [backend, write] of [
      ["Vulkan (SPIR-V)", () => writeSpirv(handle, info)],
      ["Metal", () => writeMsl(handle, info)],
      ["DirectX 12 (HLSL)", () => writeHlsl(handle, info)],
    ]) {
      try {
        const written = write();
        out.translate[backend] = {
          ok: true,
          bytes: typeof written === "string" ? written.length : written.length * 4,
        };
      } catch (e) {
        out.translate[backend] = { ok: false, error: e.formatted ?? e.message };
      }
    }
    // A translation failure is a pack problem, exactly as in the Rust check.
    for (const [backend, r] of Object.entries(out.translate)) {
      if (!r.ok) {
        out.ok = false;
        out.error = `${backend} refuses it: ${r.error}`;
      }
    }
  }
  handle?.free?.();
  info?.free?.();
  results.push(out);
}

process.stdout.write(JSON.stringify({ naga: nagaVersion, results }));
