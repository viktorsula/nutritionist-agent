#!/bin/bash
# Скрипт запуска веб-интерфейса

echo "🚀 Запуск веб-интерфейса Nutritionist Agent..."
echo ""

# Проверка .env
if [ ! -f .env ]; then
    echo "❌ Файл .env не найден!"
    echo "Скопируйте .env.example в .env и заполните ключи"
    exit 1
fi

# Проверка зависимостей
python -c "import streamlit" 2>/dev/null || {
    echo "📦 Устанавливаю зависимости..."
    pip install -q -r requirements.txt
}

echo "✅ Всё готово!"
echo ""
echo "🌐 Веб-интерфейс будет доступен по адресу:"
echo "   http://localhost:8501"
echo ""
echo "📌 В GitHub Codespaces — смотри вкладку 'PORTS' для публичного URL"
echo ""

# Запуск Streamlit
python -m streamlit run app.py \
    --server.port=8501 \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --browser.gatherUsageStats=false
