"""
Outbox system-сообщений (ADR-029): сохранённые намерения доставки.

Намерение (system_message_intents) пишется в транзакции бизнес-операции;
публикация через app.chat.system_publisher — после commit; повтор —
scripts/deliver_system_message_intents.py.
"""
