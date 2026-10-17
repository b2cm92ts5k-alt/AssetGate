# Asset Gate

[ภาษาไทย](README.th.md)

**Check 3D models for games — in Blender, then in Unity — and fix what is wrong before it reaches your game or the Unity Asset Store.**

Made for people who model by hand or generate models with AI (Meshy, Tripo, and so on) and want a repeatable check instead of a manual checklist.

| Gate | Where | Checks |
|---|---|---|
| 1 | Blender add-on | Broken mesh, intersecting faces, normals, transforms, triangulation, pivot, names, materials, UVs, texel density, texture size, baked lighting, FBX settings, polygon count |
| 2 | Unity tool | Import settings, separate materials, URP/Lit shader and texture slots, smoothness, surface type, prefab, collider, LOD, color space, standard test scene + screenshot, console |
| 3 | Unity tool + web page | Pack folders, path length, demo scene, README, notices, unused files, store images, store page drafts (Store mode only) |

**Two modes:** **Game** for models in your own game (Gate 1 + 2) · **Store** for packs you sell on the Unity Asset Store (Gate 1 + 2 + 3).

## Features

- One **Check** button in each program; results say what failed and how to fix it
- **Fix buttons** for most failures — they show what will change first, Ctrl+Z works in Blender, and original textures are never overwritten
- **Confirm** buttons for advice that depends on your work (e.g. intersecting parts on purpose, a pivot at a hinge) — not everything is a fixed rule
- **Export to Unity** from Blender: sends the FBX and PNG textures into your Unity project (folders are created for you) and converts metallic-roughness for URP
- **Setup** in Unity: import settings, URP materials with the right texture slots, prefab and collider in one click
- Polygon count advice by model type and platform
- English and Thai
- Nothing is sent over the internet — the parts talk through JSON files in a local Data folder

## Requirements

- Blender **4.2+** (tested on 4.5 and 5.2)
- Unity **6 (6000.0)+** with **URP** (tested on 6000.3 and 6000.5)
- Chrome or Edge for the web page (Store mode only)

## Install

**Blender** — download `asset_gate-1.0.0.zip` from Releases → Edit > Preferences > Get Extensions → arrow menu → **Install from Disk…** → in the 3D Viewport press N → **Asset Gate** tab.

**Unity** — Window > Package Manager → **+** → **Install package from git URL…**

```
https://github.com/b2cm92ts5k-alt/AssetGate.git?path=/unity/com.etlolz.assetgate
```

Then open **Tools > Asset Gate > Open Window**.

**Web page** (Store mode) — open `web/index.html` in Chrome or Edge.

## Quick start

1. Blender: pick your **Unity project** in the panel once
2. Enter a **Folder** and **Model** name → **Check** → fix what fails, confirm what you have reviewed
3. **Export to Unity** (the FBX field can stay empty the first time)
4. Unity: select the FBX in `Assets/<Folder>/Meshes` → **Setup** → **Check**
5. Store mode: **Check Pack**, then open the web page and choose `<Unity project>/AssetGate`

Full guide, including every check and how to fix it: **[docs/MANUAL.en.md](docs/MANUAL.en.md)**

## Repository layout

| Folder | What |
|---|---|
| `blender_addon/asset_gate/` | Blender extension (Gate 1, Export to Unity) |
| `unity/com.etlolz.assetgate/` | Unity Editor package (Gate 2–3) |
| `web/index.html` | Gate 3 page — single file, no build step |
| `config/default.config.json` | Default thresholds (copied to the Data folder on first use) |
| `schema/` | JSON Schemas for reports, confirmations, state and config |
| `tests/` | Blender, Unity batch and web tests |
| `tools/` | Build and validation scripts |
| `docs/` | Manuals |

## Build and test (for contributors)

```bash
python tools/build_addon.py
```

```bash
"<blender.exe>" -b --factory-startup --python tests/blender/run_tests.py -- <empty folder>
```

```bash
node --test tests/web/logic.test.mjs
```

```bash
python tools/validate_schemas.py
```

The Unity batch test and the code rules are in [CONTRIBUTING.md](CONTRIBUTING.md).

## License

- Blender add-on: **GPL-3.0-or-later**
- Unity tool, web page and the rest: **Asset Gate Free License** — free for any work including commercial work; you may share it for free; you may not sell the tool itself

Models and packs you make are yours. Details: [LICENSE.md](LICENSE.md).

[Changelog](CHANGELOG.md)
