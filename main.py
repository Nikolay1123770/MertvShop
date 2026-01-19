import logging
import uuid
import json
import asyncio
import os
import sys
import hashlib
import hmac
import time
from datetime import datetime
from typing import Dict, List, Optional
import aiohttp
from urllib.parse import urlencode

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
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
YOOMONEY_WALLET = "4100118889570559"
YOOMONEY_NOTIFICATION_SECRET = "fL8QIMDHIeudGlqCPNR7eux/"
WEB_APP_URL = "https://mertvshop.bothost.ru"

# ================= ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ =================
active_orders = {}

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

# ================= ФУНКЦИИ ПЛАТЕЖЕЙ =================

def generate_yoomoney_url(order_id, amount, description):
    """
    Генерирует URL для оплаты через ЮМани без использования библиотеки
    """
    base_url = "https://yoomoney.ru/quickpay/confirm.xml"
    
    params = {
        "receiver": YOOMONEY_WALLET,
        "quickpay-form": "small",
        "targets": description,
        "paymentType": "SB",
        "sum": amount,
        "label": order_id,
        "successURL": f"{WEB_APP_URL}/success?order_id={order_id}"
    }
    
    return f"{base_url}?{urlencode(params)}"

# ================= API ДЛЯ САЙТА =================

async def http_index(request):
    """Отдает HTML файл"""
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
        
        # Вычисляем общую стоимость и формируем описание товаров
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
            return web.json_response({'status': 'error', 'message': 'Пустая корзина'})

        # Создаем уникальный ID заказа
        order_id = str(uuid.uuid4())
        
        # Формируем описание для платежа
        description = f"Order {order_id[:8]}"
        items_text = ", ".join(items_list)
        
        # Сохраняем информацию о заказе
        active_orders[order_id] = {
            "user_id": user_id,
            "amount": total_price,
            "items_text": items_text,
            "status": "pending",
            "created_at": time.time()
        }
        
        # Генерируем платежную ссылку
        payment_url = generate_yoomoney_url(
            order_id=order_id,
            amount=total_price,
            description=description
        )
        
        return web.json_response({
            'status': 'ok',
            'order_id': order_id,
            'payment_url': payment_url,
            'amount': total_price,
            'auto_check': True
        })

    except Exception as e:
        logger.error(f"API Error: {e}")
        return web.json_response({'status': 'error', 'message': str(e)}, status=500)

async def api_check_payment(request):
    """Проверяет статус оплаты заказа"""
    order_id = request.query.get('order_id')
    
    if not order_id or order_id not in active_orders:
        return web.json_response({
            'paid': False, 
            'error': 'Заказ не найден'
        })
    
    order = active_orders.get(order_id)
    
    if order.get('status') == 'paid':
        return web.json_response({
            'paid': True,
            'status': 'completed'
        })
    
    return web.json_response({
        'paid': False,
        'status': 'pending',
        'message': 'Ожидание подтверждения оплаты'
    })

async def api_success_payment(request):
    """Обрабатывает возврат после успешной оплаты"""
    order_id = request.query.get('order_id')
    
    if not order_id or order_id not in active_orders:
        return web.Response(text="Заказ не найден", status=404)
    
    order = active_orders.get(order_id)
    
    # Если заказ еще не отмечен как оплаченный, обрабатываем его
    if order.get('status') != 'paid':
        order['status'] = 'paid'
        # Отправляем уведомления
        asyncio.create_task(notify_payment_success(order_id, order))
    
    # Редирект на страницу успеха
    return web.Response(
        body='<html><script>window.close();</script><body>Оплата получена! Вы можете закрыть это окно.</body></html>',
        content_type='text/html'
    )

async def yoomoney_notification(request):
    """Обрабатывает уведомления от ЮМани"""
    try:
        data = await request.post()
        logger.info(f"Получено уведомление от ЮМани: {data}")
        
        # Получение параметров
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
            logger.warning(f"Недействительная подпись от ЮМани: {sha1_hash}")
            return web.Response(text="Неверная подпись", status=400)
        
        # Проверяем тип уведомления
        if notification_type == 'p2p-incoming' and codepro == 'false':
            order_id = label
            
            # Проверяем наличие заказа
            if order_id in active_orders:
                order = active_orders[order_id]
                
                # Проверяем статус заказа
                if order.get('status') != 'paid':
                    order['status'] = 'paid'
                    # Отправляем уведомления
                    asyncio.create_task(notify_payment_success(order_id, order))
                    logger.info(f"Платеж подтвержден через уведомление: {order_id}")
            else:
                logger.warning(f"Получен платеж для неизвестного заказа: {order_id}")
        
        return web.Response(text="OK")
        
    except Exception as e:
        logger.error(f"Ошибка обработки уведомления ЮМани: {e}")
        return web.Response(text="Ошибка", status=500)

# ================= ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =================

bot_app = None

async def notify_payment_success(order_id, order):
    """Отправляет уведомления о успешной оплате"""
    if bot_app:
        try:
            # Уведомление администратору
            admin_message = (
                f"💰 НОВАЯ ОПЛАТА\n"
                f"Сумма: {order['amount']}₽\n"
                f"User ID: {order['user_id']}\n"
                f"Товары: {order['items_text']}\n"
                f"ID: {order_id}"
            )
            
            await bot_app.bot.send_message(
                chat_id=ADMIN_ID, 
                text=admin_message
            )
            
            # Уведомление пользователю
            user_message = "✅ Оплата успешно получена! Спасибо за покупку. Ваш заказ будет обработан в ближайшее время."
            
            await bot_app.bot.send_message(
                chat_id=order['user_id'],
                text=user_message
            )
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления: {e}")

async def cleanup_old_orders():
    """Периодическая очистка старых заказов (раз в час)"""
    while True:
        try:
            current_time = time.time()
            
            # Удаляем заказы старше 24 часов
            for order_id in list(active_orders.keys()):
                order = active_orders[order_id]
                if current_time - order.get('created_at', 0) > 86400:
                    if order.get('status') != 'paid':
                        logger.info(f"Удаление устаревшего заказа: {order_id}")
                        del active_orders[order_id]
        
        except Exception as e:
            logger.error(f"Ошибка при очистке старых заказов: {e}")
        
        # Запускаем каждый час
        await asyncio.sleep(3600)

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

# ================= ОСНОВНАЯ ФУНКЦИЯ =================

async def main():
    global bot_app
    
    # 1. Запускаем бота
    bot_app = Application.builder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CallbackQueryHandler(show_support, pattern='^support$'))
    
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling()
    print("🤖 Бот работает...")

    # 2. Запускаем веб-сервер для API
    app = web.Application()
    app.router.add_get('/', http_index)              
    app.router.add_post('/api/create_order', api_create_order)
    app.router.add_get('/api/check_payment', api_check_payment)
    app.router.add_post('/api/yoomoney_notification', yoomoney_notification)
    app.router.add_get('/success', api_success_payment)  # Обработка успешного платежа
    
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 3000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"🌍 API запущен на порту {port}")
    
    # 3. Запускаем фоновую задачу очистки старых заказов
    asyncio.create_task(cleanup_old_orders())
    print("💰 Система платежей запущена")

    # 4. Ждем остановки
    stop_event = asyncio.Event()
    await stop_event.wait()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
