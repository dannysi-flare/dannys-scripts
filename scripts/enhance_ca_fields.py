import json
import csv
from typing import Dict, List, Any, Optional
import re

class CAFieldEnhancer:
    def __init__(self):
        self.ca_data = []
        self.docoloco_schema = {}
        self.schema_fields = {}
        
    def load_ca_enhanced_csv(self, file_path: str):
        """Load the current enhanced CA Data Points CSV"""
        self.ca_data = []
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                self.ca_data.append(row)
        print(f"Loaded {len(self.ca_data)} rows from enhanced CA Data Points")
    
    def load_docoloco_schema(self, file_path: str):
        """Load docoloco JSON schema for reference"""
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
                        array_field_name = f"{field_name}[].{prop_name}"
                        merged_def = {**field_def, **prop_def}
                        merged_def.pop('items', None)
                        self.schema_fields[array_field_name] = merged_def
        
        print(f"Loaded {len(self.schema_fields)} field definitions from docoloco schema")
    
    def infer_big_bucket_from_data_point(self, data_point: str, izzy_bucket: str) -> str:
        """Infer Big Bucket from data point and izzy bucket"""
        dp_lower = data_point.lower()
        
        # Client-related fields
        if any(word in dp_lower for word in ['client', 'my', 'your', 'age', 'height', 'weight', 'ssn', 'dl', 'dob']):
            return 'Client'
        
        # Opposing party fields
        if any(word in dp_lower for word in ['opposing', 'spouse']):
            return 'Opposing party'
        
        # Marriage fields
        if any(word in dp_lower for word in ['married', 'marriage', 'maiden', 'separated', 'divorce']):
            return 'Marriage'
        
        # Children fields
        if any(word in dp_lower for word in ['children', 'child', 'custody', 'pregnancy']):
            return 'Children'
        
        # Case/Legal fields
        if any(word in dp_lower for word in ['case', 'court', 'order', 'legal', 'attorney', 'support']):
            return 'Case details'
        
        # Financial fields
        if any(word in dp_lower for word in ['income', 'salary', 'wage', 'money', 'expense', 'asset', 'debt', 'property', 'tax', 'insurance']):
            return 'Financial'
        
        # Use Izzy Bucket as fallback mapping
        izzy_to_big = {
            'Generic Client Info': 'Client',
            'Client Employment info': 'Client',
            'Opposing Party Info': 'Opposing party',
            'Marriage Info': 'Marriage',
            'Child Generic Info': 'Children',
            'Custody Info': 'Children',
            'General Financial': 'Financial',
            'Household Info': 'Household',
            'Payroll': 'Financial',
            'Income': 'Financial',
            'Expenses': 'Financial',
            'Assets': 'Financial',
            'CA Assets': 'Financial',
            'CA Debts': 'Financial'
        }
        
        return izzy_to_big.get(izzy_bucket, 'Other')
    
    def infer_little_bucket_from_data_point(self, data_point: str, big_bucket: str) -> str:
        """Infer Little Bucket from data point and big bucket"""
        dp_lower = data_point.lower()
        
        if big_bucket == 'Client':
            if any(word in dp_lower for word in ['name', 'phone', 'email', 'address', 'age', 'height', 'weight', 'ssn', 'dl', 'dob', 'gender']):
                return 'Personal details'
            elif any(word in dp_lower for word in ['job', 'employ', 'work', 'occupation', 'military', 'income', 'salary']):
                return 'Employment details'
            elif any(word in dp_lower for word in ['school', 'college', 'degree', 'education', 'license', 'certification', 'vocational']):
                return 'Schooling and Certifications'
            else:
                return 'Personal details'
        
        elif big_bucket == 'Opposing party':
            if any(word in dp_lower for word in ['name', 'phone', 'email', 'address', 'age', 'height', 'weight', 'ssn', 'dl', 'dob', 'gender']):
                return 'Personal details'
            elif any(word in dp_lower for word in ['job', 'employ', 'work', 'occupation', 'military', 'income']):
                return 'Employment details'
            else:
                return 'Personal details'
        
        elif big_bucket == 'Marriage':
            if any(word in dp_lower for word in ['married', 'marriage', 'separated', 'place']):
                return 'Marriage details'
            elif any(word in dp_lower for word in ['maiden', 'prenup']):
                return 'Additional information'
            else:
                return 'Marriage details'
        
        elif big_bucket == 'Children':
            if any(word in dp_lower for word in ['name', 'gender', 'birth', 'age', 'ssn', 'address']):
                return 'Minor Children'
            elif any(word in dp_lower for word in ['history', 'lived', 'previous']):
                return 'Address history'
            elif any(word in dp_lower for word in ['custody', 'pregnancy', 'other']):
                return 'Additional info'
            elif any(word in dp_lower for word in ['property', 'insurance']):
                return 'Property'
            elif any(word in dp_lower for word in ['court', 'order', 'case']):
                return 'Existing court orders'
            else:
                return 'Minor Children'
        
        elif big_bucket == 'Case details':
            if any(word in dp_lower for word in ['court', 'order', 'case', 'dvro']):
                return 'Existing court orders'
            elif any(word in dp_lower for word in ['support', 'attorney', 'served', 'waiver']):
                return 'Key details'
            else:
                return 'Key details'
        
        elif big_bucket == 'Financial':
            return 'Financial details'
        
        else:
            return ''
    
    def generate_description_from_data_point(self, data_point: str, existing_description: str) -> str:
        """Generate description from data point if missing"""
        if existing_description and existing_description.strip():
            return existing_description.strip()
        
        dp = data_point.replace('[]', '').replace('.', ' ')
        
        # Convert camelCase to readable text
        readable = re.sub(r'([a-z])([A-Z])', r'\1 \2', dp)
        readable = readable.replace('_', ' ').strip()
        
        # Create question format
        if readable.lower().startswith(('is', 'are', 'do', 'did', 'have', 'has')):
            return f"{readable}?"
        elif 'age' in readable.lower():
            return "How old are you?"
        elif 'name' in readable.lower():
            return f"What is your {readable.lower()}?"
        elif 'address' in readable.lower():
            return f"What is your {readable.lower()}?"
        elif 'phone' in readable.lower():
            return f"What is your {readable.lower()}?"
        elif 'email' in readable.lower():
            return f"What is your {readable.lower()}?"
        elif 'date' in readable.lower() or 'dob' in readable.lower():
            return f"What is your {readable.lower()}?"
        elif 'income' in readable.lower() or 'salary' in readable.lower():
            return f"What is your {readable.lower()}?"
        else:
            return f"Please provide your {readable.lower()}"
    
    def generate_client_facing_label(self, data_point: str, existing_label: str) -> str:
        """Generate client facing label from data point if missing"""
        if existing_label and existing_label.strip():
            return existing_label.strip()
        
        dp = data_point.replace('[]', '').replace('.', ' ')
        readable = re.sub(r'([a-z])([A-Z])', r'\1 \2', dp)
        readable = readable.replace('_', ' ').strip()
        
        # Convert to title case and clean up
        label = readable.title()
        
        # Special cases
        if 'Ssn' in label:
            label = label.replace('Ssn', 'SSN')
        if 'Dl' in label and 'Dl' in label:
            label = label.replace('Dl', "Driver's license")
        if 'Dob' in label:
            label = label.replace('Dob', 'Date of birth')
        if 'Client' in label:
            label = label.replace('Client ', '')
        if 'Opposing Party' in label:
            label = label.replace('Opposing Party ', "Spouse's ")
        
        return label.strip()
    
    def generate_attorney_facing_label(self, data_point: str, client_label: str, existing_label: str) -> str:
        """Generate attorney facing label from other fields if missing"""
        if existing_label and existing_label.strip():
            return existing_label.strip()
        
        # Use client label as base, but make it more concise for attorneys
        if client_label and client_label.strip():
            attorney_label = client_label.strip()
            
            # Simplify for attorney view
            attorney_label = attorney_label.replace('What is your ', '')
            attorney_label = attorney_label.replace('How old are you?', 'Age')
            attorney_label = attorney_label.replace('Please provide your ', '')
            
            return attorney_label.strip()
        
        return self.generate_client_facing_label(data_point, '')
    
    def generate_placeholder_text(self, data_point: str, ui_component: str) -> str:
        """Generate appropriate placeholder text based on field type"""
        dp_lower = data_point.lower()
        
        if 'date' in dp_lower or ui_component == 'Date picker (string-date)':
            return 'Select date'
        elif 'phone' in dp_lower or ui_component == 'Phone number (string)':
            return 'Enter phone number'
        elif 'email' in dp_lower or ui_component == 'Email (string)':
            return 'Enter email address'
        elif 'address' in dp_lower:
            return 'Enter address'
        elif 'name' in dp_lower:
            return 'Enter name'
        elif 'age' in dp_lower or ui_component == 'Number':
            return 'Enter number'
        elif ui_component == 'True/false (boolean)':
            return ''  # Boolean fields don't need placeholder
        elif ui_component == 'Selection (string-enum)':
            return 'Select option'
        else:
            return 'Enter text'
    
    def find_matching_schema_field(self, data_point: str) -> Optional[Dict[str, Any]]:
        """Find matching field in docoloco schema"""
        # Direct match
        if data_point in self.schema_fields:
            return self.schema_fields[data_point]
        
        # Handle array notation differences
        if '[]' in data_point:
            simplified = data_point.replace('[]', '')
            if simplified in self.schema_fields:
                return self.schema_fields[simplified]
        
        # Partial name matching
        for schema_field, schema_def in self.schema_fields.items():
            clean_schema_field = schema_field.replace('[]', '').replace('.', '')
            clean_data_point = data_point.replace('[]', '').replace('.', '')
            
            if (clean_data_point in clean_schema_field or 
                clean_schema_field in clean_data_point):
                return schema_def
        
        return None
    
    def enhance_row(self, row: Dict[str, str]) -> Dict[str, str]:
        """Enhance a single row with missing field data"""
        data_point = row.get('Data Point', '')
        izzy_bucket = row.get('Izzy Bucket', '')
        
        # Find schema data if available
        schema_field = self.find_matching_schema_field(data_point)
        
        # Fill Big Bucket if empty
        if not row.get('Big Bucket', '').strip():
            if schema_field and schema_field.get('flare_bucket'):
                # Map schema bucket to big bucket
                bucket_mapping = {
                    'CLIENT': 'Client',
                    'OPPOSING_PARTY': 'Opposing party',
                    'MARRIAGE': 'Marriage',
                    'CHILDREN': 'Children',
                    'ASSETS': 'Financial',
                    'CASE_DETAILS': 'Case details',
                    'ATTORNEY_ONLY': 'Attorney',
                    'PERSONAL_INFORMATION': 'Client'
                }
                row['Big Bucket'] = bucket_mapping.get(schema_field.get('flare_bucket'), 
                                                     self.infer_big_bucket_from_data_point(data_point, izzy_bucket))
            else:
                row['Big Bucket'] = self.infer_big_bucket_from_data_point(data_point, izzy_bucket)
        
        # Fill Little Bucket if empty
        if not row.get('Little Bucket', '').strip():
            if schema_field and schema_field.get('flare_subBucket'):
                # Map schema sub-bucket to little bucket
                sub_bucket = schema_field.get('flare_subBucket')
                if sub_bucket == 'PERSONAL_DETAILS':
                    row['Little Bucket'] = 'Personal details'
                elif sub_bucket == 'EMPLOYMENT_DETAILS':
                    row['Little Bucket'] = 'Employment details'
                elif sub_bucket == 'MINOR_CHILDREN':
                    row['Little Bucket'] = 'Minor Children'
                elif sub_bucket == 'ADDRESS_HISTORY':
                    row['Little Bucket'] = 'Address history'
                elif sub_bucket == 'MARRIAGE_DETAILS':
                    row['Little Bucket'] = 'Marriage details'
                elif sub_bucket == 'ADDITIONAL_INFORMATION':
                    row['Little Bucket'] = 'Additional information'
                elif sub_bucket == 'KEY_DETAILS':
                    row['Little Bucket'] = 'Key details'
                elif sub_bucket == 'EXISTING_COURT_ORDERS':
                    row['Little Bucket'] = 'Existing court orders'
                else:
                    row['Little Bucket'] = self.infer_little_bucket_from_data_point(data_point, row.get('Big Bucket', ''))
            else:
                row['Little Bucket'] = self.infer_little_bucket_from_data_point(data_point, row.get('Big Bucket', ''))
        
        # Fill Description if empty
        if not row.get('Description', '').strip():
            if schema_field and schema_field.get('flare_displayName'):
                # Use schema display name as basis for description
                display_name = schema_field.get('flare_displayName')
                if not display_name.endswith('?'):
                    row['Description'] = f"What is your {display_name.lower()}?"
                else:
                    row['Description'] = display_name
            else:
                row['Description'] = self.generate_description_from_data_point(data_point, row.get('Description', ''))
        
        # Fill Client facing label if empty
        if not row.get('Client facing label', '').strip():
            if schema_field and schema_field.get('flare_displayName'):
                row['Client facing label'] = schema_field.get('flare_displayName')
            else:
                row['Client facing label'] = self.generate_client_facing_label(data_point, row.get('Client facing label', ''))
        
        # Fill Placeholder text if empty
        if not row.get('Placeholder text', '').strip():
            ui_component = row.get('UI Component (schema type)', '')
            row['Placeholder text'] = self.generate_placeholder_text(data_point, ui_component)
        
        # Fill Hint text if empty (use schema helper text if available)
        if not row.get('Hint text', '').strip() and schema_field:
            helper_text = schema_field.get('flare_clientHelperText', '')
            if helper_text:
                row['Hint text'] = helper_text
        
        # Fill Attorney facing label if empty
        if not row.get('Attorney facing label', '').strip():
            if schema_field and schema_field.get('flare_attorneyDisplay'):
                row['Attorney facing label'] = schema_field.get('flare_attorneyDisplay')
            else:
                row['Attorney facing label'] = self.generate_attorney_facing_label(
                    data_point, 
                    row.get('Client facing label', ''), 
                    row.get('Attorney facing label', '')
                )
        
        return row
    
    def enhance_all_rows(self):
        """Enhance all rows in the CA data"""
        print("Enhancing all rows with missing field data...")
        
        enhanced_count = 0
        for i, row in enumerate(self.ca_data):
            enhanced_row = self.enhance_row(row)
            self.ca_data[i] = enhanced_row
            enhanced_count += 1
        
        print(f"Enhanced {enhanced_count} rows")
    
    def save_enhanced_csv(self, output_path: str):
        """Save the fully enhanced CSV"""
        if not self.ca_data:
            print("No data to save")
            return
        
        fieldnames = list(self.ca_data[0].keys())
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.ca_data)
        
        print(f"Fully enhanced CSV saved to: {output_path}")

def main():
    # File paths
    enhanced_ca_path = '/Users/dannysivan/dannys-scripts/inputs/CA-data-points-enhanced.csv'
    docoloco_schema_path = '/Users/dannysivan/dannys-scripts/inputs/docoloco-schema.json'
    output_path = '/Users/dannysivan/dannys-scripts/inputs/CA-data-points-fully-enhanced.csv'
    
    # Initialize enhancer
    enhancer = CAFieldEnhancer()
    
    # Load data
    print("Loading data sources...")
    enhancer.load_ca_enhanced_csv(enhanced_ca_path)
    enhancer.load_docoloco_schema(docoloco_schema_path)
    
    # Enhance all fields
    enhancer.enhance_all_rows()
    
    # Save enhanced CSV
    enhancer.save_enhanced_csv(output_path)
    
    print("Field enhancement completed successfully!")

if __name__ == "__main__":
    main()



