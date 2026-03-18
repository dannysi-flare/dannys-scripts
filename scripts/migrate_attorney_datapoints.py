#!/usr/bin/env python3
"""
Migrate attorney data points to express open cases.

Optimized approach:
1. Fetches all express service type IDs from catalog (1 call)
2. Fetches all services metadata in parallel (25 calls concurrently)
   - This gives us userId, caseId, legalTeam per service
3. Filters to open services only, deduplicates by userId
4. Pre-fetches all unique attorneys in parallel
5. Writes attorney data points per user in parallel via data-collection API

Usage:
    python scripts/migrate_attorney_datapoints.py [--dry-run] [--limit N] [--concurrency N]

Environment variables (.env):
    BASE_URL           - API gateway base URL (e.g. https://api.platform.flaretechnologies.com)
    X_API_KEY          - API gateway key
    DOCOLOCO_SCHEMA_ID - The docoloco data schema ID
"""

import argparse
import logging
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

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


def fetch_all_open_services(express_type_ids: list[str], concurrency: int) -> dict[str, dict]:
    """Fetch open services for all express types in parallel. Returns user_id -> info mapping."""
    user_to_info: dict[str, dict] = {}
    lock = threading.Lock()
    total_services = 0

    def fetch_one(st_id: str) -> tuple[str, list[dict]]:
        services = get_open_services_for_type(st_id)
        return st_id, services

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(fetch_one, st_id): st_id for st_id in express_type_ids}

        for future in as_completed(futures):
            st_id = futures[future]
            try:
                _, open_services = future.result()
            except Exception as e:
                logger.error("Failed to fetch services for type %s: %s", st_id, e)
                continue

            with lock:
                for service in open_services:
                    user_id = service.get("userId")
                    case_id = service.get("caseId")
                    if not user_id:
                        continue

                    attorney_id = None
                    for member in service.get("legalTeam", []):
                        if member.get("role") == RESPONSIBLE_ATTORNEY_ROLE:
                            attorney_id = member.get("userId")
                            break

                    if not attorney_id:
                        continue

                    if user_id not in user_to_info:
                        user_to_info[user_id] = {
                            "caseId": case_id,
                            "attorneyId": attorney_id,
                            "serviceTypeId": st_id,
                        }

                total_services += len(open_services)

    logger.info("Total open express services: %d", total_services)
    logger.info("Unique users to process: %d", len(user_to_info))
    return user_to_info


def prefetch_attorneys(attorney_ids: set[str], concurrency: int) -> dict[str, dict | None]:
    """Fetch all unique attorneys in parallel. Returns attorney_id -> data mapping."""
    cache: dict[str, dict | None] = {}
    lock = threading.Lock()
    warned: set[str] = set()

    logger.info("Pre-fetching %d unique attorneys (concurrency=%d)...", len(attorney_ids), concurrency)

    def fetch_one(aid: str) -> tuple[str, dict | None]:
        try:
            return aid, get_attorney(aid)
        except requests.HTTPError as e:
            logger.error("Failed to fetch attorney %s: %s", aid, e)
            return aid, None

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(fetch_one, aid): aid for aid in attorney_ids}

        for future in as_completed(futures):
            aid, data = future.result()
            with lock:
                cache[aid] = data

            # Warn about missing data (once per attorney)
            if data:
                attorney_data = data.get("attorneyData", {}) or {}
                missing = []
                if not (attorney_data.get("barDetails") or {}).get("barNumber"):
                    missing.append("barNumber")
                if not (attorney_data.get("lawFirm") or {}).get("phoneNumber"):
                    missing.append("lawFirm.phoneNumber")
                if not ((attorney_data.get("lawFirm") or {}).get("address") or {}).get("street"):
                    missing.append("lawFirm.address")
                if missing and aid not in warned:
                    warned.add(aid)
                    logger.warning("Attorney %s missing data: %s", aid, ", ".join(missing))

    fetched = sum(1 for v in cache.values() if v is not None)
    logger.info("Fetched %d/%d attorneys successfully", fetched, len(attorney_ids))
    return cache


def write_data_points_parallel(
    users_to_process: list[tuple[str, dict]],
    attorney_cache: dict[str, dict | None],
    dry_run: bool,
    concurrency: int,
) -> dict[str, int]:
    """Write data points for all users in parallel. Returns stats."""
    stats = {"success": 0, "skipped": 0, "error": 0, "dry_run": 0}
    lock = threading.Lock()
    processed = 0

    def process_one(user_id: str, info: dict) -> tuple[str, str]:
        attorney_id = info["attorneyId"]
        attorney = attorney_cache.get(attorney_id)
        if attorney is None:
            return "error", user_id

        data_points = build_attorney_data_points(attorney)
        if not data_points:
            return "skipped", user_id

        if dry_run:
            return "dry_run", user_id

        try:
            add_user_data_points(user_id, data_points)
            return "success", user_id
        except requests.HTTPError as e:
            logger.error("Failed to write data points for user %s: %s", user_id, e)
            return "error", user_id

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {
            executor.submit(process_one, user_id, info): user_id
            for user_id, info in users_to_process
        }

        for future in as_completed(futures):
            status, user_id = future.result()
            with lock:
                stats[status] += 1
                processed += 1
                if processed % 100 == 0:
                    logger.info(
                        "  Progress: %d/%d (success=%d, skip=%d, err=%d)",
                        processed, len(users_to_process),
                        stats["success"], stats["skipped"], stats["error"],
                    )

    return stats


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
    parser.add_argument(
        "--concurrency",
        type=int,
        default=10,
        help="Number of concurrent requests (default: 10)",
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
    logger.info("Concurrency: %d", args.concurrency)
    if args.dry_run:
        logger.info("DRY RUN MODE - no data will be written")

    # Step 1: Get express service type IDs
    express_type_ids = get_express_service_type_ids()

    # Step 2: Fetch all open services in parallel
    logger.info("Fetching open services for all express types...")
    user_to_info = fetch_all_open_services(express_type_ids, args.concurrency)

    # Apply limit
    users_to_process = list(user_to_info.items())
    if args.limit:
        users_to_process = users_to_process[: args.limit]
        logger.info("Limited to %d users", len(users_to_process))

    # Step 3: Pre-fetch all unique attorneys in parallel
    unique_attorney_ids = {info["attorneyId"] for _, info in users_to_process}
    attorney_cache = prefetch_attorneys(unique_attorney_ids, args.concurrency)

    # Step 4: Write data points in parallel
    logger.info("Writing data points for %d users...", len(users_to_process))
    stats = write_data_points_parallel(users_to_process, attorney_cache, args.dry_run, args.concurrency)

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
