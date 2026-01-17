# mëpтв 🥀 | Декабрьский снег ♡ | Ultimate Edition (Mini App + Hybrid)
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
# 🔴 ЗАПОЛНИ ЭТИ ДАННЫЕ 🔴
TOKEN = "8557420124:AAFuZfN5E1f0-qH-cIBSqI9JK309R6s88Q8"
ADMIN_ID = 1691654877
YOOMONEY_TOKEN = "86F31496F52C1B607A0D306BE0CAE639CFAFE7A45D3C88AF4E1759B22004954D"
YOOMONEY_WALLET = "4100118889570559"

# Ссылка на твой сайт (Mini App). Убедись, что это HTTPS.
WEB_APP_URL = "https://mertvshop.bothost.ru" 

# ================= ИНИЦИАЛИЗАЦИЯ =================

try:
    ym_client = Client(YOOMONEY_TOKEN)
except Exception as e:
    logger.error(f"Ошибка Юмани: {e}")

# База данных в памяти
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

# ================= ВЕБ-СЕРВЕР (ДЛЯ MINI APP) =================

async def http_handler(request):
    """Отдает красивый index.html"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, "index.html")
    
    if os.path.exists(file_path):
        return web.FileResponse(file_path)
    else:
        return web.Response(text=f"Error 404: index.html not found in {current_dir}", status=404)

# ================= ГЛАВНОЕ МЕНЮ =================

def get_main_menu_keyboard():
    return InlineKeyboardMarkup([
        # Кнопка для открытия Mini App
        [InlineKeyboardButton("📱 Открыть магазин (Mini App)", web_app=WebAppInfo(url=WEB_APP_URL))],
        # Кнопка для старого текстового меню
        [InlineKeyboardButton("🛍 Каталог (Текст)", callback_data='catalog')],
        [InlineKeyboardButton("🛒 Корзина", callback_data='cart'), InlineKeyboardButton("👤 Профиль", callback_data='profile')],
        [InlineKeyboardButton("👨‍💻 Поддержка", callback_data='support')]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = (
        f"👋 *Привет, {user.first_name}!*\n\n"
        "💎 *MEPTB STORE*\n"
        "Магазин цифровых товаров с моментальной выдачей.\n\n"
        "👇 *Нажмите кнопку ниже, чтобы открыть магазин:*"
    )
    
    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=get_main_menu_keyboard(), parse_mode='Markdown')
    else:
        try: await update.callback_query.message.edit_text(welcome_text, reply_markup=get_main_menu_keyboard(), parse_mode='Markdown')
        except: await update.callback_query.message.reply_text(welcome_text, reply_markup=get_main_menu_keyboard(), parse_mode='Markdown')

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await query.message.edit_text("🏠 *Главное меню*", reply_markup=get_main_menu_keyboard(), parse_mode='Markdown')

# ================= ОБРАБОТКА ДАННЫХ ИЗ MINI APP =================

async def web_app_data_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        data = json.loads(update.effective_message.web_app_data.data)
    except:
        return

    cart_items = data.get('cart', {})
    stars_amount = data.get('stars', 0)
    
    if user_id not in user_carts: user_carts[user_id] = []
    added_text = []

    # Добавляем Premium
    for p_id, count in cart_items.items():
        if count > 0 and p_id in Product.NAMES:
            for _ in range(count):
                user_carts[user_id].append({'type': p_id, 'name': Product.NAMES[p_id], 'price': Product.PRICES[p_id]})
            added_text.append(f"{Product.NAMES[p_id]}: {count} шт.")

    # Добавляем Stars
    if stars_amount > 0:
        price = stars_amount * Product.PRICES[Product.STARS]
        user_carts[user_id].append({'type': Product.STARS, 'name': f"Stars ⭐️ ({stars_amount} шт.)", 'price': price, 'amount': stars_amount})
        added_text.append(f"Stars ⭐️: {stars_amount} шт.")

    if not added_text:
        await update.message.reply_text("❌ Вы ничего не выбрали.", reply_markup=get_main_menu_keyboard())
        return

    summary = "\n".join(added_text)
    await update.message.reply_text(
        f"✅ *Товары добавлены в корзину:*\n\n{summary}\n\n👇 Нажмите «Корзина», чтобы оплатить.",
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )

# ================= СТАРЫЕ ФУНКЦИИ (КНОПКИ) =================
# Оставляем их для тех, у кого не грузит Web App

async def show_catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    kb = [
        [InlineKeyboardButton("⭐️ Stars", callback_data='stars'), InlineKeyboardButton("⚡️ Premium", callback_data='tg_premium')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')],
    ]
    await query.message.edit_text("🛍 *Каталог (Текстовая версия)*", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def stars_step1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = query.from_user.id
    user_states[user_id] = {'step': 'stars_amount', 'message_id': query.message.message_id}
    await query.message.edit_text("⌨️ *Введите количество звезд (числом):*", parse_mode='Markdown')

async def handle_stars_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in user_states: return
    try:
        amount = int(update.message.text.strip())
        user_states[user_id]['amount'] = amount
        total = amount * Product.PRICES[Product.STARS]
        kb = [[InlineKeyboardButton("✅ Добавить", callback_data='confirm_stars'), InlineKeyboardButton("❌ Отмена", callback_data='cancel_stars')]]
        await update.message.reply_text(f"Добавить {amount} Stars ({total}₽)?", reply_markup=InlineKeyboardMarkup(kb))
    except: pass

async def confirm_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer(); user_id = query.from_user.id
    if user_id in user_states:
        amt = user_states[user_id]['amount']
        user_carts.setdefault(user_id, []).append({'type': Product.STARS, 'name': f"Stars ({amt})", 'price': amt*1.6, 'amount': amt})
        del user_states[user_id]
        await query.message.edit_text("✅ Добавлено!")
        await back_to_menu(update, context)

async def cancel_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer(); del user_states[query.from_user.id]; await back_to_menu(update, context)

async def back_to_stars_input(update: Update, context: ContextTypes.DEFAULT_TYPE): await stars_step1(update, context)

async def tg_premium_option(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    kb = [[InlineKeyboardButton("3 мес", callback_data='add_tg_tg_premium_3')], [InlineKeyboardButton("🔙", callback_data='back_to_menu')]]
    await query.message.edit_text("Premium:", reply_markup=InlineKeyboardMarkup(kb))

async def add_to_cart_and_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer(); await back_to_menu(update, context)

# ================= КОРЗИНА И ОПЛАТА =================

async def show_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = query.from_user.id
    cart = user_carts.get(user_id, [])
    if not cart:
        await query.message.edit_text("🛒 *Корзина пуста*", reply_markup=get_main_menu_keyboard(), parse_mode='Markdown')
        return
    total = sum(item['price'] for item in cart)
    text = "🧾 *Ваш заказ:*\n\n"
    for item in cart: text += f"▫️ {item['name']} — {item['price']:.2f}₽\n"
    text += f"\n💰 *Итого: {total:.2f}₽*"
    kb = [[InlineKeyboardButton("💳 Оплатить (ЮMoney)", callback_data='checkout')], [InlineKeyboardButton("🗑 Очистить", callback_data='clear_cart')], [InlineKeyboardButton("🔙 Меню", callback_data='back_to_menu')]]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def clear_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_carts[update.callback_query.from_user.id] = []
    await show_cart(update, context)

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
    except: await query.message.edit_text("Ошибка создания счета")

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
    await query.message.edit_text("✅ *Оплата успешна!*", parse_mode='Markdown', reply_markup=get_main_menu_keyboard())
    try: await context.bot.send_message(ADMIN_ID, f"💰 Новая продажа! {order_data['amount']}₽\nID: {user_id}")
    except: pass

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    cart = user_carts.get(query.from_user.id, [])
    await query.message.edit_text(f"👤 *Профиль*\nID: `{query.from_user.id}`\nВ корзине: {len(cart)} товаров", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='back_to_menu')]]), parse_mode='Markdown')

async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.message.edit_text("👨‍💻 Пишите админу: @slayip", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='back_to_menu')]]))

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}", exc_info=context.error)

# ================= ЗАПУСК =================

async def main():
    # Настройка бота
    application = Application.builder().token(TOKEN).build()
    
    # Хендлеры
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data_handler))
    
    application.add_handler(CallbackQueryHandler(back_to_menu, pattern='^back_to_menu$'))
    application.add_handler(CallbackQueryHandler(show_cart, pattern='^cart$'))
    application.add_handler(CallbackQueryHandler(show_support, pattern='^support$'))
    application.add_handler(CallbackQueryHandler(show_profile, pattern='^profile$'))
    application.add_handler(CallbackQueryHandler(clear_cart, pattern='^clear_cart$'))
    application.add_handler(CallbackQueryHandler(checkout, pattern='^checkout$'))
    application.add_handler(CallbackQueryHandler(check_payment, pattern='^check_pay_'))
    
    # Старые кнопки
    application.add_handler(CallbackQueryHandler(show_catalog, pattern='^catalog$'))
    application.add_handler(CallbackQueryHandler(stars_step1, pattern='^stars$'))
    application.add_handler(CallbackQueryHandler(confirm_stars, pattern='^confirm_stars$'))
    application.add_handler(CallbackQueryHandler(cancel_stars, pattern='^cancel_stars$'))
    application.add_handler(CallbackQueryHandler(back_to_stars_input, pattern='^back_to_stars_input$'))
    application.add_handler(CallbackQueryHandler(tg_premium_option, pattern='^tg_premium$'))
    application.add_handler(CallbackQueryHandler(add_to_cart_and_back, pattern='^add_tg_'))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_stars_amount))
    
    application.add_error_handler(error_handler)
    
    # Запуск бота
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    print("🤖 Бот запущен...")

    # Настройка Web Server
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
