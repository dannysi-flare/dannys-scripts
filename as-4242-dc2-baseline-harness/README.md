# DC v2 resolved-output harness

Two read-only tools behind the data-collection v2 parity check.

Both scripts read the API key from `X_API_KEY` (environment, or the repo's `.env` — see
`env.example`) and refuse to send it anywhere but a Flare host. Nothing is hardcoded.

## `record_fixture.py` — record the pipeline's input

Pulls a data schema's properties schema plus a set of forms from staging (or a colored
environment) and writes a single gzipped fixture. Nothing is written back.

```bash
./record_fixture.py --out ~/dc2/fixture.json.gz            # staging, the immigration pilot forms
./record_fixture.py --base-url https://blue-api.artemis.flaretechnologies.com --out ~/dc2/blue.json.gz
```

The fixture is deliberately **not committed to vinny** — it is ~1.5MB of real schema. Keep it
under `~/dc2/` (or anywhere outside a repo) and point the vinny spec at it:

```bash
cd ~/src/vinny-worktrees/<worktree>
PATH="$HOME/.nvm/versions/node/v22.23.1/bin:$PATH" \
  DC2_FIXTURE=~/dc2/fixture.json.gz UPDATE_BASELINE=1 npx jest resolved-output.recorded   # record
PATH="$HOME/.nvm/versions/node/v22.23.1/bin:$PATH" \
  DC2_FIXTURE=~/dc2/fixture.json.gz npx jest resolved-output.recorded                     # compare
```

The baseline is written next to the fixture as `<fixture>.baseline.json`: a sha256 of the fully
resolved schema per case (each form alone, then the union of all forms) plus the per-field
`flare_*` / type / required surface for the union. The sha catches any change at all; the field
surface says which field changed.

`apps/data-requests-ms/src/data-requests-aggregator/resolved-output.recorded.spec.ts` skips
itself when `DC2_FIXTURE` is unset, so CI never needs this data. The always-on CI gate is
`resolved-output.spec.ts`, which builds a miniature fixture in TypeScript and asserts the merge,
precedence and ordering rules directly.

Record a fresh fixture before deploying a v2 branch, and after any deliberate change re-record
the baseline so the next diff is clean.

## `lint_form_flare_text.py` — where the form text lives today

Read-only report: per form, how many properties carry presentation `flare_*` inline, and which
properties two forms disagree about. `flare_displayOrder` is excluded because it is derived from
`$defs` key order, not authored.

```bash
./lint_form_flare_text.py --out lint-docoloco-$(date +%F).md
./lint_form_flare_text.py --forms IMM-I-130,IMM-AOS,IMM-I-90 --out lint-pilot-immigration-$(date +%F).md
```

Latest output is checked in beside the scripts: 136 of 144 forms carry presentation text inline;
679 properties disagree across all forms, 17 across the immigration pilot — and those 17 are
audience wording (petitioner "you" vs "the beneficiary"), not authoring drift.
