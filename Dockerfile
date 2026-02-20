# Use an official Python runtime as a parent image
FROM python:3.14-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install PyTorch with CUDA 12.8 support FIRST (from CUDA wheel index)
# cu128 required for RTX 5090 Blackwell (sm_120) — cu126 only supports up to sm_90
# Must happen before requirements.txt to prevent CPU-only torch overwrite
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cu128

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
CMD ["python", "app.py"]
