#!/usr/bin/env python3

import argparse
import logging
import subprocess
import sys
from pathlib import Path

import boto3
from botocore.exceptions import (
    NoCredentialsError, ClientError, ProfileNotFound
)

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

STAGING_BUCKET = "marble-drafts-staging"
PRODUCTION_BUCKET = "marble-drafts-production"


def check_aws_sso_login():
    """Check if AWS SSO session is valid and prompt login if needed."""
    try:
        # Try to get credentials to check if SSO session is valid
        session = boto3.Session()
        credentials = session.get_credentials()

        if credentials is None:
            raise NoCredentialsError

        # Test if credentials work by making a simple STS call
        sts_client = session.client('sts')
        sts_client.get_caller_identity()

        return True
    except (NoCredentialsError, ClientError, ProfileNotFound):
        print("AWS SSO session not found or expired. "
              "Running 'aws sso login'...")

        try:
            subprocess.run(
                ["aws", "sso", "login"],
                check=True,
                capture_output=True,
                text=True
            )
            print("✓ AWS SSO login successful")
            return True
        except subprocess.CalledProcessError as e:
            logger.error("AWS SSO login failed: %s", e)
            logger.error("Command output: %s", e.stderr)
            return False
        except FileNotFoundError:
            logger.error("AWS CLI not found. Please install AWS CLI first.")
            return False


def check_object_exists(s3_client, bucket_name: str, object_key: str) -> bool:
    """Check if an object exists in S3 bucket."""
    try:
        s3_client.head_object(Bucket=bucket_name, Key=object_key)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            return False
        raise


def find_backup_name(s3_client, bucket_name: str, original_key: str) -> str:
    """Find an available backup name by incrementing the number."""
    base_name = f"{original_key}.bak"
    counter = 1

    while True:
        backup_key = f"{base_name}{counter}"
        if not check_object_exists(s3_client, bucket_name, backup_key):
            return backup_key
        counter += 1


def create_backup_if_needed(s3_client, bucket_name: str, object_key: str):
    """Create a backup of existing object if it exists."""
    if not check_object_exists(s3_client, bucket_name, object_key):
        return None

    backup_key = find_backup_name(s3_client, bucket_name, object_key)

    print(f"Object already exists. Creating backup: {backup_key}")

    # Copy existing object to backup
    copy_source = {'Bucket': bucket_name, 'Key': object_key}
    s3_client.copy_object(
        CopySource=copy_source,
        Bucket=bucket_name,
        Key=backup_key
    )

    print(f"✓ Backup created: s3://{bucket_name}/{backup_key}")
    return backup_key


def upload_file_to_s3(
    file_path: str, s3_object_name: str, bucket_name: str
) -> bool:
    """Upload a file to S3 bucket."""
    path_obj = Path(file_path)

    if not path_obj.exists():
        logger.error("File not found: %s", file_path)
        sys.exit(1)

    if not path_obj.is_file():
        logger.error("Path is not a file: %s", file_path)
        sys.exit(1)

    try:
        s3_client = boto3.client('s3')

        # Create backup if object already exists
        backup_key = create_backup_if_needed(
            s3_client, bucket_name, s3_object_name
        )

        print(f"Uploading {file_path} to s3://{bucket_name}/{s3_object_name}")

        # Upload the file
        s3_client.upload_file(
            str(path_obj),
            bucket_name,
            s3_object_name
        )

        print(
            f"✓ File uploaded successfully to "
            f"s3://{bucket_name}/{s3_object_name}"
        )
        if backup_key:
            print(f"✓ Previous version backed up as: {backup_key}")
        return True
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'NoSuchBucket':
            logger.error("Bucket '%s' does not exist", bucket_name)
        elif error_code == 'AccessDenied':
            logger.error("Access denied to bucket '%s'", bucket_name)
        else:
            logger.error("Failed to upload file: %s", e)
        return False
    except Exception as e:
        logger.error("Unexpected error during upload: %s", e)
        return False


def confirm_production_upload(
    bucket_name: str, file_path: str, s3_object_name: str
) -> bool:
    """Prompt user for confirmation when uploading to production."""
    print("\n⚠️  WARNING: You are about to upload to PRODUCTION bucket!")
    print(f"   Bucket: {bucket_name}")
    print(f"   File: {file_path}")
    print(f"   S3 Path: {s3_object_name}")
    print("\nThis action will affect the production environment.")

    while True:
        response = input("Do you want to continue? (y/N): ").strip().lower()
        if response in ['y', 'yes']:
            return True
        elif response in ['n', 'no', '']:
            print("Upload cancelled.")
            return False
        else:
            print("Please enter 'y' for yes or 'n' for no.")


def main():
    parser = argparse.ArgumentParser(
        description="Upload a file to S3 (marble-drafts buckets)"
    )
    parser.add_argument(
        "file_path",
        help="Path to the local file to upload"
    )
    parser.add_argument(
        "s3_object_name",
        help="S3 object name/path for the uploaded file"
    )
    parser.add_argument(
        "--prod",
        action="store_true",
        help="Use production bucket (marble-drafts-production) "
             "instead of staging"
    )

    args = parser.parse_args()

    # Determine bucket based on --prod flag
    bucket_name = PRODUCTION_BUCKET if args.prod else STAGING_BUCKET

    print(f"Target bucket: {bucket_name}")

    # Production confirmation check
    if args.prod:
        if not confirm_production_upload(
            bucket_name, args.file_path, args.s3_object_name
        ):
            sys.exit(0)

    # Check AWS SSO authentication
    if not check_aws_sso_login():
        logger.error("AWS authentication failed")
        sys.exit(1)

    # Upload file
    success = upload_file_to_s3(
        args.file_path, args.s3_object_name, bucket_name
    )

    if not success:
        sys.exit(1)

    print("\n=== Upload Complete ===")
    print(f"File: {args.file_path}")
    print(f"S3 Location: s3://{bucket_name}/{args.s3_object_name}")
    print("======================")


if __name__ == "__main__":
    main()
