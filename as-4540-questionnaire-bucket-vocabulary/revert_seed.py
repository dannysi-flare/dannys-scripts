#!/usr/bin/env python3
"""
AS-4540 - Revert a seed run from its JSONL log.

  insert          -> delete the document this run created
  set_description -> $unset description (the run only ever sets it where there was none)

Documents the run skipped are absent from the log and are never touched, as are the 32
pre-existing parented documents.

Default is DRY-RUN. Pass --apply to write.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import pymongo
from bson import ObjectId

DB = "data-collection"
COLLECTION = "questionnairebuckets"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("log", help="seed_log_<env>_<stamp>.jsonl from the run to undo")
    parser.add_argument("--env", choices=["staging", "production"], default="staging")
    parser.add_argument("--uri", help="Overrides --env")
    parser.add_argument("--apply", action="store_true", help="Write. Without it, dry-run.")
    args = parser.parse_args()

    uri = args.uri or os.environ.get(f"MONGODB_{args.env.upper()}_URI")
    if not uri:
        sys.exit(f"No URI. Set MONGODB_{args.env.upper()}_URI or pass --uri.")

    entries = [json.loads(line) for line in Path(args.log).read_text().splitlines() if line.strip()]
    if not entries:
        sys.exit(f"{args.log} has no entries - nothing to revert.")
    if any(not e.get("_id") for e in entries):
        sys.exit(f"{args.log} has entries without an _id - that is a DRY-RUN log, nothing was written.")

    mode = "APPLY" if args.apply else "DRY-RUN"
    client = pymongo.MongoClient(uri, socketTimeoutMS=120_000, connectTimeoutMS=30_000, retryReads=True)
    col = client[DB][COLLECTION]

    counts = {"insert": 0, "set_description": 0}
    for entry in entries:
        counts[entry["action"]] += 1
        if not args.apply:
            continue
        _id = ObjectId(entry["_id"])
        if entry["action"] == "insert":
            col.delete_one({"_id": _id})
        else:
            col.update_one({"_id": _id}, {"$unset": {"description": ""}})

    print(f"[{mode}] {args.env}: delete {counts['insert']}, unset description {counts['set_description']}")
    if args.apply:
        print(f"  after: {col.count_documents({})} documents, "
              f"{col.count_documents({'parent': None})} parentless")
    else:
        print("Dry run. Re-run with --apply to write.")

    client.close()


if __name__ == "__main__":
    main()
