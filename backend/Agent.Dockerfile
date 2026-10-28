FROM python:3.12-slim
WORKDIR /app
COPY backend/agent-requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && useradd -m -u 10001 askdb && mkdir /state && chown askdb /state
COPY backend/agentic /app/agentic
USER askdb
ENV ASKDB_STATE_DIR=/state
EXPOSE 8081
CMD ["uvicorn","agentic.api:app_factory","--factory","--host","0.0.0.0","--port","8081"]
