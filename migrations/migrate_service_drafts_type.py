#!/usr/bin/env python3
"""
Migration script to set type='SERVICE' for all existing ServiceDrafts.

Context: PR1 of FLA-21/DC-2449 adds a required `type` field to ServiceDrafts.
All existing documents need to be migrated to have type='SERVICE'.

Usage:
    python migrate_service_drafts_type.py [--mongo-uri MONGO_URI] [--dry-run]

Environment Variables:
    MONGO_URI: MongoDB connection string (default: staging marble database)

Examples:
    # Dry run on staging
    python migrate_service_drafts_type.py --dry-run

    # Actual migration on staging
    python migrate_service_drafts_type.py

    # Custom MongoDB URI
    python migrate_service_drafts_type.py --mongo-uri "mongodb+srv://..." --dry-run
"""

import argparse
import logging
import os
import sys
from typing import Optional

from pymongo import MongoClient
from pymongo.database import Database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Default MongoDB URI for staging
DEFAULT_MONGO_URI = (
    "mongodb+srv://node:marblerules1@marble-staging2.jycnt.mongodb.net/marble"
)

COLLECTION_NAME = "servicedrafts"
SERVICE_DRAFT_TYPE = "SERVICE"


class ServiceDraftsTypeMigration:
    """Migration to set type='SERVICE' for all existing ServiceDrafts."""

    def __init__(self, mongo_uri: str, dry_run: bool = True):
        """
        Initialize the migration.

        Args:
            mongo_uri: MongoDB connection string
            dry_run: If True, simulate the migration without making changes
        """
        self.mongo_uri = mongo_uri
        self.dry_run = dry_run
        self.client: Optional[MongoClient] = None
        self.db: Optional[Database] = None

    def connect(self) -> bool:
        """Connect to MongoDB."""
        try:
            logger.info("Connecting to MongoDB...")
            self.client = MongoClient(self.mongo_uri)

            # Parse database name from URI
            if "/" in self.mongo_uri.split("@")[-1]:
                db_name = self.mongo_uri.split("@")[-1].split("/")[1].split("?")[0]
            else:
                db_name = "marble"

            self.db = self.client[db_name]

            # Test connection
            self.db.command('ping')
            logger.info(f"Connected to MongoDB database: {db_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            return False

    def disconnect(self) -> None:
        """Disconnect from MongoDB."""
        if self.client:
            self.client.close()
            logger.info("Disconnected from MongoDB")

    def get_counts(self) -> dict:
        """Get document counts."""
        collection = self.db[COLLECTION_NAME]

        total = collection.count_documents({})
        with_type = collection.count_documents({"type": {"$exists": True}})
        without_type = collection.count_documents({"type": {"$exists": False}})

        return {
            "total": total,
            "with_type": with_type,
            "without_type": without_type
        }

    def get_sample_documents(self, limit: int = 5) -> list:
        """Get sample documents that would be updated."""
        collection = self.db[COLLECTION_NAME]
        return list(collection.find(
            {"type": {"$exists": False}},
            {"_id": 1, "userId": 1, "caseId": 1, "serviceId": 1, "status": 1}
        ).limit(limit))

    def run_migration(self) -> dict:
        """
        Run the migration.

        Returns:
            Dictionary with migration results
        """
        collection = self.db[COLLECTION_NAME]

        # Get counts before migration
        counts = self.get_counts()
        logger.info(f"Total ServiceDrafts: {counts['total']}")
        logger.info(f"Already have type: {counts['with_type']}")
        logger.info(f"Missing type (to migrate): {counts['without_type']}")

        if counts['without_type'] == 0:
            logger.info("No documents need migration. All ServiceDrafts already have a type field.")
            return {"status": "no_changes_needed", "counts": counts}

        if self.dry_run:
            logger.info(f"[DRY RUN] Would update {counts['without_type']} documents to have type='{SERVICE_DRAFT_TYPE}'")

            # Show sample documents
            sample = self.get_sample_documents()
            if sample:
                logger.info("Sample documents to be updated:")
                for i, doc in enumerate(sample, 1):
                    logger.info(f"  {i}. _id: {doc['_id']}, userId: {doc.get('userId')}, "
                              f"caseId: {doc.get('caseId')}, serviceId: {doc.get('serviceId')}")

            logger.warning("To run the actual migration, remove the --dry-run flag")
            return {"status": "dry_run", "counts": counts, "sample": sample}

        # Run actual migration
        logger.info("Running migration...")

        result = collection.update_many(
            {"type": {"$exists": False}},
            {"$set": {"type": SERVICE_DRAFT_TYPE}}
        )

        logger.info(f"Migration complete!")
        logger.info(f"  Matched: {result.matched_count}")
        logger.info(f"  Modified: {result.modified_count}")

        # Verify
        remaining = collection.count_documents({"type": {"$exists": False}})
        if remaining == 0:
            logger.info("Verification passed: All ServiceDrafts now have a type field.")
        else:
            logger.warning(f"Warning: {remaining} documents still missing type field.")

        return {
            "status": "completed",
            "matched": result.matched_count,
            "modified": result.modified_count,
            "remaining_without_type": remaining
        }


def main():
    parser = argparse.ArgumentParser(
        description="Migrate ServiceDrafts to have type='SERVICE'"
    )
    parser.add_argument(
        "--mongo-uri",
        default=os.environ.get("MONGO_URI", DEFAULT_MONGO_URI),
        help="MongoDB connection string"
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

    args = parser.parse_args()

    # --execute flag disables dry-run
    dry_run = args.dry_run and not args.execute

    logger.info("=" * 50)
    logger.info("ServiceDrafts Type Migration")
    logger.info("=" * 50)
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    logger.info(f"Collection: {COLLECTION_NAME}")
    logger.info(f"Target type: {SERVICE_DRAFT_TYPE}")
    logger.info("")

    migration = ServiceDraftsTypeMigration(
        mongo_uri=args.mongo_uri,
        dry_run=dry_run
    )

    if not migration.connect():
        sys.exit(1)

    try:
        result = migration.run_migration()
        logger.info(f"Result: {result}")
    finally:
        migration.disconnect()


if __name__ == "__main__":
    main()
