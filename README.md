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
