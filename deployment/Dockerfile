# Use an older but more stable Python image 
FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Install dependencies for OpenCV with optimized space usage
# The key changes are combining commands and clearing apt cache in the same layer
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
    # Minimal dependencies for OpenCV and video processing
    libgl1 \
    libglib2.0-0 \
    ffmpeg \
    # Clean up in the same layer to reduce image size
    && rm -rf /var/cache/apt/* /var/lib/apt/lists/* \
    && apt-get clean

# Copy the requirements file into the container
COPY requirements.txt .

# Install the dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set environment variable for Streamlit
ENV STREAMLIT_SERVER_PORT=8000
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_SERVER_ENABLE_CORS=false

# Default entry point is app.py but can be overridden
ARG ENTRY_FILE=app.py
ENV ENTRY_FILE=${ENTRY_FILE}

# Expose port
EXPOSE 8000

# Start the Streamlit app with additional debug information
CMD echo "Starting Streamlit app with Python $(python --version)" && \
    streamlit --version && \
    streamlit run $ENTRY_FILE --server.port 8000 --server.enableCORS false --server.enableXsrfProtection false
