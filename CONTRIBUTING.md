# Contributing

Thanks for helping. Bug reports and pull requests are welcome — please open an issue first for larger changes.

## Rules the code follows

- **Check ids never change** (`m1-1` … `k3-10`). New checks get new ids; retired checks keep their id.
- **Thresholds live in `config/default.config.json`**, never in code. After changing it run `python tools/build_addon.py` (it also copies the config into the Unity package).
- **The three parts only talk through JSON files in the Data folder.** Blender writes `*.blender.json` / `*.blender.confirms.json`; Unity writes `*.unity.json` / `*.unity.confirms.json` / `*.unity.store.json` / screenshots; the web page writes `state.json`.
- **Check is read-only.** Only Export to Unity, Setup and Fix buttons change files, and only when the user presses them.
- **Unknown = `pending` or `review`**, never `pass`.
- **Schemas:** do not remove or rename fields; add fields with a version bump, and update `schema/`.
- **Every UI text in both languages:** `blender_addon/asset_gate/i18n.py` and `unity/com.etlolz.assetgate/Editor/Lang.cs`.

## Tests

Blender (run on a supported Blender version, with an empty output folder):

```bash
"<blender.exe>" -b --factory-startup --python tests/blender/run_tests.py -- <empty folder>
```

Web page logic:

```bash
node --test tests/web/logic.test.mjs
```

Schemas and language tables:

```bash
python tools/validate_schemas.py
```

```bash
python tests/unity/check_lang.py
```

Unity batch test — use a **copy** of a URP project at a short path (Windows path length limit):

1. Copy `Assets`, `Packages` and `ProjectSettings` of a URP project to e.g. `%TEMP%\agu`
2. Add the package (`unity/com.etlolz.assetgate`) to the copy's `Packages/manifest.json` as a `file:` dependency
3. Put `tests/unity/AssetGateBatchTest.cs` in the copy's `Assets/Editor`
4. Run:

```bash
Unity.exe -batchmode -projectPath <copy> -executeMethod AssetGateBatchTest.Run -logFile <log> -quit -agData <data folder> -agOut <result.json> -agFbx <Assets/...fbx>
```

Every automatic check needs a passing case and a deliberately broken case in the tests.
