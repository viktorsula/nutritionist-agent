"""
Тест _execute_one: update/upsert-цепочки НЕ вызывают `.single()`.

Регрессия (прод): на `supabase==2.10.0` билдер `.update().eq()` — это
`SyncFilterRequestBuilder` без метода `.single()` → 6 update-путей молча падали
(`'SyncFilterRequestBuilder' object has no attribute 'single'`); в т.ч. скользящая
сводка диалога (долговременная память) не записывалась. Локальная 2.31 маскировала.

Здесь эмулируем прод-билдер (без `.single()`) и проверяем, что `_execute_one`
корректно берёт первую строку из списка `data`, а вызванная цепочка не трогает `.single()`.
"""

from database.queries import _execute_one


class _ProdBuilder:
    """Билдер как на проде 2.10.0: есть execute(), НЕТ single()."""

    def __init__(self, data):
        self._data = data

    def execute(self):
        class _Resp:
            pass

        r = _Resp()
        r.data = self._data
        return r

    def __getattr__(self, name):
        # Явно воспроизводим прод: обращение к .single() — ошибка.
        if name == "single":
            raise AttributeError("'SyncFilterRequestBuilder' object has no attribute 'single'")
        raise AttributeError(name)


def test_execute_one_returns_first_row_from_list():
    row = {"id": "c1", "conversation_summary": "abc"}
    assert _execute_one(_ProdBuilder([row])) == row


def test_execute_one_returns_none_on_empty_list():
    assert _execute_one(_ProdBuilder([])) is None


def test_execute_one_does_not_call_single():
    # Если бы код где-то дёрнул .single() на этом билдере — тест упал бы AttributeError.
    assert _execute_one(_ProdBuilder([{"id": "x"}])) == {"id": "x"}
