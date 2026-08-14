# UK Open Data Index — web UI + API
#
# The image expects a data volume mounted at /app/data containing index.db,
# embeddings.npy and emb_keys.json (built by the pipeline — see refresh.sh).
# Model weights are baked in at build time so cold starts don't hit the
# network.

FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# bake the embedding model into the image
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

COPY *.py sources.yaml ./
COPY web/ web/

ENV DATA_DIR=/app/data
EXPOSE 8000
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
