# Бэкенд проекта = FastAPI (api/main.py). Веб-интерфейс — отдельный React-SPA
# (frontend/, деплоится статикой), в этот образ НЕ входит.
# Streamlit (app.py, web/) — legacy, в образе не запускается.
FROM python:3.11-slim

WORKDIR /app

# Системные зависимости для сборки колёс (grpc и пр.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render/локально пробрасывают порт через переменную $PORT (по умолчанию 8000).
ENV PORT=8000
EXPOSE 8000

# Точка входа — FastAPI через uvicorn (sh -c для подстановки $PORT).
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
