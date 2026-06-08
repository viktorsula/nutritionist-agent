# GOTO

## Цель
Начать следующую сессию с Блока 5: `document_metadata` + `pgvector`, а затем перейти к коду, начиная с `database/client.py` и `database/queries.py`.

## Текущее состояние
- Supabase live-экземпляр доступен через `SUPABASE_URL` и `SUPABASE_SERVICE_KEY`.
- Таблицы из Блоков 1-4 доступны и проверены: `users`, `clients`, `client_profiles`, `wellness_plans`, `conversations`, `client_events`, `nutrition_plans`, `tasks`, `notification_schedule`, `audit_logs`, `system_settings`.
- Таблица `system_settings` содержит хотя бы одну запись.
- Таблицы Блока 5 (`document_metadata`, `knowledge_base`, `client_documents`) в live Supabase не найдены.
- Дополнительные таблицы, описанные в `docs/schema.sql` (`sessions`, `messages`, `nutrition_diary`, `measurements`, `nutritionist_tasks`), тоже не обнаружены как live таблицы.

## Что уже сделано в коде
- `database/client.py` уже существует и содержит базовые функции `get_supabase_client()` и `get_supabase_service_client()`.
- `database/models.py` уже содержит dataclass-описания для `DocumentMetadata`, `KnowledgeBaseChunk`, `ClientDocumentChunk`.
- `database/queries.py` уже содержит вставку и выборку для `document_metadata`, `knowledge_base` и `client_documents`.
- `.env.example` включает `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`, `OPENAI_API_KEY` и другие ключи.

## Различия и несоответствия
- `docs/progress.md` говорит, что Блок 5 ещё не сделан, но `docs/schema.sql` уже содержит определения для `document_metadata`, `knowledge_base`, `client_documents` и даже pgvector index.
- В live Supabase Блок 5 пока не задеплоен, несмотря на это определение в схеме.
- В `database/models.py` нет dataclass-моделей для таблиц Блоков 1-4, хотя они необходимы для полноценного слоя данных.
- `database/queries.py` содержит только базовые insert/select для блок 5, но не полный CRUD, не векторный поиск и не обработку ошибок.
- `requirements.txt` не содержит явно `pgvector`, `openai`, `langgraph` и другие зависимости, которые потребуются для полного Блока 5 + оркестрации.

## План на следующую сессию
1. Проверить live Supabase:
   - включена ли `vector` extension
   - существуют ли таблицы Блока 5
2. Если таблицы Блока 5 отсутствуют, задеплоить их по `docs/schema.sql`:
   - `document_metadata`
   - `knowledge_base`
   - `client_documents`
3. Убедиться, что `SUPABASE_SERVICE_ROLE_KEY` работает и что сервисный клиент имеет нужные права.
4. Расширить `database/client.py`:
   - добавить проверку конфигурации
   - добавить health check
   - поддержать явное подключение к сервисной роли и анонимному клиенту
5. Доработать `database/models.py`:
   - добавить модели для Block 1-4
   - сохранить текущие модели Block 5
6. Расширить `database/queries.py`:
   - CRUD для клиентских таблиц и базовых сущностей
   - весь поток работы с `document_metadata`
   - векторный поиск по `knowledge_base` и `client_documents`
   - обработку ошибок и валидацию embedding
7. Обновить `requirements.txt` по необходимым dependency для Блока 5 и LLM/embeddings.

## Вопросы для уточнения
1. Нужно ли сразу привести live Supabase в полное соответствие с `docs/schema.sql` или сначала ограничиться только Block 5?
2. Какая модель эмбеддингов будет использоваться: OpenAI, Hugging Face, или локальная?
3. Нужен ли в `database/client.py` только синхронный API, или сразу поддержка async?
4. Какие RLS-политики ожидаются для сервисной роли Supabase?
5. Требуется ли реализовывать на этом этапе весь CRUD для Block 1-4, или достаточно только поддержки Block 5 + минимального client wrapper?

## Команда "Plan agent"
- В репозитории нет явного скрипта `Plan agent`.
- Я выполнил внутренний анализ/планирование через агентное исследование и подготовил этот файл на основе текущей информации.

---

Файл `GOTO.md` готов как основа для следующей итерации.
