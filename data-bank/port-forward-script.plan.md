# Port Forward and Environment Generation Script

Create a shell script at `scripts/devops/port_forward_services.sh` that handles service port forwarding from Kubernetes clusters and generates environment files.

## Core Functionality

The script will:

1. **Parse service names** - Accept service names in both formats (`catalog_ms` or `catalog-ms`)
2. **AWS SSO authentication** - Check and login to AWS SSO if needed using existing patterns from upload script
3. **Port forwarding** - Use `kubectl port-forward` to forward services from staging/production to local ports
4. **Environment file generation** - Create `.env` files in `outputs/` directory with `SERVICE_NAME_URL=http://localhost:PORT` format

## Key Features

### Command Line Interface

```bash
./scripts/devops/port_forward_services.sh service1 service2 [--prod] [--color COLOR]
# Examples:
./scripts/devops/port_forward_services.sh catalog_ms users-ms  # staging (default)
./scripts/devops/port_forward_services.sh catalog_ms --prod   # production (with confirmation)
./scripts/devops/port_forward_services.sh --color blue services-ms users-ms  # forward blue-services-ms and blue-users-ms
./scripts/devops/port_forward_services.sh --color red catalog-ms --prod      # forward red-catalog-ms to production
```

### Service Name Handling

- Accept both `catalog_ms` and `catalog-ms` formats as input
- Convert to proper Kubernetes deployment names (`catalog-ms`)
- Generate environment variable names (`CATALOG_MS_URL`)

### Port Management

- Use kubectl to find available local ports starting from 8080
- Track used ports to avoid conflicts when forwarding multiple services
- Store port mappings for cleanup

### Environment File Output

- Create `outputs/` directory in vinny project root
- Generate timestamped env files: `outputs/services_staging_YYYYMMDD_HHMMSS.env`
- Include all forwarded services in format: `SERVICE_NAME_URL=http://localhost:PORT`

## Implementation Details

### File Structure

- `scripts/devops/port_forward_services.sh` - Main script
- `outputs/` - Directory for generated env files (create if doesn't exist)
- `data-bank/port-forward-script.plan.md` - Plan documentation for future reference

### AWS/Kubernetes Integration

- Use AWS SSO login pattern from existing upload script
- Configure kubectl context for staging (`staging/artemis`) or production (`production/vinny`)
- Use `kubectl port-forward deployment/SERVICE-NAME PORT:PORT` commands

### Process Management

- Run port-forward commands in background
- Create PID file to track running processes
- Provide cleanup function to stop all port-forwards
- Handle script interruption gracefully

### Error Handling

- Validate service names against existing apps directory
- Check kubectl and AWS CLI availability
- Verify Kubernetes cluster connectivity
- Handle port conflicts and retry with different ports

## Dependencies

- kubectl (Kubernetes CLI)
- AWS CLI with SSO configured
- bash shell
- Standard Unix utilities (ps, kill, etc.)

### Production Warning

When using --prod flag, script displays warning message requiring user to type 'y' before proceeding with production environment operations.

### Color Prefix Support

The --color flag allows prefixing service names with specified color (e.g., --color blue with services-ms becomes blue-services-ms).
