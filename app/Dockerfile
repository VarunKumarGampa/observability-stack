# Start from an official Python image
# 'slim' means minimal size — no extras we don't need
FROM python:3.12-slim

# Set the working directory inside the container
WORKDIR /app

# Copy requirements first (Docker caches this layer)
# If app.py changes but requirements don't, Docker skips reinstalling packages
COPY requirements.txt .

# Install the Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Copy the app code
COPY app.py .

# Tell Docker this container listens on port 5000
EXPOSE 5000

# Command to run when container starts
CMD ["python", "app.py"]