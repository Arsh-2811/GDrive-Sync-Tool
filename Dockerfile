# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set environment variables for Python
ENV PYTHONDONTWRITEBYTECODE 1 # Prevents python creating .pyc files
ENV PYTHONUNBUFFERED 1      # Ensures logs print directly to stdout/stderr for Docker

# Set the working directory in the container
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code into the container
COPY ./gdrive_downloader ./gdrive_downloader

# Create directories expected by the application (though volumes handle persistence)
# These commands run during image build, volumes are mounted at runtime.
RUN mkdir -p /app/downloads /app/state /app/secrets

# Set the default command to run when the container starts
# This executes the main entry point of the application
CMD ["python", "-m", "gdrive_downloader.main"]