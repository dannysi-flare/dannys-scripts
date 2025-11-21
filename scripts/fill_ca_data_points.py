import json
import csv
from typing import Dict, List, Any, Optional
import re

class DataPointsFiller:
    def __init__(self):
        self.ca_data = []
        self.docoloco_schema = {}
        self.az_data = []
        self.schema_fields = {}
        
    def load_ca_data_points(self, file_path: str):
        """Load CA Data Points CSV as base template"""
        self.ca_data = []
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                self.ca_data.append(row)
        print(f"Loaded {len(self.ca_data)} rows from CA Data Points")
    
    def load_docoloco_schema(self, file_path: str):
        """Load docoloco JSON schema"""
        with open(file_path, 'r', encoding='utf-8') as f:
            self.docoloco_schema = json.load(f)
        
        # Extract field definitions from $defs
        self.schema_fields = {}
        defs = self.docoloco_schema.get('schema', {}).get('$defs', {})
        
        for field_name, field_def in defs.items():
            self.schema_fields[field_name] = field_def
            
            # Handle array fields - extract nested properties  
            if field_def.get('type') == 'array':
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
                        self.schema_fields[array_field_name] = merged_def
        
        print(f"Loaded {len(self.schema_fields)} field definitions from docoloco schema")
    
    def load_az_data_points(self, file_path: str):
        """Load AZ Data Points CSV for reference patterns"""
        self.az_data = []
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                self.az_data.append(row)
        print(f"Loaded {len(self.az_data)} rows from AZ Data Points")
    
    def get_ui_component_from_schema(self, field_def: Dict[str, Any]) -> str:
        """Map docoloco schema field definition to UI component"""
        flare_format = field_def.get('flare_format')
        field_type = field_def.get('type')
        format_attr = field_def.get('format')
        
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
        elif format_attr == 'date' or (field_type == 'string' and any(date_word in field_def.get('flare_displayName', '').lower() for date_word in ['date', 'birth', 'married', 'separated'])):
            return 'Date picker (string-date)'
        elif field_type == 'string':
            return 'Text field (string)'
        elif field_type == 'array':
            return 'Array'
        else:
            return 'Text field (string)'  # Default fallback
    
    def get_ui_component_from_az(self, data_point: str) -> Optional[str]:
        """Get UI component from AZ data points by field name match"""
        for az_row in self.az_data:
            if az_row.get('Data Point') == data_point:
                ui_component = az_row.get('UI Component (schema type)', '').strip()
                if ui_component:
                    return ui_component
        return None
    
    def infer_ui_component_from_field_info(self, ca_row: Dict[str, str]) -> str:
        """Infer UI component from CA row information when no schema match"""
        data_point = ca_row.get('Data Point', '').lower()
        description = ca_row.get('Description', '').lower()
        
        # Phone number patterns
        if 'phone' in data_point or 'phone' in description:
            return 'Phone number (string)'
        
        # Email patterns  
        if 'email' in data_point or 'email' in description:
            return 'Email (string)'
        
        # Date patterns
        if any(word in data_point or word in description for word in ['date', 'birth', 'dob', 'married', 'separated', 'start', 'end']):
            return 'Date picker (string-date)'
        
        # Boolean patterns (yes/no questions)
        if description.startswith('are you') or description.startswith('do you') or description.startswith('did you') or description.startswith('have you') or description.startswith('is '):
            return 'True/false (boolean)'
        
        # Number patterns
        if any(word in data_point or word in description for word in ['age', 'number', 'hours', 'years', 'zip', 'income', 'many']):
            return 'Number'
        
        # Selection patterns (multiple choice indicators)
        if 'what is your' in description and any(word in description for word in ['status', 'type', 'level']):
            return 'Selection (string-enum)'
        
        # Default to text field
        return 'Text field (string)'
    
    def find_matching_schema_field(self, data_point: str) -> Optional[Dict[str, Any]]:
        """Find matching field in docoloco schema"""
        # Direct match
        if data_point in self.schema_fields:
            return self.schema_fields[data_point]
        
        # Handle array notation differences
        if '[]' in data_point:
            # Try without [] notation
            simplified = data_point.replace('[]', '')
            if simplified in self.schema_fields:
                return self.schema_fields[simplified]
        
        # Partial name matching
        for schema_field, schema_def in self.schema_fields.items():
            # Remove [] notation for comparison
            clean_schema_field = schema_field.replace('[]', '').replace('.', '')
            clean_data_point = data_point.replace('[]', '').replace('.', '')
            
            # Check if data point is contained in schema field or vice versa
            if (clean_data_point in clean_schema_field or 
                clean_schema_field in clean_data_point):
                return schema_def
        
        return None
    
    def format_enum_options(self, enum_values: List[str]) -> str:
        """Format enum values as selection options"""
        if not enum_values:
            return ''
        
        options = []
        for i, value in enumerate(enum_values):
            letter = chr(ord('a') + i)
            options.append(f"{letter}) {value}")
        
        return ' '.join(options)
    
    def fill_row_data(self, ca_row: Dict[str, str]) -> Dict[str, str]:
        """Fill missing data in a CA row using schema and AZ data"""
        data_point = ca_row.get('Data Point', '')
        
        # Find matching schema field
        schema_field = self.find_matching_schema_field(data_point)
        
        # Fill UI Component (mandatory field)
        if not ca_row.get('UI Component (schema type)', '').strip():
            ui_component = None
            
            # Try to get from schema
            if schema_field:
                ui_component = self.get_ui_component_from_schema(schema_field)
            
            # Try to get from AZ data
            if not ui_component:
                ui_component = self.get_ui_component_from_az(data_point)
            
            # Infer from field information
            if not ui_component:
                ui_component = self.infer_ui_component_from_field_info(ca_row)
            
            ca_row['UI Component (schema type)'] = ui_component
        
        # Fill other fields from schema if available and empty
        if schema_field:
            # Client facing label
            if not ca_row.get('Client facing label', '').strip():
                flare_display_name = schema_field.get('flare_displayName', '')
                if flare_display_name:
                    ca_row['Client facing label'] = flare_display_name
            
            # Hint text
            if not ca_row.get('Hint text', '').strip():
                flare_client_helper_text = schema_field.get('flare_clientHelperText', '')
                if flare_client_helper_text:
                    ca_row['Hint text'] = flare_client_helper_text
            
            # Selection options
            if not ca_row.get('Selection options (if type = selection)', '').strip():
                enum_values = schema_field.get('enum', [])
                if enum_values:
                    ca_row['Selection options (if type = selection)'] = self.format_enum_options(enum_values)
            
            # Validation text
            if not ca_row.get('Validation text (if required)', '').strip():
                flare_validation_message = schema_field.get('flare_validationMessage', '')
                if flare_validation_message:
                    ca_row['Validation text (if required)'] = flare_validation_message
            
            # Attorney facing label
            if not ca_row.get('Attorney facing label', '').strip():
                flare_attorney_display = schema_field.get('flare_attorneyDisplay', '')
                if flare_attorney_display:
                    ca_row['Attorney facing label'] = flare_attorney_display
        
        return ca_row
    
    def fill_all_data(self):
        """Fill missing data in all CA Data Points rows"""
        print("Filling missing data...")
        
        filled_count = 0
        ui_component_filled = 0
        
        for i, row in enumerate(self.ca_data):
            original_ui_component = row.get('UI Component (schema type)', '').strip()
            
            filled_row = self.fill_row_data(row)
            self.ca_data[i] = filled_row
            
            # Count UI components filled
            if not original_ui_component and filled_row.get('UI Component (schema type)', '').strip():
                ui_component_filled += 1
            
            filled_count += 1
        
        print(f"Processed {filled_count} rows, filled {ui_component_filled} UI Component fields")
    
    def save_enhanced_csv(self, output_path: str):
        """Save the enhanced CA Data Points CSV"""
        if not self.ca_data:
            print("No data to save")
            return
        
        fieldnames = list(self.ca_data[0].keys())
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.ca_data)
        
        print(f"Enhanced CSV saved to: {output_path}")

def main():
    # File paths
    ca_data_path = '/Users/dannysivan/Downloads/CA Data Points (1).csv'
    docoloco_schema_path = '/Users/dannysivan/dannys-scripts/inputs/docoloco-schema.json'
    az_data_path = '/Users/dannysivan/Downloads/AZ Data Points.csv'
    output_path = '/Users/dannysivan/dannys-scripts/inputs/CA-data-points-enhanced.csv'
    
    # Initialize filler
    filler = DataPointsFiller()
    
    # Load all data sources
    print("Loading data sources...")
    filler.load_ca_data_points(ca_data_path)
    filler.load_docoloco_schema(docoloco_schema_path)
    filler.load_az_data_points(az_data_path)
    
    # Fill missing data
    filler.fill_all_data()
    
    # Save enhanced CSV
    filler.save_enhanced_csv(output_path)
    
    print("Process completed successfully!")

if __name__ == "__main__":
    main()
