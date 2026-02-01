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
