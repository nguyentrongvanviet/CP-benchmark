FROM debian:bookworm-slim@sha256:7c7b2c966bc9ee8cedfeef67e0e279108992c77681fa595db4a9d65c06ccc587
RUN apt-get update && apt-get install -y --no-install-recommends g++ python3 ca-certificates && rm -rf /var/lib/apt/lists/*
COPY worker.py /opt/cpbench/worker.py
ENTRYPOINT ["python3", "-I", "/opt/cpbench/worker.py"]
