"""
Turn-буфер входящих Telegram-сообщений (Фаза 2).

Зачем: клиент часто шлёт серию коротких сообщений подряд («вешу 80», «и съел кашу»,
«как дела?») или альбом из нескольких фото. Без буфера каждый апдейт обрабатывается
отдельно — лишние вызовы графа и спам ответами. Буфер копит сообщения по чату и после
паузы («тишины») обрабатывает их одним «ходом»:

- подряд идущие ТЕКСТОВЫЕ сообщения склеиваются в один текст (определитель Шага 1 сам
  разрежет на сегменты);
- фото с одним media_group_id (альбом) склеиваются в один ход: обрабатываем ПЕРВОЕ фото
  с общей подписью и сообщаем «получено N фото» (Вариант 1 — без переделки vision);
- голос/документ/одиночное фото — отдельным ходом, как раньше.

Debounce настраивается env TELEGRAM_TURN_DEBOUNCE_SEC (секунды). Значение ≤ 0 ВЫКЛЮЧАЕТ
буфер — сообщение обрабатывается немедленно (старое поведение, аварийный выключатель).

Допущение: один процесс бота (буфер в памяти). На Render — один uvicorn-воркер.
"""

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# chat_id -> {"items": [item, ...], "task": asyncio.Task | None}
_buffers: Dict[int, Dict[str, Any]] = {}

DEFAULT_DEBOUNCE_SEC = 7.0


def _debounce_sec() -> float:
    """Окно debounce из env (сек). ≤ 0 — буфер выключен."""
    raw = os.environ.get("TELEGRAM_TURN_DEBOUNCE_SEC")
    if raw is None:
        return DEFAULT_DEBOUNCE_SEC
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_DEBOUNCE_SEC


async def enqueue(item: Dict[str, Any]) -> None:
    """
    Кладёт сообщение в буфер чата и (пере)взводит таймер сброса.

    item: {kind, update, message, metadata, media_group_id?} — медиа-байты уже скачаны
    вызывающим хендлером и лежат в metadata.
    """
    # Аварийный выключатель: без debounce обрабатываем сразу (старое поведение).
    if _debounce_sec() <= 0:
        await _dispatch_turns(_group([item]))
        return

    chat_id = item["update"].effective_chat.id
    buf = _buffers.setdefault(chat_id, {"items": [], "task": None})
    buf["items"].append(item)

    task = buf.get("task")
    if task and not task.done():
        task.cancel()
    buf["task"] = asyncio.create_task(_flush_after(chat_id, _debounce_sec()))


async def _flush_after(chat_id: int, delay: float) -> None:
    """Ждёт паузу; если за это время не пришло новое сообщение — сбрасывает буфер чата."""
    try:
        await asyncio.sleep(delay)
    except asyncio.CancelledError:
        return  # пришло новое сообщение — таймер перевзведён, этот сброс отменён

    buf = _buffers.pop(chat_id, None)
    if not buf or not buf["items"]:
        return
    try:
        await _dispatch_turns(_group(buf["items"]))
    except Exception as e:  # noqa: BLE001 — буфер не должен падать молча
        logger.exception(f"turn_buffer flush failed for chat {chat_id}: {e}")


def _merge_single_photo_with_text(items: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    """
    Частый случай: ОДНО одиночное фото + текст(ы) в окне (без голоса/документа/альбома)
    → один photo-ход, где текст(ы) становятся подписью фото.

    Иначе фото и текст ушли бы РАЗНЫМИ ходами → два ответа на один смысловой ход
    (фото → vision, текст → diary-clarify). Подпись передаётся определителю вместе с
    фото, и он видит цельный ход. Возвращает None, если случай не подходит (тогда —
    общая логика _group).
    """
    photos = [it for it in items if it["kind"] == "photo" and not it.get("media_group_id")]
    album = [it for it in items if it["kind"] == "photo" and it.get("media_group_id")]
    voice_doc = [it for it in items if it["kind"] in ("voice", "document")]
    texts = [it for it in items if it["kind"] == "text"]

    if len(photos) != 1 or album or voice_doc or not texts:
        return None

    photo = photos[0]
    caption: List[str] = []
    for it in items:  # сохраняем порядок буфера: подпись фото + тексты как пришли
        if it is photo:
            if photo.get("message"):
                caption.append(photo["message"])
        elif it["kind"] == "text" and it.get("message"):
            caption.append(it["message"])

    merged = dict(photo)
    merged["message"] = "\n".join(c for c in caption if c)
    return [{"type": "single", "item": merged}]


def _group(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Группирует буфер в «ходы» с сохранением порядка:
    - одиночное фото + текст(ы) → один photo-ход (текст = подпись, см. _merge_single_photo_with_text);
    - подряд текст → один text-ход (склейка через \\n);
    - подряд фото с одним media_group_id → один album-ход;
    - прочее (одиночное фото / голос / документ) → single-ход.
    """
    merged = _merge_single_photo_with_text(items)
    if merged is not None:
        return merged

    turns: List[Dict[str, Any]] = []
    text_acc: List[str] = []
    text_update = None

    def flush_text() -> None:
        nonlocal text_acc, text_update
        if text_acc:
            turns.append({
                "type": "text",
                "update": text_update,
                "message": "\n".join(t for t in text_acc if t),
            })
            text_acc = []
            text_update = None

    i, n = 0, len(items)
    while i < n:
        it = items[i]
        if it["kind"] == "text":
            text_acc.append(it.get("message") or "")
            text_update = it["update"]
            i += 1
        elif it["kind"] == "photo" and it.get("media_group_id"):
            flush_text()
            mg = it["media_group_id"]
            group: List[Dict[str, Any]] = []
            while (
                i < n
                and items[i]["kind"] == "photo"
                and items[i].get("media_group_id") == mg
            ):
                group.append(items[i])
                i += 1
            turns.append({"type": "album", "items": group})
        else:
            flush_text()
            turns.append({"type": "single", "item": it})
            i += 1
    flush_text()
    return turns


async def _dispatch_turns(turns: List[Dict[str, Any]]) -> None:
    """Последовательно отправляет каждый «ход» в роутер (порядок ответов сохраняется)."""
    from .handlers import _dispatch_to_router  # ленивый импорт — избегаем цикла

    for turn in turns:
        if turn["type"] == "text":
            upd = turn["update"]
            await _typing(upd)
            await _dispatch_to_router(
                upd, None,
                message=turn["message"],
                message_type="text",
                metadata={
                    "telegram_id": upd.effective_user.id,
                    "username": upd.effective_user.username or "unknown",
                    "message_id": upd.message.message_id,
                },
            )
        elif turn["type"] == "album":
            await _dispatch_album(turn["items"])
        else:  # single
            it = turn["item"]
            await _typing(it["update"])
            await _dispatch_to_router(
                it["update"], None,
                message=it.get("message") or "",
                message_type=it["kind"],
                metadata=it["metadata"],
            )


async def _dispatch_album(items: List[Dict[str, Any]]) -> None:
    """Альбом (Вариант 1): анализируем ПЕРВОЕ фото с общей подписью; сообщаем «получено N фото»."""
    from .handlers import _dispatch_to_router

    first = items[0]
    count = len(items)
    caption = next((g.get("message") for g in items if g.get("message")), "") or ""

    if count > 1:
        try:
            await first["update"].message.reply_text(
                f"📸 Получено фото: {count}. Анализирую первое."
            )
        except Exception:  # noqa: BLE001 — heads-up не критичен
            pass

    metadata = dict(first["metadata"])
    metadata["album_count"] = count

    await _typing(first["update"])
    await _dispatch_to_router(
        first["update"], None,
        message=caption,
        message_type="photo",
        metadata=metadata,
    )


async def _typing(update) -> None:
    """Показывает индикатор «печатает…» перед обработкой хода (best-effort)."""
    try:
        await update.message.chat.send_action("typing")
    except Exception:  # noqa: BLE001
        pass
