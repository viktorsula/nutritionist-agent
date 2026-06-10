"""
Примеры использования utils/llm.py

Демонстрирует различные способы вызова LLM для агентов.
"""

from utils.llm import call_llm


# ========================================
# ПРИМЕР 1: Диалог с клиентом (GROQ)
# ========================================

def example_dialog():
    """
    Ежедневный диалог с клиентом.
    Использует: Groq llama-3.3-70b (бесплатно, быстро)
    """
    response = call_llm(
        task_type='dialog',
        messages=[
            {
                "role": "system",
                "content": "Ты помощник нутрициолога. Отвечай доброжелательно и профессионально на русском языке."
            },
            {
                "role": "user",
                "content": "Что мне съесть на завтрак, если я хочу похудеть?"
            }
        ]
    )

    print("=== ДИАЛОГ С КЛИЕНТОМ ===")
    print(f"Провайдер: {response['provider']}")
    print(f"Модель: {response['model']}")
    print(f"Ответ: {response['content']}")
    print(f"Токены: {response['usage']['input_tokens']} in, {response['usage']['output_tokens']} out")
    print()


# ========================================
# ПРИМЕР 2: Аналитика клиента (CLAUDE)
# ========================================

def example_analytics():
    """
    Глубокий анализ данных клиента.
    Использует: Claude Sonnet (качество++, ~$3/M токенов)
    """
    client_data = {
        "name": "Мария",
        "age": 35,
        "weight_history": [75, 74.5, 74, 73.8, 74.2],
        "meals_count": 12,
        "exercise_days": 3
    }

    response = call_llm(
        task_type='analytics',
        messages=[
            {
                "role": "system",
                "content": "Ты эксперт-аналитик по нутрициологии. Анализируй данные клиентов и давай профессиональные рекомендации."
            },
            {
                "role": "user",
                "content": f"Проанализируй прогресс клиента за неделю:\n{client_data}\n\nДай краткую оценку и рекомендации."
            }
        ],
        temperature=0.2  # Более детерминированный анализ
    )

    print("=== АНАЛИТИКА КЛИЕНТА ===")
    print(f"Провайдер: {response['provider']}")
    print(f"Модель: {response['model']}")
    print(f"Анализ: {response['content'][:200]}...")
    print(f"Токены: {response['usage']['total_tokens']} total")
    print()


# ========================================
# ПРИМЕР 3: Эксперимент с новой моделью
# ========================================

def example_experiment():
    """
    A/B тестирование новой модели.
    Явное указание provider + model для эксперимента.
    """
    # Обычная модель (из маппинга)
    response_default = call_llm(
        task_type='summary',
        messages=[
            {
                "role": "user",
                "content": "Суммаризируй: клиент ел овсянку, яблоко, курицу с рисом, творог"
            }
        ]
    )

    # Экспериментальная модель (Claude Haiku — быстрее и дешевле)
    response_experiment = call_llm(
        provider='claude',
        model='claude-haiku-4',
        messages=[
            {
                "role": "user",
                "content": "Суммаризируй: клиент ел овсянку, яблоко, курицу с рисом, творог"
            }
        ]
    )

    print("=== A/B ТЕСТИРОВАНИЕ ===")
    print(f"Вариант A (default): {response_default['model']}")
    print(f"  Токены: {response_default['usage']['total_tokens']}")
    print(f"  Ответ: {response_default['content'][:100]}...")
    print()
    print(f"Вариант B (experiment): {response_experiment['model']}")
    print(f"  Токены: {response_experiment['usage']['total_tokens']}")
    print(f"  Ответ: {response_experiment['content'][:100]}...")
    print()


# ========================================
# ПРИМЕР 4: Premium модель для VIP клиента
# ========================================

def example_premium_client(client_tier: str):
    """
    Разные модели для разных уровней подписки.
    """
    if client_tier == 'premium':
        # VIP клиенты получают Claude Opus (самая мощная модель)
        response = call_llm(
            provider='claude',
            model='claude-opus-4-8',
            messages=[
                {
                    "role": "system",
                    "content": "Ты персональный нутрициолог премиум класса."
                },
                {
                    "role": "user",
                    "content": "Составь мне план питания на неделю"
                }
            ]
        )
    else:
        # Обычные клиенты — стандартная модель
        response = call_llm(
            task_type='planning',
            messages=[
                {
                    "role": "system",
                    "content": "Ты помощник нутрициолога."
                },
                {
                    "role": "user",
                    "content": "Составь мне план питания на неделю"
                }
            ]
        )

    print(f"=== КЛИЕНТ {client_tier.upper()} ===")
    print(f"Модель: {response['model']}")
    print(f"Ответ: {response['content'][:150]}...")
    print()


# ========================================
# ПРИМЕР 5: Переопределение параметров
# ========================================

def example_override_params():
    """
    Переопределение temperature и max_tokens для task_type.
    """
    # Креативный ответ (высокая температура)
    response_creative = call_llm(
        task_type='dialog',
        messages=[
            {
                "role": "user",
                "content": "Придумай интересный рецепт завтрака"
            }
        ],
        temperature=0.9,  # Высокая креативность
        max_tokens=1000
    )

    # Строгий ответ (низкая температура)
    response_strict = call_llm(
        task_type='dialog',
        messages=[
            {
                "role": "user",
                "content": "Сколько калорий в 100г куриной грудки?"
            }
        ],
        temperature=0.1,  # Детерминированный ответ
        max_tokens=100
    )

    print("=== ПЕРЕОПРЕДЕЛЕНИЕ ПАРАМЕТРОВ ===")
    print(f"Креативный (temp=0.9): {response_creative['content'][:100]}...")
    print(f"Строгий (temp=0.1): {response_strict['content'][:100]}...")
    print()


# ========================================
# ПРИМЕР 6: Использование в агенте
# ========================================

def dialog_agent_example(user_message: str, client_context: dict):
    """
    Пример использования в dialog_agent.

    Args:
        user_message: Сообщение от клиента
        client_context: Контекст клиента (имя, цели, ограничения)
    """
    # Формируем system prompt с учётом контекста клиента
    system_prompt = f"""Ты ИИ-ассистент нутрициолога.

Клиент: {client_context.get('name', 'Клиент')}
Цель: {client_context.get('goal', 'Не указана')}
Ограничения: {', '.join(client_context.get('restrictions', [])) or 'Нет'}
Аллергии: {', '.join(client_context.get('allergies', [])) or 'Нет'}

Отвечай профессионально, учитывая индивидуальные особенности клиента."""

    # Вызов LLM
    response = call_llm(
        task_type='dialog',
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
    )

    # Логирование для отладки
    print(f"[AGENT] User: {user_message}")
    print(f"[AGENT] Model: {response['model']}")
    print(f"[AGENT] Response: {response['content']}")
    print(f"[AGENT] Tokens: {response['usage']['total_tokens']}")

    return response['content']


# ========================================
# ЗАПУСК ПРИМЕРОВ
# ========================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ utils/llm.py")
    print("="*60 + "\n")

    print("⚠️  Для запуска примеров нужны API ключи в .env:")
    print("   - GROQ_API_KEY")
    print("   - ANTHROPIC_API_KEY")
    print("   - GOOGLE_API_KEY\n")

    # Раскомментируйте для запуска с реальными API ключами:

    # example_dialog()
    # example_analytics()
    # example_experiment()
    # example_premium_client('premium')
    # example_premium_client('basic')
    # example_override_params()

    # Пример использования в агенте
    # client_context = {
    #     'name': 'Мария',
    #     'goal': 'Похудение на 5 кг',
    #     'restrictions': ['без глютена'],
    #     'allergies': ['орехи']
    # }
    # dialog_agent_example(
    #     "Что мне съесть на ужин?",
    #     client_context
    # )

    print("✅ Примеры готовы. Добавьте API ключи и раскомментируйте нужные функции.")
