FROM python:3.11-slim

WORKDIR /app
COPY la_liga/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared/ ./shared/
COPY la_liga/producer.py .

CMD ["python", "-u", "producer.py"]
