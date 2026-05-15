import asyncio
import logging
import time
import random
import uuid
import aiohttp
import xml.etree.ElementTree as ET
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, FSInputFile, InputMediaPhoto
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiocryptopay import AioCryptoPay, Networks

import config
import database as db

logging.basicConfig(level=logging.INFO)

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()
crypto = AioCryptoPay(token=config.CRYPTO_BOT_TOKEN, network=Networks.MAIN_NET)

# ==========================================
# --- ID PREMIUM ЭМОДЗИ ДЛЯ КНОПОК ---
# ==========================================
E_CATALOG = "5368324170671202286"
E_PROFILE = "5368324170671202286"
E_DEPOSIT = "5368324170671202286"
E_SUPPORT = "5368324170671202286"
E_ABOUT =   "5368324170671202286"
E_SUCCESS = "5368324170671202286" 
E_DANGER =  "5368324170671202286" 
E_BACK =    "5368324170671202286" 
E_DEFAULT = "5368324170671202286" 

# --- Парсинг курса ЦБ РФ ---
async def get_usd_rate() -> float:
    url = "https://cbr.ru/scripts/XML_daily.asp"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                xml_data = await response.text()
                root = ET.fromstring(xml_data)
                for valute in root.findall('Valute'):
                    if valute.get('ID') == 'R01235': 
                        return float(valute.find('Value').text.replace(',', '.'))
    except Exception as e:
        logging.error(f"Ошибка получения курса: {e}")
    return 100.0

# --- FSM Состояния ---
class UserBuyState(StatesGroup):
    waiting_for_promo = State()

class ProfilePromoState(StatesGroup):
    waiting_for_code = State()

class DepositFlow(StatesGroup):
    waiting_for_custom_amount = State()
    waiting_for_receipt = State()

class AdminSBPState(StatesGroup):
    waiting_for_custom_amount = State()

class AdminCategoryState(StatesGroup):
    waiting_for_name = State()

class AdminCategoryEditState(StatesGroup):
    waiting_for_emoji = State()

class AdminProductState(StatesGroup):
    waiting_for_name = State()
    waiting_for_desc = State()
    waiting_for_price = State()

class AdminEditProductState(StatesGroup):
    waiting_for_new_name = State()
    waiting_for_new_desc = State()
    waiting_for_new_price = State()
    waiting_for_emoji = State()
    waiting_for_infinite_content = State()

class AdminItemState(StatesGroup):
    waiting_for_content = State()

class AdminUserState(StatesGroup):
    waiting_for_username = State()
    waiting_for_new_balance = State()

class AdminPromoState(StatesGroup):
    waiting_for_type = State()
    waiting_for_code = State()
    waiting_for_value = State()
    waiting_for_uses = State()

class AdminGiveawayState(StatesGroup):
    waiting_for_type = State()
    waiting_for_target = State()
    waiting_for_duration = State()
    waiting_for_winners = State()
    waiting_for_prize_type = State()
    waiting_for_prize_value = State()

class AdminUIState(StatesGroup):
    waiting_for_emoji = State()

# --- Middleware ---
@dp.message.outer_middleware()
async def check_ban_middleware(handler, event: Message, data: dict):
    if event.from_user:
        user = db.get_user(user_id=event.from_user.id)
        if user and user.get('is_blocked'):
            await event.answer("🚫 Ваш профиль заблокирован администрацией.")
            return
    return await handler(event, data)

# ==========================================
# --- ИНТЕРФЕЙС И КЛАВИАТУРЫ ---
# ==========================================
def persistent_menu():
    ui = db.get_ui()
    kb = [[KeyboardButton(text="Главное меню", icon_custom_emoji_id=ui.get('E_DEFAULT'))]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def inline_main_menu():
    ui = db.get_ui()
    kb = [
        [InlineKeyboardButton(text="Каталог", callback_data="nav_catalog", icon_custom_emoji_id=ui.get('E_CATALOG')), 
         InlineKeyboardButton(text="Пополнить баланс", callback_data="nav_deposit", icon_custom_emoji_id=ui.get('E_DEPOSIT'))],
        [InlineKeyboardButton(text="Профиль", callback_data="nav_profile", icon_custom_emoji_id=ui.get('E_PROFILE')), 
         InlineKeyboardButton(text="Поддержка", callback_data="nav_support", icon_custom_emoji_id=ui.get('E_SUPPORT'))],
        [InlineKeyboardButton(text="О боте", callback_data="nav_about", icon_custom_emoji_id=ui.get('E_ABOUT'))]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def inline_profile_menu(user_notifs_enabled):
    ui = db.get_ui()
    notif_text = "Уведомления: Вкл" if user_notifs_enabled else "Уведомления: Выкл"
    notif_icon = ui.get('E_SUCCESS') if user_notifs_enabled else ui.get('E_DANGER')
    kb = [
        [InlineKeyboardButton(text="Ввести промокод", callback_data="profile_promo", icon_custom_emoji_id=ui.get('E_DEFAULT')), 
         InlineKeyboardButton(text="Мои заказы", callback_data="profile_orders", icon_custom_emoji_id=ui.get('E_CATALOG'))],
        [InlineKeyboardButton(text=notif_text, callback_data="profile_notifs", icon_custom_emoji_id=notif_icon), 
         InlineKeyboardButton(text="История пополнений", callback_data="profile_history", icon_custom_emoji_id=ui.get('E_DEPOSIT'))],
        [InlineKeyboardButton(text="Пополнить баланс", callback_data="nav_deposit", icon_custom_emoji_id=ui.get('E_DEPOSIT'))],
        [InlineKeyboardButton(text="Назад", callback_data="nav_main", icon_custom_emoji_id=ui.get('E_BACK'))]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def inline_deposit_amounts():
    ui = db.get_ui()
    kb = [
        [InlineKeyboardButton(text="100₽", callback_data="dep_amt_100", icon_custom_emoji_id=ui.get('E_DEPOSIT')), 
         InlineKeyboardButton(text="250₽", callback_data="dep_amt_250", icon_custom_emoji_id=ui.get('E_DEPOSIT')), 
         InlineKeyboardButton(text="500₽", callback_data="dep_amt_500", icon_custom_emoji_id=ui.get('E_DEPOSIT'))],
        [InlineKeyboardButton(text="1000₽", callback_data="dep_amt_1000", icon_custom_emoji_id=ui.get('E_DEPOSIT')), 
         InlineKeyboardButton(text="2500₽", callback_data="dep_amt_2500", icon_custom_emoji_id=ui.get('E_DEPOSIT')), 
         InlineKeyboardButton(text="5000₽", callback_data="dep_amt_5000", icon_custom_emoji_id=ui.get('E_DEPOSIT'))],
        [InlineKeyboardButton(text="Другая сумма", callback_data="dep_custom", icon_custom_emoji_id=ui.get('E_DEFAULT'))],
        [InlineKeyboardButton(text="Назад", callback_data="nav_main", icon_custom_emoji_id=ui.get('E_BACK'))]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def inline_deposit_methods(amount):
    ui = db.get_ui()
    kb = [
        [InlineKeyboardButton(text="СБП (Ручной перевод)", callback_data=f"pay_sbp_{amount}", icon_custom_emoji_id=ui.get('E_DEPOSIT'))],
        [InlineKeyboardButton(text="CryptoBot (USDT)", callback_data=f"pay_crypto_{amount}", icon_custom_emoji_id=ui.get('E_DEPOSIT'))],
        [InlineKeyboardButton(text="Назад", callback_data="nav_deposit", icon_custom_emoji_id=ui.get('E_BACK'))]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def giveaway_type_ikb():
    ui = db.get_ui()
    kb = [
        [InlineKeyboardButton(text="За пополнение баланса", callback_data="ga_type_deposit", icon_custom_emoji_id=ui.get('E_DEPOSIT'))],
        [InlineKeyboardButton(text="За покупку товара", callback_data="ga_type_product", icon_custom_emoji_id=ui.get('E_CATALOG'))],
        [InlineKeyboardButton(text="Бонус первому покупателю", callback_data="ga_type_first_buy", icon_custom_emoji_id=ui.get('E_SUCCESS'))]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def prize_type_ikb():
    ui = db.get_ui()
    kb = [
        [InlineKeyboardButton(text="Деньги на баланс", callback_data="ga_prize_balance", icon_custom_emoji_id=ui.get('E_DEPOSIT'))],
        [InlineKeyboardButton(text="Промокод на скидку", callback_data="ga_prize_promo", icon_custom_emoji_id=ui.get('E_DEFAULT'))]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def admin_menu():
    ui = db.get_ui()
    kb = [
        [KeyboardButton(text="Категории", icon_custom_emoji_id=ui.get('E_CATALOG')), KeyboardButton(text="Товары", icon_custom_emoji_id=ui.get('E_CATALOG'))],
        [KeyboardButton(text="Пользователи", icon_custom_emoji_id=ui.get('E_PROFILE')), KeyboardButton(text="Промокоды", icon_custom_emoji_id=ui.get('E_DEFAULT'))],
        [KeyboardButton(text="Розыгрыши", icon_custom_emoji_id=ui.get('E_SUCCESS')), KeyboardButton(text="🎨 Эмодзи интерфейса", icon_custom_emoji_id=ui.get('E_DEFAULT'))],
        [KeyboardButton(text="Выйти из админки", icon_custom_emoji_id=ui.get('E_DANGER'))]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_main_menu_text(first_name):
    ui = db.get_ui()
    e_def = ui.get('E_DEFAULT')
    e_suc = ui.get('E_SUCCESS')
    return (
        f"<tg-emoji emoji-id=\"{e_def}\">🎉</tg-emoji> <b>Привет, {first_name}!</b>\n"
        f"Добро пожаловать в FunGuard Shop\n\n"
        f"Здесь всё просто: быстрые покупки, чистый интерфейс и моментальная выдача.\n\n"
        f"<tg-emoji emoji-id=\"{e_suc}\">🛡</tg-emoji> Надежные товары\n"
        f"<tg-emoji emoji-id=\"{e_suc}\">⚡️</tg-emoji> Моментальная выдача\n"
        f"<tg-emoji emoji-id=\"{e_suc}\">🤝</tg-emoji> Живая поддержка\n\n"
        f"Выберите раздел:"
    )

async def safe_media_switch(call: CallbackQuery, photo_path: str, text: str, reply_markup):
    media = InputMediaPhoto(media=FSInputFile(photo_path), caption=text, parse_mode="HTML")
    try:
        await call.message.edit_media(media=media, reply_markup=reply_markup)
    except Exception:
        await call.message.delete()
        await call.message.answer_photo(photo=FSInputFile(photo_path), caption=text, reply_markup=reply_markup, parse_mode="HTML")

# ==========================================
# --- НАВИГАЦИЯ ПОЛЬЗОВАТЕЛЯ ---
# ==========================================
@dp.message(Command("start"))
@dp.message(F.text == "Главное меню")
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    
    user = db.get_user(user_id=message.from_user.id)
    if not user:
        db.add_user(message.from_user.id, message.from_user.username)
        user = db.get_user(user_id=message.from_user.id)
        
    if not user.get('accepted_offer'):
        ui = db.get_ui()
        kb = [[InlineKeyboardButton(text="Я ознакомлен", callback_data="accept_offer", icon_custom_emoji_id=ui.get('E_SUCCESS'))]]
        text = (
            "❗️ Для использования бота необходимо ознакомиться с правилами оферты\n\n"
            "Добро пожаловать в FunGuard Shop! 👋\n\n"
            "Подпишитесь, чтобы узнавать все свежие новости:\n"
            "https://t.me/FunPay_Guard\n"
            "Отзывы: https://t.me/BIO_Guard\n\n"
            "📋 Перед началом:\n"
            "Ознакомьтесь с нашим публичным договором оферты:\n"
            f"→ {config.OFFER_LINK}\n\n"
            "Там подробно описаны условия использования, гарантии и как мы работаем с клиентами."
        )
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), disable_web_page_preview=True)
        return

    photo = FSInputFile("image_af4e21.jpg")
    await message.answer_photo(
        photo=photo, 
        caption=get_main_menu_text(message.from_user.first_name), 
        reply_markup=inline_main_menu(), 
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "accept_offer")
async def process_accept_offer(call: CallbackQuery):
    db.accept_offer(call.from_user.id)
    photo = FSInputFile("image_af4e21.jpg")
    await call.message.delete()
    await call.message.answer_photo(
        photo=photo, 
        caption=get_main_menu_text(call.from_user.first_name), 
        reply_markup=inline_main_menu(), 
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "nav_main")
async def edit_to_main_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_media_switch(
        call, 
        "image_af4e21.jpg", 
        get_main_menu_text(call.from_user.first_name), 
        inline_main_menu()
    )

@dp.callback_query(F.data == "nav_support")
async def show_support(call: CallbackQuery):
    ui = db.get_ui()
    e_sup = ui.get('E_SUPPORT')
    text = (f"<tg-emoji emoji-id=\"{e_sup}\">🤝</tg-emoji> <b>Поддержка</b>\n\nЕсли возникли вопросы, напишите: @manager_opiuma")
    kb = [[InlineKeyboardButton(text="Написать в поддержку", url="https://t.me/manager_opiuma", icon_custom_emoji_id=e_sup)], 
          [InlineKeyboardButton(text="Назад", callback_data="nav_main", icon_custom_emoji_id=ui.get('E_BACK'))]]
    await safe_media_switch(call, "support.jpg", text, InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "nav_about")
async def show_about(call: CallbackQuery):
    ui = db.get_ui()
    e_ab = ui.get('E_ABOUT')
    e_suc = ui.get('E_SUCCESS')
    text = (
        f"<tg-emoji emoji-id=\"{e_ab}\">ℹ️</tg-emoji> <b>О боте</b>\n\n"
        f"Мы сделали магазин в стиле «минимум шагов - максимум скорости».\n\n"
        f"<tg-emoji emoji-id=\"{e_suc}\">✅</tg-emoji> Моментальная выдача после оплаты\n"
        f"<tg-emoji emoji-id=\"{e_suc}\">🔒</tg-emoji> Безопасные сделки и стабильная работа\n\n"
        f"Если нужна помощь, откройте раздел «Поддержка» в главном меню."
    )
    kb = [[InlineKeyboardButton(text="Заказать такого бота", url="https://t.me/uhbyfc", icon_custom_emoji_id=ui.get('E_DEFAULT'))], 
          [InlineKeyboardButton(text="Назад", callback_data="nav_main", icon_custom_emoji_id=ui.get('E_BACK'))]]
    await safe_media_switch(call, "about.jpg", text, InlineKeyboardMarkup(inline_keyboard=kb))

# ==========================================
# --- ПРОФИЛЬ ---
# ==========================================
@dp.callback_query(F.data == "nav_profile")
async def show_profile(call: CallbackQuery):
    user = db.get_user(user_id=call.from_user.id)
    ui = db.get_ui()
    e_prof = ui.get('E_PROFILE')
    e_def = ui.get('E_DEFAULT')
    e_dep = ui.get('E_DEPOSIT')
    e_cat = ui.get('E_CATALOG')
    text = (
        f"<tg-emoji emoji-id=\"{e_prof}\">👤</tg-emoji> <b>Ваш профиль</b>\n\n"
        f"<tg-emoji emoji-id=\"{e_def}\">🆔</tg-emoji> ID: <code>{user['id']}</code>\n"
        f"<tg-emoji emoji-id=\"{e_prof}\">👤</tg-emoji> Имя: {call.from_user.first_name}\n"
        f"<tg-emoji emoji-id=\"{e_dep}\">💰</tg-emoji> Баланс: <b>{user['balance']}₽</b>\n"
        f"<tg-emoji emoji-id=\"{e_cat}\">🛍</tg-emoji> Покупок: <b>{user['purchases']}</b>\n"
        f"<tg-emoji emoji-id=\"{e_dep}\">💸</tg-emoji> Потрачено: <b>{user['spent']}₽</b>"
    )
    await safe_media_switch(call, "profile.jpg", text, inline_profile_menu(user['notifications']))

@dp.callback_query(F.data == "profile_notifs")
async def toggle_notifications(call: CallbackQuery):
    db.toggle_notifications(call.from_user.id)
    await call.answer("Настройки уведомлений обновлены ✅")
    user = db.get_user(user_id=call.from_user.id)
    await call.message.edit_reply_markup(reply_markup=inline_profile_menu(user['notifications']))

@dp.callback_query(F.data == "profile_orders")
async def show_orders(call: CallbackQuery):
    orders = db.get_user_orders(call.from_user.id, limit=5)
    if not orders: return await call.answer("Вы еще ничего не купили 🛒", show_alert=True)
    ui = db.get_ui()
    e_cat = ui.get('E_CATALOG')
    text = f"<tg-emoji emoji-id=\"{e_cat}\">📦</tg-emoji> <b>Ваши последние 5 покупок:</b>\n\n"
    for order in orders:
        text += f"🔹 <b>{order['product_name']}</b> ({order['price']}₽)\n📅 {order['dt']}\n🔑 <code>{order['content']}</code>\n\n"
    kb = [[InlineKeyboardButton(text="Назад в профиль", callback_data="nav_profile", icon_custom_emoji_id=ui.get('E_BACK'))]]
    await safe_media_switch(call, "profile.jpg", text, InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "profile_history")
async def show_deposit_history(call: CallbackQuery):
    deposits = db.get_user_deposits(call.from_user.id, limit=5)
    if not deposits: return await call.answer("У вас еще нет пополнений 💳", show_alert=True)
    ui = db.get_ui()
    text = f"<tg-emoji emoji-id=\"{ui.get('E_DEPOSIT')}\">🕰</tg-emoji> <b>Последние 5 пополнений:</b>\n\n"
    for dep in deposits:
        text += f"🔹 <b>{dep['amount']}₽</b> ({dep['method']})\n📅 {dep['dt']}\n\n"
    kb = [[InlineKeyboardButton(text="Назад в профиль", callback_data="nav_profile", icon_custom_emoji_id=ui.get('E_BACK'))]]
    await safe_media_switch(call, "profile.jpg", text, InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "profile_promo")
async def profile_promo_start(call: CallbackQuery, state: FSMContext):
    ui = db.get_ui()
    text = "В этом разделе активируются промокоды <b>НА БАЛАНС</b>.\nОтправьте код в чат:\n\n<i>(Если у вас промокод на скидку, вводите его при покупке товара в каталоге)</i>"
    kb = [[InlineKeyboardButton(text="Назад в профиль", callback_data="nav_profile", icon_custom_emoji_id=ui.get('E_BACK'))]]
    await safe_media_switch(call, "profile.jpg", text, InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(ProfilePromoState.waiting_for_code)

@dp.message(ProfilePromoState.waiting_for_code)
async def profile_promo_process(message: Message, state: FSMContext):
    code = message.text.strip()
    success, result = db.use_balance_promocode(message.from_user.id, code)
    if success: await message.answer(f"✅ Промокод успешно активирован! На баланс зачислено <b>{result} руб.</b>", parse_mode="HTML")
    else: await message.answer(f"❌ {result}") 
    await state.clear()

# ==========================================
# --- КАТАЛОГ И ПОКУПКА ---
# ==========================================
@dp.callback_query(F.data == "nav_catalog")
async def show_categories(call: CallbackQuery):
    categories = db.get_categories()
    if not categories: return await call.answer("Каталог пока пуст.", show_alert=True)
    ui = db.get_ui()
    kb = []
    for cat in categories:
        e_id = cat['emoji_id'] if cat['emoji_id'] else ui.get('E_CATALOG')
        kb.append([InlineKeyboardButton(text=f"{cat['name']}", callback_data=f"show_cat_{cat['id']}", icon_custom_emoji_id=e_id)])
    kb.append([InlineKeyboardButton(text="Назад", callback_data="nav_main", icon_custom_emoji_id=ui.get('E_BACK'))])
    await safe_media_switch(call, "catalog.jpg", f"<tg-emoji emoji-id=\"{ui.get('E_CATALOG')}\">🛍</tg-emoji> <b>Выберите категорию:</b>", InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("show_cat_"))
async def show_products_in_cat(call: CallbackQuery):
    cat_id = int(call.data.split("_")[2])
    cat = db.get_category(cat_id)
    products = db.get_products(category_id=cat_id)
    if not products: return await call.answer("В этой категории пока нет товаров.", show_alert=True)
    ui = db.get_ui()
    kb = []
    for p in products:
        e_id = p['emoji_id'] if p['emoji_id'] else ui.get('E_DEFAULT')
        stock_text = "∞" if p['is_infinite'] else str(p['stock'])
        kb.append([InlineKeyboardButton(text=f"{p['name']} | {p['price']}₽ | Шт: {stock_text}", callback_data=f"buy_{p['id']}", icon_custom_emoji_id=e_id)])
    kb.append([InlineKeyboardButton(text="Назад в категории", callback_data="nav_catalog", icon_custom_emoji_id=ui.get('E_BACK'))])
    await safe_media_switch(call, "catalog.jpg", f"Категория: <b>{cat['name']}</b>", InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("buy_"))
async def process_buy(call: CallbackQuery, state: FSMContext):
    product_id = int(call.data.split("_")[1])
    product = db.get_product(product_id)
    if not product: return await call.answer("Товар не найден", show_alert=True)
    
    await state.update_data(buy_product_id=product_id, applied_promo=None, applied_discount=0)
    ui = db.get_ui()
    kb = [
        [InlineKeyboardButton(text="Подтвердить покупку", callback_data="confirm_buy", icon_custom_emoji_id=ui.get('E_SUCCESS'))],
        [InlineKeyboardButton(text="Применить промокод", callback_data="apply_promo", icon_custom_emoji_id=ui.get('E_DEFAULT'))],
        [InlineKeyboardButton(text="Назад", callback_data=f"show_cat_{product['category_id']}", icon_custom_emoji_id=ui.get('E_BACK'))]
    ]
    stock_text = "∞ (Бесконечный товар)" if product['is_infinite'] else f"{product['stock']} шт."
    text = f"<b>{product['name']}</b>\n\nОписание:\n{product['description']}\n\nЦена: <b>{product['price']} руб.</b>\nВ наличии: {stock_text}"
    await safe_media_switch(call, "catalog.jpg", text, InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "apply_promo")
async def apply_promo_start(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get('buy_product_id'): return await call.answer("Ошибка сессии покупки.", show_alert=True)
    ui = db.get_ui()
    product_id = data.get('buy_product_id')
    kb = [[InlineKeyboardButton(text="Назад", callback_data=f"buy_{product_id}", icon_custom_emoji_id=ui.get('E_BACK'))]]
    await safe_media_switch(call, "catalog.jpg", "Отправьте промокод <b>НА СКИДКУ</b> в чат:", InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(UserBuyState.waiting_for_promo)

@dp.message(UserBuyState.waiting_for_promo)
async def apply_promo_process(message: Message, state: FSMContext):
    code = message.text.strip()
    data = await state.get_data()
    product_id = data.get('buy_product_id')
    if not product_id:
        await state.clear()
        return await message.answer("Ошибка сессии покупки. Начните заново.")

    product = db.get_product(product_id)
    success, discount, err = db.check_promocode(message.from_user.id, code, expected_type='discount')
    if not success: await message.answer(f"❌ {err}")
    else:
        await state.update_data(applied_promo=code, applied_discount=discount)
        await message.answer(f"✅ Скидка {discount} руб. применена!")

    data = await state.get_data()
    applied_discount = data.get('applied_discount', 0)
    ui = db.get_ui()
    kb = [
        [InlineKeyboardButton(text="Подтвердить покупку", callback_data="confirm_buy", icon_custom_emoji_id=ui.get('E_SUCCESS'))],
        [InlineKeyboardButton(text="Отменить", callback_data=f"show_cat_{product['category_id']}", icon_custom_emoji_id=ui.get('E_DANGER'))]
    ]
    stock_text = "∞" if product['is_infinite'] else str(product['stock'])
    if applied_discount > 0:
        new_price = max(0, product['price'] - applied_discount)
        text = f"<b>{product['name']}</b>\n\nСтарая цена: <s>{product['price']} руб.</s>\nК оплате: <b>{new_price} руб.</b>\nВ наличии: {stock_text}"
    else:
        kb.insert(1, [InlineKeyboardButton(text="Применить промокод", callback_data="apply_promo", icon_custom_emoji_id=ui.get('E_DEFAULT'))])
        text = f"<b>{product['name']}</b>\n\nЦена: <b>{product['price']} руб.</b>\nВ наличии: {stock_text}"
    await message.answer_photo(photo=FSInputFile("catalog.jpg"), caption=text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    await state.set_state(None)

@dp.callback_query(F.data == "confirm_buy")
async def confirm_buy(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    product_id = data.get('buy_product_id')
    promo_code = data.get('applied_promo')
    if not product_id: return await call.answer("Ошибка сессии.", show_alert=True)
    
    success, result, immediate_wins, final_price = db.buy_item(call.from_user.id, product_id, promo_code)
    if success:
        await call.message.answer(f"✅ Покупка успешна! Списано <b>{final_price} руб.</b>\n\nВаш товар:\n<code>{result}</code>", parse_mode="HTML")
        await call.message.delete()
        await state.clear()
        for ga in immediate_wins:
            if ga['prize_type'] == 'promo':
                promo_gen = f"FIRST-{str(uuid.uuid4())[:6].upper()}"
                db.add_promocode(promo_gen, 'discount', ga['prize_value'], 1)
                await call.message.answer(f"🎁 <b>СЮРПРИЗ!</b> Вы стали ПЕРВЫМ покупателем!\nПромокод на скидку: <code>{promo_gen}</code>", parse_mode="HTML")
            else:
                await call.message.answer(f"🎁 <b>СЮРПРИЗ!</b> ПЕРВЫЙ покупатель!\nНа балан зачислен бонус: <b>{ga['prize_value']} руб.</b>", parse_mode="HTML")
    else:
        await call.answer(f"❌ Ошибка: {result}", show_alert=True)

# ==========================================
# --- ПОПОЛНЕНИЕ БАЛАНСА ---
# ==========================================
@dp.callback_query(F.data == "nav_deposit")
async def show_deposit_amounts(call: CallbackQuery):
    ui = db.get_ui()
    text = f"<tg-emoji emoji-id=\"{ui.get('E_DEPOSIT')}\">💰</tg-emoji> <b>Пополнение баланса</b>\n\nВыберите сумму:"
    await safe_media_switch(call, "deposit.jpg", text, inline_deposit_amounts())

@dp.callback_query(F.data.startswith("dep_amt_"))
async def deposit_amount_selected(call: CallbackQuery):
    amount = int(call.data.split("_")[2])
    await safe_media_switch(call, "deposit.jpg", f"Выбрана сумма: <b>{amount} руб.</b>\nВыберите способ оплаты:", inline_deposit_methods(amount))

@dp.callback_query(F.data == "dep_custom")
async def deposit_custom_amount_start(call: CallbackQuery, state: FSMContext):
    ui = db.get_ui()
    kb = [[InlineKeyboardButton(text="Назад", callback_data="nav_deposit", icon_custom_emoji_id=ui.get('E_BACK'))]]
    await safe_media_switch(call, "deposit.jpg", "Введите сумму пополнения в рублях:", InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(DepositFlow.waiting_for_custom_amount)

@dp.message(DepositFlow.waiting_for_custom_amount)
async def deposit_custom_amount_entered(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Введите корректное число.")
    amount = int(message.text)
    await message.answer_photo(photo=FSInputFile("deposit.jpg"), caption=f"Выбрана сумма: <b>{amount} руб.</b>\nВыберите способ оплаты:", reply_markup=inline_deposit_methods(amount), parse_mode="HTML")
    await state.clear()

@dp.callback_query(F.data.startswith("pay_sbp_"))
async def process_pay_sbp(call: CallbackQuery, state: FSMContext):
    amount = int(call.data.split("_")[2])
    await state.update_data(amount=amount)
    ui = db.get_ui()
    text = (f"<tg-emoji emoji-id=\"{ui.get('E_DEPOSIT')}\">💳</tg-emoji> Переведите ровно <b>{amount} руб.</b> по реквизитам СБП:\n\n"
            f"<code>{config.SBP_REQUISITES}</code>\n\nПосле перевода отправьте <b>скриншот чека</b>.")
    kb = [[InlineKeyboardButton(text="Отменить", callback_data="nav_deposit", icon_custom_emoji_id=ui.get('E_DANGER'))]]
    await safe_media_switch(call, "deposit.jpg", text, InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(DepositFlow.waiting_for_receipt)

@dp.message(DepositFlow.waiting_for_receipt, F.photo)
async def deposit_sbp_receipt(message: Message, state: FSMContext):
    data = await state.get_data()
    amount = data['amount']
    user_id = message.from_user.id
    username = message.from_user.username or "Без юзернейма"
    await message.answer("⏳ Чек отправлен. Ожидайте зачисления средств.", reply_markup=persistent_menu())
    await state.clear()
    
    ui = db.get_ui()
    kb = [
        [InlineKeyboardButton(text=f"Подтвердить ({amount}₽)", callback_data=f"adm_sbp_ok_{user_id}_{amount}", icon_custom_emoji_id=ui.get('E_SUCCESS'))],
        [InlineKeyboardButton(text="Отклонить", callback_data=f"adm_sbp_no_{user_id}", icon_custom_emoji_id=ui.get('E_DANGER'))]
    ]
    for admin_id in config.ADMIN_IDS:
        try: await bot.send_photo(admin_id, message.photo[-1].file_id, caption=f"🔔 <b>СБП</b>\n@{username} | ID: <code>{user_id}</code>\nСумма: <b>{amount} руб.</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
        except: pass

@dp.callback_query(F.data.startswith("pay_crypto_"))
async def process_pay_crypto(call: CallbackQuery):
    amount_rub = float(call.data.split("_")[2])
    rate = await get_usd_rate()
    amount_usdt = round(amount_rub / rate, 2)
    if amount_usdt <= 0.1: return await call.answer(f"Сумма мала. Минимум: 0.1 USDT", show_alert=True)
    ui = db.get_ui()
    invoice = await crypto.create_invoice(asset='USDT', amount=amount_usdt)
    kb = [[InlineKeyboardButton(text="Оплатить USDT", url=invoice.bot_invoice_url, icon_custom_emoji_id=ui.get('E_DEPOSIT'))], 
          [InlineKeyboardButton(text="Проверить оплату", callback_data=f"check_crypto_{invoice.invoice_id}_{amount_rub}", icon_custom_emoji_id=ui.get('E_SUCCESS'))], 
          [InlineKeyboardButton(text="Назад", callback_data="nav_deposit", icon_custom_emoji_id=ui.get('E_BACK'))]]
    await safe_media_switch(call, "deposit.jpg", f"Сумма в рублях: {amount_rub} ₽\nК оплате: <b>{amount_usdt} USDT</b>", InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("check_crypto_"))
async def check_crypto_payment(call: CallbackQuery):
    parts = call.data.split("_")
    invoice_id, amount_rub = int(parts[2]), float(parts[3])
    invoice = await crypto.get_invoices(invoice_ids=invoice_id)
    if invoice and invoice.status == 'paid':
        db.process_deposit(call.from_user.id, amount_rub, "CryptoBot")
        await call.message.edit_caption(caption=f"✅ Оплата найдена! Зачислено {amount_rub} руб.", reply_markup=None)
        user = db.get_user(call.from_user.id)
        if user['notifications']:
            try: await bot.send_message(call.from_user.id, f"💳 Ваш баланс пополнен на {amount_rub} руб. (CryptoBot)")
            except: pass
    else:
        await call.answer("❌ Оплата пока не найдена.", show_alert=True)

# ==========================================
# --- АДМИН ПАНЕЛЬ ---
# ==========================================
@dp.message(Command("admin"), F.from_user.id.in_(config.ADMIN_IDS))
async def admin_start(message: Message):
    await message.answer("🔐 Админ панель.", reply_markup=admin_menu())

@dp.message(F.text == "Выйти из админки", F.from_user.id.in_(config.ADMIN_IDS))
async def admin_exit(message: Message):
    await message.answer("Вы вышли.", reply_markup=persistent_menu())

@dp.callback_query(F.data.startswith("adm_sbp_ok_"), F.from_user.id.in_(config.ADMIN_IDS))
async def admin_sbp_approve(call: CallbackQuery):
    _, _, _, user_id, amount = call.data.split("_")
    db.process_deposit(int(user_id), float(amount), "СБП") 
    await call.message.edit_caption(caption=call.message.caption + f"\n\n✅ <b>Одобрено {amount} руб.</b>", parse_mode="HTML")
    user = db.get_user(int(user_id))
    if user and user['notifications']:
        try: await bot.send_message(user_id, f"✅ Ваш платеж по СБП подтвержден! Начислено {amount} руб.")
        except: pass

@dp.callback_query(F.data.startswith("adm_sbp_no_"), F.from_user.id.in_(config.ADMIN_IDS))
async def admin_sbp_reject(call: CallbackQuery):
    user_id = call.data.split("_")[3]
    await call.message.edit_caption(caption=call.message.caption + "\n\n❌ <b>Отклонено.</b>", parse_mode="HTML")
    user = db.get_user(int(user_id))
    if user and user['notifications']:
        try: await bot.send_message(user_id, "❌ Ваш платеж по СБП отклонен.")
        except: pass

# --- Настройки UI (Эмодзи) ---
@dp.message(F.text == "🎨 Эмодзи интерфейса", F.from_user.id.in_(config.ADMIN_IDS))
async def admin_ui_menu(message: Message):
    ui = db.get_ui()
    kb = [
        [InlineKeyboardButton(text="Каталог", callback_data="adm_ui_E_CATALOG", icon_custom_emoji_id=ui.get('E_CATALOG')),
         InlineKeyboardButton(text="Профиль", callback_data="adm_ui_E_PROFILE", icon_custom_emoji_id=ui.get('E_PROFILE'))],
        [InlineKeyboardButton(text="Пополнение", callback_data="adm_ui_E_DEPOSIT", icon_custom_emoji_id=ui.get('E_DEPOSIT')),
         InlineKeyboardButton(text="Поддержка", callback_data="adm_ui_E_SUPPORT", icon_custom_emoji_id=ui.get('E_SUPPORT'))],
        [InlineKeyboardButton(text="О боте", callback_data="adm_ui_E_ABOUT", icon_custom_emoji_id=ui.get('E_ABOUT')),
         InlineKeyboardButton(text="Успех (✅)", callback_data="adm_ui_E_SUCCESS", icon_custom_emoji_id=ui.get('E_SUCCESS'))],
        [InlineKeyboardButton(text="Отмена/Удаление (❌)", callback_data="adm_ui_E_DANGER", icon_custom_emoji_id=ui.get('E_DANGER')),
         InlineKeyboardButton(text="Назад (🔙)", callback_data="adm_ui_E_BACK", icon_custom_emoji_id=ui.get('E_BACK'))],
        [InlineKeyboardButton(text="Стандартный (⏺)", callback_data="adm_ui_E_DEFAULT", icon_custom_emoji_id=ui.get('E_DEFAULT'))]
    ]
    await message.answer("Выберите элемент, для которого хотите изменить Premium-эмодзи:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("adm_ui_"), F.from_user.id.in_(config.ADMIN_IDS))
async def admin_ui_edit(call: CallbackQuery, state: FSMContext):
    ui_key = call.data.replace("adm_ui_", "")
    await state.update_data(ui_key=ui_key)
    await call.message.answer(f"Отправьте числовой ID (или сам Premium-эмодзи) для элемента <b>{ui_key}</b>:", parse_mode="HTML")
    await state.set_state(AdminUIState.waiting_for_emoji)

@dp.message(AdminUIState.waiting_for_emoji, F.from_user.id.in_(config.ADMIN_IDS))
async def admin_ui_save(message: Message, state: FSMContext):
    emoji_id = None
    if message.text and message.text.isdigit():
        emoji_id = message.text.strip()
    elif message.entities:
        for ent in message.entities:
            if ent.type == "custom_emoji":
                emoji_id = ent.custom_emoji_id
                break
                
    if not emoji_id:
        return await message.answer("❌ Отправьте числовой ID или сам Premium-эмодзи.")
    
    data = await state.get_data()
    db.set_ui(data['ui_key'], emoji_id)
    await message.answer(f"✅ Эмодзи для <b>{data['ui_key']}</b> успешно обновлен! Все кнопки магазина перерисованы.", parse_mode="HTML")
    await state.clear()

# --- Категории ---
@dp.message(F.text == "Категории", F.from_user.id.in_(config.ADMIN_IDS))
async def admin_categories(message: Message):
    cats = db.get_categories()
    ui = db.get_ui()
    kb = [[InlineKeyboardButton(text="Создать категорию", callback_data="adm_add_cat", icon_custom_emoji_id=ui.get('E_SUCCESS'))]]
    for cat in cats: 
        kb.append([InlineKeyboardButton(text=f"{cat['name']}", callback_data=f"adm_manage_cat_{cat['id']}", icon_custom_emoji_id=cat['emoji_id'] or ui.get('E_CATALOG'))])
    await message.answer("Управление категориями:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "adm_add_cat", F.from_user.id.in_(config.ADMIN_IDS))
async def admin_add_cat_start(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Введите название:")
    await state.set_state(AdminCategoryState.waiting_for_name)

@dp.message(AdminCategoryState.waiting_for_name, F.from_user.id.in_(config.ADMIN_IDS))
async def admin_add_cat_finish(message: Message, state: FSMContext):
    db.add_category(message.text)
    await message.answer("✅ Создана!")
    await state.clear()

@dp.callback_query(F.data.startswith("adm_manage_cat_"), F.from_user.id.in_(config.ADMIN_IDS))
async def admin_manage_category(call: CallbackQuery):
    cat_id = int(call.data.split("_")[3])
    cat = db.get_category(cat_id)
    ui = db.get_ui()
    kb = [
        [InlineKeyboardButton(text="Изменить эмодзи", callback_data=f"adm_edit_cat_emoji_{cat_id}", icon_custom_emoji_id=ui.get('E_DEFAULT'))],
        [InlineKeyboardButton(text="Удалить категорию", callback_data=f"adm_del_cat_{cat_id}", icon_custom_emoji_id=ui.get('E_DANGER'))]
    ]
    await call.message.edit_text(f"Категория: <b>{cat['name']}</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

@dp.callback_query(F.data.startswith("adm_edit_cat_emoji_"), F.from_user.id.in_(config.ADMIN_IDS))
async def admin_edit_cat_emoji(call: CallbackQuery, state: FSMContext):
    cat_id = int(call.data.split("_")[4])
    await state.update_data(cat_id=cat_id)
    await call.message.answer("Отправьте числовой ID (или сам Premium-эмодзи) для этой категории:")
    await state.set_state(AdminCategoryEditState.waiting_for_emoji)

@dp.message(AdminCategoryEditState.waiting_for_emoji, F.from_user.id.in_(config.ADMIN_IDS))
async def admin_save_cat_emoji(message: Message, state: FSMContext):
    emoji_id = None
    if message.text and message.text.isdigit():
        emoji_id = message.text.strip()
    elif message.entities:
        for ent in message.entities:
            if ent.type == "custom_emoji":
                emoji_id = ent.custom_emoji_id
                break
                
    if not emoji_id: return await message.answer("❌ Отправьте числовой ID или сам Premium-эмодзи.")
    data = await state.get_data()
    db.update_category_emoji(data['cat_id'], emoji_id)
    await message.answer("✅ Эмодзи обновлен!")
    await state.clear()

@dp.callback_query(F.data.startswith("adm_del_cat_"), F.from_user.id.in_(config.ADMIN_IDS))
async def admin_del_cat(call: CallbackQuery):
    db.delete_category(int(call.data.split("_")[3]))
    await call.answer("Удалено.", show_alert=True)
    await call.message.delete()

# --- Товары ---
@dp.message(F.text == "Товары", F.from_user.id.in_(config.ADMIN_IDS))
async def admin_products_start(message: Message):
    cats = db.get_categories()
    if not cats: return await message.answer("Создайте категорию!")
    ui = db.get_ui()
    kb = [[InlineKeyboardButton(text=f"{c['name']}", callback_data=f"adm_prodcat_{c['id']}", icon_custom_emoji_id=c['emoji_id'] or ui.get('E_CATALOG'))] for c in cats]
    await message.answer("Выберите категорию:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("adm_prodcat_"), F.from_user.id.in_(config.ADMIN_IDS))
async def admin_manage_products_in_cat(call: CallbackQuery):
    cat_id = int(call.data.split("_")[2])
    products = db.get_products(category_id=cat_id)
    ui = db.get_ui()
    kb = [[InlineKeyboardButton(text="Добавить товар", callback_data=f"adm_add_prod_{cat_id}", icon_custom_emoji_id=ui.get('E_SUCCESS'))]]
    for p in products:
        stock_text = "∞" if p['is_infinite'] else str(p['stock'])
        kb.append([InlineKeyboardButton(text=f"{p['name']} ({stock_text}шт)", callback_data=f"adm_prod_{p['id']}", icon_custom_emoji_id=p['emoji_id'] or ui.get('E_DEFAULT'))])
    await call.message.edit_text("Товары:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("adm_add_prod_"), F.from_user.id.in_(config.ADMIN_IDS))
async def admin_add_product_name(call: CallbackQuery, state: FSMContext):
    await state.update_data(cat_id=int(call.data.split("_")[3]))
    await call.message.answer("Название товара:")
    await state.set_state(AdminProductState.waiting_for_name)

@dp.message(AdminProductState.waiting_for_name, F.from_user.id.in_(config.ADMIN_IDS))
async def admin_add_product_desc(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Описание:")
    await state.set_state(AdminProductState.waiting_for_desc)

@dp.message(AdminProductState.waiting_for_desc, F.from_user.id.in_(config.ADMIN_IDS))
async def admin_add_product_price(message: Message, state: FSMContext):
    await state.update_data(desc=message.text)
    await message.answer("Цена (в рублях):")
    await state.set_state(AdminProductState.waiting_for_price)

@dp.message(AdminProductState.waiting_for_price, F.from_user.id.in_(config.ADMIN_IDS))
async def admin_add_product_finish(message: Message, state: FSMContext):
    data = await state.get_data()
    db.add_product(data['cat_id'], data['name'], data['desc'], float(message.text))
    await message.answer("✅ Добавлен!")
    await state.clear()

@dp.callback_query(F.data.startswith("adm_prod_"), F.from_user.id.in_(config.ADMIN_IDS))
async def admin_manage_product(call: CallbackQuery):
    product_id = int(call.data.split("_")[2])
    product = db.get_product(product_id)
    if not product: return await call.answer("Не найден", show_alert=True)
    ui = db.get_ui()
    is_inf = product['is_infinite']
    stock_txt = "∞ (Бесконечный)" if is_inf else f"{product['stock']} шт."
    type_btn_txt = "Сделать бесконечным" if not is_inf else "Сделать обычным"
    load_btn_txt = "Содержимое (бесконечное)" if is_inf else "Загрузить (автовыдача)"
    load_callback = f"edit_inf_{product_id}" if is_inf else f"add_items_{product_id}"

    kb = [
        [InlineKeyboardButton(text="Эмодзи", callback_data=f"edit_prod_{product_id}_emoji", icon_custom_emoji_id=ui.get('E_DEFAULT')),
         InlineKeyboardButton(text=type_btn_txt, callback_data=f"toggle_inf_{product_id}", icon_custom_emoji_id=ui.get('E_DEFAULT'))],
        [InlineKeyboardButton(text=load_btn_txt, callback_data=load_callback, icon_custom_emoji_id=ui.get('E_SUCCESS'))],
        [InlineKeyboardButton(text="Название", callback_data=f"edit_prod_{product_id}_name", icon_custom_emoji_id=ui.get('E_DEFAULT')), 
         InlineKeyboardButton(text="Описание", callback_data=f"edit_prod_{product_id}_desc", icon_custom_emoji_id=ui.get('E_DEFAULT'))],
        [InlineKeyboardButton(text="Изменить цену", callback_data=f"edit_prod_{product_id}_price", icon_custom_emoji_id=ui.get('E_DEFAULT'))],
        [InlineKeyboardButton(text="Удалить", callback_data=f"del_prod_{product_id}", icon_custom_emoji_id=ui.get('E_DANGER'))]
    ]
    await call.message.edit_text(f"Товар: <b>{product['name']}</b>\nЦена: {product['price']}₽\nВ наличии: {stock_txt}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

@dp.callback_query(F.data.startswith("toggle_inf_"), F.from_user.id.in_(config.ADMIN_IDS))
async def admin_toggle_infinite(call: CallbackQuery):
    product_id = int(call.data.split("_")[2])
    db.toggle_product_infinite(product_id)
    await admin_manage_product(call)

@dp.callback_query(F.data.startswith("edit_inf_"), F.from_user.id.in_(config.ADMIN_IDS))
async def admin_edit_inf_content(call: CallbackQuery, state: FSMContext):
    await state.update_data(edit_product_id=int(call.data.split("_")[2]))
    await call.message.answer("Отправьте текст/ссылку для бесконечного товара:")
    await state.set_state(AdminEditProductState.waiting_for_infinite_content)

@dp.message(AdminEditProductState.waiting_for_infinite_content, F.from_user.id.in_(config.ADMIN_IDS))
async def admin_save_inf_content(message: Message, state: FSMContext):
    data = await state.get_data()
    db.update_product_field(data['edit_product_id'], 'infinite_content', message.text)
    await message.answer("✅ Обновлено.")
    await state.clear()

@dp.callback_query(F.data.startswith("edit_prod_"), F.from_user.id.in_(config.ADMIN_IDS))
async def admin_edit_product_start(call: CallbackQuery, state: FSMContext):
    _, _, product_id, edit_field = call.data.split("_")
    await state.update_data(edit_product_id=product_id)
    if edit_field == "name":
        await call.message.answer("Новое название:")
        await state.set_state(AdminEditProductState.waiting_for_new_name)
    elif edit_field == "desc":
        await call.message.answer("Новое описание:")
        await state.set_state(AdminEditProductState.waiting_for_new_desc)
    elif edit_field == "price":
        await call.message.answer("Новая цена:")
        await state.set_state(AdminEditProductState.waiting_for_new_price)
    elif edit_field == "emoji":
        await call.message.answer("Отправьте числовой ID (или сам Premium-эмодзи):")
        await state.set_state(AdminEditProductState.waiting_for_emoji)

@dp.message(AdminEditProductState.waiting_for_emoji, F.from_user.id.in_(config.ADMIN_IDS))
async def admin_edit_prod_emoji(message: Message, state: FSMContext):
    emoji_id = None
    if message.text and message.text.isdigit():
        emoji_id = message.text.strip()
    elif message.entities:
        for ent in message.entities:
            if ent.type == "custom_emoji":
                emoji_id = ent.custom_emoji_id
                break
                
    if not emoji_id: return await message.answer("❌ Отправьте числовой ID или сам Premium-эмодзи.")
    data = await state.get_data()
    db.update_product_field(data['edit_product_id'], 'emoji_id', emoji_id)
    await message.answer("✅ Обновлено!")
    await state.clear()

@dp.message(AdminEditProductState.waiting_for_new_name, F.from_user.id.in_(config.ADMIN_IDS))
async def admin_edit_prod_name(message: Message, state: FSMContext):
    data = await state.get_data()
    db.update_product_field(data['edit_product_id'], 'name', message.text)
    await message.answer("✅ Обновлено.")
    await state.clear()

@dp.message(AdminEditProductState.waiting_for_new_desc, F.from_user.id.in_(config.ADMIN_IDS))
async def admin_edit_prod_desc(message: Message, state: FSMContext):
    data = await state.get_data()
    db.update_product_field(data['edit_product_id'], 'description', message.text)
    await message.answer("✅ Обновлено.")
    await state.clear()

@dp.message(AdminEditProductState.waiting_for_new_price, F.from_user.id.in_(config.ADMIN_IDS))
async def admin_edit_prod_price(message: Message, state: FSMContext):
    data = await state.get_data()
    db.update_product_field(data['edit_product_id'], 'price', float(message.text))
    await message.answer("✅ Обновлено.")
    await state.clear()

@dp.callback_query(F.data.startswith("del_prod_"), F.from_user.id.in_(config.ADMIN_IDS))
async def admin_delete_product(call: CallbackQuery):
    db.delete_product(int(call.data.split("_")[2]))
    await call.message.delete()

@dp.callback_query(F.data.startswith("add_items_"), F.from_user.id.in_(config.ADMIN_IDS))
async def admin_add_items_start(call: CallbackQuery, state: FSMContext):
    await state.update_data(product_id=int(call.data.split("_")[2]))
    await call.message.answer("Отправьте данные (одно сообщение = один товар).\nДля завершения: /stop")
    await state.set_state(AdminItemState.waiting_for_content)

@dp.message(AdminItemState.waiting_for_content, F.from_user.id.in_(config.ADMIN_IDS))
async def admin_add_items_process(message: Message, state: FSMContext):
    if message.text == "/stop":
        await message.answer("✅ Загрузка завершена.")
        return await state.clear()
    data = await state.get_data()
    db.add_item(data['product_id'], message.text)
    await message.answer("Добавлено. Следующий или /stop")

@dp.message(F.text == "Промокоды", F.from_user.id.in_(config.ADMIN_IDS))
async def admin_promocodes(message: Message):
    promos = db.get_promocodes()
    ui = db.get_ui()
    kb = [[InlineKeyboardButton(text="Создать промокод", callback_data="adm_add_promo", icon_custom_emoji_id=ui.get('E_SUCCESS'))]]
    for p in promos:
        t = "Баланс" if p['promo_type'] == 'balance' else "Скидка"
        kb.append([InlineKeyboardButton(text=f"{p['code']} ({t}, {p['discount']}₽) - {p['uses_left']} шт.", callback_data=f"adm_del_promo_{p['id']}", icon_custom_emoji_id=ui.get('E_DANGER'))])
    await message.answer("Промокоды:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "adm_add_promo", F.from_user.id.in_(config.ADMIN_IDS))
async def admin_add_promo_type(call: CallbackQuery, state: FSMContext):
    ui = db.get_ui()
    kb = [
        [InlineKeyboardButton(text="На пополнение баланса", callback_data="adm_pt_balance", icon_custom_emoji_id=ui.get('E_DEPOSIT'))],
        [InlineKeyboardButton(text="На скидку при покупке", callback_data="adm_pt_discount", icon_custom_emoji_id=ui.get('E_CATALOG'))]
    ]
    await call.message.edit_text("Выберите тип промокода:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(AdminPromoState.waiting_for_type)

@dp.callback_query(AdminPromoState.waiting_for_type, F.data.startswith("adm_pt_"), F.from_user.id.in_(config.ADMIN_IDS))
async def admin_add_promo_start(call: CallbackQuery, state: FSMContext):
    promo_type = call.data.split("_")[2]
    await state.update_data(promo_type=promo_type)
    await call.message.edit_text("Введите текст (например: SALE10):")
    await state.set_state(AdminPromoState.waiting_for_code)

@dp.message(AdminPromoState.waiting_for_code, F.from_user.id.in_(config.ADMIN_IDS))
async def admin_add_promo_value(message: Message, state: FSMContext):
    await state.update_data(code=message.text.strip())
    await message.answer("Введите сумму (в рублях):")
    await state.set_state(AdminPromoState.waiting_for_value)

@dp.message(AdminPromoState.waiting_for_value, F.from_user.id.in_(config.ADMIN_IDS))
async def admin_add_promo_uses(message: Message, state: FSMContext):
    await state.update_data(discount=float(message.text))
    await message.answer("Введите количество активаций:")
    await state.set_state(AdminPromoState.waiting_for_uses)

@dp.message(AdminPromoState.waiting_for_uses, F.from_user.id.in_(config.ADMIN_IDS))
async def admin_add_promo_finish(message: Message, state: FSMContext):
    data = await state.get_data()
    t = "пополняет баланс" if data['promo_type'] == 'balance' else "дает скидку"
    success = db.add_promocode(data['code'], data['promo_type'], data['discount'], int(message.text))
    if success: await message.answer(f"✅ Создан.")
    else: await message.answer("❌ Такой код уже есть.")
    await state.clear()

@dp.callback_query(F.data.startswith("adm_del_promo_"), F.from_user.id.in_(config.ADMIN_IDS))
async def admin_del_promo(call: CallbackQuery):
    db.delete_promocode(int(call.data.split("_")[3]))
    await call.message.delete()

@dp.message(F.text == "Пользователи", F.from_user.id.in_(config.ADMIN_IDS))
async def admin_users_start(message: Message, state: FSMContext):
    await message.answer("Введите @username или ID:")
    await state.set_state(AdminUserState.waiting_for_username)

@dp.message(AdminUserState.waiting_for_username, F.from_user.id.in_(config.ADMIN_IDS))
async def admin_users_find(message: Message, state: FSMContext):
    query = message.text
    user = db.get_user(user_id=int(query)) if query.isdigit() else db.get_user(username=query)
    if not user: return await message.answer("Не найден.")
    ui = db.get_ui()
    status = "Заблокирован 🔴" if user['is_blocked'] else "Активен 🟢"
    text = f"👤 <b>Пользователь:</b> @{user['username']}\nID: <code>{user['id']}</code>\nБаланс: {user['balance']} руб.\nСтатус: {status}"
    kb = [
        [InlineKeyboardButton(text="Изменить баланс", callback_data=f"adm_bal_{user['id']}", icon_custom_emoji_id=ui.get('E_DEFAULT'))],
        [InlineKeyboardButton(text="Разблокировать" if user['is_blocked'] else "Заблокировать", callback_data=f"adm_block_{user['id']}_{user['is_blocked']}", icon_custom_emoji_id=ui.get('E_DANGER'))]
    ]
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    await state.clear()

@dp.callback_query(F.data.startswith("adm_block_"), F.from_user.id.in_(config.ADMIN_IDS))
async def admin_toggle_block(call: CallbackQuery):
    _, _, user_id, is_blocked = call.data.split("_")
    db.set_block_status(int(user_id), 0 if int(is_blocked) == 1 else 1)
    await call.message.delete()

@dp.callback_query(F.data.startswith("adm_bal_"), F.from_user.id.in_(config.ADMIN_IDS))
async def admin_change_bal(call: CallbackQuery, state: FSMContext):
    await state.update_data(target_user=call.data.split("_")[2])
    await call.message.answer("Сумма (+ добавить, - отнять):")
    await state.set_state(AdminUserState.waiting_for_new_balance)

@dp.message(AdminUserState.waiting_for_new_balance, F.from_user.id.in_(config.ADMIN_IDS))
async def admin_update_bal(message: Message, state: FSMContext):
    data = await state.get_data()
    db.update_balance(int(data['target_user']), float(message.text))
    await message.answer("Обновлено.")
    await state.clear()

@dp.message(F.text == "Розыгрыши", F.from_user.id.in_(config.ADMIN_IDS))
async def admin_giveaways(message: Message):
    ui = db.get_ui()
    kb = [[InlineKeyboardButton(text="Создать", callback_data="adm_ga_create", icon_custom_emoji_id=ui.get('E_SUCCESS'))], 
          [InlineKeyboardButton(text="Активные", callback_data="adm_ga_list", icon_custom_emoji_id=ui.get('E_DEFAULT'))]]
    await message.answer("Розыгрыши:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "adm_ga_list", F.from_user.id.in_(config.ADMIN_IDS))
async def admin_ga_list(call: CallbackQuery):
    gas = db.get_active_giveaways()
    if not gas: return await call.message.edit_text("Активных розыгрышей нет.")
    text = "📋 <b>Активные:</b>\n\n"
    for ga in gas: text += f"ID {ga['id']} | Приз: {ga['prize_value']}₽\n"
    await call.message.edit_text(text, parse_mode="HTML")

@dp.callback_query(F.data == "adm_ga_create", F.from_user.id.in_(config.ADMIN_IDS))
async def admin_ga_create_start(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("Тип:", reply_markup=giveaway_type_ikb())
    await state.set_state(AdminGiveawayState.waiting_for_type)

@dp.callback_query(AdminGiveawayState.waiting_for_type, F.data.startswith("ga_type_"), F.from_user.id.in_(config.ADMIN_IDS))
async def admin_ga_type(call: CallbackQuery, state: FSMContext):
    ga_type = call.data.replace("ga_type_", "")
    await state.update_data(ga_type=ga_type)
    if ga_type == "deposit":
        await call.message.edit_text("Мин. сумма пополнения (в рублях):")
    else:
        products = db.get_products()
        ui = db.get_ui()
        kb = [[InlineKeyboardButton(text=p['name'], callback_data=f"ga_prod_{p['id']}", icon_custom_emoji_id=ui.get('E_CATALOG'))] for p in products]
        await call.message.edit_text("Выберите товар:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(AdminGiveawayState.waiting_for_target)

@dp.message(AdminGiveawayState.waiting_for_target, F.from_user.id.in_(config.ADMIN_IDS))
async def admin_ga_target_msg(message: Message, state: FSMContext):
    await state.update_data(target_val=float(message.text))
    await message.answer("Длительность в ЧАСАХ:")
    await state.set_state(AdminGiveawayState.waiting_for_duration)

@dp.callback_query(AdminGiveawayState.waiting_for_target, F.data.startswith("ga_prod_"), F.from_user.id.in_(config.ADMIN_IDS))
async def admin_ga_target_call(call: CallbackQuery, state: FSMContext):
    await state.update_data(target_val=int(call.data.replace("ga_prod_", "")))
    data = await state.get_data()
    if data['ga_type'] == 'first_buy':
        await call.message.edit_text("Вид бонуса?", reply_markup=prize_type_ikb())
        await state.set_state(AdminGiveawayState.waiting_for_prize_type)
    else:
        await call.message.edit_text("Длительность в ЧАСАХ:")
        await state.set_state(AdminGiveawayState.waiting_for_duration)

@dp.message(AdminGiveawayState.waiting_for_duration, F.from_user.id.in_(config.ADMIN_IDS))
async def admin_ga_duration(message: Message, state: FSMContext):
    end_time = int(time.time()) + int(float(message.text) * 3600)
    await state.update_data(end_time=end_time)
    await message.answer("Количество мест:")
    await state.set_state(AdminGiveawayState.waiting_for_winners)

@dp.message(AdminGiveawayState.waiting_for_winners, F.from_user.id.in_(config.ADMIN_IDS))
async def admin_ga_winners(message: Message, state: FSMContext):
    await state.update_data(winners=int(message.text))
    await message.answer("Вид приза?", reply_markup=prize_type_ikb())
    await state.set_state(AdminGiveawayState.waiting_for_prize_type)

@dp.callback_query(AdminGiveawayState.waiting_for_prize_type, F.data.startswith("ga_prize_"), F.from_user.id.in_(config.ADMIN_IDS))
async def admin_ga_prize_type(call: CallbackQuery, state: FSMContext):
    await state.update_data(prize_type=call.data.replace("ga_prize_", ""))
    await call.message.edit_text("Сумма приза (в рублях):")
    await state.set_state(AdminGiveawayState.waiting_for_prize_value)

@dp.message(AdminGiveawayState.waiting_for_prize_value, F.from_user.id.in_(config.ADMIN_IDS))
async def admin_ga_finish(message: Message, state: FSMContext):
    data = await state.get_data()
    db.create_giveaway(data['ga_type'], data['target_val'], data.get('end_time', 0), data.get('winners', 1), data['prize_type'], float(message.text))
    await message.answer("✅ Розыгрыш создан.")
    await state.clear()


@dp.message(F.from_user.id.in_(config.ADMIN_IDS))
async def admin_catch_all_emoji_and_stickers(message: Message, state: FSMContext):
    if await state.get_state() is not None: return 
    if message.sticker:
        return await message.answer(f"✅ <b>СТИКЕР!</b> ID:\n<code>{message.sticker.file_id}</code>\nВставлять так:\n<code>await message.answer_sticker(\"{message.sticker.file_id}\")</code>", parse_mode="HTML")
    custom_emojis = [ent for ent in message.entities or [] if ent.type == "custom_emoji"]
    if custom_emojis:
        codes = "\n\n".join([f'&lt;tg-emoji emoji-id="{e.custom_emoji_id}"&gt;💳&lt;/tg-emoji&gt;' for e in custom_emojis])
        return await message.answer(f"✅ <b>Эмодзи найдены!</b>\n\n<code>{codes}</code>", parse_mode="HTML")

async def check_giveaways_task(bot_instance: Bot):
    while True:
        try:
            await asyncio.sleep(60) 
            now = int(time.time())
            ended_gas = db.get_ended_giveaways(now)
            for ga in ended_gas:
                participants = db.get_giveaway_participants(ga['id'])
                db.finish_giveaway(ga['id']) 
                if not participants: continue
                
                winners = random.sample(participants, min(ga['winners_count'], len(participants)))
                for w in winners:
                    user_id = w['user_id']
                    if ga['prize_type'] == 'balance':
                        db.update_balance(user_id, ga['prize_value'])
                        user = db.get_user(user_id)
                        if user and user['notifications']:
                            try: await bot_instance.send_message(user_id, f"🎉 <b>ПОЗДРАВЛЯЕМ!</b> Вы победили!\nЗачислено <b>{ga['prize_value']} руб.</b>", parse_mode="HTML")
                            except: pass
                    else: 
                        promo_code = f"WIN-{str(uuid.uuid4())[:6].upper()}"
                        db.add_promocode(promo_code, 'discount', ga['prize_value'], 1)
                        user = db.get_user(user_id)
                        if user and user['notifications']:
                            try: await bot_instance.send_message(user_id, f"🎉 <b>ПОЗДРАВЛЯЕМ!</b>\nПромокод на скидку <b>{ga['prize_value']} руб.</b>:\n<code>{promo_code}</code>", parse_mode="HTML")
                            except: pass
        except: pass

async def main():
    db.init_db()
    print("Бот запущен. База данных готова!")
    asyncio.create_task(check_giveaways_task(bot))
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())