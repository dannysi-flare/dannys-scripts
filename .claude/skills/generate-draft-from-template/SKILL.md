---
name: generate-draft-from-template
description: Generate a filled PDF eform from a local template file using the documents-ms generateDraftFromTemplate endpoint. Accepts a local PDF file path, fills it with predefined tokens, and saves the output. Use when the user wants to test eform generation, fill a PDF template, or run generateDraftFromTemplate locally.
---

# Generate Draft From Template Skill

Call the local documents-ms `POST /drafts/generateDraftFromTemplate` endpoint with a PDF eform template.

## How to Use

The user provides a **local file path** to a PDF template. The skill:

1. Converts the PDF to base64
2. Looks for a matching JSONata file in the same directory (same name but `.jsonata` extension)
3. Calls `POST http://localhost:4008/drafts/generateDraftFromTemplate` with:
   - `base64Content`: the base64-encoded PDF
   - `base64Jsonata`: the base64-encoded JSONata (if found)
   - `tokens`: the merged token set (see below)
   - `format`: `E_FORM`
   - `options.isSkipEformFlattening`: `true` (keeps fields editable)
4. Decodes the base64 response and saves it to a file next to the original with `_filled` suffix
5. Validates the filled PDF for fields where font size >= field height (descender clipping risk)

## Execution Steps

Run the following Python script via bash, replacing `<PDF_PATH>` with the user's file path:

```bash
python3 -c "
import base64, json, urllib.request, sys, os, glob

pdf_path = '<PDF_PATH>'
output_path = os.path.splitext(pdf_path)[0] + '_filled.pdf'
pdf_dir = os.path.dirname(pdf_path)
pdf_stem = os.path.splitext(os.path.basename(pdf_path))[0]

with open(pdf_path, 'rb') as f:
    base64_content = base64.b64encode(f.read()).decode('utf-8')

# Look for a matching .jsonata file (same name, or strip _fixed suffix, then fallback to glob)
import re as _re
base64_jsonata = None
base_stem = _re.sub(r'_fixed$', '', pdf_stem)
jsonata_candidates = [
    os.path.join(pdf_dir, pdf_stem + '.jsonata'),
    os.path.join(pdf_dir, base_stem + '.jsonata'),
]
# Only add glob fallback if no exact/base match found
for candidate in jsonata_candidates:
    if os.path.isfile(candidate):
        with open(candidate, 'rb') as f:
            base64_jsonata = base64.b64encode(f.read()).decode('utf-8')
        print(f'Found JSONata file: {candidate}')
        break
if not base64_jsonata:
    # Last resort: any .jsonata in the directory (but only if there's exactly one)
    all_jsonata = glob.glob(os.path.join(pdf_dir, '*.jsonata'))
    if len(all_jsonata) == 1:
        with open(all_jsonata[0], 'rb') as f:
            base64_jsonata = base64.b64encode(f.read()).decode('utf-8')
        print(f'Found JSONata file (fallback): {all_jsonata[0]}')
    elif all_jsonata:
        print(f'Warning: Multiple .jsonata files found but none match {pdf_stem}:', all_jsonata)
    else:
        print('Warning: No .jsonata file found in', pdf_dir)

payload = {
    'base64Content': base64_content,
    'tokens': {
        # --- Client / Petitioner identity (FL-105 + I-129F) ---
        'firstName': 'William',
        'lastName': 'Bryant',
        'clientEmail': 'airbornash82@yahoo.com',
        'clientPhone': '+12108332436',
        'clientState': 'TX',
        'clientZip': '90210',
        'addressStreet': '20659 Stone Oak Pkwy',
        'addressAptUnitEtc': 'Apt 112',
        'addressCity': 'San Antonio',
        'caseCounty': 'Bexar',
        'opposingPartyFirstName': 'Maria',
        'opposingPartyLastName': 'Gonzalez',

        # --- Petitioner (I-129F Part 1) ---
        'petitionerFirstName': 'William',
        'petitionerMiddleName': 'Arthur Acosta',
        'petitionerLastName': 'Bryant',
        'petitionerFirstNameOther': 'Bill',
        'petitionerMiddleNameOther': 'A',
        'petitionerLastNameOther': 'Bryant',
        'petitionerOtherNameQuestion': True,
        'petitionerPhone': '+12108332436',
        'petitionerCell': True,
        'petitionerCellNumber': '+12108332436',
        'petitionerEmail': 'airbornash82@yahoo.com',
        'petitionerStateBirth': 'North Carolina',
        'petitionerPlaceBirth': 'Rose Hill',
        'petitionerCountryBirth': 'United States',
        'petitionerCountyResidence': 'Duplin',
        'petitionerMarital': 'Divorced',
        'petitionerDob': '1968-03-15',
        'petitionerSex': 'Male',
        'petitionerSSN': '123-45-6789',
        'petitionerAlienRegistration': 123456789,
        'uscisAccount': 987654321,
        'petitionerCitizenship': 'Naturalization',
        'petitionerNaturalization': True,
        'petitionerCertificate': 'NAT-2005-00123',
        'petitionerIssuancePlace': 'Charlotte, NC',
        'petitionerIssuanceDate': '2005-06-15',

        # Petitioner mailing address
        'petitionerMailingAddress': '20659 Stone Oak Pkwy',
        'petitionerMailingApt': 'Apartment',
        'petitionerMailingAptDetails': '112',
        'petitionerMailingCity': 'San Antonio',
        'petitionerMailingState': 'TX',
        'petitionerMailingZip': '78258',
        'petitionerMailingProvince': 'TX',
        'petitionerMailingPostal': '78258',
        'petitionerMailingCountry': 'United States',
        'petitionerMailingInCareQuestion': True,
        'petitionerMailingInCare': 'Rosa Bryant',
        'petitionerMailingQuestion': True,

        # Petitioner current address (when different from mailing)
        'petitionerCurrentAddress': '1400 Elm Street',
        'petitionerCurrentApt': 'Suite',
        'petitionerCurrentAptDetails': '200',
        'petitionerCurrentCity': 'Dallas',
        'petitionerCurrentState': 'TX',
        'petitionerCurrentZip': '75201',
        'petitionerCurrentProvince': 'TX',
        'petitionerCurrentPostal': '75201',
        'petitionerCurrentCountry': 'United States',
        'petitionerCurrentFrom': '2020-01-15',

        # Petitioner previous addresses
        'petitionerPreviousAddress': [
            {
                'address': '500 Main St',
                'apt': 'Apartment',
                'aptDetails': '3B',
                'city': 'Austin',
                'state': 'TX',
                'zip': '73301',
                'province': 'TX',
                'postal': '73301',
                'country': 'United States',
                'from': '2015-06-01',
                'to': '2019-12-31',
            }
        ],
        'petitionerAddressHistoryQuestion': True,

        # Petitioner employer (current)
        'petitionerEmployerQuestion': True,
        'petitionerEmployerName': 'Acme Technologies Inc',
        'petitionerEmployerAddress': '789 Corporate Blvd',
        'petitionerEmployerApt': 'Floor',
        'petitionerEmployerAptDetails': '5',
        'petitionerEmployerCity': 'San Antonio',
        'petitionerEmployerState': 'TX',
        'petitionerEmployerZip': '78230',
        'petitionerEmployerProvince': 'TX',
        'petitionerEmployerPostalCode': '78230',
        'petitionerEmployerCountry': 'United States',
        'petitionerEmployerOccupation': 'Software Engineer',
        'petitionerEmployerStartDate': '2020-03-01',
        'petitionerEmployerEndDate': '2025-12-31',

        # Petitioner previous employer
        'petitionerEmployer': [
            {
                'name': 'Global Services LLC',
                'address': '321 Business Park Dr',
                'apt': 'Suite',
                'aptDetails': '100',
                'city': 'Austin',
                'state': 'TX',
                'zip': '73344',
                'province': 'TX',
                'postalCode': '73344',
                'country': 'United States',
                'occupation': 'IT Consultant',
                'startDate': '2015-01-15',
                'endDate': '2020-02-28',
            }
        ],

        # Petitioner parents
        'petitionerParent1FamilyName': 'Bryant',
        'petitionerParent1GivenName': 'Robert',
        'petitionerParent1MiddleName': 'James',
        'petitionerParent1Dob': '1940-11-22',
        'petitionerParent1Sex': 'Male',
        'petitionerParent1CountryBirth': 'United States',
        'petitionerParent1CountryResidence': 'United States',
        'petitionerParent1City': 'Wilmington',
        'petitionerParent2FamilyName': 'Bryant',
        'petitionerParent2GivenName': 'Dorothy',
        'petitionerParent2MiddleName': 'Mae',
        'petitionerParent2Dob': '1943-04-10',
        'petitionerParent2Sex': 'Female',
        'petitionerParent2CountryBirth': 'United States',
        'petitionerParent2Country': 'United States',
        'petitionerParent2City': 'Rose Hill',

        # Petitioner marriage history
        'petitionerMarriageQuestion': True,
        'petitionerMarriage': [
            {
                'lastName': 'Reyes',
                'firstName': 'Linda',
                'middleName': 'Marie',
                'date': '2010-09-14',
            }
        ],

        # Petitioner children
        'petitionerChildrenQuestion': True,
        'petitionerChildren': [
            {'age': '12'},
            {'age': '9'},
        ],

        # Petitioner other beneficiary filings
        'petitionerOtherBeneficiaryForm': True,
        'petitionerOtherBeneficiary': [
            {
                'lastName': 'Santos',
                'firstName': 'Ana',
                'middleName': 'Lucia',
                'filingDate': '2018-05-20',
                'filingAction': 'Denied',
                'Number': 'A-087654321',
            }
        ],

        # Petitioner state/country history
        'petitionerStateHistory': [
            {'state': 'TX'},
            {'state': 'NC'},
        ],
        'petitionerCountryHistory': [
            {'country': 'United States'},
            {'country': 'United States'},
        ],

        # Petitioner physical description
        'petitionerHairColor': 'Bald (No hair)',
        'petitionerEyeColor': 'Blue',
        'petitionerWeight': '260',
        'petitionerHeightInches': '9',
        'petitionerHeightFeet': '5',
        'petitionerRace': 'White',
        'petitionerEthnicity': 'Not Hispanic or Latino',

        # Petitioner criminal/restraining
        'petitionerRestraining': False,
        'petitionerGeneralArrest': False,
        'petitionerAssault': False,
        'petitionerHomicide': False,
        'petitionerDrugs': False,
        'petitionerBattered': None,
        'multipleFiler': 'Not applicable, beneficiary is my spouse or I am not a multiple filer',

        # --- FL-105 children ---
        'numberChildren': '2',
        'children': [
            {
                'name': 'Emma Bryant',
                'placeBirth': 'San Antonio, TX',
                'addyDate': '01/2020',
                'address': 'San Antonio, TX',
                'residence': 'William Bryant, 20659 Stone Oak Pkwy, San Antonio TX 78258',
            },
            {
                'name': 'Liam Bryant',
                'placeBirth': 'Austin, TX',
                'addyDate': '06/2018',
                'address': 'San Antonio, TX',
                'residence': 'William Bryant, 20659 Stone Oak Pkwy, San Antonio TX 78258',
            },
        ],

        # FL-105 other case / custody
        'otherCaseChildrenGen': True,
        'othercaseChildDeetsGen': 'Family',
        'otherCaseChildNumberGen': 'FC-2023-4567',
        'otherCaseChildCourtGen': 'Bexar County Family Court, TX',
        'otherCaseChildDateGen': '2023-06-15',
        'otherCaseChildNamesGen': 'Emma Bryant, Liam Bryant',
        'otherCaseChildAffiliationGen': 'Petitioner',
        'otherCaseChildAffiliationDetailsGen': 'Father',
        'otherCaseChildStatusGen': 'Pending',

        # FL-105 DVRO
        'dvroStatus': True,
        'dvroCourt': 'Family',
        'dvroCounty': 'Bexar',
        'dvroState': 'TX',
        'dvroCaseNumber': 'DV-2022-1234',
        'dvroExpire': '2026-12-31',

        # FL-105 other custody claims
        'otherCustody': {'claim': True},
        'othercustody': [
            {
                'name': 'Gloria Gonzalez',
                'address': '800 W Commerce St, San Antonio TX 78207',
                'children': 'Emma Bryant, Liam Bryant',
                'details': 'Claims visitation rights',
            }
        ],

        # --- Beneficiary (I-129F Part 2) ---
        'beneficiaryFirstName': 'Sofia',
        'beneficiaryMiddleName': 'Isabel',
        'beneficiaryLastName': 'Ramirez',
        'beneficiaryFirstNameOther': 'Sofi',
        'beneficiaryMiddleNameOther': 'I',
        'beneficiaryLastNameOther': 'Ramirez-Lopez',
        'beneficiaryOtherNameQuestion': True,
        'beneficiaryDob': '1985-07-22',
        'beneficiarySex': 'Female',
        'beneficiaryMaritalStatus': 'Single',
        'beneficiaryPlaceBirth': 'Bogota',
        'beneficiaryCountryBirth': 'Colombia',
        'beneficiaryCitizenship': 'Colombia',
        'beneficiaryPhone': '+573124567890',

        # Beneficiary mailing address
        'beneficiaryMailingQuestion': True,
        'beneficiaryMailingAddress': 'Calle 85 No 15-40',
        'beneficiaryMailingApt': 'Apartment',
        'beneficiaryMailingAptDetails': '502',
        'beneficiaryMailingCity': 'Bogota',
        'beneficiaryMailingState': '',
        'beneficiaryMailingZip': '',
        'beneficiaryMailingProvince': 'Cundinamarca',
        'beneficiaryMailingPostal': '110221',
        'beneficiaryMailingCountry': 'Colombia',
        'beneficiaryMailingInCareQuestion': True,
        'beneficiaryMailingInCare': 'Carlos Ramirez',

        # Beneficiary current address
        'beneficiaryCurrentAddress': 'Carrera 7 No 72-13',
        'beneficiaryCurrentApt': 'Apartment',
        'beneficiaryCurrentAptDetails': '801',
        'beneficiaryCurrentCity': 'Bogota',
        'beneficiaryCurrentState': '',
        'beneficiaryCurrentZip': '',
        'beneficiaryCurrentProvince': 'Cundinamarca',
        'beneficiaryCurrentPostal': '110231',
        'beneficiaryCurrentCountry': 'Colombia',
        'beneficiaryCurrentFrom': '2019-03-01',
        'beneficiaryAddressHistoryQuestion': True,

        # Beneficiary previous address
        'beneficiaryPreviousAddress': [
            {
                'address': 'Av Jimenez No 4-30',
                'apt': 'Floor',
                'aptDetails': '3',
                'city': 'Medellin',
                'state': '',
                'zip': '',
                'province': 'Antioquia',
                'postal': '050012',
                'country': 'Colombia',
                'from': '2014-08-01',
                'to': '2019-02-28',
            }
        ],

        # Beneficiary employer (current)
        'beneficiaryEmployerQuestion': True,
        'beneficiaryEmployerName': 'Universidad Nacional',
        'beneficiaryEmployerAddress': 'Cra 30 No 45-03',
        'beneficiaryEmployerApt': '',
        'beneficiaryEmployerAptDetails': '',
        'beneficiaryEmployerCity': 'Bogota',
        'beneficiaryEmployerState': '',
        'beneficiaryEmployerZip': '',
        'beneficiaryEmployerProvince': 'Cundinamarca',
        'beneficiaryEmployerPostalCode': '111321',
        'beneficiaryEmployerCountry': 'Colombia',
        'beneficiaryEmployerOccupation': 'Professor',
        'beneficiaryEmployerStartDate': '2019-08-15',
        'beneficiaryEmployerEndDate': '2025-12-31',

        # Beneficiary previous employer
        'beneficiaryEmployer': [
            {
                'name': 'Banco de Colombia',
                'address': 'Calle 50 No 10-20',
                'apt': 'Floor',
                'aptDetails': '8',
                'city': 'Medellin',
                'state': '',
                'zip': '',
                'province': 'Antioquia',
                'postalCode': '050015',
                'country': 'Colombia',
                'occupation': 'Financial Analyst',
                'startDate': '2014-02-01',
                'endDate': '2019-07-31',
            }
        ],

        # Beneficiary parents
        'beneficiaryParent1FamilyName': 'Ramirez',
        'beneficiaryParent1GivenName': 'Carlos',
        'beneficiaryParent1MiddleName': 'Eduardo',
        'beneficiaryParent1Dob': '1958-01-30',
        'beneficiaryParent1Sex': 'Male',
        'beneficiaryParent1CountryBirth': 'Colombia',
        'beneficiaryParent1CountryResidence': 'Colombia',
        'beneficiaryParent1City': 'Bogota',
        'beneficiaryParent2FamilyName': 'Lopez',
        'beneficiaryParent2GivenName': 'Ana',
        'beneficiaryParent2MiddleName': 'Maria',
        'beneficiaryParent2Dob': '1961-09-05',
        'beneficiaryParent2Sex': 'Female',
        'beneficiaryParent2CountryBirth': 'Colombia',
        'beneficiaryParent2Country': 'Colombia',
        'beneficiaryParent2City': 'Cali',

        # Beneficiary marriage history
        'beneficiaryMarriageQuestion': True,
        'beneficiaryMarriage': [
            {
                'lastName': 'Ortiz',
                'firstName': 'Juan',
                'middleName': 'Pablo',
            }
        ],

        # Beneficiary US entry
        'beneficiaryUSQuestion': True,
        'beneficiaryEntry': 'B-2 Tourist',
        'beneficiaryArrival': 'I-94 12345678901',
        'beneficiaryArrivalDate': '2023-11-15',
        'beneficiaryPassport': 'CO1234567',
        'beneficiaryTravelDocument': '',
        'beneficiaryCountryIssuance': 'Colombia',
        'beneficiaryTravelExpiration': '2028-06-30',

        # Beneficiary children
        'beneficiaryChildrenQuestion': True,
        'beneficiaryChildren': [
            {
                'lastName': 'Ramirez',
                'firstName': 'Valentina',
                'middleName': 'Sofia',
                'countryBirth': 'Colombia',
                'dateBirth': '2015-03-12',
                'residenceQuestion': False,
                'streetName': 'Carrera 7 No 72-13',
                'apt': 'Apartment',
                'aptDetails': '801',
                'city': 'Bogota',
                'state': '',
                'province': 'Cundinamarca',
                'zip': '',
                'postalCode': '110231',
            }
        ],

        # Beneficiary intended US address
        'beneficiaryIntendedAddressStreet': '20659 Stone Oak Pkwy',
        'beneficiaryIntendedAddressApt': 'Apartment',
        'beneficiaryIntendedAddressAptDetails': '112',
        'beneficiaryIntendedAddressCity': 'San Antonio',
        'beneficiaryIntendedAddressState': 'TX',
        'beneficiaryIntendedAddressZip': '78258',

        # Beneficiary native name/address
        'beneficiaryNativeFirstName': 'Sofia',
        'beneficiaryNativeMiddleName': 'Isabel',
        'beneficiaryNativeLastName': 'Ramirez Lopez',
        'beneficiaryNativeStreetNumber': 'Carrera 7 No 72-13',
        'beneficiaryNativeApt': 'Apartment',
        'beneficiaryNativeAptDetails': '801',
        'beneficiaryNativeCity': 'Bogota',
        'beneficiaryNativeProvince': 'Cundinamarca',
        'beneficiaryNativePostalCode': '110231',
        'beneficiaryNativeCountry': 'Colombia',

        # Beneficiary relationship / meeting
        'beneficiaryRelated': False,
        'beneficiaryRelatedDegree': '',
        'beneficiaryInPerson': True,
        'beneficiaryInPersonLocation': 'Bogota, Colombia',
        'beneficiaryInPersonDate': '2022-06-10',

        # Beneficiary consular processing
        'beneficiaryConsularCity': 'Bogota',
        'beneficiaryConsularCountry': 'Colombia',

        # --- Marriage broker ---
        'marriageBrokerQuestion': False,
        'marriageBrokerName': '',
        'marriageBrokerFirstName': '',
        'marriageBrokerLastName': '',
        'marriageBrokerOrganization': '',
        'marriageBrokerWebsite': '',
        'marriageBrokerStreet': '',
        'marriageBrokerApt': '',
        'marriageBrokerAptDetails': '',
        'marriageBrokerCity': '',
        'marriageBrokerProvince': '',
        'marriageBrokerCountry': '',
        'marriageBrokerPostalCode': '',
        'marriageBrokerPhone': '',

        # --- Interpreter ---
        'interpreterQuestion': True,
        'interpreterFirstName': 'Marco',
        'interpreterLastName': 'Lucas',
        'interpreterEmail': 'huzyb@mailinator.com',
        'interpreterMobile': '+13054373036',
        'interpreterPhone': '+15225216172',
        'interpreterOrganization': 'Curry and Hickman Co',
    },
    'format': 'E_FORM',
    'options': {
        'isSkipEformFlattening': True,
    },
}

if base64_jsonata:
    payload['base64Jsonata'] = base64_jsonata

data = json.dumps(payload).encode('utf-8')
req = urllib.request.Request(
    'http://localhost:4008/drafts/generateDraftFromTemplate',
    data=data,
    headers={'Content-Type': 'application/json'},
)

try:
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read().decode('utf-8'))
    if 'base64Content' in result:
        content = base64.b64decode(result['base64Content'])
        with open(output_path, 'wb') as f:
            f.write(content)
        print(f'Saved filled PDF to: {output_path} ({len(content)} bytes)')
    else:
        print('Unexpected response:', json.dumps(result, indent=2))
except urllib.error.HTTPError as e:
    print(f'HTTP {e.code}: {e.read().decode()}')
"
```

## Post-Generation Validation

After generating each filled PDF, run this validation script to detect fields where the font size is too large for the field height (causes descender clipping on letters like y, g, p, q, j).

Replace `<OUTPUT_PDF_PATH>` with the path to the filled PDF:

```bash
python3 -c "
import pikepdf, re

pdf_path = '<OUTPUT_PDF_PATH>'
pdf = pikepdf.open(pdf_path)
DESCENDER_RATIO = 1.25  # font needs ~1.25x its size for descenders

import math
warnings = []
for page_num, page in enumerate(pdf.pages):
    if '/Annots' not in page:
        continue
    for annot in page['/Annots']:
        obj = annot.resolve() if hasattr(annot, 'resolve') else annot
        if str(obj.get('/Subtype', '')) != '/Widget':
            continue
        rect = obj.get('/Rect')
        da = str(obj.get('/DA', ''))
        if not rect or not da:
            continue
        coords = [float(x) for x in rect]
        height = round(coords[3] - coords[1], 2)
        m = re.search(r'(\d+(?:\.\d+)?)\s+Tf', da)
        if not m:
            continue
        font_size = float(m.group(1))
        name = str(obj.get('/T', '(unknown)'))
        # For multi-line fields, compute per-line height
        ff = int(obj.get('/Ff', 0))
        is_multiline = bool(ff & (1 << 12))
        if is_multiline:
            num_lines = max(1, round(height / font_size))
            effective_height = height / num_lines
        else:
            num_lines = 1
            effective_height = height
        needed = round(font_size * DESCENDER_RATIO, 2)
        if effective_height < needed:
            deficit = round(needed - effective_height, 2)
            line_info = f', {num_lines} lines, {effective_height:.2f}pt/line' if num_lines > 1 else ''
            warnings.append((name, page_num + 1, font_size, height, needed, deficit, line_info))

if warnings:
    print(f'⚠ Found {len(warnings)} field(s) with potential descender clipping:')
    for name, pg, fs, h, needed, deficit, line_info in warnings:
        print(f'  Page {pg}: {name}')
        print(f'    font={fs}pt, height={h}pt{line_info}, needs≥{needed}pt (short by {deficit}pt)')
else:
    print('✓ All fields have sufficient height for their font size.')
"
```

Report the validation results to the user after each generation run.

## Notes

- Requires documents-ms running locally on port 4008 (`yarn watch -F=documents-ms`)
- `isSkipEformFlattening: true` keeps PDF form fields editable (not flattened)
- The `format` field is set to `E_FORM` but the endpoint auto-detects PDF vs DOCX from magic bytes
- The skill auto-discovers a `.jsonata` file in the same directory: first tries exact name match (`template.pdf` → `template.jsonata`), then falls back to any `*.jsonata` in the directory
- Tokens can be overridden by the user — ask before changing the defaults
