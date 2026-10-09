# Abuse-suite runner. Runs on the same Docker network as the app so the slow-reader test sees real
# TCP backpressure (Docker Desktop's host port proxy would buffer on the client's behalf).
FROM public.ecr.aws/docker/library/python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /suite
COPY requirements.txt .
RUN pip install --require-hashes --no-deps -r requirements.txt
COPY locustfile.py .
USER 10001
ENTRYPOINT ["locust", "-f", "locustfile.py", "--headless", "--users", "1", "--spawn-rate", "1", "--only-summary"]
