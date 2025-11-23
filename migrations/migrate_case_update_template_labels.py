#!/usr/bin/env python3
"""
Migration script to populate the label field in case update templates.

This script updates all case update templates in the catalog database:
- Sets the label field to the value of the name field
- Skips templates where the name starts with "California"

Usage:
    python migrate_case_update_template_labels.py [--mongo-uri MONGO_URI] [--dry-run]

Environment Variables:
    MONGO_URI: MongoDB connection string (default: local development)
"""

import argparse
import logging
import os
import sys
from typing import Dict, List

from pymongo import MongoClient
from pymongo.database import Database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Default MongoDB URI for local development
DEFAULT_MONGO_URI = (
    "mongodb://marble-dev-user:marblerulez42@localhost:27018/"
    "catalog?authSource=admin"
)

# Note: For staging/production, use:
# mongodb+srv://node:marblerules1@marble-stg.jycnt.mongodb.net/catalog


class CaseUpdateTemplateLabelMigration:
    """Migration to populate label fields in case update templates."""

    def __init__(self, mongo_uri: str, dry_run: bool = False):
        """
        Initialize the migration.

        Args:
            mongo_uri: MongoDB connection string
            dry_run: If True, simulate the migration without making changes
        """
        self.mongo_uri = mongo_uri
        self.dry_run = dry_run
        self.client: MongoClient = None
        self.db: Database = None

    def connect(self) -> bool:
        """Connect to MongoDB."""
        try:
            logger.info(f"Connecting to MongoDB...")
            self.client = MongoClient(self.mongo_uri)

            # Parse database name from URI
            # Format: mongodb://user:pass@host:port/dbname?params
            if "/" in self.mongo_uri.split("@")[-1]:
                db_name = self.mongo_uri.split("@")[-1].split("/")[1].split("?")[0]
            else:
                db_name = "catalog"

            self.db = self.client[db_name]

            # Test connection
            self.db.command('ping')
            logger.info(f"✅ Connected to MongoDB database: {db_name}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to connect to MongoDB: {e}")
            return False

    def disconnect(self):
        """Disconnect from MongoDB."""
        if self.client:
            self.client.close()
            logger.info("Disconnected from MongoDB")

    def get_templates_to_update(self) -> List[Dict]:
        """
        Get all case update templates that need label updates.

        Returns:
            List of templates that need to be updated
        """
        collection = self.db['caseupdatetemplates']

        # Find all templates where label field is missing or empty
        query = {
            "$or": [
                {"label": {"$exists": False}},
                {"label": None},
                {"label": ""}
            ]
        }

        templates = list(collection.find(query))
        logger.info(f"Found {len(templates)} templates to update")

        return templates

    def calculate_label(self, name: str) -> str:
        """
        Calculate the label value based on the name.

        If name starts with "California ", trim it off.
        Otherwise, use the full name.

        Args:
            name: The template name

        Returns:
            The calculated label value
        """
        if name.startswith("California "):
            return name[len("California "):]
        return name

    def update_template_labels(self, templates: List[Dict]) -> int:
        """
        Update the label field for all templates.

        Args:
            templates: List of templates to update

        Returns:
            Number of templates successfully updated
        """
        collection = self.db['caseupdatetemplates']
        updated_count = 0

        for template in templates:
            template_id = template['_id']
            name = template['name']
            label = self.calculate_label(name)

            try:
                if self.dry_run:
                    logger.info(f"[DRY RUN] Would update template '{name}' (ID: {template_id})")
                    logger.info(f"  → Setting label = '{label}'")
                    updated_count += 1
                else:
                    result = collection.update_one(
                        {"_id": template_id},
                        {"$set": {"label": label}}
                    )

                    if result.modified_count > 0:
                        logger.info(f"✅ Updated template '{name}' (ID: {template_id})")
                        logger.info(f"   → label = '{label}'")
                        updated_count += 1
                    else:
                        logger.warning(f"⚠️  Template '{name}' was not modified")

            except Exception as e:
                logger.error(f"❌ Failed to update template '{name}' (ID: {template_id}): {e}")

        return updated_count

    def run(self) -> bool:
        """
        Run the migration.

        Returns:
            True if migration completed successfully
        """
        try:
            # Connect to database
            if not self.connect():
                return False

            # Show dry run status
            if self.dry_run:
                logger.info("🔍 Running in DRY RUN mode - no changes will be made")

            # Get templates to update
            logger.info("\n🔍 Finding templates to update...")
            templates = self.get_templates_to_update()

            if not templates:
                logger.info("✅ No templates need updating - migration complete!")
                return True

            # Show templates to be updated
            logger.info("\n📋 Templates to update:")
            for template in templates:
                name = template['name']
                label = self.calculate_label(name)
                logger.info(f"  - '{name}' → label: '{label}'")

            # Confirm if not dry run
            if not self.dry_run:
                logger.info(f"\n⚠️  About to update {len(templates)} templates")
                response = input("Continue? (yes/no): ").strip().lower()
                if response not in ['yes', 'y']:
                    logger.info("Migration cancelled by user")
                    return False

            # Update templates
            logger.info("\n🚀 Starting migration...")
            updated_count = self.update_template_labels(templates)

            # Summary
            logger.info("\n" + "="*60)
            logger.info("Migration Summary:")
            logger.info(f"  Templates found: {len(templates)}")
            logger.info(f"  Templates updated: {updated_count}")

            if self.dry_run:
                logger.info("\n🔍 This was a DRY RUN - no changes were made")
                logger.info("Run without --dry-run to apply changes")
            else:
                logger.info("\n✅ Migration completed successfully!")

            logger.info("="*60)

            return True

        except Exception as e:
            logger.error(f"❌ Migration failed: {e}")
            return False

        finally:
            self.disconnect()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Migrate case update template labels'
    )
    parser.add_argument(
        '--mongo-uri',
        type=str,
        default=os.environ.get('MONGO_URI', DEFAULT_MONGO_URI),
        help='MongoDB connection URI (default: local development)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simulate the migration without making changes'
    )

    args = parser.parse_args()

    # Run migration
    migration = CaseUpdateTemplateLabelMigration(
        mongo_uri=args.mongo_uri,
        dry_run=args.dry_run
    )

    success = migration.run()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
