# Clerk GraphQL Gateway Test Environment Setup

This script automates the setup of a local Vinny environment specifically for testing the Clerk GraphQL Gateway, including the newly added Case Update Catalog operations.

## What it does

1. **🐳 Checks Docker Services** - Verifies MongoDB, Redis, and Kafka are running
2. **🚀 Starts Services** - Automatically starts Docker services if they're not running
3. **👤 Creates Admin User** - Creates a test admin user with proper permissions
4. **🔐 Gets Bearer Token** - Generates a JWT Bearer token for the admin user via auth-ms
5. **🔍 Tests GraphQL** - Validates the Clerk GraphQL Gateway and Case Update Templates using Bearer token authentication

## Prerequisites

### Required Services

The script needs these Vinny microservices running locally:

- `users-ms` (port 4003)
- `auth-ms` (port 4006)
- `clerk-graphql-gateway-ms` (port 4027)

### Starting Microservices

```bash
# In your Vinny project directory
cd /Users/dannysivan/src/vinny

# Stop these services in Docker (so you can run them locally)
yarn dc stop users-ms auth-ms clerk-graphql-gateway-ms

# Start them in watch mode
yarn watch -F=users-ms -F=auth-ms -F=clerk-graphql-gateway-ms
```

### Docker Infrastructure

The script can automatically start these if needed:
- MongoDB
- Redis
- Kafka
- Zookeeper

## Installation

```bash
# Make sure you're in the dannys-scripts directory
cd /Users/dannysivan/dannys-scripts

# Install dependencies (if not already installed)
pip install -r requirements.txt
```

## Usage

### Basic Usage

```bash
# Run the full setup (checks/starts Docker, creates user, tests GraphQL)
python scripts/local-env/setup_clerk_test_env.py
```

### Skip Docker Check

If you know Docker services are already running:

```bash
python scripts/local-env/setup_clerk_test_env.py --skip-docker
```

### Help

```bash
python scripts/local-env/setup_clerk_test_env.py --help
```

## Sample Output

```
============================================================
🚀 CLERK GRAPHQL GATEWAY TEST ENVIRONMENT SETUP
============================================================
🐳 Checking Docker services...
✅ All required Docker services are running: mongodb, redis, kafka

🔍 Checking microservices...
✅ users-ms is running
✅ auth-ms is running
✅ clerk-graphql-gateway-ms is running

👤 Creating admin user...
✅ Created admin user: 68f9386811a1ce3e261d1b0e
   Email: admin_1729459304_e8f1a2@test.com
   Note: No password set - using API token for authentication

🔐 Getting Bearer token...
✅ Bearer token generated successfully
   Token: eyJhbGciOiJIUzUxMiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjY5M...

🔍 Testing Clerk GraphQL Gateway...
   Using Bearer token for authentication

📊 Test 1: GraphQL Schema Introspection
✅ Case Update Template operations found in schema:
   Query: getCaseUpdateTemplates
   Query: getCaseUpdateTemplate
   Query: listCaseUpdateTemplates
   Mutation: createCaseUpdateTemplate
   Mutation: updateCaseUpdateTemplate

📊 Test 2: Query Case Update Templates
✅ Successfully queried case update templates
   Found 5 templates

   Sample template:
   - ID: 68f9376cca08c441c393c6f1
   - Name: Case Accepted Template
   - Usage: milestones

============================================================
🎉 SETUP AND TESTS COMPLETED SUCCESSFULLY
============================================================

📝 Admin User Details:
   User ID: 68f9386811a1ce3e261d1b0e
   Email: admin_1729459304_e8f1a2@test.com
   Name: Test Admin
   Roles: Admin

🔑 Bearer Token (copy and use for GraphQL requests):
   eyJhbGciOiJIUzUxMiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjY5MjBmNjhkMWU3OGRkYjVmNjc5MzQ5MCIsIm1hcmJsZUlkIjoiNjkyMGY2OGQxZTc4ZGRiNWY2NzkzNDkwIiwic2Vzc2lvblR5cGUiOiJUT0tFTiIsIm9yaWdpbmF0b3IiOiJ2aW5ueSIsInNlc3Npb25JZCI6IjMzYjIwYzE1LTkzN2YtNGExMi05NmE2LTVmM2E0N2VkNTdkZCIsImlhdCI6MTc2Mzc2Nzk0OSwiZXhwIjoxNzY0OTc3NTQ5fQ.tTfjTPsPVa32wsp4D7PIODRMOfPIkOCh_URSnTj9vDphftG4vBK9KxL4lqTo6EjbdfNd9-bNItAGvG07I4t5RQ

🔧 API Token (for service-to-service calls):
   264c1762-ff4c-464d-8bb2-ba34ba5ea654

💡 Usage Example (with Bearer token):
   curl -X POST http://localhost:4027/graphql \
     -H "Authorization: Bearer eyJhbGci..." \
     -H "Content-Type: application/json" \
     -d '{ "query": "query { getCaseUpdateTemplates { id name usage } }" }'

🌐 GraphQL Endpoint: http://localhost:4027/graphql
```

## Testing Case Update Templates

After running the setup script, you can manually test the GraphQL API using tools like:

### Using curl

```bash
# Set your Bearer token from the script output
BEARER_TOKEN="your-bearer-token-from-script"

# Query all templates
curl -X POST http://localhost:4027/graphql \
  -H "Authorization: Bearer $BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "query { getCaseUpdateTemplates { id name text usage validationVariables } }"
  }'

# Query single template by ID
curl -X POST http://localhost:4027/graphql \
  -H "Authorization: Bearer $BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "query { getCaseUpdateTemplate(id: \"template-id-here\") { id name text usage } }"
  }'

# Create new template
curl -X POST http://localhost:4027/graphql \
  -H "Authorization: Bearer $BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "mutation { createCaseUpdateTemplate(input: { name: \"Test Template\", text: \"Hello {{name}}\", validationVariables: [\"name\"], usage: GENERAL }) { id name } }"
  }'
```

### Using GraphQL Playground

1. Open http://localhost:4027/graphql in your browser
2. Add the Authorization header:
   ```
   {
     "Authorization": "Bearer your-bearer-token-from-script"
   }
   ```
3. Run queries like:

```graphql
# Get all templates
query GetAllTemplates {
  getCaseUpdateTemplates {
    id
    name
    text
    usage
    validationVariables
  }
}

# Get single template
query GetTemplate {
  getCaseUpdateTemplate(id: "template-id") {
    id
    name
    text
    usage
    validationVariables
  }
}

# Get paginated list
query ListTemplates {
  listCaseUpdateTemplates(request: { limit: 10, offset: 0 }) {
    results {
      id
      name
      usage
    }
    count
    pagination {
      limit
      offset
    }
  }
}

# Create template
mutation CreateTemplate {
  createCaseUpdateTemplate(
    input: {
      name: "My Template"
      text: "Hello {{variable}}"
      validationVariables: ["variable"]
      usage: GENERAL
    }
  ) {
    id
    name
  }
}

# Update template
mutation UpdateTemplate {
  updateCaseUpdateTemplate(
    id: "template-id"
    input: { name: "Updated Name" }
  ) {
    id
    name
    text
  }
}
```

## GraphQL API Reference

### Queries

- `getCaseUpdateTemplates(filter?: CaseUpdateTemplateFilterDto): [CaseUpdateTemplate!]!`
  - Get all templates, optionally filtered
  - Permissions: ADMIN_READ

- `getCaseUpdateTemplate(id: ID!): CaseUpdateTemplate!`
  - Get single template by ID
  - Permissions: ADMIN_READ

- `listCaseUpdateTemplates(request: CaseUpdateTemplatesListRequest!): CaseUpdateTemplatesList!`
  - Get paginated list with filters
  - Permissions: ADMIN_READ

### Mutations

- `createCaseUpdateTemplate(input: CreateCaseUpdateTemplateInput!): CaseUpdateTemplate!`
  - Create new template
  - Permissions: ADMIN_ALL

- `updateCaseUpdateTemplate(id: ID!, input: UpdateCaseUpdateTemplateInput!): CaseUpdateTemplate!`
  - Update existing template
  - Permissions: ADMIN_ALL

### Types

```graphql
type CaseUpdateTemplate {
  id: ID!
  name: String!
  text: String!
  validationVariables: [String!]!
  usage: CaseUpdateTemplateUsage!
}

enum CaseUpdateTemplateUsage {
  MILESTONES
  GENERAL
}

input CreateCaseUpdateTemplateInput {
  name: String!
  text: String!
  validationVariables: [String!]!
  usage: CaseUpdateTemplateUsage!
}

input UpdateCaseUpdateTemplateInput {
  name: String
  text: String
  validationVariables: [String!]
  usage: CaseUpdateTemplateUsage
}
```

## Troubleshooting

### Docker Services Not Starting

If Docker services fail to start:

```bash
# Manually start Docker services
cd /Users/dannysivan/src/vinny
yarn dc up

# Check status
yarn dc ps
```

### Microservices Not Running

Make sure you've stopped them in Docker first:

```bash
cd /Users/dannysivan/src/vinny
yarn dc stop users-ms auth-ms clerk-graphql-gateway-ms
yarn watch -F=users-ms -F=auth-ms -F=clerk-graphql-gateway-ms
```

### User Creation Fails

- Check that users-ms is running on port 4003
- Verify the admin user was created successfully
- Try creating a new admin user by running the script again
- Make sure role name is capitalized: "Admin" not "admin"

### Bearer Token Generation Fails

- Check that auth-ms is running on port 4006
- Verify the admin user was created successfully with a valid ID
- Check auth-ms logs for errors

### GraphQL Queries Return Errors

- Check that clerk-graphql-gateway-ms is running on port 4027
- Verify you're using the Bearer token (not x-api-key) in the Authorization header
- Make sure the Bearer token hasn't expired (tokens last ~14 days)
- Make sure you have ADMIN permissions (the script creates admin users with Admin role)
- Check that catalog-ms is running (it provides the backend data)

### "No Case Update Template operations found"

This means the GraphQL schema doesn't include the case update template operations. Check:

1. Is the latest code deployed to clerk-graphql-gateway-ms?
2. Did the service restart after code changes?
3. Check the schema.gql file: `apps/clerk-graphql-gateway-ms/src/schema.gql`

## Related Files

- Script: `scripts/local-env/setup_clerk_test_env.py`
- Main Vinny Project: `/Users/dannysivan/src/vinny`
- PR: https://github.com/Marble-rnd/vinny/pull/4991

## Notes

- Admin users created by this script have full permissions (ADMIN_READ, ADMIN_ALL)
- Users are created without passwords
- Bearer tokens are generated using the auth-ms tokenize endpoint
- Bearer tokens expire after approximately 14 days
- Email addresses are unique using timestamp + UUID
- The script can be run multiple times - it creates a new admin user each time
- API token `264c1762-ff4c-464d-8bb2-ba34ba5ea654` is used for service-to-service calls (creating users, tokenizing)
