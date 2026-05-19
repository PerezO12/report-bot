FROM python:3.12-slim

WORKDIR /app

# Install deps first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY bot/ bot/
COPY flows/ flows/
COPY main.py .

# Run as non-root
RUN useradd -m -u 1000 botuser
USER botuser

CMD ["python", "-u", "main.py"]
