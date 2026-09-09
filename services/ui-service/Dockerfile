FROM python:3.11-slim

WORKDIR /app


COPY services/ui-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/ui-service/app/ .

EXPOSE 7860

CMD ["python", "main.py"]
