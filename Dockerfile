FROM python:3.11-slim

WORKDIR /app

COPY bot/requirements.txt /app/bot/requirements.txt
RUN pip install --no-cache-dir -r /app/bot/requirements.txt

COPY bot/ /app/bot/

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/bot

CMD ["python", "bot/main.py"]
