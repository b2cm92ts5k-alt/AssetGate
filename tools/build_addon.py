"""Package the Blender add-on as a Blender extension: dist/asset_gate-<version>.zip (Blender 4.2+).

The zip holds the add-on files and blender_manifest.toml at its root, plus config/default.config.json.
The same config is copied into the Unity package (its first-run default, SPEC D18).

Usage: python tools/build_addon.py
Install in Blender: Edit > Preferences > Get Extensions > (menu) Install from Disk.
Check the result with: blender --command extension validate dist/asset_gate-<version>.zip
"""
import re
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "blender_addon" / "asset_gate"
MANIFEST = SOURCE / "blender_manifest.toml"


def version():
    match = re.search(r'^version\s*=\s*"([^"]+)"', MANIFEST.read_text(encoding="utf-8"), re.MULTILINE)
    return match.group(1)


def main():
    output = ROOT / "dist" / f"asset_gate-{version()}.zip"
    output.parent.mkdir(exist_ok=True)
    # Every entry gets the build time: Blender only reloads an installed add-on when the
    # timestamp of its __init__.py changes, even if only another module was edited.
    stamp = time.localtime()[:6]
    files = [(path, path.relative_to(SOURCE).as_posix()) for path in sorted(SOURCE.rglob("*.py"))]
    files.append((MANIFEST, "blender_manifest.toml"))
    files.append((ROOT / "config" / "default.config.json", "default.config.json"))
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, name in files:
            zf.writestr(zipfile.ZipInfo(name, date_time=stamp), path.read_bytes(), zipfile.ZIP_DEFLATED)
        names = zf.namelist()
    print(f"{output.relative_to(ROOT).as_posix()}: {len(names)} files")
    for name in names:
        print("  " + name)
    unity_config = ROOT / "unity" / "com.etlolz.assetgate" / "default.config.json"
    unity_config.write_bytes((ROOT / "config" / "default.config.json").read_bytes())
    print(f"{unity_config.relative_to(ROOT).as_posix()}: copied")


if __name__ == "__main__":
    main()
