# Local Vinny Test Scenario Generator

This script generates a complete test scenario in your local Vinny environment, similar to the `generateUsers.ts` script in the Vinny e2e tests.

## What it creates

1. **Practice Area** (FAMILY by default, or creates a new one)
2. **Paralegal User**
3. **Attorney User** (with paralegal in legal team)
4. **Customer User**
5. **Case** (linked to customer and practice area)
6. **Service Type**
7. **Service** (ties everything together) - _Currently skipped due to API issue_

## Features

- ✅ **MongoDB Verification**: Checks that entities were stored in local MongoDB
- ✅ **Kafka Monitoring**: Listens for and displays service-related Kafka messages
- ✅ **Unique Identifiers**: Uses timestamps and UUIDs to avoid conflicts
- ✅ **Detailed Logging**: Shows each step with emojis and status
- ✅ **Error Handling**: Graceful error handling with detailed messages

## Prerequisites

Make sure you have these Vinny services running locally:

- `users-ms` (port 4003)
- `services-ms` (port 4001)
- `catalog-ms` (port 4021)
- MongoDB (with Docker: `yarn dc up`)
- Kafka (with Docker: `yarn dc up`)

You can start the minimal services with:

```bash
# In your Vinny project
yarn dc up  # Start infrastructure
yarn dc stop auth-ms users-ms services-ms catalog-ms events-ms  # Stop the ones you want to run locally
yarn watch -F=auth-ms -F=users-ms -F=services-ms -F=catalog-ms -F=events-ms  # Run locally
```

## Installation

```bash
# Install dependencies
pip install -r requirements.txt
```

## Usage

```bash
# Basic usage (creates FAMILY practice area scenario)
python scripts/local-env/generate_test_scenario.py

# Use different practice area
python scripts/local-env/generate_test_scenario.py --practice-area BUSINESS

# Show help
python scripts/local-env/generate_test_scenario.py --help
```

## Sample Output

```
🚀 Starting test scenario generation...

🎧 Kafka listener started...
✅ Connected to MongoDB
🔍 Looking for practice area: FAMILY
✅ Found practice area: 68f93769ca08c441c393c6f3 (Test FAMILY)
👩‍💼 Creating paralegal...
✅ Created paralegal: 68f9386811a1ce3e261d1b0e (Test Paralegal)
👨‍💼 Creating attorney...
✅ Created attorney: 68f9386811a1ce3e261d1b16 (Test Attorney)
🔗 Adding practice area to attorney...
✅ Added practice area to attorney
👤 Creating customer...
✅ Created customer: 68f9386911a1ce3e261d1b25 (Test Customer)
📋 Creating case...
✅ Created case: 68f93869ca08c441c393c708
🛠️  Creating service type...
✅ Created service type: 68f93869ca08c441c393c70b (Test Service Type 183b919d)

==================================================
🎉 TEST SCENARIO CREATED SUCCESSFULLY
==================================================

📊 Summary:
Practice Area: 68f93769ca08c441c393c6f3 (Test FAMILY)
Paralegal:     68f9386811a1ce3e261d1b0e (paralegal_1729459304_e8f1a2@test.com)
Attorney:      68f9386811a1ce3e261d1b16 (attorney_1729459305_b2c4d6@test.com)
Customer:      68f9386911a1ce3e261d1b25 (customer_1729459306_a7e9f3@test.com)
Case:          68f93869ca08c441c393c708
Service Type:  68f93869ca08c441c393c70b (Test Service Type 183b919d)
Service:       skipped (Service creation skipped)
==================================================

🔍 Verifying data in MongoDB...
✅ Found 3/3 users in MongoDB
✅ Found 1/1 cases in MongoDB
✅ Found 0/1 services in MongoDB

📨 Kafka Messages Received: 0
⚠️  No service-related Kafka messages found
```

## Configuration

The script uses these default configurations:

- **Services URLs**: Direct connection to individual microservices
  - users-ms: http://localhost:4003
  - services-ms: http://localhost:4001
  - catalog-ms: http://localhost:4021
- **MongoDB**: mongodb://marble-dev-user:marblerulez42@localhost:27017/services?authSource=admin
- **Kafka**: localhost:9092

## Troubleshooting

### Connection Issues

- Make sure your Vinny services are running locally (not in Docker)
- Verify ports are correct with `yarn dc ps`
- Check that MongoDB and Kafka containers are running with `yarn dc up`

### Phone Number Validation

- The script uses timestamp-based phone numbers to avoid conflicts
- Phone numbers are validated using libphonenumber-js

### Email Conflicts

- Emails use timestamp + UUID to ensure uniqueness
- If you still get conflicts, wait a second and try again

### Service Creation Issues

- Currently the service creation step is skipped due to an API issue
- This might be resolved by running additional services or using different endpoints

## Files Created

The script creates entities in your local Vinny environment that you can view in:

- **MongoDB**: Collections `users`, `cases`, `services` in the `services` database
- **Vinny UI**: If you have a frontend connected to your local services

## Next Steps

After running this script, you can:

1. View the created entities in your Vinny frontend
2. Use the IDs in other tests or API calls
3. Modify the script to create different scenarios
4. Add additional entity types (documents, events, etc.)
