#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_DIR="$SCRIPT_DIR/models/all-MiniLM-L6-v2"

# Download the ChromaDB embedding model if not already present
if [ ! -f "$MODEL_DIR/onnx/model.onnx" ]; then
    echo "Downloading all-MiniLM-L6-v2 embedding model..."
    mkdir -p "$MODEL_DIR"
    TARBALL="$MODEL_DIR/onnx.tar.gz"
    curl -fSL -o "$TARBALL" \
        "https://chroma-onnx-models.s3.amazonaws.com/all-MiniLM-L6-v2/onnx.tar.gz"
    tar -xzf "$TARBALL" -C "$MODEL_DIR"
    rm -f "$TARBALL"
    echo "Model downloaded to $MODEL_DIR"
fi

docker build -t valheim-mcp-knowledge "$SCRIPT_DIR"
