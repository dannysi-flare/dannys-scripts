#!/usr/bin/env python3
"""
Migrate attorney data points to express open cases.

Optimized approach:
1. Fetches all express service type IDs from catalog (1 call)
2. For each express service type, fetches all services metadata (25 calls)
   - This gives us userId, caseId, legalTeam per service
3. Filters to open services only, deduplicates by userId
4. Fetches attorney data for each unique attorney (N calls)
5. Writes attorney data points per user via data-collection API

Usage:
    python scripts/migrate_attorney_datapoints.py [--dry-run] [--limit N]

Environment variables (.env):
    BASE_URL           - API gateway base URL (e.g. https://api.platform.flaretechnologies.com)
    X_API_KEY          - API gateway key
    DOCOLOCO_SCHEMA_ID - The docoloco data schema ID
"""

import argparse
import logging
import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
X_API_KEY = os.getenv("X_API_KEY", "")
DOCOLOCO_SCHEMA_ID = os.getenv("DOCOLOCO_SCHEMA_ID", "")

RESPONSIBLE_ATTORNEY_ROLE = "RESPONSIBLE_ATTORNEY"

session = requests.Session()


def get_headers() -> dict:
    return {
        "x-api-key": X_API_KEY,
        "Content-Type": "application/json",
    }


def get_express_service_type_ids() -> list[str]:
    """Fetch all express service type IDs from catalog."""
    url = f"{BASE_URL}/catalog/services/list"
    params = {"filter[isExpress]": "true"}
    resp = session.get(url, headers=get_headers(), params=params)
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results", [])
    ids = [st["serviceTypeId"] for st in results]
    logger.info("Found %d express service types", len(ids))
    return ids


def get_open_services_for_type(service_type_id: str) -> list[dict]:
    """Fetch all open services metadata for a given service type ID."""
    url = f"{BASE_URL}/services/list/metadata"
    resp = session.post(url, headers=get_headers(), json={"serviceTypeId": service_type_id})
    resp.raise_for_status()
    data = resp.json()
    return [s for s in data if s.get("status") == "open"]


def get_attorney(attorney_id: str) -> dict:
    """Fetch attorney user data."""
    url = f"{BASE_URL}/attorneys/{attorney_id}"
    resp = session.get(url, headers=get_headers())
    resp.raise_for_status()
    return resp.json()


def build_attorney_data_points(attorney: dict) -> dict[str, str]:
    """Extract attorney data points matching the vinny data-hydration logic."""
    attorney_data = attorney.get("attorneyData", {}) or {}
    name = attorney.get("name", {}) or {}
    bar_details = attorney_data.get("barDetails", {}) or {}
    law_firm = attorney_data.get("lawFirm", {}) or {}
    address = law_firm.get("address", {}) or {}

    first = name.get("first", "")
    middle = name.get("middle", "")
    last = name.get("last", "")
    attorney_name = " ".join(filter(None, [first, middle, last]))

    data_points = {}
    if attorney_name:
        data_points["attorneyName"] = attorney_name
    if first:
        data_points["attorneyFirstName"] = first
    if middle:
        data_points["attorneyMiddleName"] = middle
    if last:
        data_points["attorneyLastName"] = last
    if bar_details.get("barNumber"):
        data_points["attorneyBarNumber"] = bar_details["barNumber"]
    if bar_details.get("licensingJurisdiction"):
        data_points["attorneyState"] = bar_details["licensingJurisdiction"]
    if law_firm.get("phoneNumber"):
        data_points["attorneyPhone"] = law_firm["phoneNumber"]
    if attorney.get("email"):
        data_points["attorneyEmail"] = attorney["email"]
    if address.get("street"):
        data_points["attorneyStreetAddress"] = address["street"]
    if address.get("unit"):
        data_points["attorneyStreetAddressUnit"] = address["unit"]
    if address.get("city"):
        data_points["attorneyCity"] = address["city"]
    if address.get("postalCode"):
        data_points["attorneyZip"] = address["postalCode"]

    return data_points


def add_user_data_points(user_id: str, data_points: dict[str, str]) -> None:
    """Write attorney data points to a user via data-collection API."""
    url = f"{BASE_URL}/data-collection-ms/data-points/{user_id}"
    payload = {
        "dataSchemaId": DOCOLOCO_SCHEMA_ID,
        "data": [
            {
                "dataPoints": data_points,
                "context": {
                    "type": "USER",
                    "id": user_id,
                },
                "source": {
                    "type": "ATTORNEY_PROFILE",
                },
            }
        ],
    }
    resp = session.patch(url, headers=get_headers(), json=payload)
    resp.raise_for_status()


def main():
    parser = argparse.ArgumentParser(
        description="Migrate attorney data points for express open cases"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing data points",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of users to process (0 = all)",
    )
    args = parser.parse_args()

    if not BASE_URL:
        logger.error("BASE_URL not set in environment")
        sys.exit(1)
    if not X_API_KEY:
        logger.error("X_API_KEY not set in environment")
        sys.exit(1)
    if not DOCOLOCO_SCHEMA_ID:
        logger.error("DOCOLOCO_SCHEMA_ID not set in environment")
        sys.exit(1)

    logger.info("Base URL: %s", BASE_URL)
    logger.info("Schema ID: %s", DOCOLOCO_SCHEMA_ID)
    if args.dry_run:
        logger.info("DRY RUN MODE - no data will be written")

    # Step 1: Get express service type IDs
    express_type_ids = get_express_service_type_ids()

    # Step 2: For each express service type, get open services
    # Collect unique user -> (caseId, attorneyId) mappings
    user_to_info: dict[str, dict] = {}
    total_services = 0

    for i, st_id in enumerate(express_type_ids):
        logger.info("Fetching services for express type %d/%d: %s", i + 1, len(express_type_ids), st_id)
        try:
            open_services = get_open_services_for_type(st_id)
        except requests.HTTPError as e:
            logger.error("  Failed to fetch services for type %s: %s", st_id, e)
            continue

        for service in open_services:
            user_id = service.get("userId")
            case_id = service.get("caseId")
            if not user_id:
                continue

            # Find responsible attorney from legalTeam
            attorney_id = None
            for member in service.get("legalTeam", []):
                if member.get("role") == RESPONSIBLE_ATTORNEY_ROLE:
                    attorney_id = member.get("userId")
                    break

            if not attorney_id:
                continue

            # Keep first occurrence per user (dedup)
            if user_id not in user_to_info:
                user_to_info[user_id] = {
                    "caseId": case_id,
                    "attorneyId": attorney_id,
                    "serviceTypeId": st_id,
                }

        total_services += len(open_services)
        logger.info("  Found %d open services", len(open_services))
        time.sleep(0.05)

    logger.info("Total open express services: %d", total_services)
    logger.info("Unique users to process: %d", len(user_to_info))

    # Apply limit
    users_to_process = list(user_to_info.items())
    if args.limit:
        users_to_process = users_to_process[: args.limit]
        logger.info("Limited to %d users", len(users_to_process))

    # Step 3: Cache attorneys to avoid redundant fetches
    attorney_cache: dict[str, dict | None] = {}
    stats = {"success": 0, "skipped": 0, "error": 0, "dry_run": 0}

    for i, (user_id, info) in enumerate(users_to_process):
        attorney_id = info["attorneyId"]
        case_id = info["caseId"]

        if (i + 1) % 50 == 0 or i == 0:
            logger.info(
                "Processing user %d/%d: %s (case: %s, attorney: %s)",
                i + 1, len(users_to_process), user_id, case_id, attorney_id,
            )

        # Fetch attorney (cached)
        if attorney_id not in attorney_cache:
            try:
                attorney_cache[attorney_id] = get_attorney(attorney_id)
            except requests.HTTPError as e:
                logger.error("  Failed to fetch attorney %s: %s", attorney_id, e)
                attorney_cache[attorney_id] = None
                stats["error"] += 1
                continue

        attorney = attorney_cache[attorney_id]
        if attorney is None:
            stats["error"] += 1
            continue

        # Build data points
        data_points = build_attorney_data_points(attorney)
        if not data_points:
            stats["skipped"] += 1
            continue

        # Check for missing attorney data
        attorney_data = attorney.get("attorneyData", {}) or {}
        missing = []
        if not (attorney_data.get("barDetails") or {}).get("barNumber"):
            missing.append("barNumber")
        if not (attorney_data.get("lawFirm") or {}).get("phoneNumber"):
            missing.append("lawFirm.phoneNumber")
        if not ((attorney_data.get("lawFirm") or {}).get("address") or {}).get("street"):
            missing.append("lawFirm.address")
        if missing and attorney_id not in getattr(main, '_warned_attorneys', set()):
            if not hasattr(main, '_warned_attorneys'):
                main._warned_attorneys = set()
            main._warned_attorneys.add(attorney_id)
            logger.warning(
                "Attorney %s missing data: %s",
                attorney_id,
                ", ".join(missing),
            )

        if args.dry_run:
            stats["dry_run"] += 1
            if (i + 1) % 50 == 0 or i == 0:
                logger.info(
                    "  DRY_RUN: would write %d data points for user %s (%s)",
                    len(data_points), user_id, list(data_points.keys()),
                )
            continue

        # Write data points
        try:
            add_user_data_points(user_id, data_points)
            stats["success"] += 1
        except requests.HTTPError as e:
            logger.error("  Failed to write data points for user %s: %s", user_id, e)
            stats["error"] += 1

        time.sleep(0.05)

    # Summary
    logger.info("=" * 50)
    logger.info("Migration complete!")
    logger.info("  Unique attorneys fetched: %d", len(attorney_cache))
    logger.info("  Success: %d", stats["success"])
    logger.info("  Skipped: %d", stats["skipped"])
    logger.info("  Errors:  %d", stats["error"])
    if args.dry_run:
        logger.info("  Dry run: %d", stats["dry_run"])


if __name__ == "__main__":
    main()
