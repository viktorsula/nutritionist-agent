"""
Тестовый файл для проверки utils/llm.py

Проверяет:
1. Импорты работают
2. Структура функций корректна
3. DEFAULT_TASK_MODEL_MAPPING содержит нужные типы задач
4. Доступность провайдеров

Запуск:
    python3 utils/test_llm.py
"""

import sys
import os


def test_imports():
    """Проверка импортов"""
    print("=" * 60)
    print("ТЕСТ 1: Проверка импортов")
    print("=" * 60)

    try:
        from utils.llm import (
            call_llm,
            get_model_config,
            list_available_providers,
            list_task_types,
            DEFAULT_TASK_MODEL_MAPPING
        )
        print("✅ Все импорты успешны")
        return True
    except Exception as e:
        print(f"❌ Ошибка импорта: {e}")
        return False


def test_default_mapping():
    """Проверка DEFAULT_TASK_MODEL_MAPPING"""
    print("\n" + "=" * 60)
    print("ТЕСТ 2: Проверка DEFAULT_TASK_MODEL_MAPPING")
    print("=" * 60)

    from utils.llm import DEFAULT_TASK_MODEL_MAPPING

    expected_task_types = [
        'dialog',
        'analytics',
        'vision',
        'nutrition_analysis',
        'summary',
        'planning'
    ]

    print(f"\nОжидаемые task_type: {expected_task_types}")
    print(f"Найденные task_type: {list(DEFAULT_TASK_MODEL_MAPPING.keys())}")

    for task_type in expected_task_types:
        if task_type in DEFAULT_TASK_MODEL_MAPPING:
            config = DEFAULT_TASK_MODEL_MAPPING[task_type]
            print(f"\n✅ {task_type}:")
            print(f"   Provider: {config['provider']}")
            print(f"   Model: {config['model']}")
            print(f"   Temperature: {config['temperature']}")
            print(f"   Max tokens: {config['max_tokens']}")
            if 'description' in config:
                print(f"   Description: {config['description']}")
        else:
            print(f"❌ {task_type} отсутствует в маппинге!")
            return False

    print("\n✅ Все task_type корректно настроены")
    return True


def test_get_model_config():
    """Проверка get_model_config()"""
    print("\n" + "=" * 60)
    print("ТЕСТ 3: Проверка get_model_config()")
    print("=" * 60)

    from utils.llm import get_model_config

    try:
        # Проверяем корректный task_type
        config = get_model_config('dialog')
        print(f"\n✅ get_model_config('dialog') вернул:")
        print(f"   {config}")

        # Проверяем некорректный task_type
        try:
            config = get_model_config('nonexistent_task')
            print("❌ Должна была быть ошибка для несуществующего task_type")
            return False
        except ValueError as e:
            print(f"\n✅ Корректная ошибка для неизвестного task_type:")
            print(f"   {str(e)[:100]}...")

        return True

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False


def test_available_providers():
    """Проверка доступных провайдеров"""
    print("\n" + "=" * 60)
    print("ТЕСТ 4: Проверка доступных провайдеров")
    print("=" * 60)

    from utils.llm import list_available_providers

    available = list_available_providers()
    print(f"\nДоступные провайдеры: {available}")

    # Проверяем наличие API ключей
    print("\nПроверка переменных окружения:")
    keys = {
        'GROQ_API_KEY': 'Groq',
        'ANTHROPIC_API_KEY': 'Claude',
        'GOOGLE_API_KEY': 'Gemini'
    }

    for key, provider in keys.items():
        if os.environ.get(key):
            print(f"✅ {key} установлен ({provider} доступен)")
        else:
            print(f"⚠️  {key} не найден ({provider} недоступен)")

    if not available:
        print("\n⚠️  Ни один провайдер не доступен.")
        print("   Установите API ключи в .env для тестирования реальных вызовов")
    else:
        print(f"\n✅ Доступно провайдеров: {len(available)}")

    return True


def test_task_types_list():
    """Проверка list_task_types()"""
    print("\n" + "=" * 60)
    print("ТЕСТ 5: Проверка list_task_types()")
    print("=" * 60)

    from utils.llm import list_task_types

    task_types = list_task_types()
    print(f"\nВсе task_type с описаниями:")
    for task, description in task_types.items():
        print(f"  • {task}: {description}")

    print(f"\n✅ Всего task_type: {len(task_types)}")
    return True


def test_call_llm_validation():
    """Проверка валидации параметров call_llm()"""
    print("\n" + "=" * 60)
    print("ТЕСТ 6: Проверка валидации call_llm()")
    print("=" * 60)

    from utils.llm import call_llm

    # Тест 1: Без task_type и без provider+model
    try:
        call_llm(messages=[{"role": "user", "content": "test"}])
        print("❌ Должна была быть ошибка при отсутствии task_type и provider+model")
        return False
    except ValueError as e:
        print(f"✅ Корректная ошибка при отсутствии параметров:")
        print(f"   {str(e)[:80]}...")

    # Тест 2: Пустые messages
    try:
        call_llm(messages=[], task_type='dialog')
        print("❌ Должна была быть ошибка при пустых messages")
        return False
    except ValueError as e:
        print(f"\n✅ Корректная ошибка при пустых messages:")
        print(f"   {str(e)}")

    print("\n✅ Валидация параметров работает корректно")
    return True


def run_all_tests():
    """Запуск всех тестов"""
    print("\n" + "=" * 60)
    print("ТЕСТИРОВАНИЕ utils/llm.py")
    print("=" * 60)

    tests = [
        test_imports,
        test_default_mapping,
        test_get_model_config,
        test_available_providers,
        test_task_types_list,
        test_call_llm_validation
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА в {test.__name__}: {e}")
            results.append(False)

    # Итоги
    print("\n" + "=" * 60)
    print("ИТОГИ ТЕСТИРОВАНИЯ")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"\nПройдено: {passed}/{total}")

    if passed == total:
        print("\n✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ")
        print("\nutils/llm.py готов к использованию!")
        print("\nСледующие шаги:")
        print("1. Добавьте API ключи в .env для реальных вызовов")
        print("2. Обновите requirements.txt (groq, anthropic, google-generativeai)")
        print("3. Создайте агентов, использующих call_llm()")
    else:
        print(f"\n⚠️  ПРОВАЛЕНО ТЕСТОВ: {total - passed}")
        return False

    return True


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
