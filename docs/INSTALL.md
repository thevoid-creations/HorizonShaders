# Installing Horizon Aurora

Two minutes, no tools, no other software. The pack works with the Horizon you
install from [playhorizon.dev](https://playhorizon.dev) through the Horizon
launcher — **no modified build, no launcher mod, no patched game files.**

## The short version

1. Start Horizon and get into a world (the pack draws on the world, not on the
   title screen).
2. **Esc → Options → Horizon Settings... → Shader Packs...**
3. Press **Open Pack Folder** at the bottom of that page.
4. Copy **`Horizon-Aurora.hshader`** into the folder that opened.
5. Go back one page (**Done**) and open **Shader Packs...** again so the list
   refreshes. **Horizon Aurora (Horizon): OFF** appears.
6. Click it. The chat says the pack loaded, the line reads **ON**, and the world
   is graded.
7. Click it again to turn it off; Horizon goes back to its vanilla renderer
   immediately.

Everything in that list is a real control in Horizon's own UI:
`Options → Horizon Settings...` is `Page::Horizon`, `Shader Packs...` is
`Page::ShaderPacks`, `Open Pack Folder` is `Event::OpenShaderPackFolder` and the
pack button reads *"<name> (Horizon): ON/OFF"*
(`crates/horizon-client-render/src/options_ui.rs`).

## Where the folder actually is

The folder is `shaderpacks`, **beside `options.txt`**, in the game folder of
whichever Horizon instance you are playing
(`Game::shader_packs_dir()` in `crates/horizon-client/src/game/options.rs`
resolves `options.txt`'s directory and appends `shaderpacks`).

Because the launcher can keep several instances, the reliable answer is the one
above: let the game open the folder for you with **Open Pack Folder**. If you
prefer to do it by hand, find `options.txt` — it is in the same folder as
`saves`, `resourcepacks` and `horizon-graphics.txt` — and put a `shaderpacks`
folder next to it.

Nothing needs to be unpacked. A `.hshader` file and an unpacked pack folder are
both accepted, and a folder is the easier thing to edit.

## Checking it worked

| Signal | Meaning |
| --- | --- |
| `Shader pack Horizon Aurora 1.0.0: Sky, Terrain, Air, Grade in N ms` in the log | all four stages compiled and are running |
| Chat: `Shader pack Horizon Aurora reloaded` | a file was saved and picked up (hot reload) |
| Chat: `Shader pack <name> refused:` followed by lines | the pack failed the check; the red lines say which file, line and column |

The game refuses a pack that fails Horizon's own check *before* it draws
anything with it, so a broken download cannot leave you with a black screen: you
keep the previous look and get a message instead.

## Turning it off

Click the pack again on the **Shader Packs** page, or pick a different pack.
Turning it off drops every pipeline the pack built and returns to Horizon's
vanilla renderer.

## Windows notes

- Horizon's game folder is chosen by the launcher when it creates the instance;
  the **Open Pack Folder** button is the quickest way to it and avoids guessing
  between `%APPDATA%` and the launcher's own instance folder.
- Windows may hide the file extension. `Horizon-Aurora.hshader` must stay
  `.hshader` — if Explorer shows `Horizon-Aurora` and calls it a "Compressed
  (zipped) folder", turn on *File name extensions* in the View tab first.
- Do not let a browser turn it into `Horizon-Aurora(1).hshader` and then drop
  the other copy in too; Horizon lists both and picks one, which is confusing
  but harmless.

## macOS and Linux

Same steps; **Open Pack Folder** opens Finder or your file manager at the right
place. On Linux, a flatpak or sandboxed launcher may keep the game folder
somewhere unusual — use the button rather than hunting for it.

## For pack developers

Setting `HORIZON_SHADER_PACK=Horizon-Aurora` in the environment starts the game
with that folder or file name from `shaderpacks` and wins over the saved pick
(`crates/horizon-client/src/game/shader_packs.rs`). Saving any file of the pack
while the game runs rebuilds it within half a second; if the new version does
not compile, the chat says where and the last good version keeps drawing.

## If you want the official checker too

You do not need it to install the pack — the game runs exactly the same check
when it loads one. To run the CLI from a Horizon checkout:

```sh
cargo install --path crates/horizon-shader-api
horizon-shader check  packs/Horizon-Aurora
horizon-shader pack   packs/Horizon-Aurora --out Horizon-Aurora.hshader
```

Both should print `horizon_aurora 1.0.0 (shader API 0.1): ok` and the same
SHA-256 as `dist/SHA256SUMS`.
