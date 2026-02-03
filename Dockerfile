FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for building psycopg2 and other packages
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Copy pre-built manager frontend (must exist locally before docker build)
# If manager_frontend/dist doesn't exist, this will fail - run 'npm run build' first
COPY manager_frontend/dist /app/manager_frontend/dist

# Command to run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
