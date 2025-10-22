# DevOps Scripts

## Port Forward Services Script

The `port_forward_services.py` script handles port forwarding from Kubernetes clusters (staging/production) to local ports and generates environment files with service URLs.

This script is part of dannys-scripts and works with the vinny project located at `/Users/dannysivan/src/vinny`.

### Usage

```bash
python scripts/devops/port_forward_services.py service1 [service2 ...] [--prod] [--color COLOR] [--background]
# (can also use python3 on systems where python != python3)
```

### Examples

```bash
# Forward staging services (default)
python scripts/devops/port_forward_services.py catalog_ms users-ms

# Forward production service (requires confirmation)
python scripts/devops/port_forward_services.py catalog_ms --prod

# Forward services with color prefix
python scripts/devops/port_forward_services.py --color blue services-ms users-ms
# This forwards: blue-services-ms, blue-users-ms

# Production with color prefix
python scripts/devops/port_forward_services.py --color red catalog-ms --prod
# This forwards: red-catalog-ms in production

# Run in background (processes continue after script exits)
python scripts/devops/port_forward_services.py catalog-ms --background
```

### Features

- **AWS SSO Authentication**: Automatically checks and prompts for AWS SSO login if needed
- **Service Name Flexibility**: Accepts both `catalog_ms` and `catalog-ms` formats
- **Color Prefixing**: Use `--color` flag to prefix service names (e.g., `blue-services-ms`)
- **Production Warning**: Requires typing 'y' to confirm production environment operations
- **Port Management**: Automatically finds available ports in range 5000-6000
- **Environment File Generation**: Creates timestamped `.env` files in `outputs/` directory
- **Process Management**: Tracks and manages background port-forward processes
- **Background Mode**: Option to start port-forwards and exit immediately
- **Graceful Cleanup**: Stops all port-forwards on script exit or interruption

### Output

The script generates environment files in the dannys-scripts `outputs/` directory with the format:

```
outputs/services_staging.env
outputs/services_production.env
```

Example content:

```bash
# Generated port-forward environment file
# Environment: staging
# Generated: Wed Oct 22 15:30:45 PDT 2025
# Services forwarded: catalog-ms users-ms

CATALOG_MS_URL=http://localhost:5000
USERS_MS_URL=http://localhost:5001
```

### Requirements

- `kubectl` - Kubernetes CLI
- `aws` - AWS CLI with SSO configured
- `bash` - Shell environment
- Network access to Kubernetes clusters

### Service Validation

The script validates that services exist in the vinny project's `apps/` directory before attempting to forward them. If a service is not found, it will list available services.

### Cleanup

The script automatically cleans up all port-forward processes when:

- Script is interrupted (Ctrl+C)
- Script exits normally
- Script is terminated

### Troubleshooting

1. **AWS SSO Issues**: Run `aws sso login` manually if authentication fails
2. **kubectl Context**: Ensure you have access to staging/production Kubernetes clusters
3. **Service Not Found**: Check that the service exists in the `apps/` directory
4. **Port Conflicts**: The script automatically finds available ports in range 5000-6000
