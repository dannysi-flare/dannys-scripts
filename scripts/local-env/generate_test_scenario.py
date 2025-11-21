#!/usr/bin/env python3
"""
Script to create a test scenario with an attorney, customer, case, and service
similar to Vinny's generateUsers.ts script.

This script creates the minimal entities needed for testing:
1. Practice Area (if doesn't exist)
2. Paralegal User
3. Attorney User (with paralegal in legal team)
4. Customer User
5. Case (linked to customer)
6. Service Type
7. Service (ties everything together)
"""

import argparse
import json
import logging
import os
import sys
import threading
import time
import uuid
from typing import Any, Dict

import requests
from kafka import KafkaConsumer
from pymongo import MongoClient

# Configure logging to show info messages
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration - Use individual services directly since api-gateway
# might not be running
USERS_MS_URL = "http://localhost:4003"
SERVICES_MS_URL = "http://localhost:4001"
CATALOG_MS_URL = "http://localhost:4021"
AUTH_MS_URL = "http://localhost:4006"

# MongoDB connection - using Docker container settings
MONGO_URI = (
    "mongodb://marble-dev-user:marblerulez42@localhost:27018/"
    "services?authSource=admin"
)

# Kafka connection
KAFKA_BROKERS = ["localhost:9092"]

# Override Docker hostnames for localhost development
os.environ["MONGO_HOST_NAME"] = "localhost"
os.environ["KAFKA_HOST"] = "localhost"

# API Token (from vinny e2e tests)
API_TOKEN = "264c1762-ff4c-464d-8bb2-ba34ba5ea654"


class TestScenarioGenerator:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'x-api-key': API_TOKEN,
            'Content-Type': 'application/json'
        })
        self.mongo_client = None
        self.kafka_messages = []
        self.kafka_consumer = None
        self.kafka_thread = None

    def setup_kafka_listener(self):
        """Setup Kafka consumer to monitor service events"""
        self.kafka_events = []
        try:
            # Create consumer for key topics
            self.kafka_consumer = KafkaConsumer(
                'services',
                'users', 
                'vinny-cases',
                'services-events',
                bootstrap_servers=['localhost:9092'],
                value_deserializer=lambda x: json.loads(x.decode('utf-8')),
                consumer_timeout_ms=2000,  # 2 second timeout
                auto_offset_reset='latest'  # Only new messages
            )
            
            # Start consumer in background thread
            self.kafka_thread = threading.Thread(
                target=self._consume_kafka_events, 
                daemon=True
            )
            self.kafka_thread.start()
            logger.info(
                "✅ Kafka listener started for topics: "
                "services, users, vinny-cases, services-events"
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to setup Kafka listener: {e}")
            logger.info("Continuing without Kafka monitoring...")
            self.kafka_consumer = None
            return False

    def _consume_kafka_events(self):
        """Background thread to consume Kafka events"""
        if not self.kafka_consumer:
            return
            
        try:
            for message in self.kafka_consumer:
                event_data = {
                    'topic': message.topic,
                    'timestamp': time.time(),
                    'value': message.value
                }
                self.kafka_events.append(event_data)
                logger.info(
                    f"📨 Kafka event from {message.topic}: {message.value}"
                )
                
        except Exception as e:
            logger.error(f"Kafka consumer error: {e}")

    def analyze_kafka_events(self, entities: Dict[str, Any]):
        """Analyze collected Kafka events for our created entities"""
        if not self.kafka_events:
            print("❌ No Kafka events captured")
            return
            
        print("\n🔍 KAFKA EVENTS ANALYSIS")
        print("========================")
        print(f"Total events captured: {len(self.kafka_events)}")
        
        # Group events by topic
        by_topic = {}
        for event in self.kafka_events:
            topic = event['topic']
            if topic not in by_topic:
                by_topic[topic] = []
            by_topic[topic].append(event)
        
        # Analyze each topic
        for topic, events in by_topic.items():
            print(f"\n📋 Topic: {topic} ({len(events)} events)")
            
            # Look for our specific entity IDs in the events
            for event in events:
                value = event['value']
                
                # Check for user events
                user_ids = [
                    entities['customer']['id'],
                    entities['attorney']['id'],
                    entities['paralegal']['id']
                ]
                if any(uid in str(value) for uid in user_ids):
                    print(f"  ✅ User event found: {value}")
                
                # Check for case events  
                if entities['case']['id'] in str(value):
                    print(f"  ✅ Case event found: {value}")
                
                # Check for service events
                service_ids = [
                    entities['service']['id'],
                    entities['service_type']['id']
                ]
                if any(sid in str(value) for sid in service_ids):
                    print(f"  ✅ Service event found: {value}")

    def connect_mongo(self):
        """Connect to MongoDB"""
        try:
            # Use direct localhost connection without replica set config
            mongo_uri = (
                "mongodb://marble-dev-user:marblerulez42@localhost:27018/"
                "services?authSource=admin&directConnection=true"
            )
            self.mongo_client = MongoClient(mongo_uri)
            self.mongo_client.admin.command('ping')
        except Exception as e:
            logger.error(f"Could not connect to MongoDB: {e}")
            return False
        return True

    def get_or_create_practice_area(
        self, key: str = "FAMILY"
    ) -> Dict[str, Any]:
        """Get existing practice area or create test one"""
        response = self.session.get(
            f"{SERVICES_MS_URL}/administration/practice-areas/key/{key}"
        )

        if response.status_code == 200:
            return response.json()

        create_data = {"displayName": f"Test {key}", "key": key}

        response = self.session.post(
            f"{SERVICES_MS_URL}/administration/practice-areas",
            json=create_data
        )
        if response.status_code == 201:
            return response.json()
        else:
            raise Exception(f"Failed to create practice area: {response.text}")

    def create_user(
        self, user_data: Dict[str, Any], endpoint: str = "users"
    ) -> Dict[str, Any]:
        """Create a user"""
        response = self.session.post(
            f"{USERS_MS_URL}/{endpoint}", json=user_data
        )
        if response.status_code == 201:
            return response.json()
        else:
            raise Exception(
                f"Failed to create user: {response.status_code} - "
                f"{response.text}"
            )

    def create_paralegal(self) -> Dict[str, Any]:
        """Create a paralegal user"""
        paralegal_data = {
            "name": {
                "first": "Test",
                "middle": "SCRIPT-GENERATED",
                "last": "Paralegal"
            },
            "email": (
                f"paralegal_{int(time.time())}_"
                f"{uuid.uuid4().hex[:6]}@test.com"
            ),
            "roles": ["Paralegal"]
        }

        return self.create_user(paralegal_data)

    def create_attorney(
        self, practice_area_id: str, paralegal_id: str
    ) -> Dict[str, Any]:
        """Create an attorney with legal team"""
        attorney_data = {
            "name": {
                "first": "Test",
                "middle": "SCRIPT-GENERATED",
                "last": "Attorney"
            },
            "email": (
                f"attorney_{int(time.time())+1}_"
                f"{uuid.uuid4().hex[:6]}@test.com"
            ),
            "phone": f"+177{str(int(time.time()))[-6:]}",
            "roles": ["Attorney"],
            "attorneyData": {
                "isActive": True,
                "status": "ACTIVE",
                "attorneyType": "CASE_ATTORNEY",
                "languages": ["ENGLISH"],
                "caseCapacity": 5,
                "practiceAreasIds": [],
                "onboardingStateId": "CA",
                "additionalPhones": [{
                    "number": "+16198421030",
                    "type": "DIALPAD"
                }],
                "legalTeam": {
                    "members": [{
                        "userId": paralegal_id,
                        "role": "CASE_PARALEGAL"
                    }]
                }
            }
        }

        attorney = self.create_user(attorney_data, "attorneys")

        practice_area_data = {
            "practiceAreaId": practice_area_id,
            "servicePreferences": [],
            "serviceExpertises": [],
            "locations": [],
            "performsLSS": True,
            "handlesCases": True
        }

        pa_response = self.session.post(
            f"{USERS_MS_URL}/attorneys/{attorney['id']}/practice-areas",
            json=practice_area_data
        )
        if pa_response.status_code != 201:
            logger.error(
                f"Failed to add practice area: {pa_response.text}"
            )

        return attorney

    def create_customer(self) -> Dict[str, Any]:
        """Create a customer"""
        customer_data = {
            "name": {
                "first": "Test",
                "middle": "SCRIPT-GENERATED",
                "last": "Customer"
            },
            "email": (
                f"customer_{int(time.time())+2}_"
                f"{uuid.uuid4().hex[:6]}@test.com"
            ),
            "phone": f"+178{str(int(time.time()))[-6:]}",
            "roles": ["Customer"],
            "customerData": {
                "consentForCreditCheck": False
            }
        }

        return self.create_user(customer_data, "customers")

    def create_case(
        self, user_id: str, practice_area_id: str
    ) -> Dict[str, Any]:
        """Create a case"""
        case_data = {
            "userId": user_id,
            "practiceAreaId": practice_area_id,
            "status": "accepted",
            "additionalFields": {}
        }

        response = self.session.post(
            f"{SERVICES_MS_URL}/cases", json=case_data
        )
        if response.status_code == 201:
            return response.json()
        else:
            raise Exception(f"Failed to create case: {response.text}")

    def create_service_type(self, practice_area_id: str) -> Dict[str, Any]:
        """Create service type in BOTH services-ms and catalog-ms"""
        service_name = f"Test Service Type {uuid.uuid4().hex[:8]}"
        
        # Step 1: Create in services-ms (like e2e does)
        services_ms_data = {
            "name": service_name,
            "description": "Test service type for script",
            "practiceAreaId": practice_area_id,
            "stateIds": [{"id": "1"}],
            "isActive": True,
            "isAddendumOnly": False
        }
        
        print("📝 Creating service type in services-ms...")
        response = self.session.post(
            f"{SERVICES_MS_URL}/service-types", json=services_ms_data
        )
        
        if response.status_code != 201:
            raise Exception(
                f"Failed to create in services-ms: {response.text}"
            )
            
        service_type = response.json()
        print(f"✅ Created in services-ms: {service_type['id']}")
        
        # Step 2: Create in catalog-ms using the SAME ID (like e2e does)
        catalog_data = {
            "serviceTypeName": service_type["name"],
            "serviceTypeId": service_type["id"],  # Same ID!
            "modifierId": "68f93769ca08c441c393c6f3",
            "serviceCode": f"E2E_{uuid.uuid4().hex[:6].upper()}",
            "metadata": {
                "status": "ACTIVE"
            },
            "content": {
                "practiceAreaId": practice_area_id,
                "firm": "Marble",
                "category": service_type.get("description", "Test Category"),
                "description": {
                    "legalDescription": service_type.get(
                        "description", "Test service"
                    ),
                },
                "isAddendumProduct": False
            }
        }
        
        print("📝 Creating service type in catalog-ms...")
        catalog_response = self.session.post(
            f"{CATALOG_MS_URL}/catalog/services", json=catalog_data
        )
        
        if catalog_response.status_code == 201:
            print(f"✅ Created in catalog-ms: {service_type['id']}")
        else:
            print(
                f"⚠️  Catalog-ms creation failed: "
                f"{catalog_response.status_code} - {catalog_response.text}"
            )
            print("   Continuing with services-ms service type only...")
        
        return service_type

    def create_service(
        self,
        service_type_id: str,
        practice_area_id: str,
        case_id: str,
        user_id: str,
        attorney_id: str
    ) -> Dict[str, Any]:
        """Create a service"""
        service_data = {
            "name": "Test Service - Script Generated",
            "caseId": case_id,
            "userId": user_id,
            "serviceTypeId": service_type_id,
            "practiceAreaId": practice_area_id,
            "status": "pending",
            "location": {
                "state": "California",
                "county": "CA"
            },
            "legalTeam": [
                {
                    "userId": user_id,
                    "role": "CASE_MANAGER"
                },
                {
                    "userId": attorney_id,
                    "role": "RESPONSIBLE_ATTORNEY"
                }
            ],
            "opposingParty": {
                "firstName": "Test",
                "lastName": "Opposition"
            }
        }

        print(
            f"🔍 Creating service with data: "
            f"{json.dumps(service_data, indent=2)}"
        )
        response = self.session.post(
            f"{SERVICES_MS_URL}/services", json=service_data
        )
        print(
            f"🔍 Service creation response: "
            f"{response.status_code} - {response.text}"
        )
        if response.status_code == 201:
            return response.json()
        else:
            raise Exception(f"Failed to create service: {response.text}")

    def verify_mongo_data(self, entities: Dict[str, Any]):
        """Verify entities exist in MongoDB"""
        if not self.mongo_client:
            return

        db = self.mongo_client['services']

        user_ids = [
            entities['paralegal']['id'],
            entities['attorney']['id'],
            entities['customer']['id']
        ]
        users_count = db.users.count_documents({"_id": {"$in": user_ids}})
        cases_count = db.cases.count_documents(
            {"_id": entities['case']['id']}
        )
        services_count = db.services.count_documents(
            {"_id": entities['service']['id']}
        )

        if users_count != 3:
            logger.error(f"Expected 3 users, found {users_count}")
        if cases_count != 1:
            logger.error(f"Expected 1 case, found {cases_count}")
        if services_count != 1:
            logger.error(f"Expected 1 service, found {services_count}")

    def run(self, practice_area_key: str = "FAMILY"):
        """Run the complete test scenario generation"""
        self.setup_kafka_listener()
        self.connect_mongo()
        time.sleep(2)

        try:
            practice_area = self.get_or_create_practice_area(practice_area_key)
            paralegal = self.create_paralegal()
            attorney = self.create_attorney(
                practice_area['id'], paralegal['id']
            )
            customer = self.create_customer()
            case = self.create_case(customer['id'], practice_area['id'])
            print(f"✅ Case created: {case['id']}")
            
            service_type = self.create_service_type(practice_area['id'])
            print(
                f"✅ Service type created: "
                f"{service_type['id']} - {service_type['name']}"
            )
            
            # Try service creation (customer as service owner to match case)
            print("📝 Creating service...")
            try:
                service = self.create_service(
                    service_type['id'],
                    practice_area['id'],
                    case['id'],
                    customer['id'],  # Customer as service owner (matches case)
                    attorney['id']
                )
                print(f"✅ Service created: {service['id']}")
            except Exception as e:
                print(f"❌ Service creation failed: {e}")
                service = {"id": "failed", "name": "Service creation failed"}

            entities = {
                'practice_area': practice_area,
                'paralegal': paralegal,
                'attorney': attorney,
                'customer': customer,
                'case': case,
                'service_type': service_type,
                'service': service
            }

            self.print_summary(entities)
            
            # Wait a bit for Kafka events to be captured
            print("\n⏳ Waiting for Kafka events to be captured...")
            time.sleep(5)
            
            # Analyze Kafka events
            self.analyze_kafka_events(entities)
            
            # Verify MongoDB data
            self.verify_mongo_data(entities)

            return entities

        except Exception as e:
            logger.error(f"Error: {e}")
            sys.exit(1)

    def print_summary(self, entities: Dict[str, Any]):
        """Print summary of created entities"""
        summary_lines = [
            "=" * 50,
            "TEST SCENARIO CREATED SUCCESSFULLY",
            "=" * 50,
            "",
            "Summary:",
            (
                f"Practice Area: {entities['practice_area']['id']} "
                f"({entities['practice_area']['displayName']})"
            ),
            (
                f"Paralegal:     {entities['paralegal']['id']} "
                f"({entities['paralegal']['email']})"
            ),
            (
                f"Attorney:      {entities['attorney']['id']} "
                f"({entities['attorney']['email']})"
            ),
            (
                f"Customer:      {entities['customer']['id']} "
                f"({entities['customer']['email']})"
            ),
            f"Case:          {entities['case']['id']}",
            (
                f"Service Type:  {entities['service_type']['id']} "
                f"({entities['service_type']['name']})"
            ),
            (
                f"Service:       {entities['service']['id']} "
                f"({entities['service']['name']})"
            ),
            "=" * 50
        ]
        print("\n".join(summary_lines))


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Generate test scenario with attorney, customer, case, and service"
        )
    )
    parser.add_argument(
        "--practice-area",
        "-pa",
        default="FAMILY",
        help="Practice area key to use (default: FAMILY)"
    )

    args = parser.parse_args()

    generator = TestScenarioGenerator()
    generator.run(args.practice_area)


if __name__ == "__main__":
    main()
