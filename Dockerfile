FROM python:3.12.5-slim

# System deps for OpenCV, MoviePy/ffmpeg and fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libgl1 \
        libglib2.0-0 \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . .

EXPOSE 8501

ENTRYPOINT ["streamlit", "run", "video-analysis-with-aoai.py", "--server.port=8501", "--server.address=0.0.0.0"]