FROM python:3.12-slim AS builder
WORKDIR /app
COPY common/ /app/common/
COPY payment/ /app/payment/
RUN pip install --no-cache-dir --prefix=/install -r /app/payment/requirements.txt

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY --from=builder /app/common /app/common
COPY --from=builder /app/payment /app/payment
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1
RUN useradd --uid 10001 --create-home appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "payment.main:app", "--host", "0.0.0.0", "--port", "8000"]
