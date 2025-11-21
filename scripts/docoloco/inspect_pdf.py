#!/usr/bin/env python3

import sys
from PyPDF2 import PdfReader

def inspect_pdf(pdf_path):
    try:
        reader = PdfReader(pdf_path)
        
        print(f"PDF has {len(reader.pages)} pages")
        print(f"\nRoot keys: {list(reader.trailer['/Root'].keys())}")
        
        if '/AcroForm' in reader.trailer['/Root']:
            acro_form = reader.trailer['/Root']['/AcroForm']
            print(f"\nAcroForm keys: {list(acro_form.keys())}")
            print(f"AcroForm dict: {acro_form}")
        else:
            print("\nNo AcroForm found")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python inspect_pdf.py <pdf_path>")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    inspect_pdf(pdf_path)

