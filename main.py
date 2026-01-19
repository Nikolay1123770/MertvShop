import logging
import uuid
import json
import asyncio
import os
import sys
import hmac
import hashlib
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
YOOMONEY_WALLET = "4100118944797800"
YOOMONEY_NOTIFICATION_SECRET = "fL8QIMDHIeudGlqCPNR7eux/"  # Получить в настройках HTTP-уведомлений
WEB_APP_URL = "https://mertvshop.bothost.ru" 
PAYMENT_CHECK_INTERVAL = 10  # Интервал проверки платежей в секундах (для подстраховки)

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
    """Отдает HTML файл, вычисляя абсолютный путь"""
    base_path = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_path, "index.html")
    
    if os.path.exists(file_path):
        return web.FileResponse(file_path)
    else:
        return web.Response(text=f"Error 404: index.html not found.\nSearched in: {file_path}", status=404)

async def api_create_order(request):
    """Создает заказ и возвращает ссылку на оплату"""
    try:
        data = await request.json()
        user_id = data.get('user_id')
        cart_items = data.get('cart', {})
        stars_amount = data.get('stars', 0)
        
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

        order_id = str(uuid.uuid4())
        active_orders[order_id] = {
            "user_id": user_id,
            "amount": total_price,
            "items_text": ", ".join(items_list),
            "status": "pending",
            "created_at": asyncio.get_event_loop().time()
        }

        # Создаем платеж с редиректом обратно в приложение
        success_url = f"{WEB_APP_URL}/success?order_id={order_id}"
        quickpay = Quickpay(
            receiver=YOOMONEY_WALLET,
            quickpay_form="shop",
            targets=f"Order {order_id[:8]}",
            paymentType="SB",
            sum=total_price,
            label=order_id,
            successURL=success_url
        )

        return web.json_response({
            'status': 'ok',
            'order_id': order_id,
            'payment_url': quickpay.base_url,
            'amount': total_price,
            'auto_check': True  # Указываем клиенту, что проверка автоматическая
        })

    except Exception as e:
        logger.error(f"API Error: {e}")
        return web.json_response({'status': 'error', 'message': str(e)}, status=500)

async def api_check_payment(request):
    """API для проверки статуса оплаты"""
    order_id = request.query.get('order_id')
    if not order_id or order_id not in active_orders:
        return web.json_response({'paid': False, 'error': 'Order not found'})
    
    order_data = active_orders[order_id]
    
    # Если заказ уже оплачен в нашей системе
    if order_data.get('status') == 'paid':
        return web.json_response({'paid': True, 'status': 'completed'})
        
    # Если заказ еще в обработке, проверяем через API
    try:
        is_paid = await check_payment_status(order_id)
        if is_paid:
            return web.json_response({'paid': True, 'status': 'completed'})
        else:
            return web.json_response({
                'paid': False, 
                'status': 'pending',
                'message': 'Ожидание оплаты. Статус обновляется автоматически.'
            })
        
    except Exception as e:
        logger.error(f"Payment check error: {e}")
        return web.json_response({'paid': False, 'error': str(e)})

async def check_payment_status(order_id):
    """Проверяет статус оплаты через API ЮМани"""
    if order_id not in active_orders:
        return False
        
    order_data = active_orders[order_id]
    if order_data.get('status') == 'paid':
        return True
        
    try:
        history = ym_client.operation_history(label=order_id)
        is_paid = any(op.status == "success" and op.label == order_id for op in history.operations)
        
        if is_paid:
            await process_successful_payment(order_id, order_data)
            return True
            
        return False
        
    except Exception as e:
        logger.error(f"YooMoney API Error: {e}")
        return False

# ================= ОБРАБОТКА УВЕДОМЛЕНИЙ ЮМАНИ =================

async def yoomoney_notification(request):
    """Обработчик уведомлений от ЮМани"""
    try:
        data = await request.post()
        logger.info(f"YooMoney notification received: {data}")
        
        # Проверка подписи
        notification_type = data.get('notification_type')
        operation_id = data.get('operation_id')
        amount = data.get('amount')
        currency = data.get('currency')
        datetime_str = data.get('datetime')
        sender = data.get('sender')
        codepro = data.get('codepro')
        label = data.get('label')
        sha1_hash = data.get('sha1_hash')
        
        # Формируем строку для проверки подписи
        check_str = f"{notification_type}&{operation_id}&{amount}&{currency}&{datetime_str}&{sender}&{codepro}&{YOOMONEY_NOTIFICATION_SECRET}&{label}"
        calculated_hash = hashlib.sha1(check_str.encode()).hexdigest()
        
        # Проверяем подпись
        if calculated_hash != sha1_hash:
            logger.warning(f"Invalid hash from YooMoney: {sha1_hash} vs {calculated_hash}")
            return web.Response(text="Invalid signature", status=400)
        
        # Проверяем тип уведомления и статус операции
        if notification_type == 'p2p-incoming' and codepro == 'false':
            order_id = label
            if order_id in active_orders:
                order_data = active_orders[order_id]
                await process_successful_payment(order_id, order_data)
                logger.info(f"Payment processed via notification: {order_id}")
            else:
                logger.warning(f"Payment for unknown order: {order_id}")
                
        return web.Response(text="OK", status=200)
        
    except Exception as e:
        logger.error(f"Error processing YooMoney notification: {e}")
        return web.Response(text="Error", status=500)

# ================= ПЕРИОДИЧЕСКАЯ ПРОВЕРКА ПЛАТЕЖЕЙ =================

async def periodic_payment_check():
    """Регулярно проверяет активные заказы для подстраховки"""
    while True:
        try:
            current_time = asyncio.get_event_loop().time()
            orders_to_check = []
            
            # Собираем заказы для проверки
            for order_id, order_data in active_orders.items():
                if order_data.get('status') != 'paid':
                    # Проверяем заказы не старше 24 часов
                    if current_time - order_data.get('created_at', 0) < 86400:
                        orders_to_check.append(order_id)
            
            # Проверяем каждый заказ
            for order_id in orders_to_check:
                await check_payment_status(order_id)
                
            # Чистим старые заказы (старше 24 часов)
            for order_id in list(active_orders.keys()):
                order_data = active_orders[order_id]
                if current_time - order_data.get('created_at', 0) > 86400:
                    if order_data.get('status') != 'paid':
                        logger.info(f"Removing expired order: {order_id}")
                        del active_orders[order_id]
            
        except Exception as e:
            logger.error(f"Error in periodic payment check: {e}")
            
        await asyncio.sleep(PAYMENT_CHECK_INTERVAL)

# ================= ОБЩИЕ ФУНКЦИИ =================

bot_app = None 

async def process_successful_payment(order_id, order_data):
    """Обработка успешного платежа"""
    if order_data.get('status') == 'paid':
        return  # Уже обработан
        
    # Обновляем статус заказа
    order_data['status'] = 'paid'
    
    # Уведомляем админа и пользователя
    await notify_admin_success(order_id, order_data)

async def notify_admin_success(order_id, order_data):
    if bot_app:
        msg = (
            f"💰 НОВАЯ ОПЛАТА\n"
            f"Сумма: {order_data['amount']}₽\n"
            f"User ID: {order_data['user_id']}\n"
            f"Товары: {order_data['items_text']}\n"
            f"ID: {order_id}"
        )
        try:
            await bot_app.bot.send_message(chat_id=ADMIN_ID, text=msg, parse_mode='Markdown')
            await bot_app.bot.send_message(chat_id=order_data['user_id'], text="✅ Оплата получена! Ждите выдачи.")
        except Exception as e:
            logger.error(f"Error sending notification: {e}")

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

async def main():
    global bot_app
    
    # 1. БОТ
    bot_app = Application.builder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CallbackQueryHandler(show_support, pattern='^support$'))
    
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling()
    print("🤖 Бот работает...")

    # 2. WEB SERVER
    app = web.Application()
    app.router.add_get('/', http_index)              
    app.router.add_post('/api/create_order', api_create_order) 
    app.router.add_get('/api/check_payment', api_check_payment)
    app.router.add_post('/api/yoomoney_notification', yoomoney_notification)
    
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 3000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    print(f"🌍 API запущен на порту {port}")
    await site.start()
    
    # 3. Запускаем фоновую проверку платежей для подстраховки
    asyncio.create_task(periodic_payment_check())
    
    print("💰 Автоматическая система платежей запущена")

    stop_event = asyncio.Event()
    await stop_event.wait()

if __name__ == '__main__':
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
