# Database Migrations

This folder contains database migration scripts for the Vinny application.

## Prerequisites

Make sure you have PyMongo installed:

```bash
pip install pymongo
```

## Running Migrations

### Case Update Template Label Migration

This migration populates the `label` field in case update templates with the value from the `name` field, except for templates where the name starts with "California".

**Before running:** Make sure the `label` field has been added to the CaseUpdateTemplate schema in the codebase.

#### Dry Run (Recommended First)

Always run with `--dry-run` first to see what changes will be made:

```bash
# Local environment
python migrations/migrate_case_update_template_labels.py --dry-run

# With custom MongoDB URI
python migrations/migrate_case_update_template_labels.py \
  --mongo-uri "mongodb://user:pass@host:port/catalog?authSource=admin" \
  --dry-run
```

#### Apply Changes

Once you've verified the dry run output:

```bash
# Local environment
python migrations/migrate_case_update_template_labels.py

# With custom MongoDB URI
python migrations/migrate_case_update_template_labels.py \
  --mongo-uri "mongodb://user:pass@host:port/catalog?authSource=admin"
```

#### Using Environment Variable

You can also set the MongoDB URI via environment variable:

```bash
export MONGO_URI="mongodb://user:pass@host:port/catalog?authSource=admin"
python migrations/migrate_case_update_template_labels.py
```

## Migration Details

### migrate_case_update_template_labels.py

- **What it does:** Sets `label = name` for all case update templates
- **Skips:** Templates where `name` starts with "California"
- **Collection:** `caseupdatetemplates` in the `catalog` database
- **Safe to re-run:** Yes (only updates documents where label is missing or empty)

## Safety Features

- **Dry run mode:** Test migrations without making changes
- **Confirmation prompt:** Asks for confirmation before applying changes
- **Detailed logging:** Shows all changes being made
- **Error handling:** Continues processing if individual updates fail

## Best Practices

1. Always run with `--dry-run` first
2. Backup your database before running migrations in production
3. Test migrations in staging/dev environment first
4. Review the migration summary after completion
