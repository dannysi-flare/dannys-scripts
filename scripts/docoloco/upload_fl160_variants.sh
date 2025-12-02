#!/bin/bash

# Script to upload FL-160 variant files to S3 production
cd /Users/dannysivan/src/dannys-scripts
source venv/bin/activate

JSONATA_DIR="/Users/dannysivan/src/claude-prompts/jsonata_documents"

# Array of FL-160 variant files to upload
FILES=(
  "fl-160-joint.jsonata"
  "fl-160-solo.jsonata"
  "fl-160-joint-response.jsonata"
  "fl-160-solo-response.jsonata"
)

for filename in "${FILES[@]}"; do
  file="$JSONATA_DIR/$filename"
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
