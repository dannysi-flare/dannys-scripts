#!/usr/bin/env python3
"""Data-collection v2 per-pair migration tooling (AS-4246).

Three subcommands, all dry-run unless `--apply` is passed:

  derive-schema    Build a (practiceArea, jurisdiction) `dataschemas` row from the datapoints
                   the pair's forms actually reference, instead of cloning the monolith.
  copy-datapoints  Copy a user's docoloco datapoints into the derived schema's partition.
  revert           Undo either of the above from the JSON log they wrote.

Resolution chain used by derive-schema:

    serviceTypeId → catalog.servicescatalog (latest version)
        → serviceResources[].resourceKey → catalog.draftscatalog (latest) → formKey
        → data-collection.forms (isLatest) → properties            = the referenced datapoints
        + flare_condition / allOf closure                          = the gating datapoints
        + questionnaires[].sections[].buckets[].subBuckets[].dataPoints[].name

The derived row is created by `key` — that is the path the catalog binding
(`stateInfo[state].dataSchemaKey`) resolves through. `DataSchema.dataSchemaId` is dead code
(AS-4239) and is deliberately not written; the id everything else references is the document `_id`.

Usage:
    export MONGO_URI='<staging or prod URI>'   # credentials live in ~/.claude/.claude.local.md

    # size the pilot pair (immigration / US-FED), write the derived schema to a file
    ./pair_migration.py derive-schema \
        --service-type-id 6a134e51e7fb6df0f3c9b325 \
        --extra-form-key mini-q:IMM-I-130-beneficiary \
        --key immigration-us-fed --name 'Immigration (US-FED)' \
        --out /tmp/immigration-us-fed.json

    ./pair_migration.py derive-schema ... --apply     # writes the dataschemas row

    # size the copy before the schema row exists, then copy one test user's answers
    ./pair_migration.py copy-datapoints --to-keys-file /tmp/immigration-us-fed.json
    ./pair_migration.py copy-datapoints --to-key immigration-us-fed --user-id <userId> --apply

    ./pair_migration.py revert --log logs/20260910-120000-copy-datapoints.json --apply
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
CATALOG_DB = "catalog"
DATA_COLLECTION_DB = "data-collection"
MAX_CLOSURE_ITERATIONS = 10
LOG_DIR = Path(__file__).resolve().parent / "logs"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("pair-migration")


# ---------------------------------------------------------------- infrastructure


def connect() -> MongoClient:
    """Open a client from $MONGO_URI. The URI is never logged."""
    uri = os.environ.get("MONGO_URI") or os.environ.get("MONGODB_STAGING_URI")
    if not uri:
        sys.exit("set MONGO_URI (credentials are in ~/.claude/.claude.local.md)")
    return MongoClient(uri, appname="as-4246-pair-migration")


def oid_or_str(value: str) -> list:
    """Both id forms seen in staging: some references are ObjectId, some plain strings."""
    out = [value]
    if len(value) == 24:
        try:
            out.append(ObjectId(value))
        except Exception:  # noqa: BLE001 - not an ObjectId, the string form is enough
            pass
    return out


def latest_by(docs: list, lineage_field: str) -> list:
    """Collapse versioned catalog documents to the highest versionId per lineage id."""
    best: dict[str, dict] = {}
    for doc in docs:
        lineage = str(doc.get(lineage_field) or doc["_id"])
        if doc.get("versionId", 1) >= best.get(lineage, {}).get("versionId", -1):
            best[lineage] = doc
    return list(best.values())


def write_log(operation: str, payload: dict) -> Path:
    """Persist what an --apply run changed, so `revert` has something to read."""
    LOG_DIR.mkdir(exist_ok=True)
    path = LOG_DIR / f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{operation}.json"
    payload = {"operation": operation, "recordedAt": datetime.now(timezone.utc).isoformat(), **payload}
    path.write_text(json.dumps(payload, indent=1, default=str))
    log.info("log written: %s", path)
    return path


# ---------------------------------------------------------------- field closure


def parse_field_path(field_key: str) -> tuple[str, str | None]:
    """`children[].name` → ("children", "name"). Single-level only, as in vinny."""
    head, _, tail = field_key.partition("[].")
    return (head, tail or None)


def resolve_field_dependencies(field_keys: set[str], properties: dict, all_of: list) -> set[str]:
    """Port of `libs/data-collection-utils/src/lib/field-dependencies.ts`.

    Adds the transitive gating closure of `field_keys`: `flare_condition.key` on a property in
    the set, plus `allOf[*].if` keys whose `then` introduces a key in the set. This is the step
    that catches a screening datapoint that gates others but is never templated.
    """
    closure = {parse_field_path(key)[0] for key in field_keys}
    for _ in range(MAX_CLOSURE_ITERATIONS):
        before = len(closure)

        for key in list(closure):
            prop = properties.get(key)
            condition = prop.get("flare_condition") if isinstance(prop, dict) else None
            if isinstance(condition, dict) and isinstance(condition.get("key"), str):
                closure.add(condition["key"])

        for clause in all_of:
            if not isinstance(clause, dict):
                continue
            if_clause, then_clause = clause.get("if"), clause.get("then")
            if not isinstance(if_clause, dict) or not isinstance(then_clause, dict):
                continue
            then_props = then_clause.get("properties")
            if not isinstance(then_props, dict) or not (set(then_props) & closure):
                continue
            for required in if_clause.get("required") or []:
                if isinstance(required, str):
                    closure.add(required)
            if isinstance(if_clause.get("properties"), dict):
                closure.update(if_clause["properties"])

        if len(closure) == before:
            break
    return closure


# ---------------------------------------------------------------- derive-schema


def collect_form_keys(catalog, service_type_ids: list[str]) -> tuple[list[str], list[str]]:
    """Walk service types → their latest draft resources → the form keys those drafts fill."""
    ids = [form for sid in service_type_ids for form in oid_or_str(sid)]
    service_types = latest_by(list(catalog.servicescatalog.find({"serviceTypeId": {"$in": ids}})), "serviceTypeId")
    found = {str(st["serviceTypeId"]) for st in service_types}
    missing = [sid for sid in service_type_ids if sid not in found]

    resource_keys = {
        str(resource["resourceKey"])
        for st in service_types
        for resource in st.get("serviceResources") or []
        if resource.get("resourceKey")
    }
    resource_ids = [form for key in resource_keys for form in oid_or_str(key)]
    drafts = latest_by(
        list(catalog.draftscatalog.find({"$or": [{"_id": {"$in": resource_ids}}, {"draftTypeId": {"$in": resource_ids}}]})),
        "draftTypeId",
    )
    for st in service_types:
        log.info("service type %s v%s — %s", st["serviceTypeId"], st.get("versionId"), st.get("serviceTypeName"))
    log.info("%d resource keys → %d draft lineages", len(resource_keys), len(drafts))
    return sorted({draft["formKey"] for draft in drafts if draft.get("formKey")}), missing


def questionnaire_keys(dc, keys: list[str]) -> set[str]:
    """Datapoint names a questionnaire references, so seeding one can't outrun the schema."""
    names: set[str] = set()
    for key in keys:
        doc = dc.questionnaires.find_one({"key": key})
        if not doc:
            log.warning("questionnaire %r not found", key)
            continue
        for section in doc.get("sections") or []:
            for bucket in section.get("buckets") or []:
                for sub in bucket.get("subBuckets") or []:
                    names.update(dp["name"] for dp in sub.get("dataPoints") or [] if dp.get("name"))
    return names


def derive_schema(args) -> None:
    """Compute the pair's field set and (with --apply) create/update the `dataschemas` row."""
    client = connect()
    catalog, dc = client[CATALOG_DB], client[DATA_COLLECTION_DB]

    form_keys, missing_service_types = collect_form_keys(catalog, args.service_type_ids or [])
    if missing_service_types:
        log.error("service types not found in catalog: %s", missing_service_types)
    form_keys = sorted(set(form_keys) | set(args.extra_form_keys or []))
    if not form_keys:
        sys.exit("no forms resolved — pass --service-type-id and/or --extra-form-key")

    forms = list(dc.forms.find({"isLatest": True, "key": {"$in": form_keys}}))
    for key in sorted(set(form_keys) - {f["key"] for f in forms}):
        log.error("form %r has no live version", key)
    off_schema = [f["key"] for f in forms if str(f.get("dataSchemaId")) != args.source_schema_id]
    if off_schema:
        log.warning("forms on a different data schema (excluded): %s", off_schema)
    forms = [f for f in forms if str(f.get("dataSchemaId")) == args.source_schema_id]

    union: dict[str, dict] = {}
    all_of: list = []
    for form in forms:
        parsed = json.loads(form["dataSchema"])
        union.update(parsed.get("properties") or {})
        all_of += parsed.get("allOf") or []
        log.info("form %-34s %4d properties", form["key"], len(parsed.get("properties") or {}))

    seeds = set(union) | questionnaire_keys(dc, args.questionnaire_keys or [])
    closure = resolve_field_dependencies(seeds, union, all_of)
    gating_only = sorted(closure - {parse_field_path(k)[0] for k in seeds})

    source = dc.dataschemas.find_one({"_id": ObjectId(args.source_schema_id)})
    if not source:
        sys.exit(f"source schema {args.source_schema_id} not found")
    source_defs = json.loads(source["dataSchema"]).get("$defs") or {}

    # A key the source library never defined can only be defined by the form that references it —
    # taking the inline copy is what makes "covers every datapoint the forms reference" true.
    derived_defs = {}
    inline_fallbacks = []
    for key in sorted(closure):
        if key in source_defs:
            derived_defs[key] = source_defs[key]
        elif key in union:
            derived_defs[key] = union[key]
            inline_fallbacks.append(key)
        else:
            log.error("field %r is referenced but defined nowhere — it will be missing", key)
    derived = {"type": "object", "$defs": derived_defs}
    body = json.dumps(derived)

    log.info("---- derived schema plan ----")
    log.info("forms                 %d", len(forms))
    log.info("referenced datapoints %d", len(union))
    log.info("gating closure adds   %d %s", len(gating_only), gating_only[:10])
    log.info("questionnaire adds    %d", len(seeds) - len(union))
    log.info("derived $defs         %d (source library has %d)", len(derived_defs), len(source_defs))
    log.info("inline fallbacks      %d %s", len(inline_fallbacks), inline_fallbacks[:10])
    log.info("form allOf clauses    %d (not carried onto the schema — parity with docoloco)", len(all_of))
    log.info("payload               %d KB", len(body) // 1024)

    if args.out:
        Path(args.out).write_text(json.dumps(derived, indent=1))
        log.info("derived schema written to %s", args.out)

    existing = dc.dataschemas.find_one({"key": args.key})
    if existing:
        log.warning("key %r already exists as _id=%s — would replace its dataSchema", args.key, existing["_id"])
    if not args.apply:
        log.info("DRY RUN — nothing written. Re-run with --apply.")
        return

    if existing:
        dc.dataschemas.update_one(
            {"_id": existing["_id"]}, {"$set": {"name": args.name, "dataSchema": body, "updatedAt": datetime.now(timezone.utc)}}
        )
        schema_id = existing["_id"]
        write_log(
            "derive-schema",
            {"key": args.key, "dataSchemaId": str(schema_id), "created": False, "previousDataSchema": existing["dataSchema"]},
        )
    else:
        now = datetime.now(timezone.utc)
        schema_id = dc.dataschemas.insert_one(
            {"key": args.key, "name": args.name, "dataSchema": body, "createdAt": now, "updatedAt": now, "__v": 0}
        ).inserted_id
        write_log("derive-schema", {"key": args.key, "dataSchemaId": str(schema_id), "created": True})
    log.info("dataschemas _id = %s — bind with stateInfo[<state>].dataSchemaKey = %r", schema_id, args.key)


# ---------------------------------------------------------------- copy-datapoints


def target_key_set(dc, to_schema_id: str | None, to_key: str | None, keys_file: str | None) -> tuple[ObjectId | None, set[str]]:
    """The new schema's `$defs` names are the unit of the copy, alongside the user.

    `keys_file` takes derive-schema's `--out` file so the copy can be sized before the
    `dataschemas` row exists — measure first, write second.
    """
    if keys_file:
        keys = set(json.loads(Path(keys_file).read_text()).get("$defs") or {})
        log.info("target key set from %s — %d keys (schema row not required)", keys_file, len(keys))
        return None, keys
    query = {"_id": ObjectId(to_schema_id)} if to_schema_id else {"key": to_key}
    target = dc.dataschemas.find_one(query)
    if not target:
        sys.exit(f"target schema not found: {to_schema_id or to_key}")
    keys = set(json.loads(target["dataSchema"]).get("$defs") or {})
    log.info("target schema _id=%s key=%r — %d keys", target["_id"], target.get("key"), len(keys))
    return target["_id"], keys


def copy_datapoints(args) -> None:
    """Copy (user × target key set) from the source partition into the target partition."""
    client = connect()
    dc = client[DATA_COLLECTION_DB]
    target_id, keys = target_key_set(dc, args.to_schema_id, args.to_key, args.to_keys_file)
    target_id_str = str(target_id) if target_id else None
    if target_id_str is None and args.apply:
        sys.exit("--to-keys-file is for sizing only; apply needs --to-schema-id or --to-key")

    query = {"dataPoints.dataSchemaId": args.from_schema_id}
    if args.user_ids:
        query["userId"] = {"$in": args.user_ids}
    elif not args.all_users:
        log.info("no --user-id given: sizing every user with a source partition (apply needs --all-users)")

    users = 0
    copied = 0
    already = 0
    skipped_keys: set[str] = set()
    malformed: list[str] = []
    changes = []
    for doc in dc.datapoints.find(query, {"userId": 1, "dataPoints": 1}):
        containers = {c["dataSchemaId"]: c for c in doc.get("dataPoints") or []}
        source = containers.get(args.from_schema_id)
        if not source:
            continue
        present = {dp["key"] for dp in (containers.get(target_id_str) or {}).get("dataPoints") or []}
        take = []
        for dp in source.get("dataPoints") or []:
            # Staging holds at least one container nested inside a container (no `key` at all).
            # Never copy a malformed row — it would look like a datapoint named nothing.
            if not isinstance(dp.get("key"), str):
                malformed.append(doc["userId"])
            elif dp["key"] not in keys:
                skipped_keys.add(dp["key"])
            elif dp["key"] in present:
                already += 1
            else:
                # `source` is provenance: copy it verbatim, never synthesise it. Encrypted values
                # need no re-encryption — the key derives from userId, not from the schema.
                take.append({**dp, "dataSchemaId": target_id_str})
        if not take:
            continue
        users += 1
        copied += len(take)
        changes.append({"userId": doc["userId"], "keys": [dp["key"] for dp in take]})
        if args.apply:
            if target_id_str in containers:
                dc.datapoints.update_one(
                    {"userId": doc["userId"], "dataPoints.dataSchemaId": target_id_str},
                    {"$push": {"dataPoints.$.dataPoints": {"$each": take}}},
                )
            else:
                dc.datapoints.update_one(
                    {"userId": doc["userId"]},
                    {"$push": {"dataPoints": {"dataSchemaId": target_id_str, "dataPoints": take}}},
                )

    log.info("---- datapoint copy plan ----")
    log.info("users touched          %d", users)
    log.info("datapoints copied      %d", copied)
    log.info("already in target      %d (idempotent re-run)", already)
    log.info("source keys not in pair %d (left behind by design)", len(skipped_keys))
    if malformed:
        log.warning("malformed source rows skipped: %d (users %s)", len(malformed), sorted(set(malformed))[:5])
    if not args.apply:
        log.info("DRY RUN — nothing written. Re-run with --apply (and --all-users for the whole population).")
        return
    if not args.user_ids and not args.all_users:
        sys.exit("refusing to apply to every user without --all-users")
    write_log(
        "copy-datapoints",
        {"fromSchemaId": args.from_schema_id, "toSchemaId": target_id_str, "users": users, "datapoints": copied, "changes": changes},
    )


# ---------------------------------------------------------------- revert


def revert(args) -> None:
    """Undo a logged run: pull the copied datapoints, or restore/delete the derived schema."""
    client = connect()
    dc = client[DATA_COLLECTION_DB]
    entry = json.loads(Path(args.log).read_text())
    operation = entry["operation"]
    log.info("reverting %s recorded at %s", operation, entry.get("recordedAt"))

    if operation == "copy-datapoints":
        target = entry["toSchemaId"]
        total = sum(len(change["keys"]) for change in entry["changes"])
        log.info("would pull %d datapoints from the %s partition of %d users", total, target, len(entry["changes"]))
        if not args.apply:
            log.info("DRY RUN — nothing written. Re-run with --apply.")
            return
        for change in entry["changes"]:
            dc.datapoints.update_one(
                {"userId": change["userId"], "dataPoints.dataSchemaId": target},
                {"$pull": {"dataPoints.$.dataPoints": {"key": {"$in": change["keys"]}}}},
            )
        # A partition this run created and then emptied should not linger.
        dc.datapoints.update_many(
            {"dataPoints": {"$elemMatch": {"dataSchemaId": target, "dataPoints": {"$size": 0}}}},
            {"$pull": {"dataPoints": {"dataSchemaId": target, "dataPoints": {"$size": 0}}}},
        )
        log.info("pulled %d datapoints", total)
        return

    if operation == "derive-schema":
        schema_id = ObjectId(entry["dataSchemaId"])
        action = "delete" if entry.get("created") else "restore the previous dataSchema on"
        log.info("would %s dataschemas %s (key %r)", action, schema_id, entry["key"])
        if not args.apply:
            log.info("DRY RUN — nothing written. Re-run with --apply.")
            return
        if entry.get("created"):
            dc.dataschemas.delete_one({"_id": schema_id})
        else:
            dc.dataschemas.update_one({"_id": schema_id}, {"$set": {"dataSchema": entry["previousDataSchema"]}})
        log.info("reverted — unbind stateInfo[<state>].dataSchemaKey separately if it was set")
        return

    sys.exit(f"unknown operation in log: {operation}")


# ---------------------------------------------------------------- cli


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    derive = subparsers.add_parser("derive-schema", help="derive a pair's data schema from its forms")
    derive.add_argument("--service-type-id", action="append", dest="service_type_ids")
    derive.add_argument("--extra-form-key", action="append", dest="extra_form_keys",
                        help="a form not reachable through a draft resource (mini-questionnaires)")
    derive.add_argument("--questionnaire-key", action="append", dest="questionnaire_keys",
                        help="also seed from the datapoints this questionnaire references")
    derive.add_argument("--source-schema-id", default=DOCOLOCO_SCHEMA_ID)
    derive.add_argument("--key", required=True, help="the new schema's key — the catalog binding resolves through it")
    derive.add_argument("--name", required=True)
    derive.add_argument("--out", help="also write the derived JSON schema here for review")
    derive.add_argument("--apply", action="store_true")
    derive.set_defaults(func=derive_schema)

    copy = subparsers.add_parser("copy-datapoints", help="copy (user x pair key set) into the new partition")
    copy.add_argument("--from-schema-id", default=DOCOLOCO_SCHEMA_ID)
    copy.add_argument("--to-schema-id")
    copy.add_argument("--to-key")
    copy.add_argument("--to-keys-file", help="derive-schema --out file; sizes the copy before the schema row exists")
    copy.add_argument("--user-id", action="append", dest="user_ids")
    copy.add_argument("--all-users", action="store_true", help="required to apply without --user-id")
    copy.add_argument("--apply", action="store_true")
    copy.set_defaults(func=copy_datapoints)

    rev = subparsers.add_parser("revert", help="undo a logged run")
    rev.add_argument("--log", required=True)
    rev.add_argument("--apply", action="store_true")
    rev.set_defaults(func=revert)

    args = parser.parse_args()
    if args.command == "copy-datapoints" and not (args.to_schema_id or args.to_key or args.to_keys_file):
        sys.exit("pass --to-schema-id, --to-key or --to-keys-file")
    args.func(args)


if __name__ == "__main__":
    main()
