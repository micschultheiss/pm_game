FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080
EXPOSE 8080

# Single worker is load-bearing: the web frontend keeps game state in a
# module-level dict (web.py:_games), so multiple workers would split
# sessions across independent in-memory stores.
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:8080", "--access-logfile", "-", "web:app"]
