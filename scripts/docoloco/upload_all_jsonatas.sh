#!/bin/bash

# Script to upload all jsonata files to S3 production
cd /Users/dannysivan/src/dannys-scripts
source venv/bin/activate

JSONATA_DIR="/Users/dannysivan/src/claude-prompts/jsonata_documents"

for file in "$JSONATA_DIR"/*.jsonata; do
  filename=$(basename "$file")
  echo ""
  echo "=================================================="
  echo "Uploading $filename to jsonatas/CA/$filename"
  echo "=================================================="
  echo "y" | python3 scripts/docoloco/upload_s3_draft.py "$file" "jsonatas/CA/$filename" --prod

  if [ $? -eq 0 ]; then
    echo "✓ Successfully uploaded $filename"
  else
    echo "✗ Failed to upload $filename"
  fi
done

echo ""
echo "=================================================="
echo "Upload process complete!"
echo "=================================================="
