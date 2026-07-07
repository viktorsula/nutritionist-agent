"""
Постобработка текста ответа клиенту — слой ПРЕДСТАВЛЕНИЯ (не логика агента).

`tables_to_text` разворачивает Markdown-таблицы в плоский текст-список. Нужен потому, что
LLM (Claude) устойчиво форматирует данные с датами/значениями таблицей вопреки промпту, а
таблицы плохо читаются в чате и ЛОМАЮТСЯ в Telegram. Рассуждение и выбор данных остаются у
модели — меняется только вид на выходе.
"""

import re

# Строка-разделитель GFM-таблицы: ячейки из дефисов (с опц. выравниванием ':'), ≥2 колонок.
_SEP_RE = re.compile(r"^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)+\|?\s*$")


def _cells(line: str) -> list:
    """Разбить строку-ряд таблицы на ячейки (без ведущего/замыкающего '|')."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def tables_to_text(md: str) -> str:
    """
    Развернуть Markdown-таблицы в текст-список; остальной текст не трогать.

    Каждый ряд данных → строка `- ячейка — ячейка — …` (пустые ячейки и строка-заголовок
    отбрасываются). Таблица детектится по строке-разделителю (`|---|---|`) под строкой-заголовком,
    поэтому одиночные '|' в обычном тексте ложно не срабатывают. Не бросает исключений.
    """
    if not md or "|" not in md:
        return md

    try:
        lines = md.split("\n")
        out: list = []
        i, n = 0, len(lines)
        while i < n:
            # header (строка с '|') + следующая строка-разделитель → начало таблицы
            if i + 1 < n and "|" in lines[i] and _SEP_RE.match(lines[i + 1]):
                j = i + 2
                converted: list = []
                while j < n and "|" in lines[j] and lines[j].strip():
                    vals = [c for c in _cells(lines[j]) if c]
                    if vals:
                        converted.append("- " + " — ".join(vals))
                    j += 1
                out.extend(converted)
                i = j  # пропустить заголовок + разделитель + ряды
                continue
            out.append(lines[i])
            i += 1
        return "\n".join(out)
    except Exception:
        return md  # презентация не должна ронять ответ
