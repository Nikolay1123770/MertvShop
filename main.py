# mëpтв 🥀 | Декабрьский снег ♡ | Full SPA Edition
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
TOKEN = "ВСТАВЬ_ТОКЕН_БОТА"
ADMIN_ID = 1691654877
YOOMONEY_TOKEN = "ВСТАВЬ_ТОКЕН_ЮМАНИ"
YOOMONEY_WALLET = "ВСТАВЬ_НОМЕР_КОШЕЛЬКА"
WEB_APP_URL = "https://mertvshop.bothost.ru" 

# ================= ИНИЦИАЛИЗАЦИЯ =================
try:
    ym_client = Client(YOOMONEY_TOKEN)
except Exception as e:
    logger.error(f"Error YM: {e}")

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

# ================= API ДЛЯ САЙТА (WEB APP) =================

async def http_index(request):
    """Отдает HTML файл"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, "index.html")
    if os.path.exists(file_path):
        return web.FileResponse(file_path)
    return web.Response(text="404: index.html not found", status=404)

async def api_create_order(request):
    """Создает заказ и возвращает ссылку на оплату"""
    try:
        data = await request.json()
        user_id = data.get('user_id')
        cart_items = data.get('cart', {})
        stars_amount = data.get('stars', 0)
        
        # Считаем сумму на сервере (безопасно)
        total_price = 0
        items_list = []

        # Premium
        for p_id, count in cart_items.items():
            if count > 0 and p_id in Product.PRICES:
                total_price += count * Product.PRICES[p_id]
                items_list.append(f"{Product.NAMES[p_id]} x{count}")

        # Stars
        if stars_amount > 0:
            total_price += stars_amount * Product.PRICES[Product.STARS]
            items_list.append(f"Stars ⭐️ x{stars_amount}")

        if total_price <= 0:
            return web.json_response({'status': 'error', 'message': 'Empty cart'})

        # Генерируем ссылку
        order_id = str(uuid.uuid4())
        active_orders[order_id] = {
            "user_id": user_id,
            "amount": total_price,
            "items_text": ", ".join(items_list)
        }

        quickpay = Quickpay(
            receiver=YOOMONEY_WALLET,
            quickpay_form="shop",
            targets=f"Order {order_id[:8]}",
            paymentType="SB",
            sum=total_price,
            label=order_id
        )

        return web.json_response({
            'status': 'ok',
            'order_id': order_id,
            'payment_url': quickpay.base_url,
            'amount': total_price
        })

    except Exception as e:
        logger.error(f"API Error: {e}")
        return web.json_response({'status': 'error'}, status=500)

async def api_check_payment(request):
    """Проверяет оплату по запросу с сайта"""
    order_id = request.query.get('order_id')
    order_data = active_orders.get(order_id)
    
    if not order_data:
        return web.json_response({'paid': False, 'error': 'Order not found'})

    try:
        history = ym_client.operation_history(label=order_id)
        is_paid = any(op.status == "success" and op.label == order_id for op in history.operations)
        
        if is_paid:
            # Если оплачено - уведомляем админа и удаляем заказ
            await notify_admin_success(order_id, order_data)
            del active_orders[order_id]
            return web.json_response({'paid': True})
            
        return web.json_response({'paid': False})
        
    except Exception as e:
        logger.error(f"Check Error: {e}")
        return web.json_response({'paid': False})

# Глобальная переменная для application, чтобы отправлять сообщения
bot_app = None 

async def notify_admin_success(order_id, order_data):
    """Отправляет уведомление админу в Телеграм"""
    if bot_app:
        msg = (
            f"💰 **НОВАЯ ОПЛАТА (Через WebApp)**\n"
            f"Сумма: {order_data['amount']}₽\n"
            f"User ID: `{order_data['user_id']}`\n"
            f"Товары: {order_data['items_text']}\n"
            f"ID: `{order_id}`"
        )
        try:
            await bot_app.bot.send_message(chat_id=ADMIN_ID, text=msg, parse_mode='Markdown')
            # Можно и пользователю спасибо сказать
            await bot_app.bot.send_message(chat_id=order_data['user_id'], text="✅ Оплата получена! Ждите выдачи.")
        except:
            pass

# ================= БОТ (ТОЛЬКО ЗАПУСК И МЕНЮ) =================

def get_main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛍 Открыть магазин", web_app=WebAppInfo(url=WEB_APP_URL))],
        [InlineKeyboardButton("👨‍💻 Поддержка", callback_data='support')]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *MEPTB SHOP*\nЛучшие цифровые товары.\nЖми кнопку:",
        reply_markup=get_main_menu_keyboard(),
        parse_mode='Markdown'
    )

async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("Админ: @slayip")

async def main():
    global bot_app
    
    # 1. Запуск Бота
    bot_app = Application.builder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CallbackQueryHandler(show_support, pattern='^support$'))
    
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling()
    print("🤖 Бот работает...")

    # 2. Запуск Веб-сервера (API + Сайт)
    app = web.Application()
    app.router.add_get('/', http_index)              # Главная
    app.router.add_post('/api/create_order', api_create_order) # Создание заказа
    app.router.add_get('/api/check_payment', api_check_payment) # Проверка
    
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 3000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    print(f"🌍 API запущен на порту {port}")
    await site.start()

    stop_event = asyncio.Event()
    await stop_event.wait()

if __name__ == '__main__':
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
