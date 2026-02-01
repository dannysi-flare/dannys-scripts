#!/usr/bin/env python3
"""
Extract active services with their milestones and current step information.

Output fields per service:
- Service ID (flare service id)
- Service Type ID
- For each milestone:
  - Milestone ID
  - Milestone Name
  - Current Active Step Name

Usage:
    python scripts/extract_services_milestones.py [--output csv|json] [--file output_path]

Requested by: Dana Lazovsky
Jira: DC-2531
Linear: FLA-44
"""

import argparse
import csv
import json
import logging
import os
import sys
from datetime import datetime
from typing import Any

from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# MongoDB connection strings by environment
DB_CONFIGS = {
    "staging": {
        "services": "mongodb+srv://node:marblerules1@marble-staging2.jycnt.mongodb.net/services",
        "catalog": "mongodb+srv://node:marblerules1@marble-staging2.jycnt.mongodb.net/catalog"
    },
    "production": {
        "services": "mongodb+srv://node:7YWXdRmQ8iaDrtWR@marble-prod.wd92l.mongodb.net/services",
        "catalog": "mongodb+srv://node:7YWXdRmQ8iaDrtWR@marble-prod.wd92l.mongodb.net/catalog"
    }
}


def get_db_connections(env: str = "staging") -> tuple[Any, Any]:
    """Establish connections to services and catalog databases."""
    config = DB_CONFIGS[env]

    services_client = MongoClient(config["services"])
    catalog_client = MongoClient(config["catalog"])

    services_db = services_client.get_database()
    catalog_db = catalog_client.get_database()

    return services_db, catalog_db


def load_milestone_definitions(catalog_db: Any) -> dict[str, dict]:
    """Load all milestone definitions from catalog database."""
    milestones = {}
    for milestone in catalog_db.servicemilestones.find():
        milestone_id = str(milestone["_id"])
        milestones[milestone_id] = {
            "name": milestone.get("name", "Unknown"),
            "defaultSteps": milestone.get("defaultSteps", [])
        }
    logger.info(f"Loaded {len(milestones)} milestone definitions")
    return milestones


def load_service_types(catalog_db: Any) -> dict[str, dict]:
    """Load service types with their milestone configurations from servicesCatalog."""
    service_types = {}
    for st in catalog_db.servicescatalog.find():
        # Use serviceTypeId as the key since that's what services reference
        service_type_id = str(st.get("serviceTypeId", st["_id"]))
        version_id = st.get("versionId", 1)

        # Store by serviceTypeId-versionId to handle versioning
        key = f"{service_type_id}:{version_id}"
        service_types[key] = {
            "name": st.get("serviceTypeName", "Unknown"),
            "milestonesList": st.get("serviceMilestonesList", [])
        }

        # Also store by just serviceTypeId for fallback
        if service_type_id not in service_types:
            service_types[service_type_id] = service_types[key]

    logger.info(f"Loaded {len(service_types)} service type configurations")
    return service_types


def get_current_step_name(
    milestone_progress: dict,
    milestone_def: dict,
    service_type_milestone: dict | None
) -> str:
    """
    Determine the current active step based on milestone progress.

    Uses the milestone completion percentage to find which step is current.
    """
    percent_completed = milestone_progress.get("milestonePercentCompleted") or 0

    # Get steps - prefer service type specific steps, fallback to default
    steps = []
    if service_type_milestone and service_type_milestone.get("steps"):
        steps = service_type_milestone["steps"]
    elif milestone_def and milestone_def.get("defaultSteps"):
        steps = milestone_def["defaultSteps"]

    if not steps:
        if percent_completed >= 100:
            return "COMPLETED"
        elif percent_completed > 0:
            return "IN_PROGRESS"
        return "NOT_STARTED"

    # Find the current step based on completion percentage
    # Steps are ordered by completionPercent, find the one we're currently at or just passed
    current_step = None
    for step in sorted(steps, key=lambda s: s.get("completionPercent") or 0):
        step_percent = step.get("completionPercent") or 0
        if percent_completed >= step_percent:
            current_step = step
        else:
            break

    if current_step:
        return current_step.get("name", "UNKNOWN")

    # If we haven't reached any step yet, return the first one or NOT_STARTED
    if steps:
        return steps[0].get("name", "NOT_STARTED")
    return "NOT_STARTED"


def extract_services_data(
    marble_db: Any,
    milestone_definitions: dict[str, dict],
    service_types: dict[str, dict],
    statuses: list[str] | None = None,
    limit: int | None = None
) -> list[dict]:
    """Extract all active services with their milestone information."""
    results = []

    # Query services (not soft-deleted, optionally filtered by status)
    query: dict[str, Any] = {"removedAt": None}

    if statuses and "all" not in statuses:
        # Handle case-insensitive status matching
        query["status"] = {"$in": statuses}

    services_cursor = marble_db.services.find(query)
    if limit:
        services_cursor = services_cursor.limit(limit)
    total_services = marble_db.services.count_documents(query)
    logger.info(f"Found {total_services} active services")

    for service in services_cursor:
        service_id = str(service["_id"])
        service_name = service.get("name", "")
        service_type_id = str(service.get("serviceTypeId", ""))
        service_type_version = service.get("versionId") or service.get("serviceTypeVersionId", 1)

        # Get service type configuration
        service_type_key = f"{service_type_id}:{service_type_version}"
        service_type = service_types.get(service_type_key) or service_types.get(service_type_id)

        # Get service type name from catalog or from service document
        service_type_name = ""
        if service_type:
            service_type_name = service_type.get("name", "")
        if not service_type_name:
            service_type_name = service.get("serviceTypeName", "")

        service_type_milestones = {}

        if service_type:
            # Build a lookup of milestone configs by milestone ID
            for ms_item in service_type.get("milestonesList", []):
                ms_id = str(ms_item.get("serviceMilestoneId", ""))
                if ms_id:
                    service_type_milestones[ms_id] = ms_item

        # Extract milestone progress
        progress = service.get("progress", {})
        milestones_progress = progress.get("milestones", {})

        if not milestones_progress:
            # Service has no milestone progress yet
            results.append({
                "serviceId": service_id,
                "serviceName": service_name,
                "serviceTypeId": service_type_id,
                "serviceTypeName": service_type_name,
                "milestoneId": "",
                "milestoneName": "NO_MILESTONES",
                "currentActiveStepName": "NOT_STARTED"
            })
            continue

        # Process each milestone
        for milestone_key, milestone_progress in milestones_progress.items():
            milestone_id = str(milestone_progress.get("serviceMilestoneId", milestone_key))
            milestone_def = milestone_definitions.get(milestone_id, {})
            milestone_name = milestone_def.get("name", "Unknown")

            # Get service-type specific milestone config
            st_milestone = service_type_milestones.get(milestone_id)

            # Determine current step
            current_step = get_current_step_name(
                milestone_progress,
                milestone_def,
                st_milestone
            )

            results.append({
                "serviceId": service_id,
                "serviceName": service_name,
                "serviceTypeId": service_type_id,
                "serviceTypeName": service_type_name,
                "milestoneId": milestone_id,
                "milestoneName": milestone_name,
                "currentActiveStepName": current_step
            })

    logger.info(f"Extracted {len(results)} milestone records from {total_services} services")
    return results


def output_csv(data: list[dict], file_path: str | None = None) -> None:
    """Output data as CSV."""
    if not data:
        logger.warning("No data to output")
        return

    fieldnames = ["serviceId", "serviceName", "serviceTypeId", "serviceTypeName", "milestoneId", "milestoneName", "currentActiveStepName"]

    if file_path:
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        logger.info(f"CSV written to {file_path}")
    else:
        writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)


def output_json(data: list[dict], file_path: str | None = None) -> None:
    """Output data as JSON."""
    if file_path:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        logger.info(f"JSON written to {file_path}")
    else:
        print(json.dumps(data, indent=2, default=str))


def main():
    parser = argparse.ArgumentParser(
        description="Extract active services with milestone information"
    )
    parser.add_argument(
        "--output", "-o",
        choices=["csv", "json"],
        default="csv",
        help="Output format (default: csv)"
    )
    parser.add_argument(
        "--file", "-f",
        help="Output file path (default: stdout)"
    )
    parser.add_argument(
        "--status", "-s",
        nargs="+",
        default=["open"],
        help="Service statuses to include (default: open). Use 'all' for all statuses."
    )
    parser.add_argument(
        "--env",
        choices=["staging", "production"],
        default="staging",
        help="Environment to query (default: staging)"
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=None,
        help="Limit number of services to process (default: no limit)"
    )
    args = parser.parse_args()

    load_dotenv()

    logger.info(f"Connecting to {args.env} databases...")
    marble_db, catalog_db = get_db_connections(args.env)

    logger.info("Loading milestone definitions...")
    milestone_definitions = load_milestone_definitions(catalog_db)

    logger.info("Loading service type configurations...")
    service_types = load_service_types(catalog_db)

    status_display = "all" if "all" in args.status else ", ".join(args.status)
    limit_display = f", limit: {args.limit}" if args.limit else ""
    logger.info(f"Extracting services data (statuses: {status_display}{limit_display})...")
    data = extract_services_data(marble_db, milestone_definitions, service_types, args.status, args.limit)

    # Determine output file path
    output_file = args.file
    if not output_file and args.output:
        # Generate default filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"outputs/services_milestones_{timestamp}.{args.output}"
        os.makedirs("outputs", exist_ok=True)

    if args.output == "csv":
        output_csv(data, output_file)
    else:
        output_json(data, output_file)

    logger.info("Done!")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Script failed: {e}")
        raise
