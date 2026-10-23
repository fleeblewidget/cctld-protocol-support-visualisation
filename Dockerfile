FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Results are written to /app/output; mount a volume there to collect them.
ENTRYPOINT ["python", "maps.py"]
CMD ["/data/results.csv"]
