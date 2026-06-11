FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8097

ARG MEDIASYNC_VERSION=dev
ENV MEDIASYNC_VERSION=${MEDIASYNC_VERSION}

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8097"]
