FROM python:3.11-slim

WORKDIR /app

COPY . /app

RUN pip install --upgrade pip \
    && pip install -r requirements.txt

ENV PYTHONUNBUFFERED=1

EXPOSE 5000

# Serve the GMAIS web interface (offline deterministic backend by default).
CMD ["python", "-m", "gmais.webapp"]
