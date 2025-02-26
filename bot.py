from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters
)
import sqlite3
import datetime

# Константы для состояний ConversationHandler
CHOOSING_ROOM, CHOOSING_DATE, CHOOSING_TIME = range(3)

# Подключение к БД
def get_db_connection():
    return sqlite3.connect('bookings.db')

# Команда /start
async def start(update: Update, context):
    await update.message.reply_text(
        "Привет! Я бот для бронирования переговорных комнат.\n"
        "Используйте /book чтобы начать бронирование."
    )

# Команда /book
async def book(update: Update, context):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM rooms")
    rooms = cursor.fetchall()
    conn.close()

    buttons = [
        [InlineKeyboardButton(room[1], callback_data=f"room_{room[0]}")]
        for room in rooms
    ]
    await update.message.reply_text(
        "Выберите комнату:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return CHOOSING_ROOM

# Обработка выбора комнаты
async def choose_room(update: Update, context):
    query = update.callback_query
    await query.answer()
    context.user_data['room_id'] = int(query.data.split('_')[1])
    await query.edit_message_text("Введите дату в формате ДД-ММ-ГГГГ:")
    return CHOOSING_DATE

# Обработка даты
async def choose_date(update: Update, context):
    date_text = update.message.text
    try:
        date = datetime.datetime.strptime(date_text, "%d-%m-%Y").date()
        context.user_data['date'] = date
        await update.message.reply_text("Введите время начала (ЧЧ:ММ):")
        return CHOOSING_TIME
    except ValueError:
        await update.message.reply_text("Неверный формат даты. Попробуйте снова.")
        return CHOOSING_DATE

# Проверка доступности времени
def is_time_slot_available(room_id, start_time, end_time):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM bookings 
        WHERE room_id = ? 
        AND ((start_time < ? AND end_time > ?) OR (start_time < ? AND end_time > ?))
    ''', (room_id, end_time, start_time, start_time, end_time))
    result = cursor.fetchone()
    conn.close()
    return result is None

# Обработка времени
async def choose_time(update: Update, context):
    time_text = update.message.text
    try:
        start_time = datetime.datetime.strptime(time_text, "%H:%M").time()
        date = context.user_data['date']
        start_datetime = datetime.datetime.combine(date, start_time)
        end_datetime = start_datetime + datetime.timedelta(hours=1)

        room_id = context.user_data['room_id']
        if is_time_slot_available(room_id, start_datetime, end_datetime):
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO bookings (room_id, user_id, start_time, end_time)
                VALUES (?, ?, ?, ?)
            ''', (room_id, update.message.from_user.id, start_datetime, end_datetime))
            conn.commit()
            conn.close()
            await update.message.reply_text("Бронь успешно создана!")
        else:
            await update.message.reply_text("Это время уже занято. Выберите другое.")
    except ValueError:
        await update.message.reply_text("Неверный формат времени. Попробуйте снова.")
    
    return ConversationHandler.END

# Команда /mybookings
async def my_bookings(update: Update, context):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT rooms.name, bookings.start_time, bookings.end_time 
        FROM bookings 
        JOIN rooms ON bookings.room_id = rooms.id 
        WHERE user_id = ?
    ''', (update.message.from_user.id,))
    bookings = cursor.fetchall()
    conn.close()

    if not bookings:
        await update.message.reply_text("У вас нет активных бронирований.")
    else:
        text = "Ваши бронирования:\n" + "\n".join(
            [f"{b[0]} с {b[1]} до {b[2]}" for b in bookings]
        )
        await update.message.reply_text(text)

def main():
    application = Application.builder().token("YOUR_BOT_TOKEN").build()

    # ConversationHandler для бронирования
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('book', book)],
        states={
            CHOOSING_ROOM: [CallbackQueryHandler(choose_room)],
            CHOOSING_DATE: [MessageHandler(filters.TEXT, choose_date)],
            CHOOSING_TIME: [MessageHandler(filters.TEXT, choose_time)],
        },
        fallbacks=[]
    )

    application.add_handler(CommandHandler('start', start))
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('mybookings', my_bookings))

    application.run_polling()

if __name__ == '__main__':
    main()
