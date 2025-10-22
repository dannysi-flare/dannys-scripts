# S3 Upload Script Implementation

## Script Requirements

Create `scripts/docoloco/upload_s3_draft.py` that:

- Takes file path and S3 object name as command line arguments
- Supports `--prod` flag to switch between `marble-drafts-staging` (default) and `marble-drafts-production` buckets
- Checks AWS SSO login status and prompts login if needed
- Uploads the file to the specified S3 bucket

## Implementation Details

### Command Line Interface

- `file_path`: Local file path to upload
- `s3_object_name`: S3 object key/path for the uploaded file
- `--prod`: Optional flag to use production bucket

### AWS Authentication Flow

1. Check if AWS SSO session is valid by attempting to get credentials
2. If invalid/missing, run `aws sso login` subprocess
3. Use boto3 with default credential chain for S3 operations

### Key Components

- Follow existing script patterns: logging (errors only), argparse, error handling
- Add boto3 dependency to `requirements.txt`
- Use same code structure as `copy_schema_forms.py`
- Include proper error handling and user feedback

### Files to Modify

- Create: `scripts/docoloco/upload_s3_draft.py`
- Update: `requirements.txt` (add boto3)

## Success Criteria

- Script successfully uploads files to correct S3 bucket
- Handles AWS SSO authentication seamlessly
- Provides clear feedback on upload success/failure
- Follows project coding standards

### To-dos

- [x] Add boto3 to requirements.txt for S3 operations
- [x] Create upload_s3_draft.py with command line arguments, AWS SSO check, and S3 upload functionality
- [x] Implement AWS SSO session validation and login prompt
- [x] Implement S3 upload logic with bucket selection based on --prod flag
- [x] Add comprehensive error handling and user feedback
- [x] Add production confirmation prompt (requires user to type 'y' before uploading to production)
- [x] Implement automatic backup system for existing files (creates .bak<number> versions)
