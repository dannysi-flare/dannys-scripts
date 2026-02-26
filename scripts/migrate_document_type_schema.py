#!/usr/bin/env python3
"""
Migrate document types to data-collection schemas and forms.

For document types that were created without schemas/forms, this script:
1. Fetches the document type details from catalog-ms
2. Updates the data schema with the document type definition
3. Creates a document form for the document type

Usage:
    python scripts/migrate_document_type_schema.py <document_type_id> [<document_type_id> ...]

Environment variables (.env):
    BASE_URL       - API gateway base URL (e.g. https://api.staging.helloflare.com)
    X_API_KEY      - API gateway key
    SCHEMA_ID      - The data schema ID to update (DOCUMENT_SCHEMA_IDENTIFIER)
"""

import argparse
import logging
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
X_API_KEY = os.getenv("X_API_KEY", "")
SCHEMA_ID = os.getenv("SCHEMA_ID", "")


def get_headers() -> dict:
    return {
        "x-api-key": X_API_KEY,
        "Content-Type": "application/json",
    }


def fetch_document_type(document_type_id: str) -> dict:
    """Fetch document type details from catalog-ms."""
    url = f"{BASE_URL}/catalog/documents/{document_type_id}"
    resp = requests.get(url, headers=get_headers())
    resp.raise_for_status()
    return resp.json()


def update_schema_documents(schema_id: str, document_types: list[dict]) -> dict:
    """PATCH data schema with document type definitions."""
    url = f"{BASE_URL}/data-collection/data-schemas/{schema_id}/documents"
    resp = requests.patch(url, headers=get_headers(), json=document_types)
    resp.raise_for_status()
    return resp.json()


def create_document_forms(schema_id: str, document_types: list[dict]) -> list[dict]:
    """POST to create document forms."""
    url = f"{BASE_URL}/data-collection/forms/document-forms"
    payload = {
        "dataSchemaId": schema_id,
        "documentTypes": document_types,
    }
    resp = requests.post(url, headers=get_headers(), json=payload)
    resp.raise_for_status()
    return resp.json()


def migrate_document_type(document_type_id: str, schema_id: str) -> None:
    """Run the full migration for a single document type."""
    logger.info(f"Fetching document type {document_type_id}...")
    doc_type = fetch_document_type(document_type_id)
    logger.info(f"  Found: {doc_type['name']} ({doc_type['id']})")

    doc_type_data = [
        {"id": doc_type["id"], "name": doc_type["name"], "multiple": True}
    ]

    logger.info(f"  Updating schema {schema_id} with document definition...")
    schema = update_schema_documents(schema_id, doc_type_data)
    logger.info(f"  Schema updated: {schema.get('id', schema_id)}")

    logger.info(f"  Creating document form...")
    forms = create_document_forms(schema["id"], doc_type_data)
    logger.info(f"  Forms created: {len(forms)}")


def main():
    parser = argparse.ArgumentParser(
        description="Migrate document types to data-collection schemas and forms"
    )
    parser.add_argument(
        "document_type_ids",
        nargs="+",
        help="One or more document type IDs to migrate",
    )
    parser.add_argument(
        "--schema-id",
        default=SCHEMA_ID,
        help="Data schema ID (overrides SCHEMA_ID env var)",
    )
    args = parser.parse_args()

    if not BASE_URL:
        logger.error("BASE_URL not set in .env")
        sys.exit(1)
    if not X_API_KEY:
        logger.error("X_API_KEY not set in .env")
        sys.exit(1)
    if not args.schema_id:
        logger.error("SCHEMA_ID not set in .env or --schema-id flag")
        sys.exit(1)

    for doc_id in args.document_type_ids:
        try:
            migrate_document_type(doc_id, args.schema_id)
            logger.info(f"  Done.\n")
        except requests.HTTPError as e:
            logger.error(f"  Failed for {doc_id}: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            logger.error(f"  Failed for {doc_id}: {e}")


if __name__ == "__main__":
    main()
