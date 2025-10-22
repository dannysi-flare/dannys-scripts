# Schema and Forms Copy Script

## Overview

Create a Python script at `dannys-scripts/scripts/docoloco/copy_schema_forms.py` that copies a data schema and all its associated forms from an input schema to an output schema, prefixing form keys with "docoloco-", and updates catalog drafts that reference these forms.

## Implementation Steps

### 1. Script Structure

Follow the pattern of `generate_draft.py`:

- Use argparse for CLI arguments (input_schema_id, output_schema_id)
- Load environment variables from .env file (DATA_COLLECTION_MS_URL, CATALOG_MS_URL, X_API_KEY)
- Use requests library for HTTP calls
- Log only errors

### 2. Core Functionality

**Step 1: Fetch Input Schema**

- GET `/data-schemas/{input_schema_id}` from data-collection-ms
- Extract: id, name, key, schema (JSON)

**Step 2: Update Output Schema**

- PUT `/data-schemas/{output_schema_id}` with input schema data
- Payload: `{ "name": ..., "key": ..., "schema": {...} }`

**Step 3: Fetch Input Schema Forms**

- GET `/forms?dataSchemaId={input_schema_id}` from data-collection-ms
- Returns array of FormDto objects with: id, name, key, schema, dataSchemaId

**Step 4: Create/Update Forms**

For each form from input schema:

- Generate new key: `f"docoloco-{form.key}"`
- Check if form exists: GET `/forms?dataSchemaId={output_schema_id}&keys={new_key}`
- If exists: PUT `/forms/{existing_id}` with updated data
- If not exists: POST `/forms` with new form data
- Payload: `{ "name": form.name, "key": new_key, "schema": form.schema, "dataSchemaId": output_schema_id }`

**Step 5: Search and Update Catalog Drafts**

- Collect all new form keys: `["docoloco-key1", "docoloco-key2", ...]`
- GET `/catalog/drafts?formKeys={comma_separated_keys}` from catalog-ms
- For each draft found: PATCH `/catalog/drafts/{draft.id}` with `{ "formKey": new_form_key }`

### 3. Error Handling

- Validate environment variables exist
- Handle HTTP errors with response.raise_for_status()
- Log failures and exit with sys.exit(1) on critical errors
- Print summary of operations (schemas updated, forms created/updated, drafts updated)

### 4. Environment Variables Needed

Add to `.env` file:

```
DATA_COLLECTION_MS_URL=http://localhost:3000
CATALOG_MS_URL=http://localhost:3001
X_API_KEY=your-api-key
```

## Key Files to Reference

- `/Users/dannysivan/src/vinny/apps/data-collection-ms/src/data-schemas/data-schemas.controller.ts` (lines 59-82, 84-96)
- `/Users/dannysivan/src/vinny/apps/data-collection-ms/src/forms/forms.controller.ts` (lines 46-62, 81-104, 106-120)
- `/Users/dannysivan/src/vinny/apps/catalog-ms/src/drafts/draft-catalog.controller.ts` (lines 80-88, 90-104)
- `/Users/dannysivan/dannys-scripts/scripts/docoloco/generate_draft.py` (for code style)