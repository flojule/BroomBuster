FROM python:3.12-slim

WORKDIR /app

# System deps for geopandas / shapely
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgdal-dev \
    libspatialindex-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt ./requirements.txt
COPY api/requirements.txt ./api-requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r api-requirements.txt

# Copy source
COPY src/      ./src/
COPY api/      ./api/
COPY frontend/ ./frontend/
COPY data/     ./data/

EXPOSE 8000
CMD ["uvicorn", "api.api:app", "--host", "0.0.0.0", "--port", "8000"]
