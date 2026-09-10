# Danny's Scripts

Personal automation scripts.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp env.example .env
```

Edit `.env` and add your API keys and environment variables.

## Usage

### Port Forward Services

Port-forward Kubernetes services from staging/production and generate environment files:

```bash
python scripts/devops/port_forward_services.py service1 [service2 ...] [--prod] [--color COLOR] [--background]
```

This script will:

- Check AWS SSO authentication (prompts login if needed)
- Port-forward specified services from Kubernetes clusters
- Generate environment files with `SERVICE_NAME_URL=http://localhost:PORT` format
- Handle both service name formats: `catalog_ms` or `catalog-ms`
- Support color prefixing for multi-environment deployments

Examples:

```bash
# Forward staging services (default)
python scripts/devops/port_forward_services.py catalog_ms users-ms

# Forward production service (requires confirmation)
python scripts/devops/port_forward_services.py catalog_ms --prod

# Forward services with color prefix
python scripts/devops/port_forward_services.py --color blue services-ms users-ms

# Run in background mode
python scripts/devops/port_forward_services.py catalog-ms --background
```

### Copy Schema Forms

Copy a data schema and all its forms from an input schema to an output schema, with form keys prefixed with "docoloco-":

```bash
python scripts/docoloco/copy_schema_forms.py <input_schema_id> <output_schema_id>
```

This script will:

- Copy the entire schema from input to output
- Create/update all forms with "docoloco-" prefix
- Update catalog drafts that reference these forms

### Generate Draft

Generate a document draft from a template:

```bash
python scripts/docoloco/generate_draft.py <document_path> <tokens_path> [-o output_path]
```

### Upload S3 Draft

Upload a file to S3 (marble-drafts buckets):

```bash
python scripts/docoloco/upload_s3_draft.py <file_path> <s3_object_name> [--prod]
```

This script will:

- Check AWS SSO authentication (prompts `aws sso login` if needed)
- Upload file to `marble-drafts-staging` by default
- Use `marble-drafts-production` with `--prod` flag (requires confirmation)
- Automatically backup existing files with `.bak<number>` naming
- Provide clear feedback on upload status

Example:

```bash
# Upload to staging
python scripts/docoloco/upload_s3_draft.py ./documents/draft.pdf documents/client-123/draft.pdf

# Upload to production
python scripts/docoloco/upload_s3_draft.py ./documents/draft.pdf documents/client-123/draft.pdf --prod
```

### Merge Schema from Google Sheets

Automate schema and form updates in Vinny staging using Google Sheets as input:

```bash
python scripts/docoloco/merge_schema_from_sheets.py --sheets-url "<GOOGLE_SHEETS_URL>" [OPTIONS]
```

This script will:

1. Authenticate with Google Sheets (OAuth2 interactive flow)
2. Download CSV from the specified Google Sheets document
3. Call draft-driver-100x merge endpoint to generate merged schema and form
4. Display merge results and change summary
5. Prompt for confirmation (y/n)
6. Update schema and form in Vinny staging API
7. Save intermediate CSV file for debugging

**Setup**:

1. Install Google Sheets API dependencies (already included in requirements.txt):
   ```bash
   pip install -r requirements.txt
   ```

2. Create Google Sheets API credentials:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select existing
   - Enable Google Sheets API
   - Create OAuth2 credentials (Desktop app)
   - Download credentials JSON
   - Save to `~/.claude/google-sheets-credentials.json`

3. Configure environment variables in `.env`:
   ```bash
   SCHEMA_ID=your-global-schema-id
   FORM_ID=your-form-id-or-leave-empty
   VINNY_API_URL=https://staging.api.helloflare.com/data-collection
   VINNY_API_KEY=your-api-key
   DRAFT_DRIVER_API_URL=http://localhost:8001
   GOOGLE_SHEETS_CREDENTIALS_PATH=~/.claude/google-sheets-credentials.json
   ```

**Examples**:

```bash
# Basic usage (uses env vars for form_id)
python scripts/docoloco/merge_schema_from_sheets.py \
  --sheets-url "https://docs.google.com/spreadsheets/d/ABC123/edit"

# Specify form ID explicitly
python scripts/docoloco/merge_schema_from_sheets.py \
  --sheets-url "https://docs.google.com/spreadsheets/d/ABC123" \
  --form-id "form-xyz-456"

# Export specific sheet
python scripts/docoloco/merge_schema_from_sheets.py \
  --sheets-url "https://docs.google.com/spreadsheets/d/ABC123" \
  --sheet-name "CA Fields"

# Verbose debug mode
python scripts/docoloco/merge_schema_from_sheets.py \
  --sheets-url "https://docs.google.com/spreadsheets/d/ABC123" \
  -v

# Auto-accept (skip confirmation)
python scripts/docoloco/merge_schema_from_sheets.py \
  --sheets-url "https://docs.google.com/spreadsheets/d/ABC123" \
  --yes
```

**First-Time Setup**:

On first run, the script will open your browser for Google OAuth2 authentication. After granting permissions, the script will save a token file (`~/.claude/google-sheets-token.json`) for future use. You won't need to authenticate again unless the token expires or is revoked.

### Fix PDF Form Font Sizes

Fix PDF form templates by setting consistent font sizes across all text fields. This addresses issues where form fields have different font sizes embedded in their Default Appearance (DA), causing inconsistent text rendering when filled programmatically.

```bash
node scripts/fix_pdf_font_sizes.js <input.pdf> <output.pdf> [fontSize]
```

**Requirements**: Node.js and pdf-lib. Run from the vinny directory to use its pdf-lib installation, or install globally with `npm install -g pdf-lib`.

**What it does**:
1. Embeds Helvetica font into the PDF
2. Sets all text fields to use the same font size (default: 9pt)
3. Clears existing appearance streams so they regenerate fresh
4. Updates all field appearances with the embedded font

**Examples**:

```bash
# Fix FL-105 template with default 9pt font
cd ~/src/vinny
node ~/src/dannys-scripts/scripts/fix_pdf_font_sizes.js ~/Downloads/fl105_clean.pdf ~/Downloads/fl105_fixed.pdf

# Fix with custom font size (10pt)
node ~/src/dannys-scripts/scripts/fix_pdf_font_sizes.js ~/Downloads/fl140.pdf ~/Downloads/fl140_fixed.pdf 10
```

**Use case**: When CA court eform templates have fields with inconsistent font sizes (e.g., RESPONDENT field renders much larger than other fields), run this script on the source PDF before uploading to S3. The fixed template will render consistently when filled by documents-ms.

### Data-Collection v2 — Pair Migration Tooling (AS-4246)

`as-4246-dc2-pair-migration/pair_migration.py` derives a per-(practiceArea, jurisdiction) data
schema from the datapoints a pair's forms actually reference, and copies that pair's datapoints
into the new partition. Used by the Milestone 1 test plan, steps P5 and P8.

Every subcommand is **dry-run by default**; a write needs `--apply`. `--apply` writes a JSON log
under `as-4246-dc2-pair-migration/logs/` (git-ignored — it holds user ids) which `revert` replays.

```bash
export MONGO_URI='<staging URI>'   # credentials: ~/.claude/.claude.local.md — never echo it

# 1. derive the pair's schema (immigration / US-FED). Reviews the plan, writes nothing.
./pair_migration.py derive-schema \
    --service-type-id 6a134e51e7fb6df0f3c9b325 \
    --service-type-id 6a1c17dc227c6489bd84c2ce \
    --service-type-id 6a2026c24086ae2d3bafc6be \
    --extra-form-key 'mini-q:IMM-I-130-beneficiary' \
    --extra-form-key 'mini-q:beneficiary-aos' \
    --key immigration-us-fed --name 'Immigration (US-FED)' \
    --out /tmp/immigration-us-fed.json

./pair_migration.py derive-schema ... --apply        # creates the dataschemas row

# 2. size the copy before the schema row exists, then copy a test user's answers
./pair_migration.py copy-datapoints --to-keys-file /tmp/immigration-us-fed.json
./pair_migration.py copy-datapoints --to-key immigration-us-fed --user-id <userId> --apply

# 3. undo either step from its log
./pair_migration.py revert --log logs/20260910-201500-copy-datapoints.json --apply
```

**Field set** = the union of the `properties` on the live forms attached to those service types
(`serviceResources[].resourceKey` → `draftscatalog` → `formKey` → `forms`), plus the
`flare_condition` / `allOf` gating closure (a port of
`libs/data-collection-utils/src/lib/field-dependencies.ts`), plus anything a `--questionnaire-key`
references. Forms that a draft resource doesn't reach — mini-questionnaires — need
`--extra-form-key`.

**Rules it enforces**:

- The row is created by **`key`**: that is the path the catalog binding
  `stateInfo[state].dataSchemaKey` resolves through. `DataSchema.dataSchemaId` is dead code
  (AS-4239) and is never written — the id everything else references is the document `_id`.
- **Copy, don't move.** Source rows are never touched, so reverting a flip is just unbinding.
- The unit is **(user × the new schema's key set)**, never the whole user — a user's datapoints
  may span practice areas.
- `source` is copied **verbatim**; encrypted values need no re-encryption (the key derives from
  `userId`, not the schema).
- Re-running a copy is idempotent: keys already in the target partition are counted, not doubled.
- Applying to the whole population requires `--all-users` on top of `--apply`.

Self-check for the closure port (no DB needed): `./test_pair_migration.py`.

### AI Recipes — Schema Key Backfill (AS-4276)

`as-4276-airecipes-schema-key/backfill_recipe_schema_key.py` pins every existing `airecipes`
document to the schema it was authored against, closing the window where a recipe with no
`dataSchemaKey` matches any schema.

```bash
export MONGO_URI='<staging URI>'    # or the repo .env; never echoed

./backfill_recipe_schema_key.py backfill              # dry run: counts + the keys it would set
./backfill_recipe_schema_key.py backfill --apply      # writes, and logs the recipe ids it touched
./backfill_recipe_schema_key.py revert --log logs/<run>.json --apply
```

The value comes from the `dataschemas` document (`--schema-id`, default docoloco
`66dee37286565b000812bb21`), **never hardcoded** — that document's `key` is `"Docoloco Schema"`
while its `name` is `"docoloco"`, so guessing gets it backwards. Recipes already bound to a
different schema are reported and left alone, and `revert` only unsets rows that still hold the
value its own log recorded.
