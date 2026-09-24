# AS-4540 — Seed the questionnaire bucket vocabulary

Part of [P-AS-686 — Retire the hardcoded bucket/sub-bucket enum](https://linear.app/helloflare/project/retire-the-hardcoded-bucketsub-bucket-enum-a3a196ee52ab).

Makes `data-collection.questionnairebuckets` the source of truth for **which** bucket, sub-bucket
and section names are legal, so vinny's `FLARE_*_VALUES` and draft-driver's `VALID_FLARE_*` can be
deleted in AS-4541 / AS-4542.

## State before the run

Staging and production are identical:

```
32 documents — all SUB_BUCKET, all parented, 0 parentless, 0 with state overrides
```

Those 32 carry client-facing `subtitle`/`guidance` for the CA divorce flow. They are a strict
subset of vinny's enum, so there is nothing to reconcile — the seed only adds.

## Order of operations

1. vinny ships the `description` field (AS-4540 part 1). **Before that the seed is pointless** —
   the DTO whitelist strips `description` on the next edit through the API.
2. `--apply` on staging, verify.
3. `--apply` on production.
4. Only then AS-4541 switches validation to read the collection.

## Files

| File | What |
|---|---|
| `extract_vocabulary.py` | One-off. Rebuilds `vocabulary.json` from the two repos at `origin/main`. |
| `vocabulary.json` | 153 nodes — 28 `BUCKET`, 118 `SUB_BUCKET`, 7 `SECTION`. |
| `seed_questionnaire_buckets.py` | The seed. Dry-run by default. |
| `revert_seed.py` | Undo a run from its JSONL log. |

## Usage

```bash
python3 seed_questionnaire_buckets.py --env staging              # dry run
python3 seed_questionnaire_buckets.py --env staging --apply
python3 revert_seed.py seed_log_staging_<stamp>.jsonl --apply    # undo
```

Reads `MONGODB_STAGING_URI` / `MONGODB_PRODUCTION_URI`, or `--uri`. Production needs the VPN.

## Dry-run result (2026-09-24, both envs)

```
32 documents, 0 of them parentless
vocabulary: 153 nodes BUCKET 28, SUB_BUCKET 118, SECTION 7
insert 153, set_description 0, skip 0
```

## Decisions worth knowing

**Everything seeds parentless.** A parentless document is the default for its `(type, name)`, and
name-only membership is exactly what the validation being replaced does today. The 32 existing
parented documents keep winning for their own `(type, name, parent)` via `resolveByParent` in
data-requests-ms, so seeding defaults alongside them changes nothing they serve. Validating the
`(bucket, subBucket)` pair is a deliberate follow-up — it would reject schemas that pass today.

**`subtitle` and `guidance` are never written.** They are client-facing copy owned by whoever wrote
those 32 documents. `description` is the AI-facing hint the draft-driver prompt reads. Not
interchangeable, and `description` is deliberately not state-overridable.

**9 of the 153 nodes seed with no description** — `APPLICANT`, `DOCUMENTS`, and the 7
`APPLICANT_*`/`APPLICATION_DETAILS` sub-buckets have no entry in vinny's `FLARE_*_METADATA` today,
so the AI prompt has never seen them either. Seeding blank keeps that unchanged rather than
inventing copy. Worth a follow-up ticket.

**Extraction must be quote-agnostic.** Both source files mix quote styles — the apostrophe names
(`PETITIONER'S_*`, `BENEFICIARY'S_*`) are double-quoted, everything else single-quoted. A
single-quote-only regex silently drops ~36 names and makes the two repos look far more divergent
than they are. They are not: buckets match 28/28, and draft-driver's 116 sub-buckets are a strict
subset of vinny's 118 (`ADDITIONAL_SERVING_DETAILS` and `SERVING_ADDRESS_DETAILS` are vinny-only).
