#!/bin/bash
# JANATPMP Ollama Initialization Script
# Runs on container startup after ollama serve is ready
# Ensures required models are pulled and custom models are created

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MODELFILE_DIR="${SCRIPT_DIR}/modelfiles"
CONFIG="${SCRIPT_DIR}/models.conf"

# Wait for Ollama API to be ready (use ollama list — curl not available in container)
echo "[ollama-init] Waiting for Ollama API..."
until ollama list > /dev/null 2>&1; do
    sleep 1
done
echo "[ollama-init] Ollama API is ready."

# Source config
source "$CONFIG"

# Phase 1: Pull required models
IFS=',' read -ra MODELS <<< "$REQUIRED"
for model in "${MODELS[@]}"; do
    model=$(echo "$model" | xargs)  # trim whitespace
    if ! ollama list | grep -q "^${model}"; then
        echo "[ollama-init] Pulling required model: $model"
        ollama pull "$model"
    else
        echo "[ollama-init] Model exists: $model"
    fi
done

# Phase 2: Pull HuggingFace models
if [ -n "$HF_REQUIRED" ]; then
    IFS=',' read -ra HF_MODELS <<< "$HF_REQUIRED"
    for model in "${HF_MODELS[@]}"; do
        model=$(echo "$model" | xargs)
        if ! ollama list | grep -q "$(echo $model | sed 's|hf.co/||')"; then
            echo "[ollama-init] Pulling HF model: $model"
            ollama pull "$model" || echo "[ollama-init] WARNING: Failed to pull $model"
        else
            echo "[ollama-init] HF model exists: $model"
        fi
    done
fi

# Phase 3: Create custom models from Modelfiles
IFS=',' read -ra CUSTOMS <<< "$CUSTOM"
for name in "${CUSTOMS[@]}"; do
    name=$(echo "$name" | xargs)
    modelfile="${MODELFILE_DIR}/${name}.Modelfile"
    if [ ! -f "$modelfile" ]; then
        echo "[ollama-init] WARNING: Modelfile not found: $modelfile"
        continue
    fi
    if ! ollama list | grep -q "^${name}"; then
        echo "[ollama-init] Creating custom model: $name"
        ollama create "$name" -f "$modelfile"
    else
        echo "[ollama-init] Custom model exists: $name"
    fi
done

# Phase 4: Optional cleanup
if [ "$CLEANUP_ENABLED" = "true" ]; then
    echo "[ollama-init] Cleanup enabled. Removing unlisted models..."
    ollama list | tail -n +2 | awk '{print $1}' | while read model; do
        if ! echo "$WHITELIST" | grep -q "$model"; then
            echo "[ollama-init] Removing unlisted model: $model"
            ollama rm "$model" || true
        fi
    done
fi

# Phase 5: Log final state
echo "[ollama-init] === Final Model State ==="
ollama list
echo "[ollama-init] Initialization complete."
