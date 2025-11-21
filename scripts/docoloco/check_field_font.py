#!/usr/bin/env python3

import sys
from PyPDF2 import PdfReader

def check_field_font(pdf_path, field_name):
    try:
        reader = PdfReader(pdf_path)
        
        if '/AcroForm' not in reader.trailer['/Root']:
            print("No AcroForm found in PDF")
            return
        
        acro_form = reader.trailer['/Root']['/AcroForm']
        
        if '/Fields' not in acro_form:
            print("No fields found in AcroForm")
            return
        
        fields = acro_form['/Fields']
        
        def find_field(fields, target_name):
            for field_ref in fields:
                field = field_ref.get_object()
                
                if '/T' in field:
                    name = field['/T']
                    
                    if name == target_name:
                        return field
                
                if '/Kids' in field:
                    result = find_field(field['/Kids'], target_name)
                    if result:
                        return result
            
            return None
        
        field = find_field(fields, field_name)
        
        if not field:
            print(f"Field '{field_name}' not found")
            print("\nAvailable fields:")
            
            def list_fields(fields, indent=0):
                for field_ref in fields:
                    field = field_ref.get_object()
                    if '/T' in field:
                        print("  " * indent + field['/T'])
                    if '/Kids' in field:
                        list_fields(field['/Kids'], indent + 1)
            
            list_fields(fields)
            return
        
        print(f"Field found: {field_name}")
        print(f"\nField properties:")
        
        if '/DA' in field:
            da = field['/DA']
            print(f"  Default Appearance (DA): {da}")
            
            if 'Tf' in da:
                parts = da.split()
                for i, part in enumerate(parts):
                    if part == 'Tf' and i > 0:
                        font_size = parts[i-1]
                        font_name = parts[i-2] if i > 1 else 'unknown'
                        print(f"  Font: {font_name}")
                        print(f"  Font Size: {font_size}")
            else:
                print("  WARNING: No 'Tf' (font) operator found in DA string!")
        else:
            print("  No DA (Default Appearance) field")
        
        if '/V' in field:
            print(f"  Value: {field['/V']}")
        
        if '/Ff' in field:
            print(f"  Field Flags: {field['/Ff']}")
        
        if '/AP' in field:
            print(f"  Has Appearance Stream: Yes")
        else:
            print(f"  Has Appearance Stream: No")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python check_field_font.py <pdf_path> <field_name>")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    field_name = sys.argv[2]
    
    check_field_font(pdf_path, field_name)

