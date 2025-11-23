#!/usr/bin/env python3
"""List all collections in the database."""

from pymongo import MongoClient

MONGO_URI = "mongodb+srv://node:marblerules1@marble-stg.jycnt.mongodb.net/marble"

client = MongoClient(MONGO_URI)
db = client['marble']

print("All collections in 'marble' database:")
print("=" * 60)

collections = sorted(db.list_collection_names())
for collection_name in collections:
    count = db[collection_name].count_documents({})
    print(f"  {collection_name}: {count} documents")

print("\n" + "=" * 60)

# Search for collections with 'template' in the name
template_collections = [c for c in collections if 'template' in c.lower()]
print(f"\nCollections with 'template' in name:")
for collection_name in template_collections:
    count = db[collection_name].count_documents({})
    print(f"  {collection_name}: {count} documents")

    # Show sample document
    sample = db[collection_name].find_one()
    if sample:
        print(f"    Sample fields: {list(sample.keys())}")

# Search for collections with 'case' in the name
case_collections = [c for c in collections if 'case' in c.lower()]
print(f"\nCollections with 'case' in name:")
for collection_name in case_collections:
    count = db[collection_name].count_documents({})
    print(f"  {collection_name}: {count} documents")

client.close()
