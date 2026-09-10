FROM python:3.11-slim

WORKDIR /service



COPY services/ui-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/ui-service/app/ ./app/

EXPOSE 7860

CMD ["python", "-m", "app.main"]
