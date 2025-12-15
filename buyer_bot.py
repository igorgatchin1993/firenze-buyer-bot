#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram-бот для заявок Firenze Buyer Studio.
Версия под aiogram 3 и Python 3.12.

ФУНКЦИИ:
- Собирает заявку по шагам.
- Шаги 2 и 3 (размер/цвет и бюджет) можно пропустить.
- Отправляет готовую заявку в закрытый канал (ID канала см. ниже).
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher, F, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram import Router
from aiogram.client.default import DefaultBotProperties

# =========================
# 1. НАСТРОЙКИ
# =========================

# 👉 СЮДА ВСТАВЬ СВОЙ РЕАЛЬНЫЙ ТОКЕН В КАВЫЧКАХ
BOT_TOKEN = "8319599095:AAG_Rv0wmig-sRa76v7Annq6_pU841vvFhc"

# 👉 ID твоего закрытого канала "Заявки Firenze Buyer Studio"
CHANNEL_ID = -1003650413645

logging.basicConfig(level=logging.INFO)

# Dispatcher + storage + router
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)


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
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Оформить заявку")]
        ],
        resize_keyboard=True
    )
    return kb



def skip_keyboard() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Пропустить")]
        ],
        resize_keyboard=True
    )
    return kb


def new_request_keyboard() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Оформить ещё одну заявку")]
        ],
        resize_keyboard=True
    )
    return kb


# =========================
# 4. ОБРАБОТЧИКИ КОМАНД
# =========================

@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    """
    Приветствие и предложение начать заявку.
    """
    await state.clear()
    text = (
        "Привет! 👋\n"
        "Я бот Анастасии, байера из Италии.\n\n"
        "С помощью меня вы можете оформить заявку на покупку товара из Италии.\n"
        "Нажмите кнопку ниже, чтобы начать."
    )
    await message.answer(text, reply_markup=start_keyboard())


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "Я помогаю оформить заявку на покупку товара из Италии.\n"
        "Нажмите /start, чтобы начать."
    )


@router.message(F.text.contains("Оформить"))
async def start_form(message: types.Message, state: FSMContext):
    """
    Начинаем анкету.
    """
    await state.set_state(Form.product)
    text = (
        "1️⃣ Пришлите, пожалуйста, <b>фото, ссылку или описание товара</b>, "
        "который вы хотите купить.\n\n"
        "Можно переслать фото из Instagram/Pinterest или ссылку с сайта бренда."
    )
    await message.answer(text, reply_markup=types.ReplyKeyboardRemove())


@router.message(Command("cancel"), StateFilter("*"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    """
    Отмена анкеты.
    """
    await state.clear()
    await message.answer(
        "Заявка отменена. Если хотите начать заново — нажмите кнопку ниже.",
        reply_markup=start_keyboard()
    )


# =========================
# 5. ШАГ 1 — ТОВАР (ОБЯЗАТЕЛЬНО)
# =========================

@router.message(StateFilter(Form.product), F.content_type.in_(
    [types.ContentType.PHOTO, types.ContentType.TEXT]
))
async def process_product(message: types.Message, state: FSMContext):
    """
    Сохраняем информацию о товаре: фото или текст.
    """
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
# 6. ШАГ 2 — РАЗМЕР/ЦВЕТ (МОЖНО ПРОПУСТИТЬ)
# =========================

@router.message(StateFilter(Form.options), F.text)
async def process_options(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()

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
# 7. ШАГ 3 — БЮДЖЕТ (МОЖНО ПРОПУСТИТЬ)
# =========================

@router.message(StateFilter(Form.budget), F.text)
async def process_budget(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()

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
# 8. ШАГ 4 — ГОРОД (ОБЯЗАТЕЛЬНО)
# =========================

@router.message(StateFilter(Form.city), F.text)
async def process_city(message: types.Message, state: FSMContext):
    city_delivery = (message.text or "").strip() or "(не указано)"
    await state.update_data(city_delivery=city_delivery)

    await state.set_state(Form.contact)
    msg = (
        "5️⃣ Оставьте, пожалуйста, <b>контакт для связи</b>:\n"
        "Ваш Telegram @username или номер телефона."
    )
    await message.answer(msg)


# =========================
# 9. ШАГ 5 — КОНТАКТ + ОТПРАВКА ЗАЯВКИ
# =========================

@router.message(StateFilter(Form.contact), F.text)
async def process_contact(message: types.Message, state: FSMContext):
    contact = (message.text or "").strip() or "(не указан)"
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
            await bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=product_photo_id,
                caption=application_text
            )
        else:
            await bot.send_message(
                chat_id=CHANNEL_ID,
                text=application_text
            )
    except Exception as e:
        logging.error(f"Ошибка при отправке заявки в канал: {e}")
        await message.answer(
            "⚠️ Произошла ошибка при отправке заявки в канал. "
            "Сообщите, пожалуйста, Анастасии."
        )

    await message.answer(
        "Спасибо! 💛\n"
        "Ваша заявка отправлена Анастасии.\n"
        "Она подберёт варианты и свяжется с вами.",
        reply_markup=new_request_keyboard()
    )


# =========================
# 10. ФОЛБЭК — ЛЮБОЙ ДРУГОЙ ТЕКСТ
# =========================

@router.message()
async def fallback(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
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
# 11. ЗАПУСК БОТА
# =========================

async def main():
    global bot
    if BOT_TOKEN == "PASTE_YOUR_NEW_TOKEN_HERE":
        raise SystemExit("❌ Пожалуйста, вставьте ваш реальный токен в переменную BOT_TOKEN!")

    print("🚀 Запускаю бота...")  # чтобы ты видела, что main реально выполняется

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML")
    )

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
