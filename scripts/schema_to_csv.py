import json
import csv
from typing import Dict, List, Any, Tuple

def load_schema(file_path: str) -> Dict[str, Any]:
    """Load and parse the JSON schema file"""
    with open(file_path, 'r') as f:
        return json.load(f)

def get_ui_component(field_def: Dict[str, Any]) -> str:
    """Map flare_format and type to UI component"""
    flare_format = field_def.get('flare_format')
    field_type = field_def.get('type')
    
    if flare_format == 'phone':
        return 'Phone number (string)'
    elif flare_format == 'email':
        return 'Email (string)'
    elif flare_format == 'SSN':
        return 'SSN field (string)'
    elif flare_format == 'currency':
        return 'Currency (string)'
    elif field_type == 'boolean':
        return 'True/false (boolean)'
    elif field_type == 'number':
        return 'Number'
    elif field_type == 'string' and 'enum' in field_def:
        return 'Selection (string-enum)'
    elif field_def.get('format') == 'date' or field_type == 'string' and 'date' in field_def.get('flare_displayName', '').lower():
        return 'Date picker (string-date)'
    elif field_type == 'string':
        return 'Text field (string)'
    elif field_type == 'array':
        return 'Array'
    else:
        return field_type or 'Text field (string)'

def format_enum_options(enum_values: List[str]) -> str:
    """Format enum values as selection options"""
    if not enum_values:
        return ''
    
    options = []
    for i, value in enumerate(enum_values):
        letter = chr(ord('a') + i)
        options.append(f"{letter}) {value}")
    
    return ' '.join(options)

def map_bucket_to_izzy_bucket(bucket: str) -> str:
    """Map flare_bucket to Izzy Bucket categories"""
    bucket_mapping = {
        'CLIENT': 'Generic Client Info',
        'OPPOSING_PARTY': 'Opposing Party Info', 
        'MARRIAGE': 'Marriage Info',
        'CHILDREN': 'Child Generic Info',
        'ASSETS': 'General Financial',
        'CASE_DETAILS': 'Marriage Info',  # Based on CA CSV pattern
        'ATTORNEY_ONLY': 'Attorney Only',
        'PERSONAL_INFORMATION': 'Generic Client Info'
    }
    return bucket_mapping.get(bucket, bucket)

def extract_fields_from_schema(schema: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    """Extract all field definitions from schema, including nested array items"""
    fields = []
    defs = schema.get('schema', {}).get('$defs', {})
    
    for field_name, field_def in defs.items():
        if field_def.get('type') == 'array':
            # Handle array fields - extract nested properties
            items = field_def.get('items', {})
            if items.get('type') == 'object':
                properties = items.get('properties', {})
                for prop_name, prop_def in properties.items():
                    # Create array notation for nested properties
                    array_field_name = f"{field_name}[].{prop_name}"
                    # Merge array-level and property-level attributes
                    merged_def = {**field_def, **prop_def}
                    # Remove conflicting array-level attributes
                    merged_def.pop('items', None)
                    fields.append((array_field_name, merged_def))
            else:
                # Simple array without object items
                fields.append((field_name, field_def))
        else:
            # Regular field
            fields.append((field_name, field_def))
    
    return fields

def create_csv_row(field_name: str, field_def: Dict[str, Any]) -> List[str]:
    """Create a CSV row from a field definition"""
    
    # Extract properties with defaults
    flare_bucket = field_def.get('flare_bucket', '')
    flare_sub_bucket = field_def.get('flare_subBucket', '')
    flare_display_name = field_def.get('flare_displayName', '')
    flare_attorney_display = field_def.get('flare_attorneyDisplay', '')
    flare_client_helper_text = field_def.get('flare_clientHelperText', '')
    flare_validation_message = field_def.get('flare_validationMessage', '')
    enum_values = field_def.get('enum', [])
    
    # Create CSV row
    row = [
        map_bucket_to_izzy_bucket(flare_bucket),  # Izzy Bucket
        flare_bucket,  # Big Bucket
        flare_sub_bucket,  # Little Bucket
        field_name,  # Data Point
        flare_display_name,  # Description
        'Existing',  # Existing/New
        '',  # Dependencies 
        get_ui_component(field_def),  # UI Component
        flare_display_name,  # Client facing label
        '',  # Placeholder text
        flare_client_helper_text,  # Hint text
        format_enum_options(enum_values),  # Selection options
        '',  # Required?
        flare_validation_message,  # Validation text
        flare_attorney_display,  # Attorney facing label
        ''  # Notes
    ]
    
    return row

def main():
    # Load schema
    schema_path = '/Users/dannysivan/dannys-scripts/inputs/docoloco-schema.json'
    schema = load_schema(schema_path)
    
    # Extract all fields
    fields = extract_fields_from_schema(schema)
    
    # Create CSV header
    header = [
        'Izzy Bucket', 'Big Bucket', 'Little Bucket', 'Data Point', 'Description',
        'Existing/New', 'Dependencies', 'UI Component (schema type)', 'Client facing label',
        'Placeholder text', 'Hint text', 'Selection options (if type = selection)',
        'Required?', 'Validation text (if required)', 'Attorney facing label', 'Notes'
    ]
    
    # Sort fields by bucket order for logical grouping
    bucket_order = ['CLIENT', 'OPPOSING_PARTY', 'MARRIAGE', 'CHILDREN', 'ASSETS', 'CASE_DETAILS', 'ATTORNEY_ONLY', 'PERSONAL_INFORMATION']
    
    def get_bucket_order(field_tuple):
        field_name, field_def = field_tuple
        bucket = field_def.get('flare_bucket', '')
        try:
            return bucket_order.index(bucket)
        except ValueError:
            return len(bucket_order)  # Put unknown buckets at the end
    
    fields.sort(key=get_bucket_order)
    
    # Generate CSV
    output_path = '/Users/dannysivan/dannys-scripts/inputs/docoloco-data-points.csv'
    
    with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        
        # Write header
        writer.writerow(header)
        
        # Write data rows
        for field_name, field_def in fields:
            row = create_csv_row(field_name, field_def)
            writer.writerow(row)
    
    print(f"CSV generated successfully: {output_path}")
    print(f"Total fields processed: {len(fields)}")

if __name__ == "__main__":
    main()




