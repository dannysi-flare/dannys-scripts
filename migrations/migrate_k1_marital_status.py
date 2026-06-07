#!/usr/bin/env python3
"""
Migration script to update K-1 visa marital status datapoint values.

Linear ticket: AS-3284 (https://linear.app/helloflare/issue/AS-3284/immigration-k-1-csv-update)

The K-1 CSV update renamed the "Single" selection option to "Single never married"
for the marital status questions. This script finds all datapoints with:
    - key in [beneficiaryMaritalStatus, petitionerMarital]
    - value == "Single"
and updates the value to "Single never married".

Usage:
    python migrate_k1_marital_status.py [--env staging|prod] [--dry-run] [--execute] [--user-id USER_ID]

Examples:
    # Dry run on staging (default)
    python migrate_k1_marital_status.py --env staging --dry-run

    # Dry run for a specific user
    python migrate_k1_marital_status.py --env staging --dry-run --user-id 64f1c2...

    # Actual migration on staging
    python migrate_k1_marital_status.py --env staging --execute

    # Production migration (dry run first!)
    python migrate_k1_marital_status.py --env prod --dry-run
"""

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

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

# MongoDB connection strings — taken from env (exported in ~/.zshrc).
# The database is selected explicitly via client[DATABASE_NAME], so the
# db path in the URI doesn't matter; authSource=admin must be present.
MONGO_URIS = {
    "staging": os.environ.get("MONGODB_STAGING_URI"),
    "prod": os.environ.get("MONGODB_PRODUCTION_URI")
}

DATABASE_NAME = "data-collection"
COLLECTION_NAME = "datapoints"

# Datapoint keys to migrate
TARGET_KEYS = [
    "beneficiaryMaritalStatus",
    "petitionerMarital"
]

OLD_VALUE = "Single"
NEW_VALUE = "Single never married"


@dataclass
class MigrationResult:
    total_documents_matched: int = 0
    total_datapoints_matched: int = 0
    total_documents_updated: int = 0
    total_datapoints_updated: int = 0
    matches: list = field(default_factory=list)
    errors: list = field(default_factory=list)


class K1MaritalStatusMigration:
    """Migration to rename 'Single' -> 'Single never married' for K-1 marital status datapoints."""

    def __init__(
        self,
        mongo_uri: str,
        schema_id: str,
        dry_run: bool = True,
        user_id: Optional[str] = None
    ):
        self.mongo_uri = mongo_uri
        self.schema_id = schema_id
        self.dry_run = dry_run
        self.user_id = user_id
        self.client: Optional[MongoClient] = None
        self.db: Optional[Database] = None

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

    def _base_match(self) -> dict:
        """Build the top-level document match filter."""
        match = {
            "dataPoints.dataPoints": {
                "$elemMatch": {
                    "dataSchemaId": self.schema_id,
                    "key": {"$in": TARGET_KEYS},
                    "value": OLD_VALUE
                }
            }
        }
        if self.user_id:
            match["userId"] = self.user_id
        return match

    def find_matching_datapoints(self) -> list:
        """
        Find all nested datapoints with a 'Single' value for the target keys.

        Returns one entry per matching nested datapoint with parent metadata.
        """
        collection = self.db[COLLECTION_NAME]

        pipeline = [
            {"$match": self._base_match()},
            {"$unwind": "$dataPoints"},
            {"$unwind": "$dataPoints.dataPoints"},
            {"$match": {
                "dataPoints.dataPoints.dataSchemaId": self.schema_id,
                "dataPoints.dataPoints.key": {"$in": TARGET_KEYS},
                "dataPoints.dataPoints.value": OLD_VALUE
            }},
            {"$project": {
                "_id": 1,
                "userId": 1,
                "key": "$dataPoints.dataPoints.key",
                "value": "$dataPoints.dataPoints.value"
            }}
        ]

        return list(collection.aggregate(pipeline, allowDiskUse=True))

    def update_document(self, doc_id) -> int:
        """
        Update all matching nested datapoints in a single document.

        Returns the number of documents modified (0 or 1).
        """
        collection = self.db[COLLECTION_NAME]
        now = datetime.now(timezone.utc)

        result = collection.update_one(
            {"_id": doc_id},
            {
                "$set": {
                    "dataPoints.$[outer].dataPoints.$[inner].value": NEW_VALUE,
                    "dataPoints.$[outer].dataPoints.$[inner].updatedAt": now,
                    "updatedAt": now
                }
            },
            array_filters=[
                {"outer.dataSchemaId": self.schema_id},
                {
                    "inner.dataSchemaId": self.schema_id,
                    "inner.key": {"$in": TARGET_KEYS},
                    "inner.value": OLD_VALUE
                }
            ]
        )

        return result.modified_count

    def run_migration(self) -> MigrationResult:
        """Run the migration."""
        result = MigrationResult()

        logger.info(f"Finding '{OLD_VALUE}' marital status datapoints for schema: {self.schema_id}")
        if self.user_id:
            logger.info(f"Limited to userId: {self.user_id}")

        matches = self.find_matching_datapoints()
        result.total_datapoints_matched = len(matches)

        # Group matches by document for update + reporting
        docs = {}
        for m in matches:
            doc_id = m["_id"]
            docs.setdefault(doc_id, []).append(m)
            result.matches.append({
                "documentId": str(doc_id),
                "userId": m.get("userId"),
                "key": m["key"],
                "currentValue": m["value"],
                "newValue": NEW_VALUE
            })

        result.total_documents_matched = len(docs)
        logger.info(
            f"Found {result.total_datapoints_matched} matching datapoints "
            f"across {result.total_documents_matched} documents"
        )

        for doc_id, doc_matches in docs.items():
            user_id = doc_matches[0].get("userId")
            keys = [m["key"] for m in doc_matches]

            if self.dry_run:
                logger.info(
                    f"[DRY RUN] Would update doc {doc_id} (userId: {user_id}): "
                    f"{keys} '{OLD_VALUE}' -> '{NEW_VALUE}'"
                )
                continue

            try:
                modified = self.update_document(doc_id)
                if modified:
                    result.total_documents_updated += 1
                    result.total_datapoints_updated += len(doc_matches)
                    logger.info(
                        f"Updated doc {doc_id} (userId: {user_id}): "
                        f"{keys} '{OLD_VALUE}' -> '{NEW_VALUE}'"
                    )
                else:
                    result.errors.append({
                        "documentId": str(doc_id),
                        "userId": user_id,
                        "reason": "update_did_not_modify"
                    })
                    logger.error(f"Doc {doc_id} (userId: {user_id}): update did not modify document")
            except Exception as e:
                result.errors.append({
                    "documentId": str(doc_id),
                    "userId": user_id,
                    "reason": "update_failed",
                    "error": str(e)
                })
                logger.error(f"Doc {doc_id} (userId: {user_id}): update failed: {e}")

        return result


def main():
    parser = argparse.ArgumentParser(
        description=f"Migrate K-1 marital status datapoints from '{OLD_VALUE}' to '{NEW_VALUE}' (AS-3284)"
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
        "--schema-id",
        help="Override data schema ID"
    )
    parser.add_argument(
        "--user-id",
        help="Limit the migration to a specific userId"
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
        "--output-report",
        help="File path to output matches/errors JSON (optional)"
    )

    args = parser.parse_args()

    # Determine MongoDB URI
    mongo_uri = args.mongo_uri or MONGO_URIS.get(args.env)
    if not mongo_uri:
        mongo_uri = os.environ.get("MONGO_URI")
    if not mongo_uri:
        logger.error(f"No MongoDB URI available for environment: {args.env}")
        sys.exit(1)

    # Determine schema ID
    schema_id = args.schema_id or SCHEMA_IDS.get(args.env)
    if not schema_id:
        logger.error(f"No schema ID configured for environment: {args.env}")
        sys.exit(1)

    # Determine dry run mode
    dry_run = args.dry_run and not args.execute

    logger.info("=" * 60)
    logger.info("K-1 Marital Status Migration (AS-3284)")
    logger.info("=" * 60)
    logger.info(f"Environment: {args.env}")
    logger.info(f"Schema ID: {schema_id}")
    logger.info(f"Keys: {TARGET_KEYS}")
    logger.info(f"Change: '{OLD_VALUE}' -> '{NEW_VALUE}'")
    if args.user_id:
        logger.info(f"User ID filter: {args.user_id}")
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    logger.info("")

    if not dry_run:
        confirm = input(f"About to update datapoints in {args.env.upper()}. Type 'yes' to continue: ")
        if confirm.strip().lower() != "yes":
            logger.info("Aborted by user")
            sys.exit(0)

    migration = K1MaritalStatusMigration(
        mongo_uri=mongo_uri,
        schema_id=schema_id,
        dry_run=dry_run,
        user_id=args.user_id
    )

    if not migration.connect():
        sys.exit(1)

    try:
        result = migration.run_migration()

        logger.info("")
        logger.info("=" * 60)
        logger.info("Migration Results")
        logger.info("=" * 60)
        logger.info(f"Documents matched: {result.total_documents_matched}")
        logger.info(f"Datapoints matched: {result.total_datapoints_matched}")
        if not dry_run:
            logger.info(f"Documents updated: {result.total_documents_updated}")
            logger.info(f"Datapoints updated: {result.total_datapoints_updated}")
        logger.info(f"Total errors: {len(result.errors)}")

        # Output report if requested
        if args.output_report:
            with open(args.output_report, 'w') as f:
                json.dump({"matches": result.matches, "errors": result.errors}, f, indent=2)
            logger.info(f"Report written to: {args.output_report}")

        if result.errors:
            logger.info("\nError details:")
            for err in result.errors[:20]:
                logger.info(f"  - documentId: {err['documentId']}, userId: {err.get('userId')}, reason: {err['reason']}")
            if len(result.errors) > 20:
                logger.info(f"  ... and {len(result.errors) - 20} more errors")

        if dry_run:
            logger.warning("\nThis was a DRY RUN. To execute, use the --execute flag.")

    finally:
        migration.disconnect()


if __name__ == "__main__":
    main()
