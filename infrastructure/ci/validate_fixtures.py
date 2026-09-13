#!/usr/bin/env python3
"""Validate example and shipped-pack manifests against schema/*.schema.json.

Run via: uv run --with jsonschema --with pyyaml python3 infrastructure/ci/validate_fixtures.py
"""
import glob
import json
import sys

import yaml
from jsonschema import Draft202012Validator

SCHEMA_MAP = {
    "pack.yaml": "schema/pack.schema.json",
    "pack.json": "schema/pack.schema.json",
    "artist.yaml": "schema/artist.schema.json",
    "artist.json": "schema/artist.schema.json",
    "feed.yaml": "schema/feed.schema.json",
}


def main() -> int:
    validators = {
        fname: Draft202012Validator(json.load(open(path)))
        for fname, path in SCHEMA_MAP.items()
    }

    ok = True
    fixtures = sorted(
        glob.glob("examples/**/*.yaml", recursive=True)
        + glob.glob("packs/**/*.json", recursive=True)
    )
    if not fixtures:
        print("no manifests found under examples/ or packs/ -- failing closed")
        return 1

    for path in fixtures:
        fname = path.rsplit("/", 1)[-1]
        validator = validators.get(fname)
        if validator is None:
            print(f"SKIP {path} (no schema mapped for filename {fname!r})")
            continue
        doc = yaml.safe_load(open(path))
        errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
        if errors:
            ok = False
            print(f"FAIL {path}")
            for error in errors:
                print(f"   - {list(error.path)}: {error.message}")
        else:
            print(f"OK   {path}")

    print("ALL VALID" if ok else "VALIDATION ERRORS")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
