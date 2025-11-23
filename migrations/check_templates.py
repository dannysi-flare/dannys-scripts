#!/usr/bin/env python3
"""Quick script to inspect case update templates."""

import sys
from pymongo import MongoClient

MONGO_URI = "mongodb+srv://node:marblerules1@marble-stg.jycnt.mongodb.net/marble"

client = MongoClient(MONGO_URI)
db = client['marble']
collection = db['caseupdatetemplates']

# Get first few documents to see structure
templates = list(collection.find().limit(5))

print(f"Found {collection.count_documents({})} total templates\n")

if templates:
    print("Sample template structure:")
    print("=" * 60)
    for i, template in enumerate(templates, 1):
        print(f"\nTemplate {i}:")
        print(f"  _id: {template.get('_id')}")
        print(f"  name: {template.get('name')}")
        print(f"  label: {template.get('label', '[NOT PRESENT]')}")
        print(f"  usage: {template.get('usage')}")
        print(f"  All fields: {list(template.keys())}")
else:
    print("No templates found")

# Count how many have label field
with_label = collection.count_documents({"label": {"$exists": True}})
without_label = collection.count_documents({"label": {"$exists": False}})

print("\n" + "=" * 60)
print(f"Templates WITH label field: {with_label}")
print(f"Templates WITHOUT label field: {without_label}")

# Show templates starting with California
california_count = collection.count_documents({"name": {"$regex": "^California"}})
print(f"Templates starting with 'California': {california_count}")

client.close()
