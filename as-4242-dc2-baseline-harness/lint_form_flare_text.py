#!/usr/bin/env python3
"""Form-text lint for data-collection v2 (AS-4242).

Reports which forms still carry presentation `flare_*` annotations inline on their own property
copies, grouped by data schema. That set is the blast radius of the precedence flip (form-inline
annotations stop winning over the schema layer), and afterwards it is the cleanup backlog.

Also reports disagreements: one property annotated with different values by two forms of the same
schema. Those cannot be resolved by the schema layer alone and need a questionnaire override.
"""
import argparse
import json
import logging
from collections import defaultdict
from pathlib import Path
from api import DEFAULT_BASE_URL, get

DOCOLOCO_SCHEMA_ID = "66dee37286565b000812bb21"

# Questionnaire-owned keys per docs/architecture/data-collection-v2-flare-inventory.md.
# flare_displayOrder is excluded: it is derived from $defs order, never authored on a form.
PRESENTATION_KEYS = (
    "flare_displayName",
    "flare_attorneyDisplay",
    "flare_clientHelperText",
    "flare_guidance",
    "flare_validationMessage",
    "flare_format",
    "flare_beneficiaryDisplay",
    "flare_beneficiaryHelperText",
    "flare_hidden",
    "flare_subBucket",
    "flare_bucket",
    "flare_countKey",
    "flare_questionnaire",
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def walk(schema: dict, path: str = ""):
    """Yield (property path, property object) for every property in a form schema."""
    for name, prop in (schema.get("properties") or {}).items():
        if not isinstance(prop, dict):
            continue
        current = f"{path}.{name}" if path else name
        yield current, prop
        yield from walk(prop, current)
        items = prop.get("items")
        if isinstance(items, dict):
            yield from walk(items, f"{current}[]")
    for branch in schema.get("allOf") or []:
        if isinstance(branch, dict):
            yield from walk(branch, path)


def lint(forms: list[dict]) -> tuple[dict, dict]:
    """Return per-form key counts and per-property value disagreements across the forms."""
    per_form: dict[str, dict[str, int]] = {}
    values: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))

    for form in forms:
        counts: dict[str, int] = defaultdict(int)
        for path, prop in walk(form.get("schema") or {}):
            for key in PRESENTATION_KEYS:
                if key in prop:
                    counts[key] += 1
                    values[(path, key)][json.dumps(prop[key], sort_keys=True)].add(form["key"])
        per_form[form["key"]] = dict(counts)

    disagreements = {
        f"{path} / {key}": {value: sorted(keys) for value, keys in variants.items()}
        for (path, key), variants in values.items()
        if len(variants) > 1
    }
    return per_form, disagreements


def report(schema_id: str, per_form: dict, disagreements: dict) -> str:
    """Render the lint result as markdown."""
    lines = [f"# Form-text lint — data schema `{schema_id}`", ""]
    annotated = {key: counts for key, counts in per_form.items() if counts}
    lines.append(f"- forms: {len(per_form)}")
    lines.append(f"- forms carrying presentation `flare_*` inline: {len(annotated)}")
    lines.append(f"- properties with cross-form value disagreements: {len(disagreements)}")
    lines += ["", "## Per form", "", "| form | " + " | ".join(k.replace("flare_", "") for k in PRESENTATION_KEYS) + " |"]
    lines.append("|" + "---|" * (len(PRESENTATION_KEYS) + 1))
    for key, counts in sorted(annotated.items(), key=lambda item: -sum(item[1].values())):
        lines.append(f"| `{key}` | " + " | ".join(str(counts.get(k, "")) for k in PRESENTATION_KEYS) + " |")

    lines += ["", "## Disagreements", ""]
    if not disagreements:
        lines.append("None.")
    for name, variants in sorted(disagreements.items()):
        lines.append(f"- **{name}**")
        for value, forms in variants.items():
            lines.append(f"  - `{value[:120]}` — {', '.join(forms)}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--data-schema-id", default=DOCOLOCO_SCHEMA_ID)
    parser.add_argument("--form-key", action="append", dest="form_keys", default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    forms = get(args.base_url, f"/data-collection/forms?dataSchemaId={args.data_schema_id}")["forms"]
    if args.form_keys:
        forms = [form for form in forms if form["key"] in args.form_keys]
    logging.info("linting %d forms", len(forms))

    per_form, disagreements = lint(forms)
    output = report(args.data_schema_id, per_form, disagreements)
    if args.out:
        args.out.write_text(output)
        logging.info("wrote %s", args.out)
    else:
        print(output)


if __name__ == "__main__":
    main()
