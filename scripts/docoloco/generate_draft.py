#!/usr/bin/env python3

import argparse
import base64
import json
import logging
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

DOCUMENTS_MS_URL = os.getenv("DOCUMENTS_MS_URL")
API_KEY = os.getenv("X_API_KEY")


def encode_file_to_base64(file_path: str) -> str:
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def load_tokens(tokens_file: str) -> dict:
    with open(tokens_file, "r") as f:
        return json.load(f)


def generate_draft(document_path: str, tokens_path: str, output_path: str):
    if not API_KEY:
        logger.error("X_API_KEY not found in environment variables")
        sys.exit(1)

    if not DOCUMENTS_MS_URL:
        logger.error("DOCUMENTS_MS_URL not found in environment variables")
        sys.exit(1)

    api_url = f"{DOCUMENTS_MS_URL}/drafts/generateDraftFromTemplate"

    try:
        base64_content = encode_file_to_base64(document_path)
        tokens = load_tokens(tokens_path)

        payload = {
            "base64Content": base64_content,
            "tokens": tokens,
            "format": "DOCX"
        }

        headers = {
            "Content-Type": "application/json",
            "x-api-key": API_KEY
        }

        response = requests.post(api_url, json=payload, headers=headers)
        response.raise_for_status()

        result = response.json()
        base64_output = result.get("base64Content")

        if not base64_output:
            raise ValueError("No base64Content in response")

        decoded_content = base64.b64decode(base64_output)

        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        with open(output_path, "wb") as f:
            f.write(decoded_content)

        print(f"Generated draft saved to: {output_path}")

    except Exception as e:
        logger.error(f"Failed to generate draft: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("document", help="Path to input document file")
    parser.add_argument("tokens", help="Path to JSON file containing tokens")
    parser.add_argument(
        "-o", "--output",
        default="outputs/Generated Petition.docx",
        help="Output file path (default: outputs/Generated Petition.docx)"
    )

    args = parser.parse_args()

    generate_draft(args.document, args.tokens, args.output)


if __name__ == "__main__":
    main()
