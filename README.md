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
