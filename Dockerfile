FROM python:3.13-slim

# libglib je jedina systemova zavislost headless opencv; bez ni cv2 neimportuje
RUN apt-get update \
 && apt-get install -y --no-install-recommends libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY dinostanice/ dinostanice/
COPY web/ web/
COPY tools/ tools/
COPY data/ data/
COPY server.py .

# ulovky prepise volume; adresar tu musi byt, aby server nastartoval i bez nej
RUN mkdir -p data/catch

EXPOSE 8000
ENV DINO_PORT=8000 PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/rigs')"

CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
