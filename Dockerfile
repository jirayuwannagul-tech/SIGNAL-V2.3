FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p data/logs data/candles storage

CMD ["sh", "-c", "gunicorn app.main:app --bind 0.0.0.0:${PORT:-8080} --workers 1 --threads 4 --timeout 120"]
