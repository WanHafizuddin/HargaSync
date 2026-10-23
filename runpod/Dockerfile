# RunPod Serverless worker for invoice reading. Build from the repository root:
#   docker build -t <dockerhub-user>/hargasync-reader:latest runpod
FROM runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Cache model weights on an attached network volume so cold starts skip the download.
ENV MODEL_ID=Qwen/Qwen2.5-VL-7B-Instruct \
    HF_HOME=/runpod-volume/hf-cache

COPY handler.py .
CMD ["python", "-u", "handler.py"]
