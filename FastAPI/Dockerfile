FROM python:3.12-slim

EXPOSE 8001


ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y  postgresql-client  libpq-dev  gcc python3-dev  && rm -rf /var/lib/apt/lists/* 


COPY ./requirements.txt .

RUN python -m pip install -r requirements.txt
RUN playwright install --with-deps chromium

WORKDIR /app

COPY . /app



RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser
RUN playwright install

CMD ["uvicorn","main:app", "--host", "0.0.0.0", "--port", "8001"]
