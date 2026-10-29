# In-game test plan

Nothing in this project has been seen on a GPU. These are the checks that only
you can do, in an order that isolates one failure at a time. Fifteen minutes for
the essentials; the last section is for when something looks wrong.

Before you start: Horizon installed through the launcher, one world loaded (the
pack draws on the world, not the title screen), and `Horizon-Aurora.hshader`
from `dist/`.

## 1. The pack is discovered

1. **Options → Horizon Settings... → Shader Packs...**
2. Expected: **Horizon Aurora (Horizon): OFF** in the list, with
   **Horizon Aurora Lite** beside it.

If the list is empty, the file is not where the game looks: press **Open Pack
Folder** and check it is in *that* folder (it is `shaderpacks`, next to
`options.txt`). Both packs appear under their manifest names, not their file
names.

## 2. It compiles and runs

3. Click **Horizon Aurora**. Expected: the button reads **ON**; the chat may say
   `Shader pack Horizon Aurora reloaded` if it was already running.
4. Look in the log (`latest.log` beside `options.txt`) for:
   `shader pack horizon_aurora 1.0.0: Sky, Terrain, Air, Grade in N ms`.

If instead the chat shows red `Shader pack ... refused:` lines, the stage that
failed and the file:line:column are in them — that is a real failure and worth
reporting. A refused pack is never drawn, so the game stays playable.

## 3. The look is there

Stand somewhere open, in clear weather, around noon:

| # | Look at | Expected with Aurora | What it would mean if not |
| --- | --- | --- | --- |
| 5 | straight up | a deeper blue than vanilla, still blue not teal | sky stage not running |
| 6 | the horizon | land that is slightly cooler and hazier the further it is | air pass not running |
| 7 | grass and leaves | a little richer green, not neon | material stage not running |
| 8 | water | deeper, colder blue; still transparent | water treatment not applied |
| 9 | the whole picture | more contrast and colour, no crushed blacks, no white sky | grade not running |

### 3b. The 2.0 screen-space effects

Each of these is one pass, so one constant in `common.wgsl` turns it off and
tells you instantly whether it is the pass that is misbehaving.

| # | Look at | Expected | If wrong, the constant to test |
| --- | --- | --- | --- |
| 9a | **inside a cave, or a corner between walls and floor** | the corners are darker and the cave reads as a shape; no grey halo around silhouettes | `AURORA_AO_STRENGTH` → `0.0` |
| 9b | **a lake, looking across it with the sun behind you** | the far shore, hills and sky are reflected in the water; the reflection fades out toward the horizon and never appears on stone | `AURORA_REFLECT` → `0.0` |
| 9c | **the sun over a ridge or through a canopy** | soft shafts of light fan across the view, tinted gold when the sun is low | `AURORA_RAYS` → `0.0` |
| 9d | **lava, a torch, the sun disc** | a soft halo; grass and stone do **not** glow | `AURORA_BLOOM` → `0.0` |
| 9e | **water at any time of day** | the surface ripples and sparkles when it faces the sun, and goes still-looking when you face away | `AURORA_WAVES` → `0.0` |

Two things that mean "this is working as designed", not a bug: the reflection
disappears when the reflected thing is off screen (screen-space reflections
cannot see behind the camera), and the contact shadows never extend far from the
geometry that casts them (they are not shadow maps).

Compare honestly: toggle the pack **off** and **on** while standing still
(step 12 below does this). The change should be obvious in the sky and in
contrast, and subtle but real everywhere else.

## 4. Sunset and night

10. `/time set 13000` in clear weather. Expected: the sky around the sun goes
    warm gold, not fluorescent orange; the opposite horizon stays blue; the sun
    disc and clouds keep their shape instead of blowing out to white.
11. `/time set 18000`. Expected: a cold, gently blue night sky, stars visible,
    dark ground still readable (not black). Caves with a torch should look
    exactly as they do without the pack — that is deliberate.

## 5. Turning it off restores vanilla

12. Click the pack again → **OFF**. Expected: the world returns to vanilla's
    look immediately, with no leftover tint, no stuck pass and the same frame
    rate as before you installed it. Toggle several times quickly; nothing
    should flicker or leak.

## 6. Changing something changes the picture

13. With the pack **ON**, open `shaderpacks/Horizon-Aurora/common.wgsl` in a
    text editor and change
    `const AURORA_SATURATION: f32 = 1.085;` to `0.20;`.
14. Save. Within about half a second the chat says
    `Shader pack Horizon Aurora reloaded` and the world turns nearly grey.
15. Change it back and save again.

This is the honest equivalent of an options screen: Horizon builds packs with
their options at defaults today, so the pack declares none and is tuned through
constants that hot reload.

## 7. A broken edit is reported, not fatal

16. Add a deliberate syntax error — delete a `;` from a line — and save.
17. Expected: the chat shows `Shader pack Horizon-Aurora refused:` with the
    file, line and column. **The world keeps drawing the last good version.**
    The game does not crash and the screen does not go black.
18. Fix the line and save; the pack comes back by itself.

## 8. Resizing and fullscreen

19. Resize the window, then press F11 for fullscreen, then back. Expected: no
    stretching, no smear, no black frame, and the vignette stays circular — the
    grade's corner falloff is corrected for aspect ratio.
20. Change **Video Settings → Render Distance** and the GUI scale. Expected: the
    aerial perspective stretches with the view distance (Aurora scales its haze
    by `frame.render_distance`), and the HUD does not change colour at all — the
    hand and HUD are drawn after the pack's passes.

## 9. Cost

21. Press **F3** while the pack runs. Expected: the overlay lists a GPU time for
    each pass — `Sky`, `Contact shading`, `Water reflections`, `Sun shafts`,
    `Bloom`, `Air`, `Grade` — as a median of the last 15 timed frames; the total
    should be within the pack's declared budget of 4.0 ms on a mid-range GPU.
    Timing waits for no frame, so it does not slow the game.
22. If the total is above ~5 ms or you drop frames, switch to **Horizon Aurora
    Lite** (two passes instead of six, no screen-space effects) and compare. If
    you want to keep the look but not the cost, set the four screen-space
    constants in `common.wgsl` to `0.0` one at a time and watch the F3 numbers.

## 10. The other dimensions and the interface

23. `/execute in the_nether run tp @s ~ ~ ~`. Expected: the Nether looks
    vanilla apart from the grade — the pack's sky stage deliberately does not
    touch it.
24. Open the inventory and pause menu. Expected: HUD, icons and menus are
    unchanged in colour. (Menus blur the world underneath, which still shows
    the pack's grade.)

## 11. The lighter variant

25. Turn Aurora off and **Horizon Aurora Lite** on. Expected: the same sky,
    terrain and grade, with flatter distance fog. If Aurora ran well, Lite is an
    option, not an upgrade.

## If something looks wrong

Work out which stage is responsible by taking the others out. Copy the pack
folder, edit the copy's `horizon-shaders.toml` to keep one stage at a time
(`[sky]`, `[material]` or a single `[[post]]`), save, and reload. A pack with
only `[sky]` tells you instantly whether a washed-out horizon is the sky or the
air pass. Send the stage that misbehaves along with the log lines from step 4.

## Reporting a problem usefully

Include: the Horizon version (title screen), the OS, the GPU, the lines from
step 4 or 17 verbatim, which of steps 5–9 looked wrong, and — if you can — a
screenshot with the pack on and off from the same spot and time of day.
