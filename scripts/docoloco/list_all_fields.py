#!/usr/bin/env python3

import sys
from PyPDF2 import PdfReader

def list_all_fields(pdf_path):
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
        
        def list_fields(fields, indent=0):
            for field_ref in fields:
                field = field_ref.get_object()
                if '/T' in field:
                    field_name = field['/T']
                    da = field.get('/DA', 'No DA')
                    value = field.get('/V', 'No value')
                    print("  " * indent + f"{field_name} | DA: {da} | Value: {value}")
                if '/Kids' in field:
                    list_fields(field['/Kids'], indent + 1)
        
        print("All fields in PDF:\n")
        list_fields(fields)
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python list_all_fields.py <pdf_path>")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    list_all_fields(pdf_path)

