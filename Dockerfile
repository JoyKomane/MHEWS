# ============================================================
#  MHEWS — Dockerfile
#  B2: Instructions for building the Python app container.
#
#  A Dockerfile is a recipe that tells Docker how to build
#  a container image for your application.
#  Docker reads it top to bottom and executes each step.
# ============================================================

# Start from the official Python 3.11 slim image.
# "slim" = smaller image, only the bare minimum included.
# This is the foundation everything else is built on.
FROM python:3.11-slim

# Set the working directory inside the container.
# All commands below will run from this folder.
# Think of it as cd /usr/src/app inside the container.
WORKDIR /usr/src/app

# Install system-level dependencies needed by GeoPandas and Fiona.
# These are C libraries that the Python packages depend on.
# Without them, pip install geopandas will fail.
# --no-install-recommends keeps the image small.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgdal-dev \
    gdal-bin \
    libgeos-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy just the requirements file first.
# Why? Docker caches each step. If your requirements.txt
# hasn't changed, Docker skips the pip install step next time
# and goes straight to copying your code. Much faster rebuilds.
COPY requirements.txt .

# Install all Python dependencies.
# --no-cache-dir keeps the image smaller.
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your project code into the container.
# The dot means "copy everything from your current folder
# into the container's WORKDIR (/usr/src/app)".
COPY . .

# Document which port the app listens on.
# This doesn't actually open the port — docker-compose.yml
# does that. It's just documentation for developers.
EXPOSE 8000

# The default command to start the app.
# Docker Compose overrides this with its own command,
# but this is useful if you ever run the container directly.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
