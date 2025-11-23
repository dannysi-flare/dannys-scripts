#!/usr/bin/env python3
"""Quick check for case update template collection."""

from pymongo import MongoClient

MONGO_URI = "mongodb+srv://node:marblerules1@marble-stg.jycnt.mongodb.net/marble"

client = MongoClient(MONGO_URI)
db = client['marble']

# Get collection names
collections = db.list_collection_names()
print(f"Total collections: {len(collections)}\n")

# Search for template-related collections
print("Collections matching 'template' or 'case':")
print("=" * 60)
for name in sorted(collections):
    if 'template' in name.lower() or ('case' in name.lower() and 'update' in name.lower()):
        print(f"  {name}")

# Check the specific collection we're looking for
collection_name = 'caseupdatetemplates'
if collection_name in collections:
    count = db[collection_name].count_documents({})
    print(f"\n'{collection_name}' exists with {count} documents")
else:
    print(f"\n'{collection_name}' NOT FOUND")

    # Try variations
    variations = [
        'case_update_templates',
        'case-update-templates',
        'caseUpdateTemplates',
        'CaseUpdateTemplate',
        'CaseUpdateTemplates'
    ]

    print("\nTrying variations:")
    for var in variations:
        if var in collections:
            count = db[var].count_documents({})
            print(f"  ✓ Found: '{var}' with {count} documents")

client.close()
