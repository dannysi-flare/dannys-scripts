#!/usr/bin/env python3
"""Backfill `dataSchemaKey` on `airecipes` (AS-4276).

AS-4276 makes AI-recipe matching (schema, name) instead of name alone, so that a recipe cannot
fire on an identically-named datapoint in another pair — the AS-3425 failure by a different
route. A recipe with no `dataSchemaKey` still matches any schema and logs a warning, so the
pre-backfill window is safe but noisy; this closes it by pinning every existing recipe to the
schema it was actually authored against: docoloco.

The key is **read from the `dataschemas` document**, never hardcoded — its `key` is
"Docoloco Schema" while its `name` is "docoloco", which read swapped, and guessing gets it wrong.

Two subcommands, both dry-run unless `--apply` is passed:

    backfill   set dataSchemaKey on recipes that don't have it
    revert     unset it again on exactly the recipes a logged run touched

Usage:
    export MONGO_URI='<staging or prod URI>'   # or put it in the repo's .env; never echoed

    ./backfill_recipe_schema_key.py backfill
    ./backfill_recipe_schema_key.py backfill --apply
    ./backfill_recipe_schema_key.py revert --log logs/20260910-120000-backfill.json --apply
"""
import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from bson import ObjectId
from pymongo import MongoClient

DOCOLOCO_SCHEMA_ID = "66dee37286565b000812bb21"
DATA_COLLECTION_DB = "data-collection"
LOG_DIR = Path(__file__).resolve().parent / "logs"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("airecipes-backfill")


def connect() -> MongoClient:
    """Open a client from $MONGO_URI, falling back to the repo `.env`. The URI is never logged.

    Same contract as `as-4242-dc2-baseline-harness/api.py` has for `X_API_KEY`: the credential
    comes from the environment, and nothing in this file carries one.
    """
    uri = os.environ.get("MONGO_URI")
    if not uri:
        env_file = Path(__file__).resolve().parent.parent / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                name, _, value = line.partition("=")
                if name.strip() == "MONGO_URI":
                    uri = value.strip().strip("\"'")
                    break
    if not uri:
        sys.exit("MONGO_URI is not set — export it or put it in the repo's .env (see env.example)")
    return MongoClient(uri, appname="as-4276-airecipes-backfill")


def write_log(operation: str, payload: dict) -> Path:
    """Persist what an --apply run changed, so `revert` has something to read."""
    LOG_DIR.mkdir(exist_ok=True)
    path = LOG_DIR / f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{operation}.json"
    path.write_text(json.dumps({"operation": operation, "recordedAt": datetime.now(timezone.utc).isoformat(), **payload}, indent=1))
    log.info("log written: %s", path)
    return path


def resolve_schema_key(dc, schema_id: str) -> str:
    """The authoritative key is the one on the `dataschemas` document, not a constant."""
    schema = dc.dataschemas.find_one({"_id": ObjectId(schema_id)}, {"key": 1, "name": 1})
    if not schema:
        sys.exit(f"data schema {schema_id} not found")
    if not schema.get("key"):
        sys.exit(f"data schema {schema_id} has no key — nothing to bind recipes to")
    log.info("schema %s → key=%r (name=%r)", schema_id, schema["key"], schema.get("name"))
    return schema["key"]


def backfill(args) -> None:
    """Set `dataSchemaKey` on every recipe that lacks one."""
    dc = connect()[DATA_COLLECTION_DB]
    schema_key = resolve_schema_key(dc, args.schema_id)

    total = dc.airecipes.count_documents({})
    pending = list(dc.airecipes.find({"dataSchemaKey": {"$in": [None, ""]}}, {"key": 1}))
    already = list(dc.airecipes.find({"dataSchemaKey": {"$nin": [None, ""]}}, {"key": 1, "dataSchemaKey": 1}))
    other_key = [r for r in already if r.get("dataSchemaKey") != schema_key]

    log.info("---- backfill plan ----")
    log.info("recipes total         %d", total)
    log.info("would set             %d → dataSchemaKey=%r", len(pending), schema_key)
    log.info("already set           %d (left alone — idempotent re-run)", len(already))
    if other_key:
        log.warning("already bound to a different schema, NOT touched: %s", [(r["key"], r["dataSchemaKey"]) for r in other_key])
    log.info("recipe keys           %s", [r["key"] for r in pending][:10])

    if not args.apply:
        log.info("DRY RUN — nothing written. Re-run with --apply.")
        return
    if not pending:
        log.info("nothing to do")
        return

    ids = [r["_id"] for r in pending]
    result = dc.airecipes.update_many({"_id": {"$in": ids}}, {"$set": {"dataSchemaKey": schema_key}})
    log.info("modified %d recipes", result.modified_count)
    write_log(
        "backfill",
        {"dataSchemaKey": schema_key, "schemaId": args.schema_id, "recipeIds": [str(i) for i in ids],
         "recipeKeys": [r["key"] for r in pending]},
    )


def revert(args) -> None:
    """Unset `dataSchemaKey` on exactly the recipes a logged run set it on."""
    dc = connect()[DATA_COLLECTION_DB]
    entry = json.loads(Path(args.log).read_text())
    if entry["operation"] != "backfill":
        sys.exit(f"not a backfill log: {entry['operation']}")

    ids = [ObjectId(i) for i in entry["recipeIds"]]
    # Only unset rows that still hold the value this run wrote — someone may have re-bound one since.
    query = {"_id": {"$in": ids}, "dataSchemaKey": entry["dataSchemaKey"]}
    log.info("logged run of %s set %d recipes to %r", entry["recordedAt"], len(ids), entry["dataSchemaKey"])
    log.info("would unset %d of them (the rest changed since and are left alone)", dc.airecipes.count_documents(query))
    if not args.apply:
        log.info("DRY RUN — nothing written. Re-run with --apply.")
        return
    result = dc.airecipes.update_many(query, {"$unset": {"dataSchemaKey": ""}})
    log.info("unset %d recipes — they match any schema again (with a warning) until re-backfilled", result.modified_count)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    fill = subparsers.add_parser("backfill", help="set dataSchemaKey on recipes that lack it")
    fill.add_argument("--schema-id", default=DOCOLOCO_SCHEMA_ID, help="the dataschemas _id whose key recipes get")
    fill.add_argument("--apply", action="store_true")
    fill.set_defaults(func=backfill)

    rev = subparsers.add_parser("revert", help="unset dataSchemaKey from a logged backfill")
    rev.add_argument("--log", required=True)
    rev.add_argument("--apply", action="store_true")
    rev.set_defaults(func=revert)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
