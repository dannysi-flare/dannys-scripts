#!/usr/bin/env python3
"""
Script to setup local Vinny environment for testing Clerk GraphQL Gateway.

This script:
1. Checks if Docker services are running (and starts them if not)
2. Creates an admin user
3. Gets a Bearer token for the admin user via auth-ms tokenize endpoint
4. Tests the Clerk GraphQL gateway with case update templates queries using Bearer token authentication

Usage:
    python scripts/local-env/setup_clerk_test_env.py
    python scripts/local-env/setup_clerk_test_env.py --skip-docker  # Skip docker check
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
import uuid
from typing import Any, Dict, Optional

import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
VINNY_ROOT = "/Users/dannysivan/src/vinny"
USERS_MS_URL = "http://localhost:4003"
AUTH_MS_URL = "http://localhost:4006"
CLERK_GRAPHQL_URL = "http://localhost:4027/graphql"

# API Token for service-to-service calls
API_TOKEN = "264c1762-ff4c-464d-8bb2-ba34ba5ea654"


class ClerkTestEnvSetup:
    def __init__(self, skip_docker: bool = False):
        self.skip_docker = skip_docker
        self.session = requests.Session()
        self.admin_user = None
        self.auth_token = None

    def check_docker_services(self) -> bool:
        """Check if required Docker services are running"""
        logger.info("🐳 Checking Docker services...")

        try:
            result = subprocess.run(
                ["yarn", "dc", "ps"],
                cwd=VINNY_ROOT,
                capture_output=True,
                text=True,
                timeout=10
            )

            # Check if MongoDB, Redis, and Kafka are running
            output = result.stdout
            required_services = ["mongodb", "redis", "kafka"]
            running_services = []

            for service in required_services:
                if service in output.lower() and "up" in output.lower():
                    running_services.append(service)

            if len(running_services) == len(required_services):
                logger.info(f"✅ All required Docker services are running: {', '.join(running_services)}")
                return True
            else:
                missing = set(required_services) - set(running_services)
                logger.warning(f"⚠️  Missing services: {', '.join(missing)}")
                return False

        except subprocess.TimeoutExpired:
            logger.warning("⚠️  Docker check timed out")
            return False
        except Exception as e:
            logger.error(f"❌ Error checking Docker services: {e}")
            return False

    def start_docker_services(self) -> bool:
        """Start Docker services using yarn dc up"""
        logger.info("🚀 Starting Docker services...")

        try:
            # Run yarn dc up in background
            process = subprocess.Popen(
                ["yarn", "dc", "up", "-d"],
                cwd=VINNY_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Wait up to 30 seconds for services to start
            logger.info("⏳ Waiting for services to start (this may take 30+ seconds)...")
            time.sleep(5)

            # Check if services are up
            for i in range(6):  # Try 6 times, 5 seconds apart
                time.sleep(5)
                if self.check_docker_services():
                    logger.info("✅ Docker services started successfully")
                    return True
                logger.info(f"   Still starting... ({(i+1)*5}s)")

            logger.warning("⚠️  Services may still be starting. Continuing anyway...")
            return True

        except Exception as e:
            logger.error(f"❌ Error starting Docker services: {e}")
            return False

    def check_microservices(self) -> Dict[str, bool]:
        """Check which microservices are running"""
        logger.info("\n🔍 Checking microservices...")

        services = {
            "users-ms": USERS_MS_URL,
            "auth-ms": AUTH_MS_URL,
            "clerk-graphql-gateway-ms": CLERK_GRAPHQL_URL,
        }

        status = {}
        for name, url in services.items():
            try:
                # Try base URL first - any response means it's running
                response = requests.get(url, timeout=2)
                # Any HTTP response (even 404) means the service is running
                if response.status_code in [200, 201, 400, 404, 405]:
                    logger.info(f"✅ {name} is running (status: {response.status_code})")
                    status[name] = True
                else:
                    logger.warning(f"⚠️  {name} returned unexpected status {response.status_code}")
                    status[name] = True  # Still consider it running
            except requests.ConnectionError:
                logger.error(f"❌ {name} is NOT running (connection refused)")
                status[name] = False
            except requests.Timeout:
                logger.error(f"❌ {name} is NOT running (timeout)")
                status[name] = False
            except requests.RequestException as e:
                logger.error(f"❌ {name} is NOT running ({str(e)[:50]})")
                status[name] = False

        return status

    def create_admin_user(self) -> Optional[Dict[str, Any]]:
        """Create an admin user for testing"""
        logger.info("\n👤 Creating admin user...")

        # Generate unique email and phone
        timestamp = int(time.time())
        unique_id = str(uuid.uuid4())[:8]

        user_data = {
            "email": f"admin_{timestamp}_{unique_id}@test.com",
            "name": {
                "first": "Test",
                "last": "Admin",
                "middle": "Clerk"
            },
            "roles": ["Admin"],  # Admin role for clerk access (capitalized)
        }

        try:
            response = self.session.post(
                f"{USERS_MS_URL}/users",
                json=user_data,
                headers={
                    'x-api-key': API_TOKEN,
                    'Content-Type': 'application/json'
                },
                timeout=10
            )

            if response.status_code in [200, 201]:
                user = response.json()
                self.admin_user = {**user_data, "id": user.get("id")}
                logger.info(f"✅ Created admin user: {user.get('id')}")
                logger.info(f"   Email: {user_data['email']}")
                logger.info(f"   Note: No password set - using API token for authentication")
                return self.admin_user
            else:
                logger.error(f"❌ Failed to create user: {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return None

        except requests.RequestException as e:
            logger.error(f"❌ Error creating user: {e}")
            return None

    def get_bearer_token(self) -> Optional[str]:
        """Get JWT Bearer token using auth-ms tokenize endpoint"""
        if not self.admin_user:
            logger.error("❌ No admin user available for tokenization")
            return None

        logger.info("\n🔐 Getting Bearer token...")

        # Call auth-ms tokenize endpoint
        tokenize_data = {
            "id": self.admin_user["id"],
            "marbleId": self.admin_user["id"],  # Using same ID for marbleId
            "sessionType": "TOKEN"
        }

        try:
            response = self.session.post(
                f"{AUTH_MS_URL}/auth/tokenize",
                json=tokenize_data,
                headers={
                    'x-api-key': API_TOKEN,
                    'Content-Type': 'application/json'
                },
                timeout=10
            )

            if response.status_code in [200, 201]:
                # The response is just the token string
                self.auth_token = response.text.strip('"')  # Remove quotes if present
                if self.auth_token:
                    logger.info("✅ Bearer token generated successfully")
                    logger.info(f"   Token: {self.auth_token[:50]}...")
                    return self.auth_token
                else:
                    logger.error("❌ No token in response")
                    return None
            else:
                logger.error(f"❌ Token generation failed: {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return None

        except requests.RequestException as e:
            logger.error(f"❌ Error during token generation: {e}")
            return None

    def test_clerk_graphql(self) -> bool:
        """Test the Clerk GraphQL gateway with case update templates queries"""
        if not self.auth_token:
            logger.error("❌ No Bearer token available for GraphQL testing")
            return False

        logger.info("\n🔍 Testing Clerk GraphQL Gateway...")
        logger.info("   Using Bearer token for authentication")

        # Test introspection query to see if case update templates are exposed
        introspection_query = """
        query IntrospectionQuery {
          __schema {
            queryType {
              fields {
                name
                description
              }
            }
            mutationType {
              fields {
                name
                description
              }
            }
          }
        }
        """

        # Test case update templates query
        case_templates_query = """
        query GetCaseUpdateTemplates {
          getCaseUpdateTemplates {
            id
            name
            text
            usage
            validationVariables
          }
        }
        """

        headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json",
        }

        # Test 1: Introspection
        logger.info("\n📊 Test 1: GraphQL Schema Introspection")
        try:
            response = self.session.post(
                CLERK_GRAPHQL_URL,
                json={"query": introspection_query},
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if "data" in data:
                    queries = data["data"]["__schema"]["queryType"]["fields"]
                    mutations = data["data"]["__schema"]["mutationType"]["fields"] if data["data"]["__schema"].get("mutationType") else []

                    # Check for case update template queries
                    template_queries = [q for q in queries if "CaseUpdateTemplate" in q["name"]]
                    template_mutations = [m for m in mutations if "CaseUpdateTemplate" in m["name"]]

                    if template_queries or template_mutations:
                        logger.info("✅ Case Update Template operations found in schema:")
                        for q in template_queries:
                            logger.info(f"   Query: {q['name']}")
                        for m in template_mutations:
                            logger.info(f"   Mutation: {m['name']}")
                    else:
                        logger.warning("⚠️  No Case Update Template operations found in schema")
                else:
                    logger.error(f"❌ GraphQL error: {data.get('errors')}")
            else:
                logger.error(f"❌ Introspection failed: {response.status_code}")
                logger.error(f"   Response: {response.text}")

        except requests.RequestException as e:
            logger.error(f"❌ Error during introspection: {e}")

        # Test 2: Query case update templates
        logger.info("\n📊 Test 2: Query Case Update Templates")
        try:
            response = self.session.post(
                CLERK_GRAPHQL_URL,
                json={"query": case_templates_query},
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if "data" in data and data["data"] is not None and data["data"].get("getCaseUpdateTemplates") is not None:
                    templates = data["data"]["getCaseUpdateTemplates"]
                    logger.info(f"✅ Successfully queried case update templates")
                    logger.info(f"   Found {len(templates)} templates")
                    if templates:
                        logger.info("\n   Sample template:")
                        sample = templates[0]
                        logger.info(f"   - ID: {sample.get('id')}")
                        logger.info(f"   - Name: {sample.get('name')}")
                        logger.info(f"   - Usage: {sample.get('usage')}")
                    return True
                elif "errors" in data:
                    logger.error(f"❌ GraphQL errors: {json.dumps(data['errors'], indent=2)}")
                    return False
                else:
                    logger.warning("⚠️  Empty response from query")
                    logger.warning(f"   Response data: {json.dumps(data, indent=2)}")
                    return False
            else:
                logger.error(f"❌ Query failed: {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False

        except requests.RequestException as e:
            logger.error(f"❌ Error during query: {e}")
            return False

    def run(self) -> bool:
        """Run the complete setup and test flow"""
        logger.info("=" * 60)
        logger.info("🚀 CLERK GRAPHQL GATEWAY TEST ENVIRONMENT SETUP")
        logger.info("=" * 60)

        # Step 1: Docker services
        if not self.skip_docker:
            if not self.check_docker_services():
                logger.info("\n💡 Docker services not running. Starting them...")
                if not self.start_docker_services():
                    logger.error("\n❌ Failed to start Docker services")
                    logger.info("💡 Try running manually: cd /Users/dannysivan/src/vinny && yarn dc up")
                    return False
        else:
            logger.info("⏭️  Skipping Docker check (--skip-docker)")

        # Step 2: Check microservices
        time.sleep(2)  # Give services a moment
        services_status = self.check_microservices()

        if not all([services_status.get("users-ms"), services_status.get("auth-ms")]):
            logger.error("\n❌ Required microservices are not running")
            logger.info("💡 Start them with:")
            logger.info("   cd /Users/dannysivan/src/vinny")
            logger.info("   yarn dc stop users-ms auth-ms clerk-graphql-gateway-ms")
            logger.info("   yarn watch -F=users-ms -F=auth-ms -F=clerk-graphql-gateway-ms")
            return False

        # Step 3: Create admin user
        if not self.create_admin_user():
            logger.error("\n❌ Failed to create admin user")
            return False

        # Step 4: Get Bearer token
        if not self.get_bearer_token():
            logger.error("\n❌ Failed to get Bearer token")
            return False

        # Step 5: Test GraphQL (using Bearer token authentication)
        success = self.test_clerk_graphql()

        # Summary
        logger.info("\n" + "=" * 60)
        if success:
            logger.info("🎉 SETUP AND TESTS COMPLETED SUCCESSFULLY")
            logger.info("=" * 60)
            logger.info("\n📝 Admin User Details:")
            logger.info(f"   User ID: {self.admin_user['id']}")
            logger.info(f"   Email: {self.admin_user['email']}")
            logger.info(f"   Name: {self.admin_user['name']['first']} {self.admin_user['name']['last']}")
            logger.info(f"   Roles: {', '.join(self.admin_user['roles'])}")
            logger.info("\n🔑 Bearer Token (copy and use for GraphQL requests):")
            logger.info(f"   {self.auth_token}")
            logger.info("\n🔧 API Token (for service-to-service calls):")
            logger.info(f"   {API_TOKEN}")
            logger.info("\n💡 Usage Example (with Bearer token):")
            logger.info(f"   curl -X POST {CLERK_GRAPHQL_URL} \\")
            logger.info(f'     -H "Authorization: Bearer {self.auth_token}" \\')
            logger.info(f'     -H "Content-Type: application/json" \\')
            logger.info(f'     -d \'{{ "query": "query {{ getCaseUpdateTemplates {{ id name usage }} }}" }}\'')
            logger.info(f"\n🌐 GraphQL Endpoint: {CLERK_GRAPHQL_URL}")
        else:
            logger.info("⚠️  SETUP COMPLETED WITH ERRORS")
            logger.info("=" * 60)
            # Still print credentials if we have them
            if self.admin_user:
                logger.info("\n📝 Admin User Details (created before error):")
                logger.info(f"   Email: {self.admin_user['email']}")
                logger.info(f"   Roles: {', '.join(self.admin_user['roles'])}")
            if self.auth_token:
                logger.info("\n🔑 Bearer Token:")
                logger.info(f"   {self.auth_token}")
            logger.info("\n🔧 API Token:")
            logger.info(f"   {API_TOKEN}")

        return success


def main():
    parser = argparse.ArgumentParser(
        description="Setup local Vinny environment for testing Clerk GraphQL Gateway"
    )
    parser.add_argument(
        "--skip-docker",
        action="store_true",
        help="Skip Docker services check and startup"
    )

    args = parser.parse_args()

    setup = ClerkTestEnvSetup(skip_docker=args.skip_docker)
    success = setup.run()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
