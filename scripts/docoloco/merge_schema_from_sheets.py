#!/usr/bin/env python3
"""
Merge schema and form from Google Sheets CSV.

This script automates the workflow of updating Vinny schemas and forms using
Google Sheets as the data source. It integrates with:
- Google Sheets API (OAuth2) for CSV export
- draft-driver-100x merge endpoint for schema processing
- Vinny data-collection API for schema/form updates

Workflow:
1. Authenticate with Google Sheets (OAuth2 interactive flow)
2. Download CSV from specified Google Sheets document
3. Call draft-driver-100x to merge CSV with existing schema
4. Display merge results and prompt for confirmation
5. Update schema and form in Vinny staging API
6. Save intermediate CSV file for debugging

Author: Danny Sivan
Date: 2025-01-02
"""

import argparse
import csv
import io
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

import requests
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Google Sheets API scope
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']


class GoogleSheetsClient:
    """Client for interacting with Google Sheets API."""

    def __init__(self, credentials_file: str, token_file: str):
        """
        Initialize Google Sheets client.

        Args:
            credentials_file: Path to OAuth2 client credentials JSON
            token_file: Path to store/retrieve access tokens
        """
        self.credentials_file = os.path.expanduser(credentials_file)
        self.token_file = os.path.expanduser(token_file)
        self.service = None

    def authenticate(self):
        """
        Authenticate with Google Sheets API using OAuth2.

        Returns:
            Google Sheets API service instance

        Raises:
            FileNotFoundError: If credentials file not found
            google.auth.exceptions.RefreshError: If authentication fails
        """
        if not os.path.exists(self.credentials_file):
            logger.error(
                f"Google Sheets credentials file not found: {self.credentials_file}"
            )
            logger.error(
                "Please create OAuth2 credentials at Google Cloud Console "
                "and save to this location."
            )
            sys.exit(1)

        creds = None

        # Load existing token if available
        if os.path.exists(self.token_file):
            try:
                creds = Credentials.from_authorized_user_file(
                    self.token_file, SCOPES
                )
                logger.debug(f"Loaded credentials from {self.token_file}")
            except Exception as e:
                logger.warning(f"Failed to load token file: {e}")

        # Refresh or authenticate
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Refreshing expired access token...")
                try:
                    creds.refresh(Request())
                    logger.info("Token refreshed successfully")
                except Exception as e:
                    logger.warning(f"Token refresh failed: {e}")
                    creds = None

            if not creds:
                logger.info(
                    "Starting interactive OAuth2 authentication flow..."
                )
                logger.info("A browser window will open for authorization")
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, SCOPES
                )
                creds = flow.run_local_server(port=0)
                logger.info("Authentication successful")

            # Save credentials for future use
            os.makedirs(os.path.dirname(self.token_file), exist_ok=True)
            with open(self.token_file, 'w') as token:
                token.write(creds.to_json())
            logger.info(f"Credentials saved to {self.token_file}")

        self.service = build('sheets', 'v4', credentials=creds)
        return self.service

    def extract_spreadsheet_id(self, url: str) -> str:
        """
        Extract spreadsheet ID from various Google Sheets URL formats.

        Args:
            url: Google Sheets URL or direct spreadsheet ID

        Returns:
            Spreadsheet ID

        Raises:
            ValueError: If URL format is invalid
        """
        # Direct ID (no URL)
        if not url.startswith('http'):
            logger.debug(f"Using direct spreadsheet ID: {url}")
            return url

        # Extract from URL
        pattern = r'/spreadsheets/d/([a-zA-Z0-9-_]+)'
        match = re.search(pattern, url)
        if not match:
            logger.error(f"Invalid Google Sheets URL: {url}")
            logger.error(
                "Expected format: "
                "https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/..."
            )
            raise ValueError(f"Invalid Google Sheets URL: {url}")

        spreadsheet_id = match.group(1)
        logger.debug(f"Extracted spreadsheet ID: {spreadsheet_id}")
        return spreadsheet_id

    def export_to_csv(
        self,
        spreadsheet_id: str,
        sheet_name: Optional[str] = None,
        range_spec: Optional[str] = None
    ) -> str:
        """
        Export Google Sheets data as CSV string.

        Args:
            spreadsheet_id: Google Sheets spreadsheet ID
            sheet_name: Specific sheet name to export (default: first sheet)
            range_spec: A1 notation range to export (e.g., "A1:P100")

        Returns:
            CSV content as string

        Raises:
            HttpError: If spreadsheet not found or access denied
            ValueError: If sheet/range invalid
        """
        if not self.service:
            self.authenticate()

        try:
            # Determine range to export
            if range_spec:
                export_range = range_spec
            elif sheet_name:
                export_range = sheet_name
            else:
                # Get first sheet name
                logger.debug("Fetching spreadsheet metadata...")
                spreadsheet = self.service.spreadsheets().get(
                    spreadsheetId=spreadsheet_id
                ).execute()
                first_sheet = spreadsheet['sheets'][0]['properties']['title']
                export_range = first_sheet
                logger.info(f"Using first sheet: {first_sheet}")

            # Fetch values
            logger.info(f"Fetching data from range: {export_range}")
            result = self.service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=export_range
            ).execute()
            values = result.get('values', [])

            if not values:
                logger.warning("No data found in the specified range")
                return ""

            logger.info(f"Fetched {len(values)} rows")

            # Convert to CSV
            output = io.StringIO()
            writer = csv.writer(output)
            for row in values:
                writer.writerow(row)

            return output.getvalue()

        except HttpError as e:
            error_code = e.resp.status
            if error_code == 404:
                logger.error(
                    f"Spreadsheet not found: {spreadsheet_id}. "
                    "Check the URL and try again."
                )
            elif error_code == 403:
                logger.error(
                    f"Access denied to spreadsheet: {spreadsheet_id}. "
                    "Check sharing settings and ensure the sheet is accessible."
                )
            else:
                logger.error(f"Failed to fetch spreadsheet data: {e}")
            raise


class DraftDriverClient:
    """Client for interacting with draft-driver-100x API."""

    def __init__(self, api_url: str, api_key: Optional[str] = None):
        """
        Initialize draft-driver client.

        Args:
            api_url: Base URL for draft-driver API
            api_key: Optional API key for authentication
        """
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key

    def csv_schema_merge(
        self,
        csv_content: str,
        schema_id: str,
        exclude_info: bool = False,
        timeout: int = 60
    ) -> Dict[str, Any]:
        """
        Call CSV schema merge endpoint.

        Args:
            csv_content: CSV file content as string
            schema_id: Schema ID to merge with
            exclude_info: Filter change comments to only errors/warnings
            timeout: Request timeout in seconds

        Returns:
            Merge response dictionary containing data_schema, form_schema,
            change_comments, stats, and validation

        Raises:
            requests.HTTPError: If API request fails
        """
        url = f"{self.api_url}/api/v1/pipeline/csv-schema-merge"

        # Create multipart form data
        files = {
            'csv_file': ('fields.csv', csv_content, 'text/csv')
        }
        data = {
            'schema_id': schema_id,
            'exclude_info_comments': str(exclude_info).lower()
        }

        headers = {}
        if self.api_key:
            headers['Authorization'] = f"Bearer {self.api_key}"

        logger.info("Calling draft-driver merge endpoint...")
        logger.debug(f"URL: {url}")
        logger.debug(f"Schema ID: {schema_id}")

        try:
            response = requests.post(
                url,
                files=files,
                data=data,
                headers=headers,
                timeout=timeout
            )
            response.raise_for_status()
            logger.info("Merge completed successfully")
            return response.json()

        except requests.Timeout:
            logger.error(
                f"Merge request timed out after {timeout} seconds. "
                "Try increasing --merge-timeout."
            )
            raise
        except requests.ConnectionError as e:
            logger.error(
                f"Failed to connect to draft-driver API at {self.api_url}. "
                "Is the service running?"
            )
            raise
        except requests.HTTPError as e:
            status_code = e.response.status_code
            if status_code == 400:
                logger.error("Merge validation failed (400 Bad Request)")
                try:
                    error_detail = e.response.json()
                    logger.error(f"Error details: {json.dumps(error_detail, indent=2)}")
                except Exception:
                    logger.error(f"Error details: {e.response.text}")
            elif status_code == 404:
                logger.error(
                    f"Schema not found (404): {schema_id}. "
                    "Verify SCHEMA_ID environment variable."
                )
            else:
                logger.error(f"Merge request failed: {e}")
            raise


class VinnyClient:
    """Client for interacting with Vinny data-collection API."""

    def __init__(self, api_url: str, api_key: str):
        """
        Initialize Vinny client.

        Args:
            api_url: Base URL for Vinny API
            api_key: API key for authentication
        """
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key

    def _get_headers(self) -> Dict[str, str]:
        """Get common headers for API requests."""
        return {
            "Content-Type": "application/json",
            "x-api-key": self.api_key
        }

    def get_schema(self, schema_id: str) -> Dict[str, Any]:
        """
        Fetch existing schema by ID.

        Args:
            schema_id: Schema ID to fetch

        Returns:
            Schema data containing id, name, key, schema

        Raises:
            requests.HTTPError: If schema not found or request fails
        """
        url = f"{self.api_url}/data-schemas/{schema_id}"
        logger.debug(f"Fetching schema: {schema_id}")

        response = requests.get(url, headers=self._get_headers())
        response.raise_for_status()
        return response.json()

    def update_schema(
        self,
        schema_id: str,
        name: str,
        key: str,
        schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update existing schema.

        Args:
            schema_id: Schema ID to update
            name: Schema name
            key: Schema key
            schema: Schema JSON

        Returns:
            Updated schema data

        Raises:
            requests.HTTPError: If update fails
        """
        url = f"{self.api_url}/data-schemas/{schema_id}"
        payload = {
            "name": name,
            "key": key,
            "schema": schema
        }

        logger.debug(f"Updating schema: {schema_id}")
        response = requests.put(
            url,
            json=payload,
            headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()

    def get_form(self, form_id: str) -> Dict[str, Any]:
        """
        Fetch existing form by ID.

        Args:
            form_id: Form ID to fetch

        Returns:
            Form data containing id, name, key, schema, dataSchemaId

        Raises:
            requests.HTTPError: If form not found or request fails
        """
        url = f"{self.api_url}/forms/{form_id}"
        logger.debug(f"Fetching form: {form_id}")

        response = requests.get(url, headers=self._get_headers())
        response.raise_for_status()
        return response.json()

    def create_form(
        self,
        name: str,
        key: str,
        schema: Dict[str, Any],
        data_schema_id: str
    ) -> Dict[str, Any]:
        """
        Create new form.

        Args:
            name: Form name
            key: Form key (must be unique)
            schema: Form schema JSON
            data_schema_id: Associated data schema ID

        Returns:
            Created form data

        Raises:
            requests.HTTPError: If creation fails
        """
        url = f"{self.api_url}/forms"
        payload = {
            "name": name,
            "key": key,
            "schema": schema,
            "dataSchemaId": data_schema_id
        }

        logger.debug(f"Creating form: {key}")
        response = requests.post(
            url,
            json=payload,
            headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()

    def update_form(
        self,
        form_id: str,
        name: str,
        key: str,
        schema: Dict[str, Any],
        data_schema_id: str
    ) -> Dict[str, Any]:
        """
        Update existing form.

        Args:
            form_id: Form ID to update
            name: Form name
            key: Form key
            schema: Form schema JSON
            data_schema_id: Associated data schema ID

        Returns:
            Updated form data

        Raises:
            requests.HTTPError: If update fails
        """
        url = f"{self.api_url}/forms/{form_id}"
        payload = {
            "name": name,
            "key": key,
            "schema": schema,
            "dataSchemaId": data_schema_id
        }

        logger.debug(f"Updating form: {form_id}")
        response = requests.put(
            url,
            json=payload,
            headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()


def save_csv_to_file(
    csv_content: str,
    schema_id: str,
    output_dir: Optional[str] = None
) -> str:
    """
    Save CSV content to file with timestamped filename.

    Args:
        csv_content: CSV content as string
        schema_id: Schema ID for filename
        output_dir: Output directory (default: outputs/)

    Returns:
        Path to saved CSV file
    """
    if output_dir is None:
        output_dir = os.getenv(
            'CSV_OUTPUT_DIR',
            os.path.join(os.path.dirname(__file__), '../../outputs')
        )

    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    filename = f"schema-merge-{schema_id}-{timestamp}.csv"
    output_path = os.path.join(output_dir, filename)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(csv_content)

    logger.info(f"CSV saved to: {output_path}")
    return output_path


def save_debug_response(response_data: Dict[str, Any], prefix: str):
    """
    Save API response to debug file.

    Args:
        response_data: Response data to save
        prefix: Filename prefix
    """
    debug_dir = os.path.join(
        os.path.dirname(__file__),
        '../../outputs/debug'
    )
    os.makedirs(debug_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    filename = f"{prefix}-{timestamp}.json"
    path = os.path.join(debug_dir, filename)

    with open(path, 'w') as f:
        json.dump(response_data, f, indent=2)

    logger.debug(f"Saved debug response to: {path}")


def display_merge_results(response: Dict[str, Any]) -> None:
    """
    Display merge results in formatted output.

    Args:
        response: Merge response containing stats, validation, change_comments
    """
    print("\n" + "=" * 50)
    print("=== CSV Schema Merge Results ===")
    print("=" * 50 + "\n")

    # Stats
    stats = response.get('stats', {})
    print("Stats:")
    print(f"  Total CSV Rows: {stats.get('total_csv_rows', 'N/A')}")
    print(f"  Valid Fields: {stats.get('total_csv_fields', 'N/A')}")
    print(f"  Fields Added: {stats.get('fields_added', 0)}")
    print(f"  Fields Modified: {stats.get('fields_modified', 0)}")
    print(f"  Skipped Rows: {stats.get('skipped_rows', 0)}")
    print(f"  Empty Rows: {stats.get('empty_rows', 0)}")

    # Validation
    validation = response.get('validation', {})
    is_valid = validation.get('valid', False)
    status = "✓ PASSED" if is_valid else "✗ FAILED"
    print(f"\nValidation: {status}")

    if not is_valid:
        errors = validation.get('errors', [])
        if errors:
            print("\nValidation Errors:")
            for error in errors:
                print(f"  [x] {error}")

    # Change comments
    comments = response.get('change_comments', [])
    if comments:
        print(f"\nChanges to be applied ({len(comments)} items):\n")
        for comment in comments:
            symbol = get_comment_symbol(comment)
            print(f"  {symbol} {comment}")

    print("\n" + "=" * 50)


def get_comment_symbol(comment: str) -> str:
    """
    Get symbol for change comment based on type.

    Args:
        comment: Change comment string

    Returns:
        Symbol to display ([+], [~], [!], [✓], [x])
    """
    comment_lower = comment.lower()
    if comment_lower.startswith('added'):
        return '[+]'
    elif comment_lower.startswith('modified') or comment_lower.startswith('updated'):
        return '[~]'
    elif comment_lower.startswith('warning'):
        return '[!]'
    elif comment_lower.startswith('error') or comment_lower.startswith('skipped'):
        return '[x]'
    else:
        return '[✓]'


def prompt_user_confirmation(
    schema_info: Dict[str, Any],
    form_info: Optional[Dict[str, Any]]
) -> bool:
    """
    Prompt user for confirmation before applying changes.

    Args:
        schema_info: Schema information dict
        form_info: Form information dict (or None if creating new)

    Returns:
        True if user confirms, False otherwise
    """
    print("\n" + "=" * 50)
    print("Review the changes above carefully.")
    print("\nThis action will:")
    print(f"  1. Update schema '{schema_info['name']}' (ID: {schema_info['id']})")

    if form_info and form_info.get('id'):
        print(f"  2. Update form '{form_info['name']}' (ID: {form_info['id']})")
    else:
        print(f"  2. Create new form (no form_id specified)")

    print(f"\nEnvironment: STAGING")
    print(f"API Endpoint: {os.getenv('VINNY_API_URL')}")
    print("=" * 50)

    while True:
        response = input("\nDo you want to proceed? (y/N): ").strip().lower()
        if response in ['y', 'yes']:
            return True
        elif response in ['n', 'no', '']:
            print("\nOperation cancelled by user.")
            return False
        else:
            print("Please enter 'y' for yes or 'n' for no.")


def generate_form_key(schema_id: str, timestamp: datetime) -> str:
    """
    Generate form key for new forms.

    Args:
        schema_id: Schema ID
        timestamp: Timestamp for uniqueness

    Returns:
        Generated form key
    """
    ts = timestamp.strftime('%Y%m%d%H%M%S')
    return f"schema-{schema_id}-{ts}"


def validate_environment() -> Dict[str, str]:
    """
    Validate required environment variables.

    Returns:
        Dictionary of configuration values

    Raises:
        SystemExit: If required variables are missing
    """
    required = {
        'SCHEMA_ID': 'Global schema ID for merging',
        'VINNY_API_URL': 'Vinny API base URL',
        'VINNY_API_KEY': 'Vinny API authentication key',
        'DRAFT_DRIVER_API_URL': 'draft-driver-100x API base URL'
    }

    missing = []
    config = {}

    for var, description in required.items():
        value = os.getenv(var)
        if not value:
            missing.append(f"  {var}: {description}")
        else:
            config[var] = value

    # Optional variables
    config['FORM_ID'] = os.getenv('FORM_ID')
    config['DRAFT_DRIVER_API_KEY'] = os.getenv('DRAFT_DRIVER_API_KEY')
    config['GOOGLE_SHEETS_CREDENTIALS_PATH'] = os.getenv(
        'GOOGLE_SHEETS_CREDENTIALS_PATH',
        os.path.expanduser('~/.claude/google-sheets-credentials.json')
    )

    if missing:
        logger.error("Missing required environment variables:")
        for var in missing:
            logger.error(var)
        logger.error("\nPlease set these variables in your .env file")
        sys.exit(1)

    return config


def run_merge_workflow(args) -> None:
    """
    Main workflow orchestrator.

    Args:
        args: Parsed command-line arguments
    """
    try:
        # 1. Validate environment
        logger.info("Step 1: Validating environment configuration")
        config = validate_environment()
        schema_id = config['SCHEMA_ID']
        form_id = args.form_id or config.get('FORM_ID')

        # 2. Google Sheets authentication
        logger.info("Step 2: Authenticating with Google Sheets")
        sheets_client = GoogleSheetsClient(
            credentials_file=config['GOOGLE_SHEETS_CREDENTIALS_PATH'],
            token_file=os.path.expanduser('~/.claude/google-sheets-token.json')
        )

        # 3. Extract spreadsheet ID
        logger.info("Step 3: Parsing Google Sheets URL")
        spreadsheet_id = sheets_client.extract_spreadsheet_id(args.sheets_url)
        logger.info(f"Spreadsheet ID: {spreadsheet_id}")

        # 4. Export CSV
        logger.info("Step 4: Exporting CSV from Google Sheets")
        csv_content = sheets_client.export_to_csv(
            spreadsheet_id,
            sheet_name=args.sheet_name,
            range_spec=args.range
        )

        if not csv_content.strip():
            logger.error("CSV export resulted in empty content")
            sys.exit(1)

        logger.info(f"Exported {len(csv_content)} bytes of CSV data")

        # 5. Save CSV to disk
        logger.info("Step 5: Saving CSV to disk")
        csv_path = save_csv_to_file(
            csv_content,
            schema_id,
            output_dir=args.output_csv
        )
        print(f"✓ CSV saved to: {csv_path}")

        # 6. Call merge endpoint
        logger.info("Step 6: Calling draft-driver merge endpoint")
        draft_client = DraftDriverClient(
            api_url=config['DRAFT_DRIVER_API_URL'],
            api_key=config.get('DRAFT_DRIVER_API_KEY')
        )
        merge_result = draft_client.csv_schema_merge(
            csv_content,
            schema_id,
            exclude_info=args.exclude_info_comments,
            timeout=args.merge_timeout
        )

        if args.verbose:
            save_debug_response(merge_result, "merge-response")

        # 7. Display results
        logger.info("Step 7: Displaying merge results")
        display_merge_results(merge_result)

        # 8. Check validation
        if not merge_result.get('validation', {}).get('valid', False):
            logger.error("Schema validation failed. Cannot proceed.")
            sys.exit(1)

        # 9. Fetch existing resources
        logger.info("Step 8: Fetching existing schema and form metadata")
        vinny_client = VinnyClient(
            api_url=config['VINNY_API_URL'],
            api_key=config['VINNY_API_KEY']
        )

        existing_schema = vinny_client.get_schema(schema_id)
        logger.info(
            f"Schema: {existing_schema['name']} (key: {existing_schema['key']})"
        )

        existing_form = None
        if form_id:
            try:
                existing_form = vinny_client.get_form(form_id)
                logger.info(
                    f"Form: {existing_form['name']} (key: {existing_form['key']})"
                )
            except requests.HTTPError as e:
                if e.response.status_code == 404:
                    logger.warning(
                        f"Form {form_id} not found, will create new form"
                    )
                    existing_form = None
                else:
                    raise
        else:
            logger.info("No form_id specified, will create new form")

        # 10. User confirmation
        if not args.yes:
            logger.info("Step 9: Awaiting user confirmation")
            confirmed = prompt_user_confirmation(
                schema_info=existing_schema,
                form_info=existing_form or {'id': None, 'name': 'New Form'}
            )
            if not confirmed:
                sys.exit(0)
        else:
            logger.info("Step 9: Skipping confirmation (--yes flag)")

        # 11. Update schema
        logger.info("Step 10: Updating schema in Vinny")
        updated_schema = vinny_client.update_schema(
            schema_id,
            name=existing_schema['name'],
            key=existing_schema['key'],
            schema=merge_result['data_schema']
        )
        print(f"✓ Schema updated: {updated_schema['name']}")

        if args.verbose:
            save_debug_response(updated_schema, "schema-update")

        # 12. Update or create form
        logger.info("Step 11: Updating/creating form in Vinny")
        if existing_form:
            # Update existing form
            updated_form = vinny_client.update_form(
                form_id,
                name=existing_form['name'],
                key=existing_form['key'],
                schema=merge_result['form_schema'],
                data_schema_id=schema_id
            )
            print(
                f"✓ Form updated: {updated_form['name']} (ID: {updated_form['id']})"
            )
            final_form = updated_form
        else:
            # Create new form
            new_key = generate_form_key(schema_id, datetime.now())
            new_name = f"Form for {existing_schema['name']}"
            created_form = vinny_client.create_form(
                name=new_name,
                key=new_key,
                schema=merge_result['form_schema'],
                data_schema_id=schema_id
            )
            print(
                f"✓ Form created: {created_form['name']} (ID: {created_form['id']})"
            )
            print(f"  Key: {created_form['key']}")
            final_form = created_form

        if args.verbose:
            save_debug_response(final_form, "form-update")

        # 13. Cleanup (optional)
        if args.cleanup_csv:
            logger.info("Step 12: Cleaning up CSV file")
            os.remove(csv_path)
            print(f"✓ CSV file deleted: {csv_path}")

        # 14. Success summary
        print("\n" + "=" * 50)
        print("=== Merge Complete ===")
        print(f"Schema: {updated_schema['name']} (ID: {schema_id})")
        print(f"Form: {final_form['name']} (ID: {final_form['id']})")
        print(
            f"CSV: {csv_path}" +
            (" (deleted)" if args.cleanup_csv else "")
        )
        print("=" * 50)

        logger.info("Workflow completed successfully")

    except KeyboardInterrupt:
        logger.info("\nOperation cancelled by user (Ctrl+C)")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Workflow failed: {e}", exc_info=True)
        sys.exit(1)


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description='Merge schema and form from Google Sheets CSV',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Basic usage with environment-configured form
  %(prog)s --sheets-url "https://docs.google.com/spreadsheets/d/ABC123/edit"

  # Specify form ID explicitly
  %(prog)s --sheets-url "https://docs.google.com/spreadsheets/d/ABC123" --form-id form-456

  # Export specific sheet and range
  %(prog)s --sheets-url "URL" --sheet-name "Form Fields" --range "A1:P100"

  # Verbose mode with custom CSV output
  %(prog)s --sheets-url "URL" --output-csv ./my-export.csv -v
        '''
    )

    # Required
    parser.add_argument(
        '--sheets-url',
        required=True,
        help='Google Sheets URL or spreadsheet ID'
    )

    # Optional
    parser.add_argument(
        '--form-id',
        help='Form ID to update (overrides FORM_ID env var, creates new if not provided)'
    )
    parser.add_argument(
        '--sheet-name',
        help='Specific sheet name to export (default: first sheet)'
    )
    parser.add_argument(
        '--range',
        help='A1 notation range to export (e.g., "A1:P100")'
    )
    parser.add_argument(
        '--output-csv',
        help='Custom path to save CSV file (default: outputs/schema-merge-{schema_id}-{timestamp}.csv)'
    )
    parser.add_argument(
        '--cleanup-csv',
        action='store_true',
        help='Delete CSV file after successful merge (default: keep for debugging)'
    )
    parser.add_argument(
        '--exclude-info-comments',
        action='store_true',
        help='Only show errors and warnings in merge comments (exclude info messages)'
    )
    parser.add_argument(
        '--merge-timeout',
        type=int,
        default=60,
        help='Timeout in seconds for merge API call (default: 60)'
    )
    parser.add_argument(
        '--env-file',
        help='Path to custom .env file'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose debug logging'
    )
    parser.add_argument(
        '--yes', '-y',
        action='store_true',
        help='Skip confirmation prompt (auto-accept)'
    )

    args = parser.parse_args()

    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load custom .env file if specified
    if args.env_file:
        load_dotenv(args.env_file, override=True)

    # Run workflow
    run_merge_workflow(args)


if __name__ == "__main__":
    main()
