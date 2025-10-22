#!/usr/bin/env python3

import argparse
import logging
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

DATA_COLLECTION_MS_URL = os.getenv("DATA_COLLECTION_MS_URL")
CATALOG_MS_URL = os.getenv("CATALOG_MS_URL")
API_KEY = os.getenv("X_API_KEY")

FORM_KEY_PREFIX = "docoloco-"


def get_headers():
    return {
        "Content-Type": "application/json",
        "x-api-key": API_KEY
    }


def fetch_schema(schema_id: str) -> dict:
    url = f"{DATA_COLLECTION_MS_URL}/data-schemas/{schema_id}"
    response = requests.get(url, headers=get_headers())
    response.raise_for_status()
    return response.json()


def update_output_schema(
    output_schema_id: str, output_schema_data: dict, input_schema: dict
):
    url = f"{DATA_COLLECTION_MS_URL}/data-schemas/{output_schema_id}"
    payload = {
        "name": output_schema_data["name"],
        "key": output_schema_data["key"],
        "schema": input_schema["schema"]
    }
    response = requests.put(url, json=payload, headers=get_headers())
    response.raise_for_status()
    return response.json()


def fetch_input_forms(input_schema_id: str) -> list:
    url = f"{DATA_COLLECTION_MS_URL}/forms"
    params = {"dataSchemaId": input_schema_id}
    response = requests.get(url, params=params, headers=get_headers())
    response.raise_for_status()
    result = response.json()
    return result.get("forms", [])


def check_form_exists(output_schema_id: str, form_key: str) -> dict | None:
    url = f"{DATA_COLLECTION_MS_URL}/forms"
    params = {
        "dataSchemaId": output_schema_id,
        "keys": form_key
    }
    response = requests.get(url, params=params, headers=get_headers())
    response.raise_for_status()
    result = response.json()
    forms = result.get("forms", [])
    return forms[0] if forms else None


def create_form(form_data: dict, output_schema_id: str, new_key: str):
    url = f"{DATA_COLLECTION_MS_URL}/forms"
    payload = {
        "name": form_data["name"],
        "key": new_key,
        "schema": form_data["schema"],
        "dataSchemaId": output_schema_id
    }
    response = requests.post(url, json=payload, headers=get_headers())
    response.raise_for_status()
    return response.json()


def update_form(
    form_id: str, form_data: dict, output_schema_id: str, new_key: str
):
    url = f"{DATA_COLLECTION_MS_URL}/forms/{form_id}"
    payload = {
        "name": form_data["name"],
        "key": new_key,
        "schema": form_data["schema"],
        "dataSchemaId": output_schema_id
    }
    response = requests.put(url, json=payload, headers=get_headers())
    response.raise_for_status()
    return response.json()


def fetch_catalog_drafts(form_keys: list) -> list:
    if not form_keys:
        return []

    url = f"{CATALOG_MS_URL}/catalog/drafts"
    params = {"formKeys": form_keys}
    response = requests.get(url, params=params, headers=get_headers())
    response.raise_for_status()
    return response.json()


def update_catalog_draft(draft_id: str, new_form_key: str):
    url = f"{CATALOG_MS_URL}/catalog/drafts/{draft_id}"
    payload = {"formKey": new_form_key}
    response = requests.patch(url, json=payload, headers=get_headers())
    response.raise_for_status()
    return response.json()


def copy_schema_forms(input_schema_id: str, output_schema_id: str):
    if not API_KEY:
        logger.error("X_API_KEY not found in environment variables")
        sys.exit(1)

    if not DATA_COLLECTION_MS_URL:
        logger.error(
            "DATA_COLLECTION_MS_URL not found in environment variables"
        )
        sys.exit(1)

    if not CATALOG_MS_URL:
        logger.error("CATALOG_MS_URL not found in environment variables")
        sys.exit(1)

    try:
        print(f"Fetching input schema: {input_schema_id}")
        input_schema = fetch_schema(input_schema_id)

        print(f"Fetching output schema: {output_schema_id}")
        output_schema = fetch_schema(output_schema_id)

        print(f"Updating output schema: {output_schema_id}")
        update_output_schema(output_schema_id, output_schema, input_schema)
        print("✓ Output schema updated")

        print(f"Fetching forms for input schema: {input_schema_id}")
        input_forms = fetch_input_forms(input_schema_id)
        print(f"Found {len(input_forms)} forms")

        created_forms = 0
        updated_forms = 0
        original_form_keys = []
        form_key_mapping = {}

        for form in input_forms:
            original_key = form["key"]
            new_key = f"{FORM_KEY_PREFIX}{original_key}"
            original_form_keys.append(original_key)
            form_key_mapping[original_key] = new_key

            existing_form = check_form_exists(output_schema_id, new_key)

            if existing_form:
                print(f"  Updating form: {new_key}")
                update_form(
                    existing_form["id"], form, output_schema_id, new_key
                )
                updated_forms += 1
            else:
                print(f"  Creating form: {new_key}")
                create_form(form, output_schema_id, new_key)
                created_forms += 1

        print(f"✓ Forms created: {created_forms}, updated: {updated_forms}")

        print(
            f"Searching for catalog drafts with original form keys: "
            f"{original_form_keys}"
        )
        catalog_drafts = fetch_catalog_drafts(original_form_keys)
        print(f"Found {len(catalog_drafts)} catalog drafts")

        updated_drafts = 0
        for draft in catalog_drafts:
            draft_id = draft["id"]
            old_form_key = draft["formKey"]
            new_form_key = form_key_mapping.get(old_form_key)

            if new_form_key:
                print(f"  Updating draft: {draft_id} "
                      f"(formKey: {old_form_key} -> {new_form_key})")
                update_catalog_draft(draft_id, new_form_key)
                updated_drafts += 1
            else:
                print(f"  Warning: No mapping found for draft {draft_id} "
                      f"with formKey: {old_form_key}")

        print(f"✓ Catalog drafts updated: {updated_drafts}")

        print("\n=== Summary ===")
        print(f"Output schema updated: {output_schema_id}")
        print(f"Forms created: {created_forms}")
        print(f"Forms updated: {updated_forms}")
        print(f"Catalog drafts updated: {updated_drafts}")
        print("=== Complete ===")

    except Exception as e:
        logger.error(f"Failed to copy schema forms: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Copy data schema and forms from input schema "
            "to output schema"
        )
    )
    parser.add_argument(
        "input_schema_id",
        help="ID of the input data schema to copy from"
    )
    parser.add_argument(
        "output_schema_id",
        help="ID of the output data schema to update"
    )

    args = parser.parse_args()

    copy_schema_forms(args.input_schema_id, args.output_schema_id)


if __name__ == "__main__":
    main()
