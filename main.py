#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram bot for Firenze Buyer Studio requests.
Version for aiogram 3 and Python 3.12+

FEATURES:
- Collects requests step by step.
- Steps 2 and 3 (size/color and budget) can be skipped.
- Sends completed request to a private channel (channel ID below).
- For Railway: starts a health server on dynamic PORT (/health) to keep the service alive.
- Detailed logs in stdout (visible in Railway Logs).
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
# 1. CONFIGURATION
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN not set! Please add it to environment variables.")

# 👉 ID of your private channel "Firenze Buyer Studio Requests"
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

# Global bot (initialized in main)
bot: Bot


# =========================
# 2. STATES (FSM)
# =========================

class Form(StatesGroup):
    product = State()    # Step 1: product (photo/description)
    options = State()    # Step 2: size/color (optional)
    budget = State()     # Step 3: budget (optional)
    city = State()       # Step 4: city/delivery
    contact = State()    # Step 5: contact


# =========================
# 3. KEYBOARDS
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
    Mini server for Railway: listens on PORT and responds to /health.
    Does not interfere with aiogram polling.
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
# 5. COMMAND HANDLERS
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
# 6. STEP 1 — PRODUCT (REQUIRED)
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
        caption = message.caption if message.caption else "(no description)"
        data["product_text"] = caption
    else:
        data["product_photo_id"] = None
        data["product_text"] = message.text if message.text else "(no description)"

    await state.update_data(**data)

    await state.set_state(Form.options)
    text = (
        "2️⃣ Please specify <b>size, color, or special preferences</b>.\n"
        "If you don’t know or don’t want to specify — press “Skip”."
    )
    await message.answer(text, reply_markup=skip_keyboard())


# =========================
# 7. STEP 2 — SIZE/COLOR (OPTIONAL)
# =========================

@router.message(StateFilter(Form.options), F.text)
async def process_options(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    logger.info("Step 2 (options) from user_id=%s text=%s", message.from_user.id, text[:120])

    if text.lower() == "пропустить":
        options = "Not specified"
    else:
        options = text

    await state.update_data(options=options)

    await state.set_state(Form.budget)
    msg = (
        "3️⃣ Would you like to specify a <b>budget</b>? You can write an amount or a range (minimum from 20 €).\n"
        "For example: up to 500 € or 300–400 €.\n\n"
        "If you don’t want to specify — write or press “Skip”."
    )
    await message.answer(msg, reply_markup=skip_keyboard())


# =========================
# 8. STEP 3 — BUDGET (OPTIONAL)
# =========================

@router.message(StateFilter(Form.budget), F.text)
async def process_budget(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    logger.info("Step 3 (budget) from user_id=%s text=%s", message.from_user.id, text[:120])

    if text.lower() == "пропустить":
        budget = "Not specified"
    else:
        budget = text

    await state.update_data(budget=budget)

    await state.set_state(Form.city)
    msg = (
        "4️⃣ Which <b>city</b> should the delivery be sent to?\n"
        "If relevant — specify pickup (only in Moscow) or delivery service."
    )
    await message.answer(msg, reply_markup=types.ReplyKeyboardRemove())


# =========================
# 9. STEP 4 — CITY (REQUIRED)
# =========================

@router.message(StateFilter(Form.city), F.text)
async def process_city(message: types.Message, state: FSMContext):
    city_delivery = (message.text or "").strip() or "(not specified)"
    logger.info("Step 4 (city) from user_id=%s city=%s", message.from_user.id, city_delivery[:120])

    await state.update_data(city_delivery=city_delivery)

    await state.set_state(Form.contact)
    msg = (
        "5️⃣ Please leave your <b>contact details</b>:\n"
        "Your Telegram @username or phone number."
    )
    await message.answer(msg)


# =========================
# 10. STEP 5 — CONTACT + SEND REQUEST
# =========================

@router.message(StateFilter(Form.contact), F.text)
async def process_contact(message: types.Message, state: FSMContext):
    contact = (message.text or "").strip() or "(not specified)"
    logger.info("Step 5 (contact) from user_id=%s contact=%s", message.from_user.id, contact[:120])

    await state.update_data(contact=contact)

    data = await state.get_data()
    await state.clear()

    user = message.from_user
    tg_username = f"@{user.username}" if user.username else f"id: {user.id}"

    product_text = data.get("product_text", "(no description)")
    product_photo_id = data.get("product_photo_id")
    options = data.get("options", "Not specified")
    budget = data.get("budget", "Not specified")
    city_delivery = data.get("city_delivery", "(not specified)")

    application_text = (
        "🛍 <b>New request</b>\n\n"
        f"👤 <b>Client:</b> {tg_username}\n\n"
        f"<b>1. Product:</b>\n{product_text}\n\n"
        f"<b>2. Size / color / preferences:</b>\n{options}\n\n"
        f"<b>3. Budget:</b>\n{budget}\n\n"
        f"<b>4. City / delivery:</b>\n{city_delivery}\n\n"
        f"<b>5. Contact:</b>\n{contact}\n"
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
        logger.exception("Error sending request to channel user_id=%s", user.id)
        await message.answer(
            "⚠️ An error occurred while sending your request. "
            "Please inform Anastasia."
        )
        return

    await message.answer(
        "Thank you! 💛\n"
        "Your request has been sent to Anastasia.\n"
        "She will find options and contact you.",
        reply_markup=new_request_keyboard()
    )


# =========================
# 11. FALLBACK — ANY OTHER TEXT
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
            "To create a request, press the button below or type /start.",
            reply_markup=start_keyboard()
        )
    else:
        await message.answer(
            "Please answer the current question or type /cancel "
            "to cancel the request."
        )


# =========================
# 12. BOT STARTUP
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

    # Health server (Railway-compatible)
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
