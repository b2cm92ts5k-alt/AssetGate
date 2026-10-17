# Asset Gate Manual (English)

[ภาษาไทย](MANUAL.th.md) · [README](../README.md)

Asset Gate checks 3D models before they go into a game, whether you modelled them yourself or generated them with AI. It checks in 3 gates:

| Gate | Where | What it checks |
|---|---|---|
| Gate 1 | Blender | Mesh, UVs, textures, names, pivot, and the FBX file before it goes to Unity |
| Gate 2 | Unity | Import settings, URP materials, prefab, collider, test scene |
| Gate 3 | Unity + web page | Whether the whole pack is ready to sell on the Unity Asset Store (Store mode only) |

---

## Contents

1. [Pick the mode for your work](#1-pick-the-mode-for-your-work)
2. [Install](#2-install)
3. [First-time setup](#3-first-time-setup)
4. [Workflow from start to finish](#4-workflow-from-start-to-finish)
5. [The Asset Gate panel in Blender](#5-the-asset-gate-panel-in-blender)
6. [The Asset Gate window in Unity](#6-the-asset-gate-window-in-unity)
7. [The web page (Gate 3)](#7-the-web-page-gate-3)
8. [Every check: what it is and how to fix it](#8-every-check-what-it-is-and-how-to-fix-it)
9. [Rules vs advice you can confirm](#9-rules-vs-advice-you-can-confirm)
10. [Fix buttons](#10-fix-buttons)
11. [The Data folder and the files the tools write](#11-the-data-folder-and-the-files-the-tools-write)
12. [Common problems](#12-common-problems)

---

## 1. Pick the mode for your work

| Mode | For | Gates |
|---|---|---|
| **Game** (default) | Models you make or generate for your own game | Gate 1 + 2, no web page needed |
| **Store** | Asset packs you sell on the Unity Asset Store | Gate 1 + 2 + 3, plus the web page for the whole pack |

Set the mode in both the Blender panel and the Unity window (keep them the same). In Game mode the store checks (m4-1…m4-4) show as "N/A" and the pack check (Gate 3) is turned off.

---

## 2. Install

### Requirements
- **Blender 4.2 or later** (tested with 4.5 and 5.2)
- **Unity 6 (6000.0) or later** with a project that uses **URP** (tested with 6000.3 and 6000.5)
- **Chrome or Edge** for the web page (Store mode only)

### Blender add-on
1. Download `asset_gate-<version>.zip` from the repo's Releases page
2. Blender → **Edit > Preferences > Get Extensions** → arrow button at the top right → **Install from Disk…** → pick the zip
3. In the 3D Viewport press **N** → **Asset Gate** tab

> Installed a version before 1.0 (the old `asset_gate.zip` add-on)? Remove it first in **Preferences > Add-ons**, restart Blender, then install. Your settings (Unity project, Data folder) need to be set again.

### Unity package
1. Open your Unity (URP) project
2. **Window > Package Manager** → **+** button → **Install package from git URL…**
3. Enter `https://github.com/b2cm92ts5k-alt/AssetGate.git?path=/unity/com.etlolz.assetgate` and press Install
   - No git on your computer: download the repo as a zip, then use **Install package from disk…** and pick `unity/com.etlolz.assetgate/package.json`
4. Open the window from **Tools > Asset Gate > Open Window**

### Web page (Store mode only)
Open `web/index.html` in Chrome or Edge (download it from the repo; nothing to install).

---

## 3. First-time setup

The three parts talk through the **Data folder**, which holds every check result. By default it is **`<Unity project>/AssetGate`** (outside `Assets`, so Unity does not import it).

| Where | What to set |
|---|---|
| Blender | Pick the **Unity project** once (the field appears in the panel while it is empty, or set it in Preferences > Add-ons > Asset Gate) |
| Unity | Nothing — it uses `<this project>/AssetGate` |
| Web page | Press **Choose Data folder** and pick `<Unity project>/AssetGate` |

**Preferences > Add-ons > Asset Gate (Blender)**

| Field | What it does |
|---|---|
| Language | Language of the panel and of check results (English / ไทย) |
| Use | Game / Store |
| Unity project | Unity project folder that **Export to Unity** delivers files into (the folder that contains `Assets`) |
| Data folder (optional) | **Leave empty** for the default · fill it in only to keep results somewhere else — then pick the same folder in the Unity window too (**Browse…** button) |

> The Blender panel always shows a **"Data folder: …"** line. It must match the **Data folder** line in the Unity window. If they differ, Unity cannot find the Blender results (Unity tells you this is the cause).

---

## 4. Workflow from start to finish

1. **Blender** — open the model file, enter the **Folder** (pack name) and **Model**, then press **Check**
2. Fix what failed (with a fix button or by hand), and press **Confirm** on items waiting for your review after you have looked at them
3. Press **Export to Unity** — it checks again and, if nothing fails, sends the FBX + textures to `Assets/<Folder>/Meshes` and `Assets/<Folder>/Textures` (folders are created for you)
4. **Unity** — switch to Unity and let it import, select the FBX in `Assets/<Folder>/Meshes`, press **Setup** (import settings + materials + prefab), then press **Check**
5. Fix what failed, and confirm items waiting for review
6. **(Store mode)** Check every model of the pack the same way → right-click the pack folder **Asset Gate > Check Pack** → open the web page to see Gate 3 for the whole pack

Changed the model after sending it? Just press **Export to Unity** again (it asks before overwriting), then **Setup** and **Check** again in Unity.

---

## 5. The Asset Gate panel in Blender

![Asset Gate panel in Blender](images/blender-panel-polycount.png)

### Top — settings

| Part | Description |
|---|---|
| English / ไทย | Language — switching re-runs the check so results show in the new language right away |
| Game / Store | Mode (see [section 1](#1-pick-the-mode-for-your-work)) |
| Data folder: … | Where results are kept — must match the Unity window |
| Folder (Game mode) / Pack (Store mode) | Folder name under `Assets/` that files are sent to, e.g. `Frostpunk Settlement Kit` → `Assets/Frostpunk Settlement Kit/Meshes/…` · **the folders are created when you press Export to Unity** |
| Model | Model name = FBX file name in Unity · may be left empty (then the FBX file name or the .blend file name is used) |
| FBX | **Leave it empty on the first check** — m1-14 then shows "not checked yet", which is normal · Export to Unity fills in the path of the file in Unity for you · **no need to clear it before sending again** · fill it in yourself only to check an FBX you exported by hand |
| Type / Platform | Optional — makes the polygon count advice (m1-16) fit your work · saved in the .blend file |
| **Check** | Checks Gate 1 on the open scene (does not change the scene or save the file) · if the FBX field is set, checks that file too, and saves results to the Data folder |
| **Export to Unity** | Checks → if nothing fails, sends the FBX + PNG textures into the Unity project and saves the results · the project must be open in Unity (6000.0 or later) · asks before overwriting files |

### Results

- **Summary box** — whether Gate 1 passes, with counts of failed · waiting for review · confirmed · passed
- **Each check** can be folded/unfolded · failed and waiting items are at the top · passed items are folded into "Passed / N/A"
- **Numbers in a check** — numbers shown as buttons (e.g. intersecting faces) enter Edit Mode and select those parts so you can see them (like 3D-Print Toolbox) · if you edit the mesh after checking, press Check again first
- **Fix buttons** — a tool icon = safe · ⚠ + "Fixing by hand is recommended" = has a risk · every button opens a window first that says what it will change (see [section 10](#10-fix-buttons))
- **Confirm — I checked this / Undo confirmation** — for items waiting for review · a confirmation is dropped by itself if a new check gives different values for that item
- **How to fix by hand** — checks without a fix button tell you how to fix them yourself
- **"Results are out of date after Undo/Redo"** — after Ctrl+Z / Ctrl+Shift+Z, fix and confirm buttons are hidden until you press Check again

![Window shown before a fix](images/blender-fix-dialog.png)

![A confirmed item moves to the passed group](images/blender-confirmed.png)

---

## 6. The Asset Gate window in Unity

Open it from **Tools > Asset Gate > Open Window** · or right-click a file in the Project window → **Asset Gate > Setup Model / Check Model / Check Pack**

| Part | Description |
|---|---|
| Language | English / ไทย — switching re-runs the check |
| Use | Game / Store (keep it the same as Blender) |
| Data folder / Browse… | Usually nothing to choose (uses `<project>/AssetGate`) · choose one only if Blender uses another folder |
| **Setup** | Select the FBX (or its prefab) in `Assets/<Pack>/Meshes`, then press: sets model and texture import settings, creates URP/Lit materials with the textures in the right slots, converts metallic-roughness to metallic-smoothness (if it was not converted on export), creates the prefab + Box Collider · safe to press again (updates what it made) · only touches that model's files |
| **Check** | Checks Gate 2 of the selected model (read-only) · takes a standard-view screenshot into the Data folder |
| **Check Pack** (Store mode) | Select the pack folder or a file in it, then press — checks the Unity part of Gate 3 |
| **Clear** | Clears the messages and results shown (e.g. after removing a model from the project) |

**Results**
- Summary box · failed items at the top · confirmed items show "Confirmed"
- **Polygon count box** — triangles and vertices in Unity with the same advice as Blender (Unity shows more vertices than Blender; that is normal, because Unity splits vertices at UV seams and hard edges) · the pack check shows totals for the whole pack
- **Fix buttons** below items that can be fixed · items that cannot be fixed show advice
- **Confirm / Undo confirmation** below items waiting for review
- **Where the model came from (Store mode)** — "Generator / plan", "Made on", "What you changed by hand" → press **Save and check again** · used by m4-1…m4-4 and for the AI disclosure draft on the web page
- **Open screenshot** — opens the standard-view screenshot

---

## 7. The web page (Gate 3)

Store mode only · open `web/index.html` → **Choose Data folder** → packs and models appear by themselves from the check results (nothing to add by hand) · the page re-reads results every 3 seconds, or press **Reload**

| Part | Description |
|---|---|
| English / ไทย | Language of the page (results written by Blender/Unity are in the language used when checking) |
| Pack bar | Pick a pack · shows how many models fully pass |
| Pack info | Unity version tested (used in the drafts) · **Max triangles per model** (Blender uses it for m1-15) · notes |
| Pack summary | Table of every model: triangles, texture size, Gate 1, Gate 2, progress, what is still open and which program to fix it in |
| Store page drafts (English) | **Technical details** from real numbers (k1-8) and **AI disclosure** from "What you changed by hand" in Unity (k1-7) — copy into the store page, then correct as needed |
| Store page images | Put images in `<Data folder>/marketing/<Pack>/` named `icon.png`, `card.png`, `cover.png`, `social.png`, `screenshot_01.png`… sizes are checked for you (k2-1…k2-5) |
| Gate 3 (A / B / C) | Every pack item · items waiting for review: press **Confirm** · items that fail on purpose: press **Accept although it fails…** and give a reason · items a machine cannot judge: **tick by hand** |
| Export JSON / Import JSON | Back up or move what you entered on the page (also reads files from checklist v2) |

---

## 8. Every check: what it is and how to fix it

Legend: **Rule** = must pass · **Confirmable** = advice; look, then confirm if it suits your work · 🔧 = has a fix button · ⚠🔧 = has a fix button with a risk; fixing by hand is recommended

### Gate 1 — Blender

#### m1-1 Broken mesh (not closed / zero size) — Rule
- **What:** non-manifold edges (holes, or more than 2 faces sharing an edge), edges between faces that point opposite ways, faces with zero area, and edges with zero length (same definitions as 3D-Print Toolbox). They cause bad shading, wrong collisions and wrong tangents in Unity.
- **Checked:** each count must be 0 · zero-size threshold = `mesh.degenerateThreshold` (0.0001 m)
- **Fix by hand:** click the number to select the bad parts → Edit Mode → Mesh > Clean Up > Degenerate Dissolve (zero size) · fill holes with Fill (F) or Grid Fill · opposite faces: Mesh > Normals > Recalculate Outside
- **Fix buttons:** 🔧 delete zero-size faces/edges · 🔧 make neighbouring faces point the same way · ⚠🔧 fill holes (may fill holes you left open on purpose)

#### m1-2 Intersecting faces — Confirmable
- **What:** faces that pass through each other in the same object · parts that overlap on purpose (e.g. a handle pushed into a shovel head) are fine · leftovers from AI or duplicated faces flicker in the game
- **Checked:** count of intersecting faces (0 = pass, more = waiting for review)
- **Fix by hand:** click the number to select and look · delete leftovers · on purpose → **Confirm**

#### m1-3 Overlapping vertices / loose parts — Rule
- **What:** vertices in the same place (cause lighting seams) and loose vertices/edges without faces (waste, and wrong bounds) · faces hidden inside the mesh are only a warning
- **Checked:** vertices closer than `mesh.mergeDistance` (0.0001 m), loose vertices, loose edges must be 0
- **Fix by hand:** Edit Mode → select all → Mesh > Merge > By Distance · Mesh > Clean Up > Delete Loose
- **Fix button:** 🔧 merge overlapping vertices + delete loose parts

#### m1-4 Face direction (normals) — Rule
- **What:** faces pointing inward are invisible or lit from the inside in Unity
- **Checked:** compared with recalculated directions; no inward faces
- **Fix by hand:** Edit Mode → select all → Shift+N (Recalculate Outside) · turn on Face Orientation in Overlays to see (blue = right, red = flipped)
- **Fix button:** 🔧 recalculate face directions (outside)

#### m1-5 Apply location/rotation/scale — Rule
- **What:** every object must have location 0, rotation 0, scale 1, otherwise size or direction is off after import into Unity
- **Fix by hand:** Object Mode → select all objects → Ctrl+A > All Transforms
- **Fix button:** 🔧 apply all transforms (the shape does not move in the world)

#### m1-6 Triangulate — Rule
- **What:** quads/ngons get split on import into Unity in a way you do not control, which can cause odd shading
- **Fix by hand:** Edit Mode → select all → Ctrl+T · do it when the model is finished (editing the shape is harder afterwards)
- **Fix button:** ⚠🔧 triangulate (quads are gone)

#### m1-7 Pivot — Confirmable
- **What:** the pivot should be at the centre of the base (the model sits on the ground without sinking or floating) · some things want it elsewhere on purpose, like a door hinge or a weapon grip
- **Checked:** distance from the pivot to the base centre (0 = pass, more = waiting for review)
- **Fix by hand:** place the 3D Cursor where you want it → Object > Set Origin > Origin to 3D Cursor, then Apply Transform
- **Fix button:** 🔧 move the base centre to the world origin (0, 0, 0) · elsewhere on purpose → **Confirm**

#### m1-8 Naming — Rule
- **What:** object, mesh, material and texture names must be English PascalCase (e.g. `ShovelHead`, `Shovel_BaseColor`), no spaces, no `.001`, and not a default name (`Cube`, `Mesh_0`, `Material`…) · these names become file names and names in Unity
- **Fix by hand:** double-click the name in the Outliner / material name field / Image Editor
- **Fix button:** ⚠🔧 rename to match the rule (shows old → new before you press) · words separated by `_` are kept so Unity can still tell texture types apart

#### m1-9 Material count — Rule (no material) / Confirmable (more than 1)
- **What:** every object needs a material · more materials means more draw calls; fine if on purpose, e.g. a transparent part
- **Fix by hand:** assign a material to every slot · combine materials by baking into one texture set (atlas)
- **Several materials on purpose** → **Confirm**

#### m1-10 UV unwrap — Rule (no UV / outside the square) / Confirmable (overlapping UVs)
- **What:** UVs must exist and stay inside the 0–1 square · overlapping UVs repeat the texture; fine on purpose (mirrored left/right, or a repeated pattern)
- **Fix by hand:** UV Editor → move/scale islands into the square · if the texture is already baked, moving UVs shifts it, so bake again
- **Fix button:** ⚠🔧 auto UV (Smart UV Project) — only for objects that have no UVs

#### m1-11 Texel density — Confirmable
- **What:** texture pixels per 1 metre of surface · when models in a pack are close to each other, they look equally sharp side by side
- **Checked:** compared with the middle value of the other models in the same pack, within `texelDensity.tolerancePercent` (25%) · no other models yet = N/A
- **Fix by hand:** scale the texture, or scale UV islands and bake again
- **Fix button:** ⚠🔧 resize textures to the pack's density — saved as new PNG files; the originals are not changed and are kept in the .blend · never larger than the original · sharper on purpose (e.g. something held close to the camera) → **Confirm**

#### m1-12 Texture size — Rule / Confirmable (differs from the pack)
- **What:** textures must be square, a size in `texture.allowedSizes` (256, 512, 1024, 2048, 4096), and all textures of this model the same size · a size different from other models in the pack is advice
- **Fix button:** ⚠🔧 resize textures to a valid size (only when it fails) · different from the pack on purpose → **Confirm** (sharpness is decided by m1-11)

#### m1-13 No baked light/shadow in the base colour — Confirmable (look with your eyes)
- **What:** AI textures often have light, shadows or highlights painted in; in a lit scene they look doubled and wrong
- **How to look:** open the base colour texture in the Image Editor · if there are some, paint them out or generate again · clean → **Confirm** (confirm again when the texture changes)

#### m1-14 FBX file — Rule
- **What:** the FBX must have: scene units Metric scale 1, axes Forward `-Z` / Up `Y`, transforms applied on export, no embedded textures, and the same objects/triangle count/size as the scene
- **Not checked yet:** normal while the FBX field is empty — Export to Unity checks this on the file it sends
- **Fails because you changed the model after sending:** press **Export to Unity** again (no need to clear the FBX field)
- **Fix button:** 🔧 export the FBX again with the right settings (only for FBX files you exported yourself)

#### m1-15 Model numbers — Rule (when a budget is set)
- **What:** triangle count, texture size, number of materials and objects · if "Max triangles per model" is set on the web page (Store mode), the model must not exceed it
- **Fix by hand:** reduce polygons with a Decimate modifier, check the shape, then apply · or raise the budget on the web page if it was set too low

#### m1-16 Polygon count fits the work — Confirmable (advice, not a rule)
- **What:** shows faces / triangles / vertices / edges / topology and what kind of work this count is usually used for
- **General levels:** ≤ 1,500 low poly · ≤ 10,000 mid poly · ≤ 100,000 high poly for games · more is not game-ready yet
- **Pick Type + Platform** in the panel to see whether it is inside / above / below the usual range (all numbers are in `config.polycount` and can be changed · sources in [POLYCOUNT.md](POLYCOUNT.md))
- **The numbers are industry ranges** — every game is different · if it suits your game → **Confirm**

### Gate 2 — Unity

| Check | Name | Kind | What is checked / how to fix |
|---|---|---|---|
| m2-1 | FBX + textures imported | Rule | The FBX and textures that Blender sent are all there · missing: press Export to Unity in Blender again · if Unity says the results are in another Data folder, make the Data folders match |
| m2-2 | Model import settings | Rule 🔧 | Scale Factor 1, Normals Import, Tangents Calculate, Mesh Compression Off, Read/Write off |
| m2-3 | Separate material files (.mat) | Rule 🔧 | Uses separate material files, not materials inside the FBX |
| m2-4 | Texture import settings | Rule 🔧 | Normal map as Normal Map, base colour sRGB on, metallic sRGB off, Max Size not smaller than the texture |
| m2-5 | Shader is URP/Lit | Rule 🔧 | Every material uses `Universal Render Pipeline/Lit` |
| m2-6 | Textures in the right slots | Rule 🔧 | Base colour → Base Map, normal → Normal Map, metallic → Metallic Map |
| m2-7 | Smoothness | Confirmable | Says where smoothness comes from · check in the screenshot that shiny/matte looks right, then confirm |
| m2-8 | Surface type | Confirmable | Opaque / Transparent compared with the base colour alpha · right → confirm |
| m2-9 | URP Asset set | Rule | **Project-wide setting (not changed for you)** — Project Settings > Graphics and every Quality level must have a URP Asset |
| m2-10 | Prefab | Rule 🔧 | A prefab with the model's name, no missing scripts/materials/meshes |
| m2-11 | Collider | Rule 🔧 / Confirmable | Has a collider whose size differs from the model by at most `collider.boundsTolerancePercent` (10%) · another collider type on purpose → check its size by eye and confirm |
| m2-12 | LOD Group | Rule | LOD meshes without a LOD Group = fail · no LOD meshes = N/A · fix in Blender (add the missing LOD meshes, or stop using LOD names) |
| m3-1 | Color space | Rule | **Project-wide setting** — Project Settings > Player > Other Settings > Color Space = Linear |
| m3-2 | Standard test scene | Rule | The same standard lighting scene for every model (camera 45°/30°, 2400×1600) |
| m3-3 | Normal map direction | Confirmable | Look at bumps in the screenshot · inverted: flip the green channel of the texture |
| m3-4 | No flickering faces (z-fighting) / broken shading | Confirmable | Look at the screenshot and the model in the scene · confirm again when the FBX changes |
| m3-5 | Scale | Confirmable | Real size in metres — check it is realistic (e.g. a door is about 2 m tall) |
| m3-6 | Pivot | Confirmable | Pivot distance from the base centre · fix in Blender (m1-7) and send again |
| m3-7 | Console messages | Rule | No errors/warnings on import and when the test scene opens · read the Console and fix the cause |
| m3-8 | Screenshot | Rule | Standard-view screenshot saved to `screenshots/<Pack>/<Model>.png` · usable for store images |
| m4-1 | Commercial rights of the generator plan | Confirmable (Store) | Fill in the tool/plan → check its current terms allow commercial use → confirm |
| m4-2 | Keep source evidence | Confirmable (Store) | Keep prompts / reference images / screenshots from generation → confirm |
| m4-3 | No one else's IP | Confirmable (Store) | The model and textures do not copy other games, brands or characters → confirm |
| m4-4 | Note what you changed | Rule (Store) | "What you changed by hand" is not empty and has been saved |

🔧 in Gate 2 = the **Fix with Setup** button (re-runs Setup for that model)

### Gate 3 — Pack (Store mode)

| Check | Name | Checked in | Kind / how to fix |
|---|---|---|---|
| k1-1 | Folders by type | Unity | Rule 🔧 — Meshes / Materials / Textures / Prefabs / Demo Scenes · button creates the missing folders |
| k1-2 | File path length | Unity | Rule — every path is at most 150 characters from `Assets/` · rename files/folders that are too long |
| k1-3 | Demo Scene | Unity | Rule 🔧 — button creates a demo scene with every prefab (the open scene is not touched) |
| k1-4 | README states URP + Unity version | Unity | Confirmable 🔧 — button creates a README from a template or adds the URP line · read the text, then confirm |
| k1-5 | Supports Unity 2022.3+ on URP | — | Tick by hand — an Asset Store requirement for your pack |
| k1-6 | Third-Party Notices | Unity | Confirmable 🔧 — button creates the file from a template · nothing from others used → confirm |
| k1-7 | AI description | Web page | Tick by hand — use the draft in "Store page drafts" |
| k1-8 | Technical description | Web page | Confirmable — use the draft from real numbers, then confirm |
| k1-9 | README / Documentation | Unity | Rule 🔧 — button creates README.txt |
| k1-10 | No one else's names/IP | — | Tick by hand |
| k2-1…k2-4 | Icon / Card / Cover / Social | Web page | Rule — exact image sizes (Social is optional) · image tips are on the web page |
| k2-5 | 5–10 screenshots | Web page | Rule — PNG, no alpha, 3:2 |
| k3-1 | Every model passes Gate 2 | Web page | Rule — the summary table shows what is open |
| k3-2 | No stale results | Web page | Rule — FBX changed after the Unity check → check in Unity again |
| k3-3…k3-5 | Consistency / new-project test / several versions | — | Tick by hand |
| k3-6 | Demo scene Console | Unity | Rule — opening the demo scene gives no errors/warnings |
| k3-7 | Unused files | Unity | Rule ⚠🔧 — button moves files no prefab/scene uses to the trash (lists them first; restorable) |
| k3-8…k3-10 | Review text / price / publisher account | — | Tick by hand |

---

## 9. Rules vs advice you can confirm

- **Rules** — things that really break if they fail (broken mesh, bad names, wrong import settings, wrong FBX) must pass · Export to Unity does not send while any Gate 1 item fails
- **Confirmable** — the tool measures, but a person decides, because it depends on your work: m1-2, m1-7, m1-9 (several materials), m1-10 (overlapping UVs), m1-11, m1-12 (differs from the pack), m1-13, m1-16, m2-7, m2-8, m2-11 (other collider types), m3-3, m3-4, m3-5, m3-6, m4-1…m4-3, k1-4, k1-6, k1-8
  - **These are not fixed rules** — if what you see suits your work, press **Confirm**
  - A confirmation is dropped by itself when that item's values change (e.g. the face count or the texture changes), so an old confirmation never vouches for new content
- **Gate 3 on the web page** has **Accept although it fails…** for items that fail on purpose (a reason is required)

---

## 10. Fix buttons

**Every fix button**
- You press it, one item at a time; nothing is fixed without asking
- A window says what will change first (Blender) or a confirm box (Unity)
- The item is checked again right after the fix
- Blender: Ctrl+Z undoes it · the .blend file is never saved for you
- Textures: always written as new files, never over the original · the original is kept in the .blend · pressing again reuses the file made before instead of making another · if the texture is packed inside the .blend, save the .blend first (new files go next to it)
- Unity: deleting = moving to the trash (restorable) · project-wide settings (URP Asset, Color space) are not changed for you

**⚠ Fixing by hand is recommended** — buttons with ⚠ work, but the result may not be what you want: filling a hole you left open on purpose, triangulating makes later shape edits harder, auto UVs are not as clean as your own unwrap · the fix does the best a machine can judge, but fixing by hand still gives the best result

---

## 11. The Data folder and the files the tools write

```
<Data folder>/                          default <Unity project>/AssetGate
  config.json                           every threshold (made from the defaults on first use; editable)
  state.json                            what you entered on the web page
  reports/<Pack>/<Model>.blender.json   Gate 1 results
  reports/<Pack>/<Model>.unity.json     Gate 2 results
  reports/<Pack>/_pack.unity.json       Gate 3 results from Unity
  reports/<Pack>/*.confirms.json        confirmations made in Blender / Unity
  reports/<Pack>/<Model>.unity.store.json  where the model came from (Store mode)
  screenshots/<Pack>/<Model>.png        standard-view screenshots
  marketing/<Pack>/                     store images you put there
```

**Export to Unity writes into the Unity project:** `Assets/<Folder>/Meshes/<Model>.fbx` and `Assets/<Folder>/Textures/*.png` (metallic-roughness textures are already converted to `_MetallicSmoothness.png`) · **Setup** adds `Materials/*.mat` and `Prefabs/<Model>.prefab`

**Change thresholds:** open `config.json` in the Data folder, e.g. `texelDensity.tolerancePercent`, `texture.allowedSizes`, `polycount` · values missing from the file fall back to the defaults

---

## 12. Common problems

| Symptom | Fix |
|---|---|
| Unity says "Blender saved the results for this FBX in another Data folder" | Make the Data folder the same in Blender and Unity (see the Data folder line in both) |
| Unity says "the Blender results are for a different FBX file" | Press Export to Unity in Blender again |
| Export to Unity: "this project is not open in Unity" | Open that project in Unity first, then press again |
| Export to Unity: version below 6000.0 | Use Unity 6 or later |
| Panel looks wrong or errors after installing a new version | Remove the old version, restart Blender, install again |
| Pink material | The project does not use URP yet (m2-9) |
| The web page cannot pick a folder | Use Chrome or Edge |

---

## Screenshots still to capture (for doc maintainers)

The images in this manual are from Blender in English. Still missing:

1. Blender panel in Thai right after install (with the Unity project picker)
2. Blender panel after a successful Export to Unity (the "Sent … files to Unity" box)
3. Unity window in Game mode after Check (with the polygon count box)
4. Unity window in Store mode, "Where the model came from" section
5. Unity window after Check Pack (with fix buttons)
6. Web page pack summary table and the store page drafts card
