#!/usr/bin/env python3
"""Check the catalog database for case update templates."""

from pymongo import MongoClient

MONGO_URI = "mongodb+srv://node:marblerules1@marble-stg.jycnt.mongodb.net/catalog"

client = MongoClient(MONGO_URI)
db = client['catalog']

print("Collections in 'catalog' database:")
print("=" * 60)

collections = sorted(db.list_collection_names())
for name in collections:
    if 'template' in name.lower() or 'case' in name.lower():
        count = db[name].count_documents({})
        print(f"  {name}: {count} documents")

print("\n" + "=" * 60)

# Check caseupdatetemplates specifically
collection_name = 'caseupdatetemplates'
if collection_name in collections:
    count = db[collection_name].count_documents({})
    print(f"\n✓ Found '{collection_name}' with {count} documents")

    if count > 0:
        # Get sample templates
        print("\nSample templates:")
        templates = list(db[collection_name].find().limit(3))
        for i, template in enumerate(templates, 1):
            print(f"\n  Template {i}:")
            print(f"    name: {template.get('name')}")
            print(f"    label: {template.get('label', '[NOT PRESENT]')}")
            print(f"    usage: {template.get('usage')}")
            print(f"    fields: {list(template.keys())}")

        # Count label status
        with_label = db[collection_name].count_documents({"label": {"$exists": True, "$ne": None, "$ne": ""}})
        without_label = db[collection_name].count_documents({
            "$or": [
                {"label": {"$exists": False}},
                {"label": None},
                {"label": ""}
            ]
        })
        california_count = db[collection_name].count_documents({"name": {"$regex": "^California"}})

        print("\n" + "=" * 60)
        print(f"Templates WITH label: {with_label}")
        print(f"Templates WITHOUT label: {without_label}")
        print(f"Templates starting with 'California': {california_count}")

else:
    print(f"\n✗ Collection '{collection_name}' NOT FOUND")

client.close()
