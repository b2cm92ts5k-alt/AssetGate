"""Static check of the Unity tool's strings (Lang.cs), runnable without Unity.

Every Lang.T("key") used in the Editor scripts must exist, English and Thai must have the
same {0} placeholders, and English text must not contain Thai.
Usage: python tests/unity/check_lang.py
"""
import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "unity" / "com.etlolz.assetgate" / "Editor"
THAI = re.compile("[฀-๿]")
PAIR = re.compile(r'\{ "([\w.\-]+)", new\[\] \{ "((?:[^"\\]|\\.)*)",\s*"((?:[^"\\]|\\.)*)" \} \}')
USE = re.compile(r'Lang\.T\("([\w.\-]+)"')
PLACEHOLDER = re.compile(r"\{\d\}")


def main():
    pairs = {k: (en, th) for k, en, th in PAIR.findall((SRC / "Lang.cs").read_text(encoding="utf-8"))}
    used = set()
    for f in SRC.glob("*.cs"):
        used |= set(USE.findall(f.read_text(encoding="utf-8")))
    titles = {"title." + i for i in re.findall(r'"(m[23]-\d+)"', (SRC / "GateChecks.cs").read_text(encoding="utf-8"))}
    titles |= {"title." + i for i in re.findall(r'"(k\d-\d+)"', (SRC / "PackChecks.cs").read_text(encoding="utf-8"))}
    statuses = {"status." + s for s in ("pass", "fail", "review", "na", "pending")}

    problems = []
    used = {k for k in used if not k.endswith(".")}   # "status." + s, "title." + id are covered below
    problems += [f"missing key: {k}" for k in sorted((used | titles | statuses) - set(pairs))]
    problems += [f"placeholders differ: {k}" for k, (en, th) in pairs.items()
                 if sorted(PLACEHOLDER.findall(en)) != sorted(PLACEHOLDER.findall(th))]
    problems += [f"Thai in English text: {k}" for k, (en, _) in pairs.items() if THAI.search(en)]
    for f in SRC.glob("*.cs"):
        if f.name == "Lang.cs":
            continue
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if THAI.search(line):
                problems.append(f"Thai text outside Lang.cs: {f.name}:{n}")

    shipped = SRC.parent / "default.config.json"
    source = SRC.parents[2] / "config" / "default.config.json"
    if not shipped.exists() or shipped.read_bytes() != source.read_bytes():
        problems.append("unity/com.etlolz.assetgate/default.config.json differs from config/default.config.json — run python tools/build_addon.py")
    print(f"{len(pairs)} strings, {len(used)} used keys, {len(titles)} titles")
    for p in problems:
        print("FAIL", p)
    print("OK" if not problems else f"{len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
