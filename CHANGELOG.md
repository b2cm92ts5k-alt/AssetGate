# Changelog

## 1.0.0 — first public release

### Blender add-on (Gate 1)
- Blender Extension format (`blender_manifest.toml`), Blender 4.2+
- Checks m1-1 … m1-16, including m1-13 baked lighting and m1-16 polygon count advice by type and platform
- Fix buttons with a preview window; Ctrl+Z works; textures written as new files, originals kept
- Confirm buttons for advice items; confirmations reset when values change
- Export to Unity: FBX + PNG textures, folders created, metallic-roughness converted to metallic-smoothness, asks before overwriting
- Game / Store modes; English / Thai with re-check on language switch
- Data folder defaults to `<Unity project>/AssetGate`

### Unity tool (Gate 2–3)
- Unity 6 (6000.0)+, URP; install from git URL
- Setup: import settings, URP/Lit materials, texture slots, prefab, collider
- Checks m2-1 … m2-12, m3-1 … m3-8, m4-1 … m4-4 (Store mode), pack checks k1/k3
- Fix buttons (Setup, pack folders, demo scene, README, notices, unused files to trash)
- Polygon count box, Clear button, store info section

### Web page (Gate 3)
- Gate 3 only; packs and models read from reports
- English / Thai
- Store page drafts (technical details, AI disclosure), store image checks
