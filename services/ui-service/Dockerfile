FROM node:22-slim AS ui-assets
WORKDIR /ui
COPY services/ui-service/package.json services/ui-service/package-lock.json ./
RUN npm ci --omit=dev

FROM python:3.11-slim

WORKDIR /service



COPY services/ui-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/ui-service/app/ ./app/
COPY --from=ui-assets /ui/node_modules/pdfjs-dist ./node_modules/pdfjs-dist

EXPOSE 7860

CMD ["python", "-m", "app.main"]
