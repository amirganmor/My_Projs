FROM python:3.11-slim

WORKDIR /app
COPY champions_league/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared/ ./shared/
COPY champions_league/producer.py .

CMD ["python", "-u", "producer.py"]
