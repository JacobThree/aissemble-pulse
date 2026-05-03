# Docker Deployment

This directory contains Docker configuration for containerized deployment.

**Mode:** Release (PyPI packages)

## Prerequisites

- Docker Desktop or Rancher Desktop
- Docker Compose (included with Docker Desktop)

## Models

- **yolov8** only — the image copies `models/yolov8/` into `/app/models/yolov8/`. If you also copy `models/sumy/` into this image, MLServer tries to load Sumy and exits with `ModuleNotFoundError: aissemble_inference_sumy` (Sumy has its own Docker image on host port 8090).

## Runtime Dependencies

The following packages are installed from PyPI:

- aissemble-inference-yolo
- mlserver>=1.6.0
- ultralytics (required by the YOLO runtime inside the container)

The Dockerfile installs **`opencv-python-headless`** after deps resolve (replacing **`opencv-python`**) so **`cv2`** works on slim images without GUI libs like **`libxcb`**.

## Quick Start

Build and start the container:

```bash
docker-compose up --build
```

The server will be available at [http://localhost:8080](http://localhost:8080)

## Usage

### Build Only

```bash
docker-compose build
```

### Start in Background

```bash
docker-compose up -d
```

### View Logs

```bash
docker-compose logs -f
```

### Stop

```bash
docker-compose down
```

## Testing

Once the container is running, test the endpoint:

```bash
curl -X POST http://localhost:8080/v2/models/<model-name>/infer \
  -H "Content-Type: application/json" \
  -d '{"inputs": [...]}'
```

## Customization

### Environment Variables

The docker-compose.yml supports these environment variables:

- `MLSERVER_HTTP_PORT`: HTTP port (default: 8080)
- `MLSERVER_GRPC_PORT`: gRPC port (default: 8081)

### Resource Limits

Edit docker-compose.yml to add resource constraints:

```yaml
services:
  mlserver:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
```

### Updating Dependencies

Edit `requirements.txt` to change package versions, then rebuild:

```bash
docker-compose build --no-cache
```

## Production Considerations

For production deployments:

1. **Multi-architecture builds**: Use `docker buildx` for ARM/AMD64 support
2. **Registry**: Push to a container registry (Docker Hub, ECR, GCR, etc.)
3. **Secrets**: Use Docker secrets or environment variable injection
4. **Health checks**: The Dockerfile includes MLServer health endpoints
5. **Logging**: Configure structured logging for your platform

## Troubleshooting

**Build fails with package not found:**

- Ensure runtime packages are published to PyPI
- Check network connectivity to PyPI

**Container exits immediately:**

- Check logs: `docker-compose logs`
- Verify model-settings.json files are valid JSON

**Port already in use:**

- Stop other services on port 8080/8081
- Or change the ports in docker-compose.yml

