FROM python:3.12-slim

EXPOSE 8000


ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y  postgresql-client  libpq-dev  gcc python3-dev  && rm -rf /var/lib/apt/lists/* 


COPY ./requirements.txt .

RUN python -m pip install -r requirements.txt

WORKDIR /app

COPY . /app


RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "backend.wsgi"]
