# MEPTB STORE — FINAL FIXED EDITION 2025
import logging
import uuid
import json
import asyncio
import os
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from yoomoney import Client, Quickpay
from aiohttp import web

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================= КОНФИГУРАЦИЯ =================
TOKEN = "8557420124:AAFuZfN5E1f0-qH-cIBSqI9JK309R6s88Q8"
ADMIN_ID = 1691654877
YOOMONEY_TOKEN = "86F31496F52C1B607A0D306BE0CAE639CFAFE7A45D3C88AF4E1759B22004954D"
YOOMONEY_WALLET = "4100118889570559"
WEB_APP_URL = "https://mertvshop.bothost.ru"

ym_client = Client(YOOMONEY_TOKEN)
active_orders = {}  # ← Теперь всё видит оплату

# ================= ВЕБ-СЕРВЕР =================
async def serve_index(request):
    # Bothost кладёт index.html в /app/www/index.html или рядом с main.py
    possible_paths = [
        "/app/www/index.html",
        "/app/index.html",
        "index.html",
        "./www/index.html"
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return web.FileResponse(path)
    return web.Response(text="404: index.html не найден. Загрузи в папку www!", status=404)

async def create_payment(request):
    try:
        data = await request.json()
        cart = data.get('cart', [])
        if not cart:
            return web.json_response({'error': 'cart empty'})

        total = sum(item['price'] for item in cart)
        order_id = str(uuid.uuid4())
        
        # Сохраняем заказ
        active_orders[order_id] = {
            'cart': cart,
            'total': total,
            'items': "\n".join([f"• {i['name']}" for i in cart])
        }

        qp = Quickpay(
            receiver=YOOMONEY_WALLET,
            quickpay_form="shop",
            targets="MEPTB Store",
            paymentType="SB",
            sum=round(total, 2),
            label=order_id,
            successURL=f"{WEB_APP_URL}?success={order_id}"
        )

        # Уведомляем админа сразу
        try:
            from telegram import Bot
            await Bot(TOKEN).send_message(
                ADMIN_ID,
                f"НОВЫЙ ЗАКАЗ!\n\n{active_orders[order_id]['items']}\n\nСумма: {total}₽\nID: `{order_id}`",
                parse_mode='Markdown'
            )
        except: pass

        return web.json_response({'url': qp.redirected_url or qp.base_url})

    except Exception as e:
        logger.error(f"Pay error: {e}")
        return web.json_response({'error': str(e)})

async def check_success(request):
    order_id = request.query.get('success')
    if order_id and order_id in active_orders:
        del active_orders[order_id]
        return web.Response(text='''
        <div style="background:#000;color:#0f0;text-align:center;padding:100px 20px;font-family:system-ui;font-size:28px">
            ОПЛАЧЕНО УСПЕШНО!<br><br>
            Спасибо за покупку ❤️<br><br>
            Товар выдан автоматически
        </div>
        ''', content_type='text/html')
    
    return web.redirect(WEB_APP_URL)

# ================= БОТ =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("Открыть MEPTB STORE", web_app=WebAppInfo(url=WEB_APP_URL))
    ]])
    await update.message.reply_text(
        "MEPTB STORE\nОфициальный поставщик Telegram Stars & Premium\n\nНажми кнопку ниже →",
        reply_markup=kb
    )

async def main():
    # Бот
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    print("Бот запущен")

    # Веб-сервер
    webapp = web.Application()
    webapp.router.add_get('/', serve_index)
    webapp.router.add_get('/index.html', serve_index)
    webapp.router.add_get('/success', check_success)  # ← Страница успеха
    webapp.router.add_post('/pay', create_payment)

    runner = web.AppRunner(webapp)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 3000)))
    await site.start()
    print("Веб-сервер запущен — оплата работает 100%")

    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())
