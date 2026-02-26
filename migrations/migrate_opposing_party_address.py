#!/usr/bin/env python3
"""
Migration script to validate and consolidate opposing party address fields.

For users with the target schema, this script:
1. Finds users who have all four address fields:
   - opposingPartyStreetAddress
   - opposingPartyCity
   - opposingPartyState
   - opposingPartyZip
2. Validates the assembled address against Google Address Validation API
3. If valid: creates opposingPartyLivingAddress with Google-normalized address
4. If invalid or missing fields: logs the userId as an error

Usage:
    python migrate_opposing_party_address.py [--env staging|prod] [--dry-run] [--execute]

Environment Variables:
    GOOGLE_API_KEY: Google Address Validation API key (required)

Examples:
    # Dry run on staging
    python migrate_opposing_party_address.py --env staging --dry-run

    # Actual migration on staging
    python migrate_opposing_party_address.py --env staging --execute

    # Production migration (dry run first!)
    python migrate_opposing_party_address.py --env prod --dry-run
"""

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import requests
from pymongo import MongoClient
from pymongo.database import Database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Schema IDs per environment
SCHEMA_IDS = {
    "staging": "66dee37286565b000812bb21",
    "prod": "66dec1950af2fa0007b0e36a"
}

# MongoDB connection strings
MONGO_URIS = {
    "staging": "mongodb+srv://node:marblerules1@marble-staging2.jycnt.mongodb.net/data-collection",
    "prod": None  # Will need to be provided via environment variable for production
}

DATABASE_NAME = "data-collection"
COLLECTION_NAME = "datapoints"

# Address field keys
ADDRESS_FIELDS = [
    "opposingPartyStreetAddress",
    "opposingPartyCity",
    "opposingPartyState",
    "opposingPartyZip"
]
TARGET_FIELD = "opposingPartyLivingAddress"

# Google Address Validation API endpoint
GOOGLE_ADDRESS_VALIDATION_URL = "https://addressvalidation.googleapis.com/v1:validateAddress"


@dataclass
class AddressComponents:
    street: str
    city: str
    state: str
    zip_code: str

    def to_assembled_string(self) -> str:
        """Assemble address components into a single string."""
        return f"{self.street}, {self.city}, {self.state} {self.zip_code}"


@dataclass
class MigrationResult:
    total_with_all_fields: int = 0
    total_with_partial_fields: int = 0
    total_already_has_living_address: int = 0
    total_valid_addresses: int = 0
    total_invalid_addresses: int = 0
    total_updated: int = 0
    errors: list = None  # type: ignore

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class GoogleAddressValidator:
    """Validates addresses using Google Address Validation API."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def validate(self, address: AddressComponents) -> tuple[bool, Optional[str]]:
        """
        Validate an address using Google Address Validation API.

        Returns:
            tuple: (is_valid, normalized_address or None)
        """
        try:
            payload = {
                "address": {
                    "regionCode": "US",
                    "addressLines": [address.to_assembled_string()]
                }
            }

            response = requests.post(
                f"{GOOGLE_ADDRESS_VALIDATION_URL}?key={self.api_key}",
                json=payload,
                timeout=10
            )

            if response.status_code != 200:
                logger.warning(f"Google API error: {response.status_code} - {response.text}")
                return False, None

            data = response.json()

            # Check the validation verdict
            verdict = data.get("result", {}).get("verdict", {})
            address_complete = verdict.get("addressComplete", False)
            has_unconfirmed = verdict.get("hasUnconfirmedComponents", True)

            # Get the formatted address from Google
            formatted_address = data.get("result", {}).get("address", {}).get("formattedAddress")

            # Consider valid if address is complete or has minimal unconfirmed components
            # and we got a formatted address back
            if formatted_address and (address_complete or not has_unconfirmed):
                return True, formatted_address

            # Also accept if geocode is present (Google found a location)
            geocode = data.get("result", {}).get("geocode")
            if formatted_address and geocode:
                return True, formatted_address

            return False, None

        except requests.exceptions.RequestException as e:
            logger.error(f"Request error validating address: {e}")
            return False, None
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return False, None


class OpposingPartyAddressMigration:
    """Migration to consolidate opposing party address fields."""

    def __init__(
        self,
        mongo_uri: str,
        schema_id: str,
        google_api_key: str,
        dry_run: bool = True
    ):
        self.mongo_uri = mongo_uri
        self.schema_id = schema_id
        self.dry_run = dry_run
        self.client: Optional[MongoClient] = None
        self.db: Optional[Database] = None
        self.validator = GoogleAddressValidator(google_api_key)

    def connect(self) -> bool:
        """Connect to MongoDB."""
        try:
            logger.info("Connecting to MongoDB...")
            self.client = MongoClient(self.mongo_uri)
            self.db = self.client[DATABASE_NAME]
            self.db.command('ping')
            logger.info(f"Connected to MongoDB database: {DATABASE_NAME}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            return False

    def disconnect(self) -> None:
        """Disconnect from MongoDB."""
        if self.client:
            self.client.close()
            logger.info("Disconnected from MongoDB")

    def find_users_with_address_fields(self) -> list:
        """
        Find all users that have any of the address fields in the target schema.

        Returns documents with userId and their address-related datapoints.
        """
        collection = self.db[COLLECTION_NAME]

        pipeline = [
            {"$unwind": "$dataPoints"},
            {"$match": {"dataPoints.dataSchemaId": self.schema_id}},
            {"$addFields": {
                "addressDataPoints": {
                    "$filter": {
                        "input": "$dataPoints.dataPoints",
                        "as": "dp",
                        "cond": {
                            "$in": ["$$dp.key", ADDRESS_FIELDS + [TARGET_FIELD]]
                        }
                    }
                }
            }},
            {"$match": {"addressDataPoints.0": {"$exists": True}}},
            {"$project": {
                "userId": 1,
                "addressDataPoints": 1,
                "schemaDataPoints": "$dataPoints"
            }}
        ]

        return list(collection.aggregate(pipeline, allowDiskUse=True))

    def extract_address_components(
        self,
        data_points: list
    ) -> tuple[Optional[AddressComponents], list[str], bool]:
        """
        Extract address components from datapoints.

        Returns:
            tuple: (AddressComponents or None, missing_fields, has_living_address)
        """
        values = {}
        has_living_address = False

        for dp in data_points:
            key = dp.get("key")
            value = dp.get("value")

            if key == TARGET_FIELD:
                has_living_address = True
                continue

            if key in ADDRESS_FIELDS and value:
                # Convert zip to string if it's a number
                if key == "opposingPartyZip":
                    value = str(value)
                values[key] = str(value).strip()

        # Check for missing fields
        missing = [f for f in ADDRESS_FIELDS if f not in values or not values[f]]

        if missing:
            return None, missing, has_living_address

        return AddressComponents(
            street=values["opposingPartyStreetAddress"],
            city=values["opposingPartyCity"],
            state=values["opposingPartyState"],
            zip_code=values["opposingPartyZip"]
        ), [], has_living_address

    def add_living_address_datapoint(
        self,
        user_id: str,
        doc_id: str,
        normalized_address: str
    ) -> bool:
        """
        Add the opposingPartyLivingAddress datapoint to the user's record.
        """
        collection = self.db[COLLECTION_NAME]

        new_datapoint = {
            "key": TARGET_FIELD,
            "value": normalized_address,
            "type": "string",
            "contextType": "USER",
            "contextId": user_id,
            "dataSchemaId": self.schema_id,
            "source": {"type": "MIGRATION", "context": "opposing_party_address_consolidation"},
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc)
        }

        # Update the document by pushing the new datapoint into the correct schema's dataPoints array
        result = collection.update_one(
            {
                "_id": doc_id,
                "dataPoints.dataSchemaId": self.schema_id
            },
            {
                "$push": {"dataPoints.$.dataPoints": new_datapoint},
                "$set": {
                    "dataPoints.$.updatedAt": datetime.now(timezone.utc),
                    "updatedAt": datetime.now(timezone.utc)
                }
            }
        )

        return result.modified_count > 0

    def run_migration(self) -> MigrationResult:
        """Run the migration."""
        result = MigrationResult()

        logger.info(f"Finding users with address fields for schema: {self.schema_id}")
        users = self.find_users_with_address_fields()
        logger.info(f"Found {len(users)} users with address-related datapoints")

        for user_doc in users:
            user_id = user_doc.get("userId")
            doc_id = user_doc.get("_id")
            address_dps = user_doc.get("addressDataPoints", [])

            # Extract address components
            address, missing_fields, has_living_address = self.extract_address_components(address_dps)

            # Skip if already has living address
            if has_living_address:
                result.total_already_has_living_address += 1
                logger.debug(f"User {user_id}: Already has {TARGET_FIELD}, skipping")
                continue

            # Log error if missing fields
            if missing_fields:
                result.total_with_partial_fields += 1
                result.errors.append({
                    "userId": user_id,
                    "reason": "missing_fields",
                    "missing": missing_fields
                })
                logger.warning(f"User {user_id}: Missing fields {missing_fields}")
                continue

            result.total_with_all_fields += 1

            # Validate address with Google (address is guaranteed non-None here)
            assert address is not None  # For type checker
            assembled = address.to_assembled_string()
            is_valid, normalized_address = self.validator.validate(address)

            if not is_valid:
                result.total_invalid_addresses += 1
                result.errors.append({
                    "userId": user_id,
                    "reason": "invalid_address",
                    "assembled_address": assembled
                })
                logger.warning(f"User {user_id}: Invalid address '{assembled}'")
                continue

            result.total_valid_addresses += 1
            logger.info(f"User {user_id}: Valid address '{assembled}' -> '{normalized_address}'")

            # Update if not dry run (normalized_address is guaranteed non-None here since is_valid is True)
            if not self.dry_run and normalized_address:
                if self.add_living_address_datapoint(user_id, doc_id, normalized_address):
                    result.total_updated += 1
                    logger.info(f"User {user_id}: Successfully added {TARGET_FIELD}")
                else:
                    result.errors.append({
                        "userId": user_id,
                        "reason": "update_failed",
                        "normalized_address": normalized_address
                    })
                    logger.error(f"User {user_id}: Failed to update document")

        return result


def main():
    parser = argparse.ArgumentParser(
        description="Migrate opposing party address fields to consolidated living address"
    )
    parser.add_argument(
        "--env",
        choices=["staging", "prod"],
        default="staging",
        help="Environment to run migration on (default: staging)"
    )
    parser.add_argument(
        "--mongo-uri",
        help="Override MongoDB connection string"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Simulate migration without making changes (default: True)"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute the migration (disables dry-run)"
    )
    parser.add_argument(
        "--output-errors",
        help="File path to output errors JSON (optional)"
    )

    args = parser.parse_args()

    # Get Google API key
    google_api_key = os.environ.get("GOOGLE_API_KEY")
    if not google_api_key:
        logger.error("GOOGLE_API_KEY environment variable is required")
        sys.exit(1)

    # Determine MongoDB URI
    mongo_uri = args.mongo_uri or MONGO_URIS.get(args.env)
    if not mongo_uri:
        mongo_uri = os.environ.get("MONGO_URI")
    if not mongo_uri:
        logger.error(f"No MongoDB URI available for environment: {args.env}")
        sys.exit(1)

    # Determine schema ID
    schema_id = SCHEMA_IDS.get(args.env)
    if not schema_id:
        logger.error(f"No schema ID configured for environment: {args.env}")
        sys.exit(1)

    # Determine dry run mode
    dry_run = args.dry_run and not args.execute

    logger.info("=" * 60)
    logger.info("Opposing Party Address Migration")
    logger.info("=" * 60)
    logger.info(f"Environment: {args.env}")
    logger.info(f"Schema ID: {schema_id}")
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    logger.info("")

    migration = OpposingPartyAddressMigration(
        mongo_uri=mongo_uri,
        schema_id=schema_id,
        google_api_key=google_api_key,
        dry_run=dry_run
    )

    if not migration.connect():
        sys.exit(1)

    try:
        result = migration.run_migration()

        logger.info("")
        logger.info("=" * 60)
        logger.info("Migration Results")
        logger.info("=" * 60)
        logger.info(f"Users with all 4 address fields: {result.total_with_all_fields}")
        logger.info(f"Users with partial fields (error): {result.total_with_partial_fields}")
        logger.info(f"Users already having {TARGET_FIELD}: {result.total_already_has_living_address}")
        logger.info(f"Valid addresses: {result.total_valid_addresses}")
        logger.info(f"Invalid addresses: {result.total_invalid_addresses}")
        if not dry_run:
            logger.info(f"Successfully updated: {result.total_updated}")
        logger.info(f"Total errors: {len(result.errors)}")

        # Output errors if requested
        if args.output_errors and result.errors:
            with open(args.output_errors, 'w') as f:
                json.dump(result.errors, f, indent=2)
            logger.info(f"Errors written to: {args.output_errors}")
        elif result.errors:
            logger.info("\nError details:")
            for err in result.errors[:20]:  # Show first 20 errors
                logger.info(f"  - userId: {err['userId']}, reason: {err['reason']}")
            if len(result.errors) > 20:
                logger.info(f"  ... and {len(result.errors) - 20} more errors")

        if dry_run:
            logger.warning("\nThis was a DRY RUN. To execute, use the --execute flag.")

    finally:
        migration.disconnect()


if __name__ == "__main__":
    main()
