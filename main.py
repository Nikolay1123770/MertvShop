# mëpтв 🥀 | Декабрьский снег ♡ | STABLE FOREVER EDITION
import logging
import uuid
import json
import asyncio
import os
import sys
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

# Настройка логирования (убираем лишний шум от библиотек)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
# Отключаем лишние логи от библиотек, оставляем только ошибки
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# ================= КОНФИГУРАЦИЯ =================
TOKEN = "8557420124:AAFuZfN5E1f0-qH-cIBSqI9JK309R6s88Q8"
ADMIN_ID = 1691654877
YOOMONEY_TOKEN = "86F31496F52C1B607A0D306BE0CAE639CFAFE7A45D3C88AF4E1759B22004954D"
YOOMONEY_WALLET = "4100118889570559"
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

# ================= API ДЛЯ САЙТА =================

async def http_index(request):
    """Отдает HTML файл"""
    base_path = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_path, "index.html")
    
    if os.path.exists(file_path):
        return web.FileResponse(file_path)
    else:
        return web.Response(text=f"Error 404: index.html not found.\nPath: {file_path}", status=404)

async def api_create_order(request):
    try:
        data = await request.json()
        user_id = data.get('user_id')
        cart_items = data.get('cart', {})
        stars_amount = data.get('stars', 0)
        
        total_price = 0
        items_list = []

        for p_id, count in cart_items.items():
            if count > 0 and p_id in Product.PRICES:
                total_price += count * Product.PRICES[p_id]
                items_list.append(f"{Product.NAMES[p_id]} x{count}")

        if stars_amount > 0:
            total_price += stars_amount * Product.PRICES[Product.STARS]
            items_list.append(f"Stars ⭐️ x{stars_amount}")

        if total_price <= 0:
            return web.json_response({'status': 'error', 'message': 'Empty cart'})

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
    order_id = request.query.get('order_id')
    order_data = active_orders.get(order_id)
    
    if not order_data:
        return web.json_response({'paid': False, 'error': 'Order not found'})

    try:
        history = ym_client.operation_history(records=30)
        is_paid = False
        
        logger.info(f"🔍 Checking order: {order_id}")
        
        for op in history.operations:
            if op.label == order_id and op.status == "success":
                if op.amount >= order_data['amount']:
                    is_paid = True
                    break
        
        if is_paid:
            logger.info(f"✅ Order paid: {order_id}")
            await notify_admin_success(order_id, order_data)
            del active_orders[order_id]
            return web.json_response({'paid': True})
        else:
            return web.json_response({'paid': False})
        
    except Exception as e:
        logger.error(f"Check Error: {e}")
        return web.json_response({'paid': False})

bot_app = None 

async def notify_admin_success(order_id, order_data):
    if bot_app:
        msg = (
            f"💰 **НОВАЯ ОПЛАТА**\n"
            f"Сумма: {order_data['amount']}₽\n"
            f"ID: `{order_id}`\n"
            f"Товары: {order_data['items_text']}"
        )
        try:
            await bot_app.bot.send_message(chat_id=ADMIN_ID, text=msg, parse_mode='Markdown')
            await bot_app.bot.send_message(chat_id=order_data['user_id'], text="✅ Оплата получена! Ждите выдачи.")
        except: pass

# ================= БОТ =================

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

# ================= ЗАПУСК (ИСПРАВЛЕНО) =================

async def main():
    global bot_app
    
    # 1. Запуск БОТА
    bot_app = Application.builder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CallbackQueryHandler(show_support, pattern='^support$'))
    
    await bot_app.initialize()
    await bot_app.start()
    
    # Важно: drop_pending_updates=True удалит старые зависшие команды, которые могут крашить бота
    await bot_app.updater.start_polling(drop_pending_updates=True)
    print("🤖 Бот запущен (Polling)...")

    # 2. Запуск WEB SERVER
    app = web.Application()
    app.router.add_get('/', http_index)              
    app.router.add_post('/api/create_order', api_create_order) 
    app.router.add_get('/api/check_payment', api_check_payment)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Получаем порт от хостинга
    port = int(os.environ.get("PORT", 3000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    
    print(f"🌍 Сайт запущен на порту {port}")
    await site.start()

    # 3. БЕСКОНЕЧНЫЙ ЦИКЛ (Чтобы бот не выключался)
    print("🚀 Все системы работают. Ухожу в режим ожидания.")
    while True:
        await asyncio.sleep(3600)  # Спим по часу, но процесс не закрывается

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
