#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram-бот для заявок Firenze Buyer Studio.
Версия под aiogram 3 и Python 3.12+

ФУНКЦИИ:
- Собирает заявку по шагам.
- Шаги 2 и 3 (размер/цвет и бюджет) можно пропустить.
- Отправляет готовую заявку в закрытый канал (ID канала см. ниже).
- Для Railway: поднимает health-сервер на динамическом PORT (/health), чтобы сервис считался "живым".
- Подробные логи в stdout (видно в Railway Logs).
"""

import asyncio
import logging
import os
import sys

from aiohttp import web

from aiogram import Bot, Dispatcher, F, types, Router
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.client.default import DefaultBotProperties

# =========================
# 1. НАСТРОЙКИ
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN not set! Please add it to environment variables.")

# 👉 ID твоего закрытого канала "Заявки Firenze Buyer Studio"
CHANNEL_ID = -1003650413645

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("firenze-bot")

# Dispatcher + storage + router
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# Глобальный bot (инициализируем в main)
bot: Bot


# =========================
# 2. СОСТОЯНИЯ (FSM)
# =========================

class Form(StatesGroup):
    product = State()    # Шаг 1: товар (фото/описание)
    options = State()    # Шаг 2: размер/цвет (можно пропустить)
    budget = State()     # Шаг 3: бюджет (можно пропустить)
    city = State()       # Шаг 4: город/доставка
    contact = State()    # Шаг 5: контакт


# =========================
# 3. КЛАВИАТУРЫ
# =========================

def start_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📝 Оформить заявку")]],
        resize_keyboard=True
    )


def skip_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Пропустить")]],
        resize_keyboard=True
    )


def new_request_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📝 Оформить ещё одну заявку")]],
        resize_keyboard=True
    )


# =========================
# 4. HEALTH SERVER (Railway PORT)
# =========================

async def start_health_server() -> web.AppRunner:
    """
    Мини-сервер для Railway: слушает PORT и отвечает /health.
    Не мешает aiogram polling.
    """
    port = int(os.getenv("PORT", "8080"))
    app = web.Application()

    async def health(request):
        return web.json_response({"status": "ok"})

    app.router.add_get("/health", health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()

    logger.info("Health server listening on 0.0.0.0:%s (GET /health)", port)
    return runner


# =========================
# 5. ОБРАБОТЧИКИ КОМАНД
# =========================

@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()

    logger.info(
        "CMD /start from user_id=%s username=%s",
        message.from_user.id,
        message.from_user.username
    )

    text = (
        "Привет! 👋\n"
        "Я бот Анастасии, байера из Италии.\n\n"
        "С помощью меня вы можете оформить заявку на покупку товара из Италии.\n"
        "Нажмите кнопку ниже, чтобы начать."
    )
    await message.answer(text, reply_markup=start_keyboard())


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    logger.info("CMD /help from user_id=%s", message.from_user.id)
    await message.answer(
        "Я помогаю оформить заявку на покупку товара из Италии.\n"
        "Нажмите /start, чтобы начать."
    )


@router.message(F.text.contains("Оформить"))
async def start_form(message: types.Message, state: FSMContext):
    logger.info("Start form from user_id=%s", message.from_user.id)

    await state.set_state(Form.product)
    text = (
        "1️⃣ Пришлите, пожалуйста, <b>фото, ссылку или описание товара</b>, "
        "который вы хотите купить.\n\n"
        "Можно переслать фото из Instagram/Pinterest или ссылку с сайта бренда."
    )
    await message.answer(text, reply_markup=types.ReplyKeyboardRemove())


@router.message(Command("cancel"), StateFilter("*"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    logger.info("CMD /cancel from user_id=%s state=%s", message.from_user.id, await state.get_state())
    await state.clear()
    await message.answer(
        "Заявка отменена. Если хотите начать заново — нажмите кнопку ниже.",
        reply_markup=start_keyboard()
    )


# =========================
# 6. ШАГ 1 — ТОВАР (ОБЯЗАТЕЛЬНО)
# =========================

@router.message(StateFilter(Form.product), F.content_type.in_(
    [types.ContentType.PHOTO, types.ContentType.TEXT]
))
async def process_product(message: types.Message, state: FSMContext):
    logger.info(
        "Step 1 (product) from user_id=%s content_type=%s",
        message.from_user.id,
        message.content_type
    )

    data = {}

    if message.photo:
        largest_photo = message.photo[-1]
        data["product_photo_id"] = largest_photo.file_id
        caption = message.caption if message.caption else "(без описания)"
        data["product_text"] = caption
    else:
        data["product_photo_id"] = None
        data["product_text"] = message.text if message.text else "(без описания)"

    await state.update_data(**data)

    await state.set_state(Form.options)
    text = (
        "2️⃣ Напишите, пожалуйста, <b>размер, цвет или особые пожелания</b>.\n"
        "Если не знаете или не хотите указывать — нажмите «Пропустить»."
    )
    await message.answer(text, reply_markup=skip_keyboard())


# =========================
# 7. ШАГ 2 — РАЗМЕР/ЦВЕТ (МОЖНО ПРОПУСТИТЬ)
# =========================

@router.message(StateFilter(Form.options), F.text)
async def process_options(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    logger.info("Step 2 (options) from user_id=%s text=%s", message.from_user.id, text[:120])

    if text.lower() == "пропустить":
        options = "Не указано"
    else:
        options = text

    await state.update_data(options=options)

    await state.set_state(Form.budget)
    msg = (
        "3️⃣ Хотите указать <b>бюджет</b>? Можно написать сумму или диапазон.\n"
        "Например: до 500 € или 300–400 €.\n\n"
        "Если не хотите указывать — напишите или нажмите «Пропустить»."
    )
    await message.answer(msg, reply_markup=skip_keyboard())


# =========================
# 8. ШАГ 3 — БЮДЖЕТ (МОЖНО ПРОПУСТИТЬ)
# =========================

@router.message(StateFilter(Form.budget), F.text)
async def process_budget(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    logger.info("Step 3 (budget) from user_id=%s text=%s", message.from_user.id, text[:120])

    if text.lower() == "пропустить":
        budget = "Не указан"
    else:
        budget = text

    await state.update_data(budget=budget)

    await state.set_state(Form.city)
    msg = (
        "4️⃣ В какой <b>город</b> нужна доставка?\n"
        "Если важно — укажите, предпочитаете личную встречу или курьера."
    )
    await message.answer(msg, reply_markup=types.ReplyKeyboardRemove())


# =========================
# 9. ШАГ 4 — ГОРОД (ОБЯЗАТЕЛЬНО)
# =========================

@router.message(StateFilter(Form.city), F.text)
async def process_city(message: types.Message, state: FSMContext):
    city_delivery = (message.text or "").strip() or "(не указано)"
    logger.info("Step 4 (city) from user_id=%s city=%s", message.from_user.id, city_delivery[:120])

    await state.update_data(city_delivery=city_delivery)

    await state.set_state(Form.contact)
    msg = (
        "5️⃣ Оставьте, пожалуйста, <b>контакт для связи</b>:\n"
        "Ваш Telegram @username или номер телефона."
    )
    await message.answer(msg)


# =========================
# 10. ШАГ 5 — КОНТАКТ + ОТПРАВКА ЗАЯВКИ
# =========================

@router.message(StateFilter(Form.contact), F.text)
async def process_contact(message: types.Message, state: FSMContext):
    contact = (message.text or "").strip() or "(не указан)"
    logger.info("Step 5 (contact) from user_id=%s contact=%s", message.from_user.id, contact[:120])

    await state.update_data(contact=contact)

    data = await state.get_data()
    await state.clear()

    user = message.from_user
    tg_username = f"@{user.username}" if user.username else f"id: {user.id}"

    product_text = data.get("product_text", "(без описания)")
    product_photo_id = data.get("product_photo_id")
    options = data.get("options", "Не указано")
    budget = data.get("budget", "Не указан")
    city_delivery = data.get("city_delivery", "(не указано)")

    application_text = (
        "🛍 <b>Новая заявка</b>\n\n"
        f"👤 <b>Клиент:</b> {tg_username}\n\n"
        f"<b>1. Товар:</b>\n{product_text}\n\n"
        f"<b>2. Размер / цвет / пожелания:</b>\n{options}\n\n"
        f"<b>3. Бюджет:</b>\n{budget}\n\n"
        f"<b>4. Город / доставка:</b>\n{city_delivery}\n\n"
        f"<b>5. Контакт:</b>\n{contact}\n"
    )

    try:
        if product_photo_id:
            logger.info("Sending application to channel (photo) user_id=%s", user.id)
            await bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=product_photo_id,
                caption=application_text
            )
        else:
            logger.info("Sending application to channel (text) user_id=%s", user.id)
            await bot.send_message(
                chat_id=CHANNEL_ID,
                text=application_text
            )
        logger.info("Application sent successfully user_id=%s", user.id)
    except Exception:
        logger.exception("Ошибка при отправке заявки в канал user_id=%s", user.id)
        await message.answer(
            "⚠️ Произошла ошибка при отправке заявки в канал. "
            "Сообщите, пожалуйста, Анастасии."
        )
        return

    await message.answer(
        "Спасибо! 💛\n"
        "Ваша заявка отправлена Анастасии.\n"
        "Она подберёт варианты и свяжется с вами.",
        reply_markup=new_request_keyboard()
    )


# =========================
# 11. ФОЛБЭК — ЛЮБОЙ ДРУГОЙ ТЕКСТ
# =========================

@router.message()
async def fallback(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    logger.info("Fallback from user_id=%s state=%s text=%s",
                message.from_user.id,
                current_state,
                (message.text or "")[:120])

    if current_state is None:
        await message.answer(
            "Чтобы оформить заявку, нажмите кнопку ниже или введите /start.",
            reply_markup=start_keyboard()
        )
    else:
        await message.answer(
            "Пожалуйста, ответьте на текущий вопрос или введите /cancel, "
            "чтобы отменить заявку."
        )


# =========================
# 12. ЗАПУСК БОТА
# =========================

async def main():
    global bot

    logger.info("🚀 Starting Firenze Buyer Studio bot...")
    logger.info("Python: %s", sys.version.replace("\n", " "))
    logger.info(
        "ENV: PORT=%s LOG_LEVEL=%s BOT_TOKEN=%s",
        os.getenv("PORT"),
        os.getenv("LOG_LEVEL"),
        "SET" if os.getenv("BOT_TOKEN") else "MISSING"
    )

    if not BOT_TOKEN:
        logger.critical("❌ BOT_TOKEN not set! Please add it to environment variables.")
        raise SystemExit(1)

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML")
    )

    # Health server (Railway-friendly)
    health_runner = await start_health_server()

    try:
        logger.info("✅ Bot initialized. Starting polling...")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception:
        logger.exception("💥 Fatal error while polling")
        raise
    finally:
        logger.info("🧹 Shutting down...")
        try:
            await health_runner.cleanup()
        except Exception:
            logger.exception("Health server cleanup failed")
        try:
            await bot.session.close()
        except Exception:
            logger.exception("Bot session close failed")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
