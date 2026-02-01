#!/usr/bin/env python3
"""
Migration script to attach caseUpdateTemplateIds to service milestone steps.

This script updates servicescatalog documents in the catalog database:
- Adds caseUpdateTemplateIds array to each step in serviceMilestonesList
- Only affects Texas express services (isExpress: true, stateInfo.TX exists)
- Can run on a specific serviceTypeId or all matching services

Usage:
    # Dry run on all Texas express services
    python migrate_step_case_update_templates.py --dry-run

    # Dry run on specific service type
    python migrate_step_case_update_templates.py --service-type-id 67cf23e871ac40000885fc64 --dry-run

    # Run on all Texas express services
    python migrate_step_case_update_templates.py --mongo-uri "mongodb+srv://..."

    # Run on specific service type
    python migrate_step_case_update_templates.py --service-type-id 67cf23e871ac40000885fc64 --mongo-uri "mongodb+srv://..."

Environment Variables:
    MONGO_URI: MongoDB connection string (default: local development)
"""

import argparse
import logging
import os
import sys
from typing import Dict, List, Optional

from bson import ObjectId
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

# Step to caseUpdateTemplateId mappings
# Format: { (service_type_pattern, step_name): [template_ids] }
# Service type patterns: "petition", "answer", "bundle"

STEP_TEMPLATE_MAPPINGS = {
    # Divorce Petition services (Marble Divorce Petition, Marble Divorce Petition with Motion)
    ("petition", "Drafting petition"): ["692d85ba390d0582cdc70726"],
    ("petition", "Drafting documents"): ["692d85ba390d0582cdc70726"],
    ("petition", "Pending signature"): ["692d85ba390d0582cdc70727"],
    ("petition", "Filing petition"): ["692d85ba390d0582cdc70728"],
    ("petition", "Filing documents"): ["692d85ba390d0582cdc70728"],
    ("petition", "Serving opposing party"): ["692d85ba390d0582cdc70729"],
    ("petition", "Service complete"): ["692d85ba390d0582cdc7072a", "692d85ba390d0582cdc7072b"],
    ("petition", "Service completed"): ["692d85ba390d0582cdc7072a", "692d85ba390d0582cdc7072b"],

    # Answer to Divorce services
    ("answer", "Drafting documents"): ["692d85ba390d0582cdc70734"],
    ("answer", "Pending signature"): ["692d85ba390d0582cdc70735"],
    ("answer", "Filing documents"): ["692d85ba390d0582cdc70736"],
    ("answer", "Service complete"): ["692d85ba390d0582cdc70737", "692d85ba390d0582cdc70738"],
    ("answer", "Service completed"): ["692d85ba390d0582cdc70737", "692d85ba390d0582cdc70738"],

    # Uncontested Divorce Bundle services - Petition milestone
    ("bundle", "Drafting"): ["692d85ba390d0582cdc7072c"],
    ("bundle", "Filing"): ["692d85ba390d0582cdc7072e"],
    ("bundle", "Pending client signature"): ["692d85ba390d0582cdc7072d"],
    ("bundle", "Pending signature"): ["692d85ba390d0582cdc7072d"],

    # Uncontested Divorce Bundle services - Service/Waiver milestone
    ("bundle", "Serving spouse/filing waiver"): ["692d85ba390d0582cdc7072f"],
    ("bundle", "Serving spouse/filling waiver"): ["692d85ba390d0582cdc7072f"],

    # Uncontested Divorce Bundle services - Final Decree milestone
    ("bundle", "60-day hold"): ["692d85ba390d0582cdc70732"],
    ("bundle", "Drafting decree"): ["692d85ba390d0582cdc70730"],
    ("bundle", "Filing/finalization"): ["692d85ba390d0582cdc70733"],
    ("bundle", "Pending parties' signatures"): ["692d85ba390d0582cdc70731"],
}


def get_service_type_pattern(service_type_name: str) -> str:
    """
    Determine the service type pattern based on the service type name.

    Args:
        service_type_name: The name of the service type

    Returns:
        Pattern string: "bundle", "answer", or "petition"
    """
    name_lower = service_type_name.lower()

    if "bundle" in name_lower:
        return "bundle"
    elif "answer" in name_lower:
        return "answer"
    else:
        return "petition"


def get_template_ids_for_step(service_type_name: str, step_name: str) -> Optional[List[str]]:
    """
    Get the caseUpdateTemplateIds for a specific step.

    Args:
        service_type_name: The name of the service type
        step_name: The name of the step

    Returns:
        List of template IDs or None if no mapping found
    """
    pattern = get_service_type_pattern(service_type_name)
    return STEP_TEMPLATE_MAPPINGS.get((pattern, step_name))


class StepCaseUpdateTemplateMigration:
    """Migration to attach caseUpdateTemplateIds to service milestone steps."""

    def __init__(
        self,
        mongo_uri: str,
        dry_run: bool = False,
        service_type_id: Optional[str] = None
    ):
        """
        Initialize the migration.

        Args:
            mongo_uri: MongoDB connection string
            dry_run: If True, simulate the migration without making changes
            service_type_id: Optional specific service type ID to update
        """
        self.mongo_uri = mongo_uri
        self.dry_run = dry_run
        self.service_type_id = service_type_id
        self.client: MongoClient
        self.db: Database

    def connect(self) -> bool:
        """Connect to MongoDB."""
        try:
            logger.info("Connecting to MongoDB...")
            self.client = MongoClient(self.mongo_uri)

            # Parse database name from URI
            if "/" in self.mongo_uri.split("@")[-1]:
                db_name = self.mongo_uri.split("@")[-1].split("/")[1].split("?")[0]
            else:
                db_name = "catalog"

            self.db = self.client[db_name]

            # Test connection
            self.db.command('ping')
            logger.info(f"Connected to MongoDB database: {db_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            return False

    def disconnect(self):
        """Disconnect from MongoDB."""
        if self.client:
            self.client.close()
            logger.info("Disconnected from MongoDB")

    def get_services_to_update(self) -> List[Dict]:
        """
        Get all services that need to be updated.

        Always applies Texas + isExpress filters as safeguards.

        Returns:
            List of services that need to be updated
        """
        collection = self.db['servicescatalog']

        # Base query: Texas express services only (safeguard)
        query = {
            "isExpress": True,
            "stateInfo.TX": {"$exists": True}
        }

        # Add specific service type filter if provided
        if self.service_type_id:
            try:
                query["serviceTypeId"] = ObjectId(self.service_type_id)
            except Exception:
                query["serviceTypeId"] = self.service_type_id

        services = list(collection.find(query))
        logger.info(f"Found {len(services)} services matching criteria")

        if self.service_type_id:
            logger.info(f"  (filtered by serviceTypeId: {self.service_type_id})")

        return services

    def calculate_updates(self, service: Dict) -> Optional[Dict]:
        """
        Calculate the updates needed for a service.

        Args:
            service: The service document

        Returns:
            Updated serviceMilestonesList or None if no updates needed
        """
        service_type_name = service.get('serviceTypeName', '')
        milestone_list = service.get('serviceMilestonesList', [])

        if not milestone_list:
            return None

        updated = False
        updated_milestone_list = []

        for milestone in milestone_list:
            updated_milestone = milestone.copy()
            updated_steps = []

            for step in milestone.get('steps', []):
                updated_step = step.copy()
                step_name = step.get('name', '')

                template_ids = get_template_ids_for_step(service_type_name, step_name)

                if template_ids:
                    # Convert to ObjectIds
                    template_object_ids = [ObjectId(tid) for tid in template_ids]

                    # Check if update is needed
                    existing_ids = step.get('caseUpdateTemplateIds', [])
                    existing_ids_str = [str(oid) for oid in existing_ids]

                    if set(existing_ids_str) != set(template_ids):
                        updated_step['caseUpdateTemplateIds'] = template_object_ids
                        updated = True

                updated_steps.append(updated_step)

            updated_milestone['steps'] = updated_steps
            updated_milestone_list.append(updated_milestone)

        return updated_milestone_list if updated else None

    def update_service(self, service: Dict, updated_milestone_list: List[Dict]) -> bool:
        """
        Update a single service document.

        Args:
            service: The original service document
            updated_milestone_list: The updated milestones list

        Returns:
            True if update was successful
        """
        collection = self.db['servicescatalog']
        service_id = service['_id']
        service_name = service.get('serviceTypeName', 'Unknown')
        service_code = service.get('serviceCode', '')

        try:
            if self.dry_run:
                logger.info(f"[DRY RUN] Would update service '{service_name}' ({service_code})")
                return True
            else:
                result = collection.update_one(
                    {"_id": service_id},
                    {"$set": {"serviceMilestonesList": updated_milestone_list}}
                )

                if result.modified_count > 0:
                    logger.info(f"Updated service '{service_name}' ({service_code})")
                    return True
                else:
                    logger.warning(f"Service '{service_name}' was not modified")
                    return False

        except Exception as e:
            logger.error(f"Failed to update service '{service_name}': {e}")
            return False

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

            # Show mode info
            if self.dry_run:
                logger.info("Running in DRY RUN mode - no changes will be made")

            logger.info("SAFEGUARD: Only updating Texas express services (isExpress=true, stateInfo.TX exists)")

            # Get services to update
            logger.info("\nFinding services to update...")
            services = self.get_services_to_update()

            if not services:
                logger.info("No services found matching criteria")
                return True

            # Calculate updates and track statistics
            updates_needed = []
            total_steps_to_update = 0

            for service in services:
                updated_milestone_list = self.calculate_updates(service)
                if updated_milestone_list:
                    # Count steps being updated
                    for milestone in updated_milestone_list:
                        for step in milestone.get('steps', []):
                            if 'caseUpdateTemplateIds' in step:
                                total_steps_to_update += 1

                    updates_needed.append((service, updated_milestone_list))

            if not updates_needed:
                logger.info("All services already have correct caseUpdateTemplateIds - no updates needed!")
                return True

            # Show summary
            logger.info(f"\nServices to update: {len(updates_needed)}")
            logger.info(f"Total steps to update: {total_steps_to_update}")

            # Show details
            logger.info("\nServices to be updated:")
            for service, _ in updates_needed:
                service_name = service.get('serviceTypeName', 'Unknown')
                service_code = service.get('serviceCode', '')
                logger.info(f"  - {service_name} ({service_code})")

            # Confirm if not dry run
            if not self.dry_run:
                logger.info(f"\nAbout to update {len(updates_needed)} services")
                response = input("Continue? (yes/no): ").strip().lower()
                if response not in ['yes', 'y']:
                    logger.info("Migration cancelled by user")
                    return False

            # Perform updates
            logger.info("\nStarting migration...")
            success_count = 0
            fail_count = 0

            for service, updated_milestone_list in updates_needed:
                if self.update_service(service, updated_milestone_list):
                    success_count += 1
                else:
                    fail_count += 1

            # Summary
            logger.info("\n" + "="*60)
            logger.info("Migration Summary:")
            logger.info(f"  Services found: {len(services)}")
            logger.info(f"  Services needing updates: {len(updates_needed)}")
            logger.info(f"  Successfully updated: {success_count}")
            logger.info(f"  Failed: {fail_count}")

            if self.dry_run:
                logger.info("\nThis was a DRY RUN - no changes were made")
                logger.info("Run without --dry-run to apply changes")
            else:
                logger.info("\nMigration completed!")

            logger.info("="*60)

            return fail_count == 0

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            return False

        finally:
            self.disconnect()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Migrate caseUpdateTemplateIds to service milestone steps'
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
    parser.add_argument(
        '--service-type-id',
        type=str,
        default=None,
        help='Specific serviceTypeId to update (optional, updates all matching if not provided)'
    )

    args = parser.parse_args()

    # Show configuration
    logger.info("="*60)
    logger.info("Step Case Update Template Migration")
    logger.info("="*60)
    logger.info(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    logger.info(f"Service Type ID: {args.service_type_id or 'ALL'}")
    logger.info("="*60 + "\n")

    # Run migration
    migration = StepCaseUpdateTemplateMigration(
        mongo_uri=args.mongo_uri,
        dry_run=args.dry_run,
        service_type_id=args.service_type_id
    )

    success = migration.run()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
