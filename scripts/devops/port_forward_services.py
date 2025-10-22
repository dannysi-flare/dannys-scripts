#!/usr/bin/env python3

import argparse
import logging
import os
import signal
import subprocess
import sys
import time
import socket
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

# Set up logging (errors only, following project patterns)
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)


class PortForwardManager:
    def __init__(self):
        self.script_dir = Path(__file__).parent
        self.dannys_scripts_root = self.script_dir.parent.parent
        self.vinny_project_root = Path("/Users/dannysivan/src/vinny")
        self.outputs_dir = self.dannys_scripts_root / "outputs"
        self.pid_file = self.outputs_dir / ".port_forward_pids"
        self.port_mapping_file = self.outputs_dir / ".port_mappings"

        self.environment = "staging"
        self.k8s_namespace = ""
        self.color_prefix = ""
        self.services = []
        self.starting_port = 5000
        self.processes = []

        # Set up signal handlers for cleanup
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle cleanup on script interruption"""
        print("\n🛑 Interrupt received, cleaning up...")
        self.cleanup()
        sys.exit(0)

    def log(self, message: str):
        """Log info message"""
        print(f"📋 [INFO] {message}")

    def error(self, message: str):
        """Log error message"""
        print(f"❌ [ERROR] {message}", file=sys.stderr)
        logger.error(message)

    def warn(self, message: str):
        """Log warning message"""
        print(f"⚠️  [WARNING] {message}", file=sys.stderr)

    def check_prerequisites(self) -> bool:
        """Check if required tools are available"""
        missing_tools = []

        for tool in ['kubectl', 'aws']:
            if not self._command_exists(tool):
                missing_tools.append(tool)

        if missing_tools:
            self.error(f"Missing required tools: {', '.join(missing_tools)}")
            self.error("Please install the missing tools and try again.")
            return False

        return True

    def _command_exists(self, command: str) -> bool:
        """Check if a command exists"""
        try:
            subprocess.run(['which', command], check=True,
                           capture_output=True, text=True)
            return True
        except subprocess.CalledProcessError:
            return False

    def check_aws_sso_login(self) -> bool:
        """Check AWS SSO login status and prompt login if needed"""
        self.log("Checking AWS SSO login status...")

        try:
            # Try to get credentials to check if SSO session is valid
            subprocess.run(['aws', 'sts', 'get-caller-identity'],
                           check=True, capture_output=True, text=True)
            self.log("✓ AWS SSO session is valid")
            return True
        except subprocess.CalledProcessError:
            msg = ("AWS SSO session not found or expired. "
                   "Running 'aws sso login'...")
            self.warn(msg)

            try:
                subprocess.run(['aws', 'sso', 'login'], check=True)
                self.log("✓ AWS SSO login successful")
                return True
            except subprocess.CalledProcessError as e:
                self.error(f"AWS SSO login failed: {e}")
                return False
            except FileNotFoundError:
                msg = "AWS CLI not found. Please install AWS CLI first."
                self.error(msg)
                return False

    def configure_kubectl_context(self) -> bool:
        """Configure kubectl context for the specified environment"""
        if self.environment == "production":
            context = ("danny.s@helloflare.com@marble-production."
                       "us-east-2.eksctl.io")
            self.k8s_namespace = "vinny"
        else:
            context = ("danny.s@helloflare.com@marble-staging."
                       "us-east-2.eksctl.io")
            self.k8s_namespace = "artemis"

        msg = (f"Configuring kubectl context for {self.environment} "
               "environment...")
        self.log(msg)

        try:
            # Set kubectl context
            subprocess.run(['kubectl', 'config', 'use-context', context],
                           check=True, capture_output=True, text=True)

            # Verify connectivity
            subprocess.run(['kubectl', 'get', 'namespaces'],
                           check=True, capture_output=True, text=True)

            self.log(f"✓ Connected to {self.environment} Kubernetes cluster")
            return True
        except subprocess.CalledProcessError:
            self.error(f"Failed to set kubectl context to '{context}' or "
                       "connect to cluster")
            msg = (f"Make sure you have access to the {self.environment} "
                   "environment")
            self.error(msg)
            return False

    def normalize_service_name(self, service: str) -> str:
        """Convert underscores to hyphens in service name"""
        return service.replace('_', '-')

    def service_to_env_var(self, service: str) -> str:
        """Convert service name to environment variable format"""
        # Remove color prefix if present for env var
        clean_service = service
        prefix_check = f"{self.color_prefix}-"
        if self.color_prefix and service.startswith(prefix_check):
            clean_service = service[len(self.color_prefix)+1:]

        # Convert to uppercase and replace hyphens with underscores
        return clean_service.upper().replace('-', '_')

    def validate_service(self, service: str) -> bool:
        """Check if service exists in vinny apps directory"""
        normalized_service = self.normalize_service_name(service)

        # Remove color prefix for validation
        clean_service = normalized_service
        if self.color_prefix:
            clean_service = normalized_service.replace(
                f"{self.color_prefix}-", "", 1)

        service_path = self.vinny_project_root / "apps" / clean_service
        if not service_path.exists():
            self.error(f"Service '{clean_service}' not found in vinny apps "
                       "directory")
            self.error("Available services:")
            try:
                apps_dir = self.vinny_project_root / "apps"
                if apps_dir.exists():
                    for app in sorted(apps_dir.iterdir()):
                        if app.is_dir() and app.name.endswith('-ms'):
                            print(f"  - {app.name}")
            except Exception:
                pass
            return False

        return True

    def find_available_port(self) -> int:
        """Find next available local port"""
        port = self.starting_port

        # Check existing mappings to avoid conflicts
        used_ports = set()
        if self.port_mapping_file.exists():
            try:
                with open(self.port_mapping_file, 'r') as f:
                    for line in f:
                        if ':' in line:
                            used_ports.add(int(line.strip().split(':')[1]))
            except Exception:
                pass

        # Find available port within range 5000-6000
        max_port = 6000
        while ((port in used_ports or self._is_port_in_use(port)) and
               port < max_port):
            port += 1
        if port >= max_port:
            raise RuntimeError("No available ports in range 5000-6000")

        return port

    def _is_port_in_use(self, port: int) -> bool:
        """Check if a port is currently in use"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('localhost', port))
                return False
        except OSError:
            return True

    def start_port_forward(self, service: str) -> Optional[
            Tuple[str, int, subprocess.Popen]]:
        """Start port forwarding for a service"""
        deployment_name = service

        # Add color prefix if specified
        if self.color_prefix:
            deployment_name = f"{self.color_prefix}-{service}"

        port = self.find_available_port()

        msg = f"Starting port-forward for {deployment_name} on port {port}..."
        self.log(msg)

        # Check if deployment exists
        try:
            subprocess.run(['kubectl', 'get', 'deployment', deployment_name,
                            '-n', self.k8s_namespace],
                           check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError:
            msg = (f"Deployment '{deployment_name}' not found in namespace "
                   f"'{self.k8s_namespace}'")
            self.error(msg)
            return None

        # Start port-forward
        try:
            process = subprocess.Popen([
                'kubectl', 'port-forward',
                f'deployment/{deployment_name}',
                f'{port}:{port}',
                '-n', self.k8s_namespace
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # Wait a moment to check if port-forward started successfully
            time.sleep(2)
            if process.poll() is not None:
                self.error(f"Failed to start port-forward for "
                           f"{deployment_name}")
                return None

            # Store process and port mapping
            self.processes.append(process)

            # Write to files for persistence
            with open(self.pid_file, 'a') as f:
                f.write(f"{process.pid}\n")

            with open(self.port_mapping_file, 'a') as f:
                f.write(f"{deployment_name}:{port}\n")

            msg = (f"✓ {deployment_name} forwarded to localhost:{port} "
                   f"(PID: {process.pid})")
            self.log(msg)
            return deployment_name, port, process

        except Exception as e:
            self.error(f"Failed to start port-forward for "
                       f"{deployment_name}: {e}")
            return None

    def generate_env_file(self) -> str:
        """Generate environment file with service URLs"""
        filename = f"services_{self.environment}.env"
        env_file = self.outputs_dir / filename

        self.log(f"Generating environment file: {env_file}")

        # Create env file with header
        with open(env_file, 'w') as f:
            f.write("# Generated port-forward environment file\n")
            f.write(f"# Environment: {self.environment}\n")
            f.write(f"# Generated: {datetime.now()}\n")
            f.write(f"# Services forwarded: {', '.join(self.services)}\n\n")

            # Add service URLs
            if self.port_mapping_file.exists():
                with open(self.port_mapping_file, 'r') as mapping_file:
                    for line in mapping_file:
                        if ':' in line:
                            deployment_name, port = line.strip().split(':')
                            env_var = self.service_to_env_var(deployment_name)
                            f.write(f"{env_var}_URL=http://localhost:{port}\n")

        self.log(f"✓ Environment file created: {env_file}")

        # Display the contents
        print("\n📋 Environment variables generated:")
        with open(env_file, 'r') as f:
            for line in f:
                if (line.strip() and
                        line.strip().endswith('_URL=http://localhost:')):
                    print(f"  {line.strip()}")

        return str(env_file)

    def production_warning(self) -> bool:
        """Show production warning and get confirmation"""
        print()
        self.warn("⚠️  PRODUCTION ENVIRONMENT WARNING ⚠️")
        self.warn("You are about to connect to PRODUCTION services.")
        self.warn("This will create port-forwards to live production systems.")
        print()
        self.warn(f"Services to forward: {', '.join(self.services)}")
        print()

        try:
            response = input("Type 'y' to continue with production "
                             "port-forwarding: ").strip()
            if response.lower() != 'y':
                self.log("Production port-forwarding cancelled.")
                return False

            self.log("Proceeding with production port-forwarding...")
            return True
        except KeyboardInterrupt:
            print("\n")
            self.log("Production port-forwarding cancelled.")
            return False

    def cleanup(self):
        """Clean up port-forward processes"""
        if self.processes or self.pid_file.exists():
            self.log("Cleaning up port-forward processes...")

            # Kill processes we started
            for process in self.processes:
                try:
                    process.terminate()
                    process.wait(timeout=5)
                    self.log(f"Stopped port-forward process {process.pid}")
                except Exception:
                    try:
                        process.kill()
                    except Exception:
                        pass

            # Clean up any remaining processes from PID file
            if self.pid_file.exists():
                try:
                    with open(self.pid_file, 'r') as f:
                        for line in f:
                            try:
                                pid = int(line.strip())
                                os.kill(pid, signal.SIGTERM)
                                self.log(f"Stopped port-forward process {pid}")
                            except (ValueError, OSError):
                                pass
                except Exception:
                    pass

            # Clean up files
            for file_path in [self.pid_file, self.port_mapping_file]:
                try:
                    if file_path.exists():
                        file_path.unlink()
                except Exception:
                    pass

    def run(self, services: List[str], environment: str = "staging",
            color_prefix: str = "", background: bool = False) -> bool:
        """Main execution function"""
        self.services = services
        self.environment = environment
        self.color_prefix = color_prefix

        self.log("Port Forward Services Script")
        self.log(f"Environment: {self.environment}")
        self.log(f"Vinny Project: {self.vinny_project_root}")
        if self.color_prefix:
            self.log(f"Color prefix: {self.color_prefix}")
        self.log(f"Services: {', '.join(self.services)}")

        # Create outputs directory
        self.outputs_dir.mkdir(exist_ok=True)

        # Clean up any existing files
        for file_path in [self.pid_file, self.port_mapping_file]:
            if file_path.exists():
                file_path.unlink()

        # Check prerequisites
        if not self.check_prerequisites():
            return False

        # Production warning
        if self.environment == "production":
            if not self.production_warning():
                return False

        # Validate all services
        self.log("Validating services...")
        for service in self.services:
            if not self.validate_service(service):
                return False

        # AWS SSO and kubectl setup
        if not self.check_aws_sso_login():
            return False

        if not self.configure_kubectl_context():
            return False

        # Start port forwarding
        failed_services = []
        for service in self.services:
            normalized_service = self.normalize_service_name(service)
            result = self.start_port_forward(normalized_service)
            if result is None:
                failed_services.append(service)

        if failed_services:
            self.error(f"Failed to forward services: "
                       f"{', '.join(failed_services)}")
            return False

        # Generate environment file
        self.generate_env_file()

        print()
        self.log("All services successfully forwarded!")

        if background:
            msg = ("Running in background mode - processes will continue "
                   "running")
            self.log(msg)
            self.log(f"PID file: {self.pid_file}")
            self.log(f"Port mappings: {self.port_mapping_file}")
            self.log(f"Use 'kill $(cat {self.pid_file})' to stop all "
                     "processes")
            return True

        self.log("Press Ctrl+C to stop all port-forwards and exit")

        # Keep script running (foreground mode)
        try:
            while True:
                time.sleep(5)
                # Check if any processes have died
                dead_processes = 0
                for process in self.processes:
                    if process.poll() is not None:
                        dead_processes += 1

                if dead_processes > 0:
                    self.warn(f"{dead_processes} port-forward process(es) "
                              "have terminated")

        except KeyboardInterrupt:
            print()
            self.log("Interrupt received, cleaning up...")

        return True


def main():
    parser = argparse.ArgumentParser(
        description=("Port-forward Kubernetes services and generate "
                     "environment files."),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s catalog_ms users-ms              # Forward staging services
  %(prog)s catalog_ms --prod                # Forward production service
  %(prog)s --color blue services-ms users-ms  # Forward blue-services-ms
  %(prog)s catalog_ms --background          # Forward in background and exit

Environment variables generated:
  If input is catalog_ms → CATALOG_MS_URL=http://localhost:PORT
        """
    )

    parser.add_argument('services', nargs='+',
                        help='Service names (catalog_ms, users-ms, etc.)')
    parser.add_argument('--prod', action='store_true',
                        help='Use production environment (requires '
                             'confirmation)')
    parser.add_argument('--color',
                        help='Prefix services with color (e.g., '
                             'blue-services-ms)')
    parser.add_argument('--background', action='store_true',
                        help='Run port-forwards in background and exit '
                             'immediately')

    args = parser.parse_args()

    environment = "production" if args.prod else "staging"
    color_prefix = args.color or ""
    background = args.background

    manager = PortForwardManager()

    try:
        success = manager.run(args.services, environment, color_prefix,
                              background)
        if not success:
            sys.exit(1)
    finally:
        # Only cleanup if not running in background
        if not background:
            manager.cleanup()


if __name__ == "__main__":
    main()
