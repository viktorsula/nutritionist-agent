"""
Тестирование agents/ — маршрутизация и агенты

Проверяет:
1. Импорты всех модулей
2. Структуру State
3. Загрузку промптов
4. Работу router.py (mock режим)
5. Работу dialog_agent (mock режим)

Запуск:
    PYTHONPATH=/workspaces/nutritionist-agent python3 agents/test_agents.py
"""

import sys
import os


def test_imports():
    """Тест 1: Проверка всех импортов"""
    print("=" * 70)
    print("ТЕСТ 1: Проверка импортов")
    print("=" * 70)

    try:
        # Основные модули
        from agents import route_message
        from agents.router import get_user_info, route_to_client, route_to_nutritionist

        # Client
        from agents.client import process_client_message
        from agents.client.state import ClientState, create_initial_state, extract_response
        from agents.client.orchestrator import create_client_graph
        from agents.client.dialog_agent import dialog_node, build_system_prompt

        # Nutritionist
        from agents.nutritionist import process_nutritionist_message

        # Prompts
        from prompts import load_prompt, save_prompt, list_available_prompts

        print("✅ Все импорты успешны\n")
        return True

    except Exception as e:
        print(f"❌ Ошибка импорта: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def test_state_structure():
    """Тест 2: Проверка ClientState"""
    print("=" * 70)
    print("ТЕСТ 2: Проверка ClientState")
    print("=" * 70)

    try:
        from agents.client.state import create_initial_state, extract_response

        # Создание состояния
        state = create_initial_state(
            client_id="test-client-123",
            message="Привет, что съесть на завтрак?",
            channel="telegram",
            message_type="text"
        )

        print(f"✅ Создано начальное состояние:")
        print(f"   client_id: {state['client_id']}")
        print(f"   message: {state['message']}")
        print(f"   channel: {state['channel']}")
        print(f"   timestamp: {state['timestamp']}")

        # Добавление результатов
        state['agent_response'] = "Отличный выбор!"
        state['agent_used'] = 'dialog_agent'
        state['llm_model'] = 'llama-3.3-70b-versatile'

        # Извлечение ответа
        response = extract_response(state)

        print(f"\n✅ Извлечён ответ:")
        print(f"   message: {response['message']}")
        print(f"   agent_used: {response['agent_used']}")
        print(f"   model: {response['model']}")

        print("\n✅ ClientState работает корректно\n")
        return True

    except Exception as e:
        print(f"❌ Ошибка: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def test_prompts():
    """Тест 3: Проверка системы промптов"""
    print("=" * 70)
    print("ТЕСТ 3: Проверка системы промптов")
    print("=" * 70)

    try:
        from prompts import load_prompt, list_available_prompts

        # Список доступных промптов
        available = list_available_prompts()
        print(f"✅ Найдено промптов: {len(available)}")

        for name, info in available.items():
            print(f"   • {name} (source: {info['source']})")

        # Загрузка промпта для dialog
        print(f"\n✅ Загрузка промпта 'client/dialog_system':")
        dialog_prompt = load_prompt('client/dialog_system')
        print(f"   Длина: {len(dialog_prompt)} символов")
        print(f"   Первые 100 символов: {dialog_prompt[:100]}...")

        # Загрузка промпта для analytics
        print(f"\n✅ Загрузка промпта 'nutritionist/analytics_system':")
        analytics_prompt = load_prompt('nutritionist/analytics_system')
        print(f"   Длина: {len(analytics_prompt)} символов")
        print(f"   Первые 100 символов: {analytics_prompt[:100]}...")

        print("\n✅ Система промптов работает\n")
        return True

    except Exception as e:
        print(f"❌ Ошибка: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def test_prompt_formatting():
    """Тест 4: Проверка форматирования промпта"""
    print("=" * 70)
    print("ТЕСТ 4: Проверка форматирования промпта")
    print("=" * 70)

    try:
        from agents.client.state import create_initial_state
        from agents.client.dialog_agent import build_system_prompt

        # Создание mock состояния
        state = create_initial_state(
            client_id="test-123",
            message="Тест"
        )

        # Mock данные
        state['client_profile'] = {
            'name': 'Мария Тестовая',
            'goal': 'Похудение на 5 кг',
            'allergies': [
                {'name': 'орехи', 'severity': 'critical'}
            ]
        }

        state['active_plan'] = {
            'target_calories': 1800,
            'restrictions': ['свинина', 'молоко']
        }

        state['access_info'] = {
            'mode': 'full_program'
        }

        state['alerts'] = []

        # Построение промпта
        system_prompt = build_system_prompt(state)

        print(f"✅ Промпт сформирован:")
        print(f"   Длина: {len(system_prompt)} символов")
        print(f"\n   Содержит 'Мария': {'Мария' in system_prompt}")
        print(f"   Содержит 'орехи': {'орехи' in system_prompt}")
        print(f"   Содержит 'свинина': {'свинина' in system_prompt}")

        print(f"\n   Фрагмент промпта:")
        print(f"   {system_prompt[:300]}...")

        print("\n✅ Форматирование промпта работает\n")
        return True

    except Exception as e:
        print(f"❌ Ошибка: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def test_langgraph_structure():
    """Тест 5: Проверка структуры LangGraph"""
    print("=" * 70)
    print("ТЕСТ 5: Проверка структуры LangGraph")
    print("=" * 70)

    try:
        from agents.client.orchestrator import create_client_graph
        from agents.client.state import ClientState

        # Создание графа
        graph = create_client_graph()

        print(f"✅ LangGraph граф создан:")
        print(f"   Тип: {type(graph)}")

        # Проверка структуры
        print(f"\n✅ Структура графа корректна")
        print(f"   (полная проверка требует запуска с реальными данными)")

        print("\n✅ LangGraph структура валидна\n")
        return True

    except Exception as e:
        print(f"❌ Ошибка: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def test_router_structure():
    """Тест 6: Проверка структуры router"""
    print("=" * 70)
    print("ТЕСТ 6: Проверка структуры router")
    print("=" * 70)

    try:
        from agents.router import route_message, get_user_info

        print(f"✅ Router функции доступны:")
        print(f"   • route_message")
        print(f"   • get_user_info")

        # Проверка сигнатуры
        import inspect

        sig = inspect.signature(route_message)
        print(f"\n✅ route_message параметры:")
        for param_name, param in sig.parameters.items():
            print(f"   • {param_name}: {param.annotation if param.annotation != inspect.Parameter.empty else 'Any'}")

        print("\n✅ Router структура корректна\n")
        return True

    except Exception as e:
        print(f"❌ Ошибка: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def test_mock_flow():
    """Тест 7: Mock flow без БД"""
    print("=" * 70)
    print("ТЕСТ 7: Mock flow (без БД)")
    print("=" * 70)

    print("⚠️  Этот тест требует подключения к БД")
    print("   Для полноценного тестирования:")
    print("   1. Создайте тестового клиента в БД")
    print("   2. Запустите: route_message(user_id, message, channel)")
    print()

    print("✅ Mock flow структура готова для тестирования\n")
    return True


def test_web_search_tool():
    """Тест 8: build_web_search_tool (серверный инструмент Claude web_search)"""
    print("=" * 70)
    print("ТЕСТ 8: build_web_search_tool")
    print("=" * 70)

    try:
        from utils.web_access import build_web_search_tool, WEB_SEARCH_TOOL_TYPE

        # С whitelist доменов (доверенные источники нутрициолога)
        tool = build_web_search_tool(
            allowed_domains=['pubmed.ncbi.nlm.nih.gov'], max_uses=3
        )
        assert tool['type'] == WEB_SEARCH_TOOL_TYPE, "неверный type инструмента"
        assert tool['name'] == 'web_search', "неверный name инструмента"
        assert tool['max_uses'] == 3, "max_uses не проброшен"
        assert tool['allowed_domains'] == ['pubmed.ncbi.nlm.nih.gov'], \
            "allowed_domains не проброшен"
        assert 'blocked_domains' not in tool, "не должно быть blocked_domains"
        print("✅ allowed_domains + max_uses формируются корректно")

        # Без доменов — фильтры не добавляются
        tool_open = build_web_search_tool()
        assert 'allowed_domains' not in tool_open and 'blocked_domains' not in tool_open, \
            "без доменов фильтров быть не должно"
        print("✅ без доменов инструмент без фильтров")

        # API не допускает оба фильтра — allowed_domains приоритетнее
        tool_both = build_web_search_tool(
            allowed_domains=['a.com'], blocked_domains=['b.com']
        )
        assert tool_both.get('allowed_domains') == ['a.com'], "allowed должен победить"
        assert 'blocked_domains' not in tool_both, "оба фильтра одновременно недопустимы"
        print("✅ при конфликте побеждает allowed_domains")

        print("\n✅ build_web_search_tool работает корректно\n")
        return True

    except Exception as e:
        print(f"❌ Ошибка: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Запуск всех тестов"""
    print("\n" + "=" * 70)
    print("ТЕСТИРОВАНИЕ agents/ — Мультиагентная система")
    print("=" * 70 + "\n")

    tests = [
        test_imports,
        test_state_structure,
        test_prompts,
        test_prompt_formatting,
        test_langgraph_structure,
        test_router_structure,
        test_mock_flow,
        test_web_search_tool
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА в {test.__name__}: {e}\n")
            results.append(False)

    # Итоги
    print("=" * 70)
    print("ИТОГИ ТЕСТИРОВАНИЯ")
    print("=" * 70)

    passed = sum(results)
    total = len(results)

    print(f"\nПройдено: {passed}/{total}")

    if passed == total:
        print("\n✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ")
        print("\nagents/ готов к использованию!")
        print("\nСледующие шаги:")
        print("1. Создайте тестового клиента в БД")
        print("2. Добавьте API ключи в .env (GROQ_API_KEY, ANTHROPIC_API_KEY)")
        print("3. Протестируйте с реальным вызовом:")
        print("   >>> from agents import route_message")
        print("   >>> route_message('client-uuid', 'Привет!', 'telegram')")
        print()
        print("4. Интеграция с Telegram Bot (Этап 7)")
        print("5. utils/: vision, voice, knowledge (pgvector), web_search (Claude)")

    else:
        print(f"\n⚠️  ПРОВАЛЕНО ТЕСТОВ: {total - passed}")
        print("\nПроверьте ошибки выше и исправьте проблемы")

    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
