#!/usr/bin/env python3
"""
Download JSONata documents from MongoDB staging database.

This script connects to the MongoDB staging database, queries the document_jsonata
collection for documents where name starts with 'CA', and downloads each document's
content to a separate file following the naming convention:
fl-<number>(-response)?.jsonata

If multiple documents exist for the same base name, only the latest one is downloaded.
"""

import os
import re
from pymongo import MongoClient
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# MongoDB connection string from environment
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI environment variable is not set. Please check your .env file.")

DATABASE_NAME = "draft-architect"
COLLECTION_NAME = "document_jsonata"

def parse_ca_name(name: str) -> Optional[Tuple[int, bool]]:
    """
    Parse CA document name to extract number and response flag.

    Examples:
        CA: FL 100 Divorce Petition -> (100, False)
        CA RE: FL 105 UCCJEA Response -> (105, True)
        CA: FL 110 Summons -> (110, False)

    Returns:
        Tuple of (number, is_response) or None if cannot parse
    """
    # Check if it's a response document (contains "RE:" or ends with "Response")
    is_response = "RE:" in name.upper() or name.strip().endswith("Response")

    # Extract FL number - look for pattern "FL <number>"
    match = re.search(r'FL\s+(\d+)', name, re.IGNORECASE)
    if match:
        number = int(match.group(1))
        return (number, is_response)

    return None

def generate_filename(number: int, is_response: bool) -> str:
    """
    Generate filename according to convention: fl-<number>(-response)?.jsonata

    Args:
        number: Document number
        is_response: Whether this is a response document

    Returns:
        Generated filename
    """
    if is_response:
        return f"fl-{number}-response.jsonata"
    else:
        return f"fl-{number}.jsonata"

def download_documents():
    """
    Connect to MongoDB and download CA documents to separate files.
    """
    print(f"Connecting to MongoDB...")
    client = MongoClient(MONGO_URI)
    db = client[DATABASE_NAME]
    collection = db[COLLECTION_NAME]

    # Query documents where document_name starts with CA
    print(f"Querying documents from {DATABASE_NAME}.{COLLECTION_NAME}...")
    query = {"document_name": {"$regex": "^CA", "$options": "i"}}
    documents = list(collection.find(query))

    print(f"Found {len(documents)} documents starting with 'CA'")

    if not documents:
        print("No documents found. Exiting.")
        return

    # Group documents by their base identity (number + is_response)
    # Key: (number, is_response), Value: list of documents
    grouped_docs: Dict[Tuple[int, bool], List[dict]] = defaultdict(list)

    for doc in documents:
        doc_name = doc.get("document_name", "")
        parsed = parse_ca_name(doc_name)

        if parsed:
            number, is_response = parsed
            grouped_docs[(number, is_response)].append(doc)
        else:
            print(f"Warning: Could not parse document name: {doc_name}")

    # For each group, select the latest document
    output_dir = os.path.join(os.getcwd(), "jsonata_documents")
    os.makedirs(output_dir, exist_ok=True)

    print(f"\nDownloading documents to: {output_dir}")
    print("-" * 60)

    downloaded_count = 0

    for (number, is_response), docs in sorted(grouped_docs.items()):
        # Sort by created_at, taking the latest
        latest_doc = max(docs, key=lambda d: d.get("created_at") or datetime.min)

        filename = generate_filename(number, is_response)
        filepath = os.path.join(output_dir, filename)

        # Get content
        content = latest_doc.get("content", "")

        if not content:
            print(f"Warning: Document {latest_doc.get('document_name')} has no content. Skipping.")
            continue

        # Write to file
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        doc_name = latest_doc.get("document_name")
        doc_id = latest_doc.get("_id")
        version = latest_doc.get("version", "N/A")
        print(f"✓ Downloaded: {filename} (from document: {doc_name}, version: {version}, id: {doc_id})")

        if len(docs) > 1:
            print(f"  (Selected latest from {len(docs)} versions)")

        downloaded_count += 1

    print("-" * 60)
    print(f"\nSuccessfully downloaded {downloaded_count} documents to {output_dir}")

    client.close()

if __name__ == "__main__":
    try:
        download_documents()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
