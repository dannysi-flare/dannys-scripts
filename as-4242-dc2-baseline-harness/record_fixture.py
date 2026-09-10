#!/usr/bin/env python3
"""Record a fixture for the data-collection v2 resolved-output harness.

Fetches the properties schema of a data schema plus the named forms and writes them as one
gzipped fixture. Keep it outside any repo — it is ~1.5MB of real schema.

Then, in a vinny worktree:
  DC2_FIXTURE=<path> UPDATE_BASELINE=1 npx jest resolved-output.recorded   # record the baseline
  DC2_FIXTURE=<path> npx jest resolved-output.recorded                     # compare
"""
import argparse
import gzip
import json
import logging
import sys
from pathlib import Path
from api import DEFAULT_BASE_URL, get

DOCOLOCO_SCHEMA_ID = "66dee37286565b000812bb21"
PILOT_FORMS = [
    "IMM-I-130",
    "IMM-AOS",
    "IMM-I-90",
    "mini-q:IMM-I-130-beneficiary",
    "mini-q:beneficiary-aos",
]
FORM_FIELDS = ("key", "name", "dataSchemaId", "versionId", "schema")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def record(base: str, data_schema_id: str, form_keys: list[str], out_path: Path) -> None:
    """Write the gzipped fixture for one data schema and its forms."""
    properties_schema = get(base, f"/data-collection/data-schemas/{data_schema_id}/properties-schema")
    forms = get(base, f"/data-collection/forms?dataSchemaId={data_schema_id}")["forms"]
    by_key = {form["key"]: form for form in forms}

    missing = [key for key in form_keys if key not in by_key]
    if missing:
        sys.exit(f"forms not found on {base} for schema {data_schema_id}: {missing}")

    fixture = {
        "recordedFrom": base,
        "dataSchemaId": data_schema_id,
        "propertiesSchema": properties_schema,
        "forms": [{field: by_key[key][field] for field in FORM_FIELDS} for key in form_keys],
    }
    payload = gzip.compress(json.dumps(fixture).encode(), 9)
    out_path.write_bytes(payload)
    logging.info(
        "wrote %s (%d KB) — %d defs, %d forms",
        out_path,
        len(payload) // 1024,
        len(properties_schema.get("$defs") or {}),
        len(form_keys),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--data-schema-id", default=DOCOLOCO_SCHEMA_ID)
    parser.add_argument("--form-key", action="append", dest="form_keys", default=None)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path.home()
        / "src/vinny/apps/data-requests-ms/src/data-requests-aggregator/baseline/fixture.json.gz",
    )
    args = parser.parse_args()
    if not args.out.parent.is_dir():
        sys.exit(f"missing output directory: {args.out.parent}")
    record(args.base_url, args.data_schema_id, args.form_keys or PILOT_FORMS, args.out)


if __name__ == "__main__":
    main()
