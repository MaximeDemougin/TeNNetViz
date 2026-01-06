FROM python:3.12-slim

WORKDIR /app

# Install system build dependencies (needed for some Python packages)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       gcc \
       libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy Poetry project files to leverage Docker cache for dependencies
COPY pyproject.toml poetry.lock* /app/

# Install Poetry and project dependencies (do not create virtualenv inside container)
RUN pip install --no-cache-dir "poetry>=1.4" \
    && poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-dev

# Copy the rest of the application
COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]