# mëpтв 🥀 | Декабрьский снег ♡ | Ultimate Hybrid Edition (Buttons + WebApp)
import logging
import uuid
import json
import asyncio
import os
from typing import Dict, List
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from yoomoney import Client, Quickpay
from aiohttp import web

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================= КОНФИГУРАЦИЯ =================

TOKEN = "8557420124:AAFuZfN5E1f0-qH-cIBSqI9JK309R6s88Q8"
ADMIN_ID = 1691654877
YOOMONEY_TOKEN = "86F31496F52C1B607A0D306BE0CAE639CFAFE7A45D3C88AF4E1759B22004954D"
YOOMONEY_WALLET = "4100118889570559"

# Ссылка на Mini App (Твой домен)
WEB_APP_URL = "https://mertvshop.bothost.tu" 

# ================= ИНИЦИАЛИЗАЦИЯ =================

try:
    ym_client = Client(YOOMONEY_TOKEN)
except Exception as e:
    logger.error(f"Ошибка инициализации Юмани: {e}")

user_carts: Dict[int, List[Dict]] = {}
user_states: Dict[int, Dict] = {}
active_orders: Dict[str, Dict] = {}

class Product:
    STARS = "stars"
    TG_PREMIUM_3 = "tg_premium_3"
    TG_PREMIUM_6 = "tg_premium_6"
    TG_PREMIUM_12 = "tg_premium_12"
    
    PRICES = {
        STARS: 1.6,
        TG_PREMIUM_3: 1250,
        TG_PREMIUM_6: 1500,
        TG_PREMIUM_12: 2750,
    }
    
    NAMES = {
        STARS: "Stars ⭐️",
        TG_PREMIUM_3: "Premium 3 мес.",
        TG_PREMIUM_6: "Premium 6 мес.",
        TG_PREMIUM_12: "Premium 12 мес.",
    }

# ================= ВЕБ-СЕРВЕР (Для работы Mini App) =================

async def http_handler(request):
    try:
        return web.FileResponse("index.html")
    except FileNotFoundError:
        return web.Response(text="Error 404: index.html not found", status=404)

# ================= ГЛАВНОЕ МЕНЮ =================

def get_main_menu_keyboard():
    return InlineKeyboardMarkup([
        # Гибридное меню: И Web App, И обычные кнопки
        [InlineKeyboardButton("📱 Открыть магазин (Mini App)", web_app=WebAppInfo(url=WEB_APP_URL))],
        [InlineKeyboardButton("🛍 Каталог (Кнопками)", callback_data='catalog')],
        [InlineKeyboardButton("🛒 Корзина", callback_data='cart'), InlineKeyboardButton("👤 Профиль", callback_data='profile')],
        [InlineKeyboardButton("👨‍💻 Поддержка", callback_data='support')]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = (
        f"👋 *Привет, {user.first_name}!*\n\n"
        "💎 *MEPTB STORE*\n"
        "Выберите удобный способ покупки:\n"
        "• Через красивое **Mini App**\n"
        "• Или классическими **кнопками**\n\n"
        "🚀 *Моментальная выдача*"
    )
    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=get_main_menu_keyboard(), parse_mode='Markdown')
    else:
        try: await update.callback_query.message.edit_text(welcome_text, reply_markup=get_main_menu_keyboard(), parse_mode='Markdown')
        except: await update.callback_query.message.reply_text(welcome_text, reply_markup=get_main_menu_keyboard(), parse_mode='Markdown')

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await query.message.edit_text("🏠 *Главное меню*", reply_markup=get_main_menu_keyboard(), parse_mode='Markdown')

# ================= ОБРАБОТКА WEB APP (САЙТ) =================

async def web_app_data_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        data = json.loads(update.effective_message.web_app_data.data)
    except: return

    cart_items = data.get('cart', {})
    stars_amount = data.get('stars', 0)
    
    if user_id not in user_carts: user_carts[user_id] = []
    added_text = []

    for p_id, count in cart_items.items():
        if count > 0 and p_id in Product.NAMES:
            for _ in range(count):
                user_carts[user_id].append({'type': p_id, 'name': Product.NAMES[p_id], 'price': Product.PRICES[p_id]})
            added_text.append(f"{Product.NAMES[p_id]}: {count} шт.")

    if stars_amount > 0:
        price = stars_amount * Product.PRICES[Product.STARS]
        user_carts[user_id].append({'type': Product.STARS, 'name': f"Stars ⭐️ ({stars_amount} шт.)", 'price': price, 'amount': stars_amount})
        added_text.append(f"Stars ⭐️: {stars_amount} шт.")

    if not added_text:
        await update.message.reply_text("❌ Пустой выбор.", reply_markup=get_main_menu_keyboard())
        return

    summary = "\n".join(added_text)
    await update.message.reply_text(f"✅ *Из Mini App добавлено:*\n{summary}\n\n👇 Перейдите в корзину.", parse_mode='Markdown', reply_markup=get_main_menu_keyboard())

# ================= СТАРАЯ ЛОГИКА (КНОПКИ) =================

async def show_catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    kb = [
        [InlineKeyboardButton("⭐️ Stars (Ввод числа)", callback_data='stars')],
        [InlineKeyboardButton("⚡️ Telegram Premium", callback_data='tg_premium')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')],
    ]
    await query.message.edit_text("🛍 *Каталог товаров*", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

# --- STARS (Ручной ввод) ---
async def stars_step1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = query.from_user.id
    user_states[user_id] = {'step': 'stars_amount', 'message_id': query.message.message_id}
    await query.message.edit_text("⌨️ *Введите количество звезд (числом):*\nКурс: 1.6₽", parse_mode='Markdown')

async def handle_stars_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in user_states or user_states[user_id].get('step') != 'stars_amount':
        if update.message.text == '/start': await start(update, context)
        return
    try:
        amount = int(update.message.text.strip())
        if amount <= 0: raise ValueError
        user_states[user_id]['amount'] = amount
        total = amount * Product.PRICES[Product.STARS]
        kb = [[InlineKeyboardButton("✅ Добавить", callback_data='confirm_stars'), InlineKeyboardButton("❌ Отмена", callback_data='cancel_stars')]]
        try: await context.bot.delete_message(chat_id=user_id, message_id=user_states[user_id]['message_id'])
        except: pass
        msg = await update.message.reply_text(f"Добавить {amount} Stars за {total:.2f}₽?", reply_markup=InlineKeyboardMarkup(kb))
        user_states[user_id]['message_id'] = msg.message_id
    except:
        await update.message.reply_text("❌ Введите корректное число.")

async def confirm_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = query.from_user.id
    if user_id in user_states:
        amt = user_states[user_id]['amount']
        price = amt * Product.PRICES[Product.STARS]
        if user_id not in user_carts: user_carts[user_id] = []
        user_carts[user_id].append({'type': Product.STARS, 'name': f"Stars ({amt})", 'price': price, 'amount': amt})
        del user_states[user_id]
        await query.message.edit_text("✅ Добавлено!")
        await back_to_menu(update, context)

async def cancel_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    if query.from_user.id in user_states: del user_states[query.from_user.id]
    await back_to_menu(update, context)

async def back_to_stars_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await stars_step1(update, context)

# --- PREMIUM (Кнопки) ---
async def tg_premium_option(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    kb = [
        [InlineKeyboardButton("3 мес - 1250₽", callback_data='add_tg_tg_premium_3')],
        [InlineKeyboardButton("6 мес - 1500₽", callback_data='add_tg_tg_premium_6')],
        [InlineKeyboardButton("12 мес - 2750₽", callback_data='add_tg_tg_premium_12')],
        [InlineKeyboardButton("🔙 Назад", callback_data='catalog')],
    ]
    await query.message.edit_text("⚡️ *Выберите период:*", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def add_to_cart_and_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = query.from_user.id
    mapping = {'add_tg_tg_premium_3': Product.TG_PREMIUM_3, 'add_tg_tg_premium_6': Product.TG_PREMIUM_6, 'add_tg_tg_premium_12': Product.TG_PREMIUM_12}
    ptype = mapping.get(query.data)
    if user_id not in user_carts: user_carts[user_id] = []
    user_carts[user_id].append({'type': ptype, 'name': Product.NAMES[ptype], 'price': Product.PRICES[ptype]})
    await query.message.edit_text(f"✅ {Product.NAMES[ptype]} добавлен!")
    await back_to_menu(update, context)

# ================= ОБЩИЙ ФУНКЦИОНАЛ (КОРЗИНА И ОПЛАТА) =================

async def show_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = query.from_user.id
    cart = user_carts.get(user_id, [])
    if not cart:
        await query.message.edit_text("🛒 *Корзина пуста*", reply_markup=get_main_menu_keyboard(), parse_mode='Markdown')
        return
    total = sum(item['price'] for item in cart)
    text = "🧾 *Ваш заказ:*\n\n"
    for idx, item in enumerate(cart, 1): text += f"{idx}. {item['name']} — {item['price']:.2f}₽\n"
    text += f"\n💰 *Итого: {total:.2f}₽*"
    kb = [[InlineKeyboardButton("💳 Оплатить (ЮMoney)", callback_data='checkout')], [InlineKeyboardButton("🗑 Очистить", callback_data='clear_cart')], [InlineKeyboardButton("🔙 Меню", callback_data='back_to_menu')]]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def clear_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_carts[update.callback_query.from_user.id] = []
    await show_cart(update, context)

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    cart = user_carts.get(query.from_user.id, [])
    await query.message.edit_text(f"👤 *Профиль*\nID: `{query.from_user.id}`\nВ корзине: {len(cart)} товаров", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='back_to_menu')]]), parse_mode='Markdown')

async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.message.edit_text("👨‍💻 Пишите админу: @slayip", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='back_to_menu')]]))

async def checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = query.from_user.id
    cart = user_carts.get(user_id, [])
    if not cart: return
    total = sum(item['price'] for item in cart)
    order_id = str(uuid.uuid4())
    active_orders[order_id] = {"user_id": user_id, "amount": total, "items": cart}
    try:
        quickpay = Quickpay(receiver=YOOMONEY_WALLET, quickpay_form="shop", targets=f"Order {order_id[:8]}", paymentType="SB", sum=total, label=order_id)
        text = f"💳 *Оплата*\nСумма: {total:.2f}₽\n\n1. Оплатите.\n2. Нажмите 'Проверить'."
        kb = [[InlineKeyboardButton("🔗 Оплатить", url=quickpay.base_url)], [InlineKeyboardButton("🔄 Проверить", callback_data=f'check_pay_{order_id}')], [InlineKeyboardButton("❌ Отмена", callback_data='back_to_menu')]]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    except Exception as e:
        logger.error(e); await query.message.edit_text("Ошибка создания счета")

async def check_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    order_id = query.data.replace('check_pay_', '')
    order_data = active_orders.get(order_id)
    if not order_data: await query.answer("Заказ не найден", show_alert=True); return
    try:
        history = ym_client.operation_history(label=order_id)
        if any(op.status == "success" and op.label == order_id for op in history.operations):
            await process_success(query, context, order_id, order_data)
        else: await query.answer("Оплата не найдена", show_alert=True)
    except: await query.answer("Ошибка проверки", show_alert=True)

async def process_success(query, context, order_id, order_data):
    user_id = order_data['user_id']
    del user_carts[user_id]; del active_orders[order_id]
    await query.message.edit_text("✅ *Оплата успешна!* Админ свяжется с вами.", parse_mode='Markdown', reply_markup=get_main_menu_keyboard())
    try: await context.bot.send_message(ADMIN_ID, f"💰 Новая продажа! {order_data['amount']}₽\nID: {user_id}")
    except: pass

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}", exc_info=context.error)

# ================= ЗАПУСК =================

async def main():
    # Настройка БОТА
    application = Application.builder().token(TOKEN).build()
    
    # Регистрация ВСЕХ обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data_handler))
    
    # Меню и общие
    application.add_handler(CallbackQueryHandler(back_to_menu, pattern='^back_to_menu$'))
    application.add_handler(CallbackQueryHandler(show_cart, pattern='^cart$'))
    application.add_handler(CallbackQueryHandler(show_support, pattern='^support$'))
    application.add_handler(CallbackQueryHandler(show_profile, pattern='^profile$'))
    application.add_handler(CallbackQueryHandler(clear_cart, pattern='^clear_cart$'))
    application.add_handler(CallbackQueryHandler(checkout, pattern='^checkout$'))
    application.add_handler(CallbackQueryHandler(check_payment, pattern='^check_pay_'))
    
    # СТАРАЯ ЛОГИКА (КНОПКИ)
    application.add_handler(CallbackQueryHandler(show_catalog, pattern='^catalog$'))
    application.add_handler(CallbackQueryHandler(stars_step1, pattern='^stars$'))
    application.add_handler(CallbackQueryHandler(confirm_stars, pattern='^confirm_stars$'))
    application.add_handler(CallbackQueryHandler(cancel_stars, pattern='^cancel_stars$'))
    application.add_handler(CallbackQueryHandler(back_to_stars_input, pattern='^back_to_stars_input$'))
    application.add_handler(CallbackQueryHandler(tg_premium_option, pattern='^tg_premium$'))
    application.add_handler(CallbackQueryHandler(add_to_cart_and_back, pattern='^add_tg_'))
    
    # Ввод текста (для звезд)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_stars_amount))
    application.add_error_handler(error_handler)
    
    # Запуск бота
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    print("🤖 Бот запущен...")

    # Настройка ВЕБ-СЕРВЕРА
    app = web.Application()
    app.router.add_get('/', http_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 3000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    print(f"🌍 Веб-сервер на порту {port}")
    await site.start()

    stop_event = asyncio.Event()
    await stop_event.wait()
    await application.stop(); await application.shutdown()

if __name__ == '__main__':
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
