# mëpтв 🥀 | Декабрьский снег ♡ | Professional Edition
import logging
import uuid
from typing import Dict, List
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from yoomoney import Client, Quickpay

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================= КОНФИГУРАЦИЯ =================
TOKEN = "8557420124:AAFuZfN5E1f0-qH-cIBSqI9JK309R6s88Q8"  # <--- ВСТАВЬ ТОКЕН БОТА
ADMIN_ID = 1691654877

# Юмани настройки
YOOMONEY_TOKEN = "86F31496F52C1B607A0D306BE0CAE639CFAFE7A45D3C88AF4E1759B22004954D"      # <--- ВСТАВЬ ТОКЕН ЮМАНИ
YOOMONEY_WALLET = "4100118889570559"  # <--- ВСТАВЬ НОМЕР КОШЕЛЬКА

# Инициализация клиента Юмани
try:
    ym_client = Client(YOOMONEY_TOKEN)
except:
    logger.error("Ошибка инициализации Юмани. Проверьте токен.")

# Хранение данных
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

# ================= ДИЗАЙН ИНТЕРФЕЙСА =================

def get_main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛍 Каталог товаров", callback_data='catalog')],
        [InlineKeyboardButton("🛒 Корзина", callback_data='cart'), InlineKeyboardButton("👤 Профиль", callback_data='profile')],
        [InlineKeyboardButton("👨‍💻 Поддержка / FAQ", callback_data='support')]
    ])

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = (
        f"👋 *Привет, {user.first_name}!*\n\n"
        "💎 *MEPTB STORE* — твой надежный поставщик цифровых товаров.\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🚀 *Моментальная выдача*\n"
        "🛡 *Безопасная сделка*\n"
        "⭐️ *Лучший курс на рынке*\n\n"
        "👇 *Воспользуйтесь меню для навигации:*"
    )
    
    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=get_main_menu_keyboard(), parse_mode='Markdown')
    else:
        try:
            await update.callback_query.message.edit_text(welcome_text, reply_markup=get_main_menu_keyboard(), parse_mode='Markdown')
        except:
             await update.callback_query.message.reply_text(welcome_text, reply_markup=get_main_menu_keyboard(), parse_mode='Markdown')

# Главное меню через callback
async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    welcome_text = (
        "🏠 *Главное меню*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Выберите интересующий раздел ниже:"
    )
    
    await query.message.edit_text(welcome_text, reply_markup=get_main_menu_keyboard(), parse_mode='Markdown')

# Профиль (заглушка для красоты)
async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    cart = user_carts.get(user.id, [])
    
    text = (
        "👤 *Личный кабинет*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 ID: `{user.id}`\n"
        f"👤 Имя: {user.first_name}\n"
        f"📦 Товаров в корзине: *{len(cart)}*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💎 *Статус:* `Покупатель`"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')]]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# Каталог
async def show_catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    text = (
        "🛍 *Каталог товаров*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔥 *Популярное:*\n"
        "• Telegram Stars — валюта для ботов и каналов.\n"
        "• Telegram Premium — новые возможности.\n\n"
        "👇 *Выберите категорию:*"
    )

    keyboard = [
        [InlineKeyboardButton("⭐️ Telegram Stars (Звёзды)", callback_data='stars')],
        [InlineKeyboardButton("⚡️ Telegram Premium", callback_data='tg_premium')],
        [InlineKeyboardButton("🔙 В главное меню", callback_data='back_to_menu')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# Stars - шаг 1
async def stars_step1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_states[user_id] = {'step': 'stars_amount', 'message_id': query.message.message_id}
    
    text = (
        "⭐️ *Покупка Stars*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💸 Текущий курс: *1 ⭐️ = 1,6₽*\n\n"
        "⌨️ *Введите желаемое количество звезд числом:*\n"
        "_(Например: 50, 100, 500)_"
    )
    
    await query.message.edit_text(text, parse_mode='Markdown')

# Обработка ввода звезд
async def handle_stars_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    if user_id not in user_states or user_states[user_id].get('step') != 'stars_amount':
        text = update.message.text.strip().lower()
        if text == '/start':
            await start(update, context)
        return
    
    try:
        amount = int(update.message.text.strip())
        if amount <= 0 or amount > 10000:
            await update.message.reply_text("❌ Введите число от 1 до 10 000.")
            return
        
        user_states[user_id]['amount'] = amount
        user_states[user_id]['step'] = 'stars_confirm'
        total_price = amount * Product.PRICES[Product.STARS]
        
        text = (
            "⭐️ *Подтверждение выбора*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 Количество: *{amount} Stars*\n"
            f"💰 Стоимость: *{total_price:.2f}₽*\n\n"
            "Добавить этот товар в корзину?"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Да, добавить", callback_data='confirm_stars'),
                InlineKeyboardButton("❌ Нет", callback_data='cancel_stars'),
            ],
            [InlineKeyboardButton("🔙 Изменить кол-во", callback_data='back_to_stars_input')]
        ]
        
        # Удаляем старое сообщение для чистоты
        try:
            await context.bot.delete_message(chat_id=user_id, message_id=user_states[user_id]['message_id'])
        except:
            pass
        
        message = await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        user_states[user_id]['message_id'] = message.message_id
        
    except ValueError:
        await update.message.reply_text("❌ Пожалуйста, отправьте только число.")

async def confirm_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if user_id in user_states and 'amount' in user_states[user_id]:
        amount = user_states[user_id]['amount']
        total_price = amount * Product.PRICES[Product.STARS]
        product = {
            'type': Product.STARS,
            'name': f"Stars ⭐️ ({amount} шт.)",
            'price': total_price,
            'amount': amount
        }
        if user_id not in user_carts:
            user_carts[user_id] = []
        user_carts[user_id].append(product)
        
        await query.message.edit_text(f"✅ *Успешно!*\nТовар добавлен в корзину.", parse_mode='Markdown')
        if user_id in user_states: del user_states[user_id]
        
        # Небольшая пауза и возврат в меню (можно через кнопку, но так быстрее)
        keyboard = [[InlineKeyboardButton("🔙 В меню", callback_data='back_to_menu'), InlineKeyboardButton("🛒 К корзине", callback_data='cart')]]
        await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await back_to_menu(update, context)

async def cancel_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id in user_states: del user_states[user_id]
    await back_to_menu(update, context)

async def back_to_stars_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_states[user_id] = {'step': 'stars_amount', 'message_id': query.message.message_id}
    await query.message.edit_text("⌨️ *Введите желаемое количество звезд числом:*", parse_mode='Markdown')

# Premium
async def tg_premium_option(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    text = (
        "⚡️ *Telegram Premium*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Эксклюзивные функции для вашего аккаунта.\n\n"
        "👇 *Выберите срок подписки:*"
    )
    
    keyboard = [
        [InlineKeyboardButton("🗓 3 месяца — 1250₽", callback_data='add_tg_tg_premium_3')],
        [InlineKeyboardButton("🗓 6 месяцев — 1500₽", callback_data='add_tg_tg_premium_6')],
        [InlineKeyboardButton("🗓 12 месяцев — 2750₽", callback_data='add_tg_tg_premium_12')],
        [InlineKeyboardButton("🔙 Назад", callback_data='catalog')],
    ]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def add_to_cart_and_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    mapping = {
        'add_tg_tg_premium_3': Product.TG_PREMIUM_3,
        'add_tg_tg_premium_6': Product.TG_PREMIUM_6,
        'add_tg_tg_premium_12': Product.TG_PREMIUM_12
    }
    ptype = mapping.get(query.data)
    product = {'type': ptype, 'name': Product.NAMES[ptype], 'price': Product.PRICES[ptype]}
    if user_id not in user_carts: user_carts[user_id] = []
    user_carts[user_id].append(product)
    
    await query.message.edit_text(f"✅ *{Product.NAMES[ptype]}* добавлен в корзину!", parse_mode='Markdown')
    
    keyboard = [[InlineKeyboardButton("🔙 В меню", callback_data='back_to_menu'), InlineKeyboardButton("🛒 К корзине", callback_data='cart')]]
    await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))

# Корзина
async def show_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    cart = user_carts.get(user_id, [])
    
    if not cart:
        text = (
            "🛒 *Корзина пуста*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Посмотрите наш каталог, там много интересного!"
        )
        keyboard = [[InlineKeyboardButton("🛍 В каталог", callback_data='catalog'), InlineKeyboardButton("🔙 Меню", callback_data='back_to_menu')]]
    else:
        total = sum(item['price'] for item in cart)
        cart_items_text = ""
        for idx, item in enumerate(cart, 1):
            cart_items_text += f"▫️ {item['name']} — *{item['price']:.2f}₽*\n"
        
        text = (
            "🧾 *Ваш заказ*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"{cart_items_text}"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 *ИТОГО К ОПЛАТЕ: {total:.2f}₽*"
        )
        
        keyboard = [
            [InlineKeyboardButton("💳 Оплатить картой / СБП (ЮMoney)", callback_data='checkout')],
            [InlineKeyboardButton("🗑 Очистить корзину", callback_data='clear_cart')],
            [InlineKeyboardButton("🔙 В меню", callback_data='back_to_menu')],
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def clear_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_carts[user_id] = []
    await query.message.edit_text("🗑 *Корзина успешно очищена!*", parse_mode='Markdown')
    
    keyboard = [[InlineKeyboardButton("🔙 В меню", callback_data='back_to_menu')]]
    await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))

# ==================== ОПЛАТА ====================

async def checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    cart = user_carts.get(user_id, [])
    
    if not cart:
        await query.message.edit_text("❌ Корзина пуста!")
        await show_cart(update, context)
        return
    
    total = sum(item['price'] for item in cart)
    
    # 1. Генерируем ID заказа
    order_id = str(uuid.uuid4())
    
    # 2. Сохраняем заказ
    active_orders[order_id] = {
        "user_id": user_id,
        "amount": total,
        "items": cart
    }
    
    # 3. Создаем ссылку YooMoney
    try:
        quickpay = Quickpay(
            receiver=YOOMONEY_WALLET,
            quickpay_form="shop",
            targets=f"MEPTB Shop: Order {order_id[:8]}",
            paymentType="SB", 
            sum=total,
            label=order_id
        )
        
        checkout_text = (
            "💳 *Формирование счета*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 Сумма: *{total:.2f}₽*\n"
            f"📄 Номер заказа: `{order_id[:8]}`\n\n"
            "❗️ *Инструкция:*\n"
            "1. Нажмите кнопку «Оплатить» ниже.\n"
            "2. Выберите удобный способ (Карта, СБП).\n"
            "3. После оплаты вернитесь сюда и нажмите «Проверить оплату»."
        )
        
        keyboard = [
            [InlineKeyboardButton("🔗 Оплатить (Переход на ЮMoney)", url=quickpay.base_url)],
            [InlineKeyboardButton("🔄 Проверить оплату", callback_data=f'check_pay_{order_id}')],
            [InlineKeyboardButton("❌ Отмена", callback_data='back_to_menu')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.edit_text(checkout_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Ошибка создания ссылки: {e}")
        await query.message.edit_text("❌ Ошибка платежной системы. Свяжитесь с поддержкой.")

async def check_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    order_id = query.data.replace('check_pay_', '')
    order_data = active_orders.get(order_id)
    
    if not order_data:
        await query.message.answer("⚠️ Срок действия заказа истек или он не найден.")
        return

    try:
        history = ym_client.operation_history(label=order_id)
        is_paid = False
        
        for operation in history.operations:
            if operation.status == "success" and operation.label == order_id:
                is_paid = True
                break
        
        if is_paid:
            await process_successful_payment(query, context, order_id, order_data)
        else:
            await query.answer("⌛️ Оплата еще не поступила. Попробуйте через 10-15 секунд.", show_alert=True)
            
    except Exception as e:
        logger.error(f"Ошибка проверки: {e}")
        await query.answer("❌ Ошибка соединения с банком.", show_alert=True)

async def process_successful_payment(query, context, order_id, order_data):
    user_id = order_data['user_id']
    items = order_data['items']
    total = order_data['amount']
    user = query.from_user
    
    order_text_lines = []
    for item in items:
        name_clean = item['name'].replace("*", "") # Чистим Markdown для админки
        if item.get('amount'):
            order_text_lines.append(f"- {name_clean}: {item['amount']} шт.")
        else:
            order_text_lines.append(f"- {name_clean}")
    order_text = "\n".join(order_text_lines)
    
    admin_message = (
        f"✅ **НОВАЯ ПРОДАЖА**\n"
        f"👤 Покупатель: @{user.username if user.username else user_id} (ID: `{user_id}`)\n"
        f"💰 Сумма: {total:.2f}₽\n\n"
        f"📦 **Товары:**\n{order_text}\n\n"
        f"🏷 ID заказа: `{order_id}`"
    )
    
    if user_id in user_carts: del user_carts[user_id]
    del active_orders[order_id]

    # Красивое сообщение об успехе
    success_text = (
        "✅ *Оплата успешно принята!*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Спасибо за покупку в MEPTB Shop! ❤️\n\n"
        "🚀 *Ваш заказ передан в обработку.*\n"
        "Администратор уже получил уведомление и скоро свяжется с вами для выдачи товара."
    )
    
    await query.message.edit_text(
        success_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 В главное меню", callback_data='back_to_menu')]])
    )
    
    try:
        keyboard = [[InlineKeyboardButton("💬 Написать покупателю", url=f"tg://user?id={user_id}")]]
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    except:
        logger.error("Не удалось отправить сообщение админу")

# Поддержка
async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    text = (
        "👨‍💻 *Техническая поддержка*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Есть вопросы по заказу или ассортименту? \n"
        "Мы всегда на связи!\n\n"
        "📞 *Контакты:* @slayip\n"
        "🕒 *Время работы:* 10:00 - 23:00 (МСК)"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 В меню", callback_data='back_to_menu')]]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}", exc_info=context.error)

def main():
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    
    application.add_handler(CallbackQueryHandler(back_to_menu, pattern='^back_to_menu$'))
    application.add_handler(CallbackQueryHandler(show_catalog, pattern='^catalog$'))
    application.add_handler(CallbackQueryHandler(show_cart, pattern='^cart$'))
    application.add_handler(CallbackQueryHandler(show_support, pattern='^support$'))
    application.add_handler(CallbackQueryHandler(show_profile, pattern='^profile$'))
    
    application.add_handler(CallbackQueryHandler(stars_step1, pattern='^stars$'))
    application.add_handler(CallbackQueryHandler(confirm_stars, pattern='^confirm_stars$'))
    application.add_handler(CallbackQueryHandler(cancel_stars, pattern='^cancel_stars$'))
    application.add_handler(CallbackQueryHandler(back_to_stars_input, pattern='^back_to_stars_input$'))
    
    application.add_handler(CallbackQueryHandler(tg_premium_option, pattern='^tg_premium$'))
    application.add_handler(CallbackQueryHandler(add_to_cart_and_back, pattern='^add_tg_tg_premium_'))
    
    application.add_handler(CallbackQueryHandler(clear_cart, pattern='^clear_cart$'))
    application.add_handler(CallbackQueryHandler(checkout, pattern='^checkout$'))
    application.add_handler(CallbackQueryHandler(check_payment, pattern='^check_pay_'))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_stars_amount))
    
    application.add_error_handler(error_handler)
    
    print("Бот MEPTB Shop (Pro Design) запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == '__main__':
    main()
