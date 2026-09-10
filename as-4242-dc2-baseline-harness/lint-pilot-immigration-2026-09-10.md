# Form-text lint — data schema `66dee37286565b000812bb21`

- forms: 5
- forms carrying presentation `flare_*` inline: 5
- properties with cross-form value disagreements: 17

## Per form

| form | displayName | attorneyDisplay | clientHelperText | guidance | validationMessage | format | beneficiaryDisplay | beneficiaryHelperText | hidden | subBucket | bucket | countKey | questionnaire |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `IMM-AOS` | 501 | 501 | 88 |  | 91 | 43 | 291 |  |  | 501 | 511 |  | 298 |
| `IMM-I-130` | 367 | 367 | 69 |  | 87 | 27 | 185 | 32 |  | 364 | 374 |  | 189 |
| `mini-q:beneficiary-aos` | 291 | 291 | 40 |  | 51 | 4 | 291 |  |  | 298 | 298 |  | 298 |
| `mini-q:IMM-I-130-beneficiary` | 156 | 156 | 27 |  | 47 | 3 | 156 | 1 |  | 160 | 160 |  | 160 |
| `IMM-I-90` | 119 | 119 | 25 |  | 18 | 15 |  |  |  | 107 | 119 |  |  |

## Disagreements

- **attorneyUscisNumber / flare_attorneyDisplay**
  - `"Attorney USCIS"` — IMM-I-90
  - `"Attorney USCIS Number"` — IMM-AOS, IMM-I-130
- **beneficiaryEmployment[].type / flare_displayName**
  - `"Details for how the beneficiary spent the beneficiary's time for the last 5 years, including: Employment, Self-employme` — IMM-AOS, mini-q:IMM-I-130-beneficiary, mini-q:beneficiary-aos
  - `"Details for how you spent your time for the last 5 years, including: Employment, Self-employment, Education History, Un` — IMM-I-130
- **beneficiaryEverImmigrationCity / flare_displayName**
  - `"In what city:"` — IMM-AOS, mini-q:IMM-I-130-beneficiary, mini-q:beneficiary-aos
  - `"If yes, in what city:"` — IMM-I-130
- **beneficiaryEverImmigrationDate / flare_displayName**
  - `"When:"` — IMM-AOS, mini-q:IMM-I-130-beneficiary, mini-q:beneficiary-aos
  - `"If yes, when:"` — IMM-I-130
- **beneficiaryEverImmigrationState / flare_displayName**
  - `"In what state:"` — IMM-AOS, mini-q:IMM-I-130-beneficiary, mini-q:beneficiary-aos
  - `"If yes, in what state:"` — IMM-I-130
- **beneficiaryHasAlienRegistration / flare_displayName**
  - `"Does the beneficiary have an Alien registration number (also called a-number)?"` — IMM-AOS, mini-q:IMM-I-130-beneficiary, mini-q:beneficiary-aos
  - `"Do you have an Alien registration number (also called a-number)?"` — IMM-I-130
- **beneficiaryOtherNameQuestion / flare_beneficiaryHelperText**
  - `"Including maiden names, aliases, or name changes"` — IMM-I-130
  - `"Including your maiden names, aliases, or name changes"` — mini-q:IMM-I-130-beneficiary
- **beneficiarySocialSecurityQuestion / flare_displayName**
  - `"Has the Social Security Administration (SSA) ever officially issued a Social Security Card to the beneficiary?"` — IMM-AOS, mini-q:IMM-I-130-beneficiary, mini-q:beneficiary-aos
  - `"Has the Social Security Administration (SSA) ever officially issued a Social Security Card to you?"` — IMM-I-130
- **petitionerMarriage[].date / flare_attorneyDisplay**
  - `"Date marriage ended"` — IMM-AOS
  - `"Date marriage ended - blank if current marriage"` — IMM-I-130
- **petitionerMarriage[].firstName / flare_attorneyDisplay**
  - `"Petitioner's previous spouse's first name"` — IMM-AOS
  - `"Petitioner's spouse's first name"` — IMM-I-130
- **petitionerMarriage[].firstName / flare_displayName**
  - `"Previous spouse's first name"` — IMM-AOS
  - `"Spouse's first name"` — IMM-I-130
- **petitionerMarriage[].lastName / flare_attorneyDisplay**
  - `"Petitioner's previous spouse's last name"` — IMM-AOS
  - `"Petitioner's spouse's last name"` — IMM-I-130
- **petitionerMarriage[].lastName / flare_displayName**
  - `"Previous spouse's last name"` — IMM-AOS
  - `"Spouse's last name"` — IMM-I-130
- **petitionerMarriage[].middleName / flare_attorneyDisplay**
  - `"Petitioner's previous spouse's middle name"` — IMM-AOS
  - `"Petitioner's spouse's middle name"` — IMM-I-130
- **petitionerMarriage[].middleName / flare_displayName**
  - `"Previous spouse's middle name"` — IMM-AOS
  - `"Spouse's middle name"` — IMM-I-130
- **petitionerNumberMarried / flare_attorneyDisplay**
  - `"Number of times petitioner has been married"` — IMM-AOS
  - `"Number of times petitioner has been married, including current marriage"` — IMM-I-130
- **petitionerNumberMarried / flare_displayName**
  - `"How many times has the petitioner been married?"` — IMM-AOS
  - `"How many times have you been married, including your current marriage?"` — IMM-I-130
