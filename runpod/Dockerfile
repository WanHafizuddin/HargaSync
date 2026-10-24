# RunPod Serverless worker for invoice reading. Build from the repository root:
#   docker build -t <dockerhub-user>/hargasync-reader:latest runpod
FROM runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04

WORKDIR /app
# Worker dependencies (torch comes from the base image). They are listed here rather than in
# a requirements file so Replit's dependency scan only sees the web app it actually deploys.
RUN pip install --no-cache-dir "runpod>=1.7" "transformers>=4.51,<5" "accelerate>=1.0" "pillow>=10"

# Cache model weights on an attached network volume so cold starts skip the download.
ENV MODEL_ID=Qwen/Qwen2.5-VL-7B-Instruct \
    HF_HOME=/runpod-volume/hf-cache

COPY handler.py .
CMD ["python", "-u", "handler.py"]
