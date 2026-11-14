# Swarm detector dashboard.
#   docker build -t swarm-detector .
#   docker run -d --restart unless-stopped -p 80:8000 --name swarm swarm-detector
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scripts ./scripts
COPY dashboard ./dashboard
COPY data ./data

# Run as an unprivileged user; uploads go to a directory that user owns.
RUN useradd --create-home swarm && mkdir -p /var/swarm_uploads /var/guard && chown swarm /var/swarm_uploads /var/guard
ENV SWARM_UPLOAD_DIR=/var/swarm_uploads GUARD_DB=/var/guard/guard.sqlite
USER swarm

EXPOSE 8000
CMD ["uvicorn", "dashboard.app:app", "--host", "0.0.0.0", "--port", "8000"]
