FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY fetch_stats.py .

CMD ["python", "-u", "fetch_stats.py"]
