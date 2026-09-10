#!/usr/bin/env python3
"""Seed a v2 state questionnaire from today's aggregated output (AS-4249).

Parity becomes structural instead of something to chase: run today's aggregation for a
(practiceArea, jurisdiction) pair and write the resolved output *as* the state questionnaire —
buckets, labels, helper text, order and required-ness. The AS-4242 diff harness then starts green
and every subsequent diff is deliberate.

Three things the resolved output supplies, and where each comes from:

  tree        `flare_questionnaire` / `flare_bucket` / `flare_subBucket` become the
              sections -> buckets -> subBuckets tree. A datapoint with no `flare_questionnaire`
              lands in GENERAL, which is what every questionnaire authored today does.
  order       DERIVED, never authored. `createGlobalOrder` walks `$defs` key order (honouring
              `flare_targetProperty`), keeps the fields the forms in play actually use, then
              RENUMBERS them 1..N — so order is relative to the form union, not to `$defs`.
              Reproduced here from data-collection-utils.ts:429-527.
  presentation / required
              layered `$defs` first, then each form's inline copy on top in --form-key order,
              because today's `aggregateFormSchemas` lets form-inline annotations win (design
              doc 3.1). `flare_required` lives almost entirely on forms, not on `$defs`.

Where two forms annotate one field differently, the last --form-key wins and the disagreement is
reported. Those are audience variants, not typos — see the design doc's measured blast radius.
Byte-identical parity is proven by the harness, not asserted here.

Dry-run by default: prints the summary and writes the document to --out. --apply upserts it.

  ./seed_state_questionnaire.py --out /tmp/immigration-us-fed.json
  ./seed_state_questionnaire.py --apply --mongo-uri "$MONGODB_STAGING_URI"
"""
import argparse
import json
import logging
import sys
from collections import Counter, defaultdict
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

# flare_* key -> questionnaire presentation field. Bucketing and order are deliberately absent:
# bucketing is the tree, order is the datapoint's own `order`. Per
# docs/architecture/data-collection-v2-flare-inventory.md.
PRESENTATION_KEYS = {
    "flare_displayName": "displayName",
    "flare_attorneyDisplay": "attorneyDisplay",
    "flare_beneficiaryDisplay": "beneficiaryDisplay",
    "flare_clientHelperText": "clientHelperText",
    "flare_beneficiaryHelperText": "beneficiaryHelperText",
    "flare_guidance": "guidance",
    "flare_validationMessage": "validationMessage",
    "flare_format": "format",
    "flare_hidden": "hidden",
    "flare_countKey": "countKey",
}
DEFAULT_SECTION = "GENERAL"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


def global_order(defs: dict) -> list[str]:
    """Field names in $defs key order, honouring flare_targetProperty (createGlobalOrder)."""
    result, seen = [], set()
    for def_name, def_value in defs.items():
        field = def_name
        if isinstance(def_value, dict) and def_value.get("flare_targetProperty"):
            field = def_value["flare_targetProperty"]
        if field not in seen:
            seen.add(field)
            result.append(field)
    return result


def resolve_annotations(
    defs: dict, forms: list[dict]
) -> tuple[dict[str, dict], dict[str, dict[str, set]]]:
    """Layer $defs then each form's inline copy, form-inline winning. Also collect disagreements.

    Returns (annotations by field, {field: {flare_key: {values seen}}} for keys two forms differ on).
    """
    annotations: dict[str, dict] = {}
    seen_values: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))

    for def_name, def_value in defs.items():
        if not isinstance(def_value, dict):
            continue
        field = def_value.get("flare_targetProperty") or def_name
        annotations.setdefault(field, {}).update(
            {key: value for key, value in def_value.items() if key.startswith("flare_")}
        )

    for form in forms:
        for field, property_schema in (form["schema"].get("properties") or {}).items():
            if not isinstance(property_schema, dict):
                continue
            inline = {key: value for key, value in property_schema.items() if key.startswith("flare_")}
            for key, value in inline.items():
                if isinstance(value, (str, int, float, bool)) or value is None:
                    seen_values[field][key].add(value)
            annotations.setdefault(field, {}).update(inline)

    disagreements = {
        field: {key: values for key, values in keys.items() if len(values) > 1}
        for field, keys in seen_values.items()
    }
    return annotations, {field: keys for field, keys in disagreements.items() if keys}


def build_data_points(annotations: dict[str, dict], order: dict[str, int]) -> tuple[list[dict], Counter]:
    """One entry per ordered field: (section, bucket, subBucket, datapoint), plus skip counts."""
    entries, skipped = [], Counter()

    for field, position in sorted(order.items(), key=lambda item: item[1]):
        flare = annotations.get(field, {})
        bucket, sub_bucket = flare.get("flare_bucket"), flare.get("flare_subBucket")
        if not bucket:
            skipped["no flare_bucket"] += 1
            continue
        if not sub_bucket:
            skipped["no flare_subBucket"] += 1
            continue

        presentation = {
            name: flare[key] for key, name in PRESENTATION_KEYS.items() if flare.get(key) is not None
        }
        data_point = {"name": field, "order": position}
        if presentation:
            data_point["presentation"] = presentation
        if flare.get("flare_required") is not None:
            data_point["required"] = bool(flare["flare_required"])

        entries.append((flare.get("flare_questionnaire") or DEFAULT_SECTION, bucket, sub_bucket, data_point))

    return entries, skipped


def build_sections(entries: list[tuple[str, str, str, dict]]) -> list[dict]:
    """Nest the entries into sections -> buckets -> subBuckets, first-seen order throughout.

    Entries arrive in computed order, so first-seen ordering places each node at its earliest
    member — the same global order today's output has.
    """
    sections: dict[str, dict[str, dict[str, list[dict]]]] = {}
    for section, bucket, sub_bucket, data_point in entries:
        sections.setdefault(section, {}).setdefault(bucket, {}).setdefault(sub_bucket, []).append(data_point)

    return [
        {
            "name": section,
            "buckets": [
                {
                    "name": bucket,
                    "subBuckets": [
                        {"name": sub_bucket, "dataPoints": data_points}
                        for sub_bucket, data_points in sub_buckets.items()
                    ],
                }
                for bucket, sub_buckets in buckets.items()
            ],
        }
        for section, buckets in sections.items()
    ]


def seed(args: argparse.Namespace) -> dict:
    """Fetch today's output for the pair and return the state-questionnaire document."""
    properties_schema = get(
        args.base_url, f"/data-collection/data-schemas/{args.data_schema_id}/properties-schema"
    )
    defs = properties_schema.get("$defs") or {}
    if not defs:
        sys.exit(f"data schema {args.data_schema_id} has no $defs — nothing to derive order from")

    all_forms = get(args.base_url, f"/data-collection/forms?dataSchemaId={args.data_schema_id}")
    by_key = {form["key"]: form for form in all_forms["forms"]}
    missing = [key for key in args.form_keys if key not in by_key]
    if missing:
        sys.exit(f"forms not found on {args.base_url} for schema {args.data_schema_id}: {missing}")
    forms = [by_key[key] for key in args.form_keys]

    annotations, disagreements = resolve_annotations(defs, forms)

    # Order is renumbered over the fields the forms in play actually use, not over all of $defs.
    in_play = {field for form in forms for field in (form["schema"].get("properties") or {})}
    ordered = [field for field in global_order(defs) if field in in_play]
    order = {field: index + 1 for index, field in enumerate(ordered)}

    unordered = sorted(in_play - set(order))
    if unordered:
        log.warning("%d form fields are absent from $defs and get no order: %s", len(unordered), unordered[:10])

    entries, skipped = build_data_points(annotations, order)
    sections = build_sections(entries)

    log.info("%d fields in play, %d ordered, %d seeded", len(in_play), len(order), len(entries))
    for reason, count in skipped.items():
        log.warning("skipped %d fields: %s — bucketing them would be authoring, not seeding", count, reason)
    log.info(
        "tree: %s",
        {section["name"]: sum(len(sb["dataPoints"]) for b in section["buckets"] for sb in b["subBuckets"]) for section in sections},
    )
    log.info("buckets: %s", sorted({b["name"] for s in sections for b in s["buckets"]}))
    log.info(
        "subBuckets: %d distinct",
        len({sb["name"] for s in sections for b in s["buckets"] for sb in b["subBuckets"]}),
    )
    written = sum(1 for _, _, _, dp in entries if "required" in dp)
    log.info(
        "required written on %d of %d datapoints, %d of them true — advisory, nothing gates on it",
        written,
        len(entries),
        sum(1 for _, _, _, dp in entries if dp.get("required")),
    )

    if disagreements:
        log.warning("%d fields are annotated differently by two forms; last --form-key wins", len(disagreements))
        for field, keys in list(disagreements.items())[:10]:
            log.warning("  %s: %s", field, {key: sorted(map(str, values)) for key, values in keys.items()})

    return {
        "key": args.key,
        "name": args.name,
        "dataSchemaId": args.data_schema_id,
        "practiceArea": args.practice_area,
        "jurisdiction": args.jurisdiction,
        "status": args.status,
        "sections": sections,
    }


def apply(document: dict, mongo_uri: str, db_name: str) -> None:
    """Upsert the questionnaire by key. Only the seeded fields are written."""
    from bson import ObjectId
    from pymongo import MongoClient

    payload = {**document, "dataSchemaId": ObjectId(document["dataSchemaId"])}
    with MongoClient(mongo_uri) as client:
        result = client[db_name]["questionnaires"].update_one(
            {"key": document["key"]}, {"$set": payload}, upsert=True
        )
    log.info(
        "upserted %s: matched=%d modified=%d upserted_id=%s",
        document["key"],
        result.matched_count,
        result.modified_count,
        result.upserted_id,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--data-schema-id", default=DOCOLOCO_SCHEMA_ID)
    parser.add_argument(
        "--form-key",
        action="append",
        dest="form_keys",
        help="form whose inline annotations win, repeatable; later keys win on conflict",
    )
    parser.add_argument("--key", default="immigration-us-fed", help="questionnaire key (upsert identity)")
    parser.add_argument("--name", default="Immigration US-FED")
    parser.add_argument("--practice-area", default="IMMIGRATION", choices=["IMMIGRATION", "FAMILY"])
    parser.add_argument("--jurisdiction", default="US-FED", help="opaque string, not a state enum")
    parser.add_argument("--status", default="DRAFT", choices=["DRAFT", "ACTIVE"])
    parser.add_argument("--out", type=Path, help="write the seeded document here")
    parser.add_argument("--apply", action="store_true", help="upsert into Mongo (default is dry-run)")
    parser.add_argument("--mongo-uri", help="required with --apply")
    parser.add_argument("--db", default="data-collection")
    args = parser.parse_args()

    args.form_keys = args.form_keys or PILOT_FORMS
    if args.apply and not args.mongo_uri:
        parser.error("--apply needs --mongo-uri")

    document = seed(args)

    if args.out:
        args.out.write_text(json.dumps(document, indent=2, sort_keys=False) + "\n")
        log.info("wrote %s", args.out)

    if not args.apply:
        log.info("dry run — nothing written to Mongo. Re-run with --apply --mongo-uri to seed.")
        return

    if args.status == "ACTIVE":
        log.warning("status=ACTIVE is the enablement act for this pair — publishing, not just authoring")
    apply(document, args.mongo_uri, args.db)


def demo() -> None:
    """Self-check: order renumbers over the form union, and form-inline text wins over $defs."""
    defs = {
        "firstName": {"flare_bucket": "CLIENT", "flare_subBucket": "PERSONAL_DETAILS", "flare_displayName": "First"},
        "unusedByAnyForm": {"flare_bucket": "CLIENT", "flare_subBucket": "PERSONAL_DETAILS"},
        "lastNameDef": {
            "flare_targetProperty": "lastName",
            "flare_bucket": "CLIENT",
            "flare_subBucket": "PERSONAL_DETAILS",
        },
        "noBucket": {"flare_displayName": "Orphan"},
    }
    forms = [
        {"schema": {"properties": {"firstName": {"flare_displayName": "First name", "flare_required": True}}}},
        {
            "schema": {
                "properties": {
                    "lastName": {"flare_displayName": "Last name"},
                    "firstName": {"flare_displayName": "Given name"},
                    "noBucket": {"flare_displayName": "Orphan"},
                }
            }
        },
    ]

    annotations, disagreements = resolve_annotations(defs, forms)
    # flare_targetProperty maps the def onto the field name it really annotates.
    assert annotations["lastName"]["flare_bucket"] == "CLIENT", annotations["lastName"]
    # Form-inline wins over $defs, and the last form wins over the first.
    assert annotations["firstName"]["flare_displayName"] == "Given name"
    assert disagreements["firstName"]["flare_displayName"] == {"First name", "Given name"}

    in_play = {field for form in forms for field in form["schema"]["properties"]}
    ordered = [field for field in global_order(defs) if field in in_play]
    # unusedByAnyForm is dropped and the rest renumber 1..N — order is not the $defs index.
    assert ordered == ["firstName", "lastName", "noBucket"], ordered
    order = {field: index + 1 for index, field in enumerate(ordered)}
    assert order["lastName"] == 2, order

    entries, skipped = build_data_points(annotations, order)
    assert skipped["no flare_bucket"] == 1, skipped
    assert [entry[3]["name"] for entry in entries] == ["firstName", "lastName"]
    assert entries[0][3] == {
        "name": "firstName",
        "order": 1,
        "presentation": {"displayName": "Given name"},
        "required": True,
    }, entries[0][3]
    # No flare_questionnaire anywhere, so everything lands in GENERAL.
    sections = build_sections(entries)
    assert [section["name"] for section in sections] == ["GENERAL"]
    assert len(sections[0]["buckets"][0]["subBuckets"][0]["dataPoints"]) == 2
    print("demo ok")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
    else:
        main()
