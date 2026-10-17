"""Validate the default config and every schema example.

Files under schema/examples/<name>/valid must pass <name>.schema.json,
files under schema/examples/<name>/invalid must be rejected.

Usage: python tools/validate_schemas.py [report.json ...]
Extra paths are validated against the report schema (e.g. reports written by the add-on),
or the confirms / store schema when the name ends with .confirms.json / .store.json.
"""
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = ROOT / "schema"
EXAMPLES_DIR = SCHEMA_DIR / "examples"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def validator_for(name):
    schema = load(SCHEMA_DIR / f"{name}.schema.json")
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def first_error(validator, path):
    errors = sorted(validator.iter_errors(load(path)), key=lambda e: list(e.absolute_path))
    if not errors:
        return None
    e = errors[0]
    where = "/".join(str(p) for p in e.absolute_path) or "(root)"
    return f"{where}: {e.message}"


def main(extra_reports=()):
    # date-time needs an optional dependency; without it the format is silently not checked
    if "date-time" not in FormatChecker.checkers:
        print("ERROR: date-time format checker missing (pip install -r requirements-dev.txt)")
        return 2

    failures = 0
    cases = [("config", ROOT / "config" / "default.config.json", True)]
    for schema_path in sorted(SCHEMA_DIR.glob("*.schema.json")):
        name = schema_path.name.removesuffix(".schema.json")
        for expected, folder in ((True, "valid"), (False, "invalid")):
            for path in sorted((EXAMPLES_DIR / name / folder).glob("*.json")):
                cases.append((name, path, expected))

    def schema_of(p):
        return "confirms" if p.endswith(".confirms.json") else "store" if p.endswith(".store.json") else "report"
    cases += [(schema_of(p), Path(p).resolve(), True) for p in extra_reports]

    validators = {}
    for name, path, expect_valid in cases:
        validator = validators.setdefault(name, validator_for(name))
        error = first_error(validator, path)
        ok = (error is None) == expect_valid
        failures += not ok
        label = "OK  " if ok else "FAIL"
        want = "valid" if expect_valid else "rejected"
        detail = f" <- {error}" if error else ""
        shown = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.name
        print(f"{label} {shown} (expect {want}){detail}")

    print(f"\n{len(cases) - failures}/{len(cases)} as expected")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
