# TODO_002: Docker Container Setup for JANATPMP

**Status:** Not Started  
**Priority:** High  
**Dependencies:** TODO_001 (dependencies should be stable)

---

## Objective

Containerize the JANATPMP Gradio application using Docker Desktop, creating the foundation for our multi-service architecture.

---

## Tasks

### 1. Create Dockerfile

Create `Dockerfile` in project root:

```dockerfile
# Use an official Python runtime as a parent image
FROM python:3.14-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose the port the app runs on
EXPOSE 7860

# Define environment variable
ENV GRADIO_SERVER_NAME="0.0.0.0"
ENV GRADIO_MCP_SERVER="True"

# Run app.py when the container launches
CMD ["gradio", "app.py"]
```

### 2. Create docker-compose.yml

Create `docker-compose.yml` in project root:

```yaml
services:
  janatpmp:
    build: .
    ports:
      - "7860:7860"
    volumes:
      - .:/app
    environment:
      - GRADIO_SERVER_NAME=0.0.0.0
      - GRADIO_MCP_SERVER=True
    restart: unless-stopped
```

### 3. Update .gitignore

Ensure `.gitignore` includes Docker-related ignores if not already present:

```
# Docker
*.log
```

### 4. Test Docker Build and Run

```bash
# Build the image
docker-compose build

# Run the container
docker-compose up

# Verify app accessible at http://localhost:7860

# Stop when done testing
docker-compose down
```

---

## Acceptance Criteria

- [ ] `Dockerfile` created in project root
- [ ] `docker-compose.yml` created in project root
- [ ] `.gitignore` includes Docker artifacts
- [ ] `docker-compose build` succeeds without errors
- [ ] `docker-compose up` launches container successfully
- [ ] Gradio UI accessible at http://localhost:7860
- [ ] Application functions identically to local Python run
- [ ] Changes to code hot-reload (volume mount working)
- [ ] All files committed to git

---

## Notes

- Volume mount (`.:/app`) enables live code changes without rebuild
- This establishes the base service; future TODOs will add Qdrant, Neo4j, etc.
- MCP server enabled by default for future Claude Desktop integration
- Using Python 3.14-slim to match local development environment

---

## Future Considerations

This single-service setup will expand to:
- Qdrant service for vector search
- Neo4j service for graph relationships  
- Shared volumes for SQLite database persistence
- Health checks and service dependencies
