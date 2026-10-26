FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /install /usr/local
COPY . .

EXPOSE 8003

ENV HOST=0.0.0.0
ENV PORT=8003

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003"]
