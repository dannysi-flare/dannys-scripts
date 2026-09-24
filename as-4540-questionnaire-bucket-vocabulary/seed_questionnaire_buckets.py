#!/usr/bin/env python3
"""
AS-4540 - Seed data-collection.questionnairebuckets with the full bucket vocabulary.

Makes the collection the source of truth for WHICH bucket/sub-bucket/section names are legal,
so vinny's FLARE_*_VALUES consts and draft-driver's VALID_FLARE_* sets can be deleted (AS-4541,
AS-4542). Until this runs the collection is only a copy deck: 32 documents, all SUB_BUCKET, all
carrying client-facing subtitle/guidance for the CA divorce flow.

RUN ONLY AFTER the `description` field ships (vinny, AS-4540 part 1). Before that the DTO
whitelist strips it on the next edit through the API.

Source of the vocabulary: vocabulary.json in this directory, generated from
  vinny         libs/data-collection-types/src/lib/types.dto.ts
  draft-driver  src/draft_driver/pipeline/consts.py
by extract_vocabulary.py. 153 nodes - 28 BUCKET, 118 SUB_BUCKET, 7 SECTION.

What gets written:

  parentless doc missing   -> INSERT {type, name, description?, createdAt, updatedAt, __v: 0}
  parentless doc present,  -> $set description only
    no description
  parentless doc present,  -> skip, hand-set copy wins (idempotent re-runs)
    has description
  parented doc (the 32)    -> NEVER TOUCHED

Every node is seeded PARENTLESS. A parentless document is the default for its (type, name), and
name-only membership is exactly what the validation being replaced does today. The 32 existing
parented documents keep winning for their own (type, name, parent) via resolveByParent in
data-requests-ms - seeding a default alongside them changes nothing they serve.

`subtitle` and `guidance` are never written. They are client-facing copy owned by whoever wrote
those 32 documents; `description` is the AI-facing hint the prompt reads, and the two are not
interchangeable. 9 of the 153 nodes have no description in vinny's metadata and seed without one.

Default is DRY-RUN. Pass --apply to write.

Connection: reads MONGODB_STAGING_URI / MONGODB_PRODUCTION_URI from env, or --uri.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pymongo

DB = "data-collection"
COLLECTION = "questionnairebuckets"
VOCABULARY = Path(__file__).parent / "vocabulary.json"
TYPES = ("BUCKET", "SUB_BUCKET", "SECTION")


def load_vocabulary():
    nodes = json.loads(VOCABULARY.read_text())
    seen = set()
    for node in nodes:
        if node["type"] not in TYPES:
            sys.exit(f"vocabulary.json: unknown type {node['type']!r} on {node['name']!r}")
        key = (node["type"], node["name"])
        if key in seen:
            sys.exit(f"vocabulary.json: duplicate node {key}")
        seen.add(key)
    return nodes


def classify(node, existing):
    """What this run would do to one vocabulary node. `existing` is its parentless doc, or None."""
    if existing is None:
        return "insert"
    if node["description"] and not existing.get("description"):
        return "set_description"
    return "skip"


def parentless_docs(col):
    """Every parentless document, keyed by (type, name). These are the defaults this script owns."""
    cursor = col.find({"parent": None}, {"type": 1, "name": 1, "description": 1})
    return {(doc["type"], doc["name"]): doc for doc in cursor}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env", choices=["staging", "production"], default="staging")
    parser.add_argument("--uri", help="Overrides --env")
    parser.add_argument("--apply", action="store_true", help="Write. Without it, dry-run.")
    parser.add_argument("--log-dir", default=str(Path(__file__).parent))
    args = parser.parse_args()

    uri = args.uri or os.environ.get(f"MONGODB_{args.env.upper()}_URI")
    if not uri:
        sys.exit(f"No URI. Set MONGODB_{args.env.upper()}_URI or pass --uri.")

    nodes = load_vocabulary()
    mode = "APPLY" if args.apply else "DRY-RUN"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = Path(args.log_dir) / f"seed_log_{args.env}_{stamp}.jsonl"

    # socketTimeoutMS + retryReads: the prod cluster is reached over VPN and a stalled socket
    # otherwise hangs the run silently rather than raising.
    client = pymongo.MongoClient(uri, socketTimeoutMS=120_000, connectTimeoutMS=30_000, retryReads=True)
    col = client[DB][COLLECTION]

    existing_by_key = parentless_docs(col)
    total_before = col.count_documents({})
    print(f"[{mode}] {args.env} {DB}.{COLLECTION}: {total_before} documents, "
          f"{len(existing_by_key)} of them parentless")
    print(f"[{mode}] vocabulary: {len(nodes)} nodes "
          + ", ".join(f"{t} {sum(1 for n in nodes if n['type'] == t)}" for t in TYPES))

    counts = {"insert": 0, "set_description": 0, "skip": 0}
    now = datetime.now(timezone.utc)

    with open(log_path, "w", buffering=1) as log:
        for node in nodes:
            existing = existing_by_key.get((node["type"], node["name"]))
            action = classify(node, existing)
            counts[action] += 1
            if action == "skip":
                continue

            entry = {"action": action, "type": node["type"], "name": node["name"]}

            if action == "insert":
                doc = {"type": node["type"], "name": node["name"], "createdAt": now, "updatedAt": now, "__v": 0}
                if node["description"]:
                    doc["description"] = node["description"]
                if args.apply:
                    # No upsert: a concurrent insert must surface as a duplicate-key error, not be
                    # silently merged into whatever the other writer put there.
                    entry["_id"] = col.insert_one(doc).inserted_id
            else:
                entry["_id"] = existing["_id"]
                entry["description"] = node["description"]
                if args.apply:
                    # Leaf key only - never rebuild the document, subtitle/guidance are not ours.
                    col.update_one({"_id": existing["_id"]}, {"$set": {"description": node["description"]}})

            entry["_id"] = str(entry.get("_id", ""))
            log.write(json.dumps(entry, default=str) + "\n")

    print(f"[{mode}] insert {counts['insert']}, set_description {counts['set_description']}, "
          f"skip {counts['skip']}")
    print(f"[{mode}] log: {log_path}")

    if args.apply:
        for node_type in TYPES:
            print(f"  after: {node_type} {col.count_documents({'type': node_type})}")
        print(f"  after: parented (untouched) {col.count_documents({'parent': {'$ne': None}})}")
    else:
        print("Dry run. Re-run with --apply to write.")

    client.close()


if __name__ == "__main__":
    main()
