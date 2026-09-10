FROM ledger-eval:local
WORKDIR /workspace/services/eval-service
EXPOSE 8005
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005"]
