import sqlite3
import asyncio
import re
from datetime import datetime, timedelta
from fastapi import FastAPI, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from aiogram import Bot, Dispatcher, F
from aiogram.types import CallbackQuery, Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder

# === НАСТРОЙКИ ===
BOT_TOKEN = "8876362225:AAHfmJgPzfvnENJf7SoaMIzAlox2Z7BwyXY" # Вставь свой токен!
ALINA_TG_ID = 6494103025 # Вставь СВОЙ числовой ID (без кавычек, просто цифры)!

app = FastAPI()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

briefing_sent_today = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def init_db():
    conn = sqlite3.connect("barber.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            phone TEXT,
            service TEXT,
            price TEXT,
            duration TEXT,
            booking_date TEXT,
            booking_time TEXT,
            status TEXT DEFAULT 'new',
            reminder_sent INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- ПРОВЕРКА ДОСТУПА (ТОЛЬКО ДЛЯ АЛИНЫ) ---
def is_alina(user_id: int) -> bool:
    return user_id == ALINA_TG_ID

def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📅 Расписание"), KeyboardButton(text="💰 Моя касса")],
            [KeyboardButton(text="🛠 Инструкция (Блок / Разблок)")]
        ],
        resize_keyboard=True
    )

# --- 1. СТАРТ И МЕНЮ ---
@dp.message(CommandStart())
async def cmd_start(message: Message):
    if not is_alina(message.from_user.id):
        await message.answer("⛔️ Извините, этот бот предназначен только для мастера.")
        return

    await message.answer(
        "Привет, Алина! Твоя личная CRM надежно защищена. 💇‍♂️\n\n"
        "👇 Используй кнопки внизу для управления расписанием и кассой.\n"
        "🔍 <b>Поиск клиента:</b> просто отправь мне его номер телефона.", 
        reply_markup=get_main_keyboard(), parse_mode="HTML"
    )

# --- 2. РАСПИСАНИЕ НА НЕДЕЛЮ ---
@dp.message(F.text == "📅 Расписание")
async def show_calendar(message: Message):
    if not is_alina(message.from_user.id): return
    
    conn = sqlite3.connect("barber.db")
    cursor = conn.cursor()
    today = datetime.now().date()
    end_date = today + timedelta(days=7)
    
    cursor.execute('''
        SELECT booking_date, booking_time, name, phone, service, status 
        FROM bookings 
        WHERE status IN ('new', 'done', 'blocked') 
        AND booking_date >= ? AND booking_date <= ?
        ORDER BY booking_date ASC, booking_time ASC
    ''', (today.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")))
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        await message.answer("На ближайшие 7 дней записей нет. Можно отдыхать! ☕️", reply_markup=get_main_keyboard())
        return
        
    schedule = {}
    for row in rows:
        b_date, b_time, b_name, b_phone, b_serv, b_status = row
        if b_date not in schedule:
            schedule[b_date] = []
        if b_status == 'blocked':
            schedule[b_date].append(f"🔒 <b>{b_time}</b> | <i>Заблокировано</i>")
        else:
            mark = "✅" if b_status == 'done' else "⏳"
            schedule[b_date].append(f"{mark} <b>{b_time}</b> | {b_name} | {b_serv}\n📞 {b_phone}")
        
    text = "📅 <b>Твоё расписание:</b>\n\n"
    for d, items in schedule.items():
        text += f"🗓 <b>{d}</b>\n" + "\n".join(items) + "\n\n"
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_keyboard())

# --- 3. ФИНАНСОВАЯ СТАТИСТИКА (КАССА) ---
@dp.message(F.text == "💰 Моя касса")
async def show_finance(message: Message):
    if not is_alina(message.from_user.id): return

    conn = sqlite3.connect("barber.db")
    cursor = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    
    cursor.execute("SELECT COUNT(*), SUM(CAST(price AS INTEGER)) FROM bookings WHERE booking_date = ? AND status = 'done'", (today,))
    today_count, today_sum = cursor.fetchone()
    today_sum = today_sum or 0

    cursor.execute("SELECT COUNT(*), SUM(CAST(price AS INTEGER)) FROM bookings WHERE status = 'done'")
    total_count, total_sum = cursor.fetchone()
    total_sum = total_sum or 0
    conn.close()

    text = (
        f"💰 <b>Твоя касса:</b>\n\n"
        f"☀️ <b>За сегодня:</b>\n"
        f"Клиентов: {today_count}\n"
        f"Выручка: <b>{today_sum} ₽</b>\n\n"
        f"🏆 <b>За всё время:</b>\n"
        f"Обслужено: {total_count}\n"
        f"Общая выручка: <b>{total_sum} ₽</b>"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_keyboard())

# --- 4. ИНСТРУКЦИЯ И УПРАВЛЕНИЕ БЛОКАМИ ---
@dp.message(F.text == "🛠 Инструкция (Блок / Разблок)")
async def help_block(message: Message):
    if not is_alina(message.from_user.id): return
    await message.answer(
        "🛠 <b>Управление занятостью:</b>\n\n"
        "🔒 <b>Заблокировать время (обед, дела):</b>\n"
        "• <code>Блок 14:00</code> (на сегодня)\n"
        "• <code>Блок 26.10 15:30</code> (на конкретную дату)\n\n"
        "🔓 <b>Снять блок (вернуть время на сайт):</b>\n"
        "• <code>Разблок 14:00</code> (на сегодня)\n"
        "• <code>Разблок 26.10 15:30</code> (на конкретную дату)", 
        parse_mode="HTML", reply_markup=get_main_keyboard()
    )

@dp.message(F.text.lower().startswith("блок "))
async def block_time(message: Message):
    if not is_alina(message.from_user.id): return
    parts = message.text.lower().replace("блок ", "").strip().split()
    if len(parts) == 1:
        b_date = datetime.now().strftime("%Y-%m-%d")
        b_time = parts[0]
    elif len(parts) == 2:
        try:
            b_date = datetime.strptime(parts[0] + f".{datetime.now().year}", "%d.%m.%Y").strftime("%Y-%m-%d")
            b_time = parts[1]
        except:
            await message.answer("❌ Ошибка формата даты. Пример: Блок 26.10 15:30", reply_markup=get_main_keyboard())
            return
    else:
        return

    conn = sqlite3.connect("barber.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO bookings (name, phone, service, price, duration, booking_date, booking_time, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", 
        ("ЛИЧНОЕ ВРЕМЯ", "-", "-", "0", "0", b_date, b_time, "blocked")
    )
    conn.commit()
    conn.close()
    await message.answer(f"🔒 Время <b>{b_time}</b> на <b>{b_date}</b> успешно заблокировано!", parse_mode="HTML", reply_markup=get_main_keyboard())

@dp.message(F.text.lower().startswith("разблок "))
async def unblock_time(message: Message):
    if not is_alina(message.from_user.id): return
    parts = message.text.lower().replace("разблок ", "").strip().split()
    if len(parts) == 1:
        b_date = datetime.now().strftime("%Y-%m-%d")
        b_time = parts[0]
    elif len(parts) == 2:
        try:
            b_date = datetime.strptime(parts[0] + f".{datetime.now().year}", "%d.%m.%Y").strftime("%Y-%m-%d")
            b_time = parts[1]
        except:
            await message.answer("❌ Ошибка формата. Пример: Разблок 26.10 15:30", reply_markup=get_main_keyboard())
            return
    else:
        return

    conn = sqlite3.connect("barber.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM bookings WHERE name = 'ЛИЧНОЕ ВРЕМЯ' AND booking_date = ? AND booking_time = ?", (b_date, b_time))
    conn.commit()
    conn.close()
    await message.answer(f"🔓 Время <b>{b_time}</b> на <b>{b_date}</b> снова свободно для клиентов!", parse_mode="HTML", reply_markup=get_main_keyboard())

# --- 5. ПОИСК КЛИЕНТА ПО НОМЕРУ ---
@dp.message(lambda msg: any(char.isdigit() for char in msg.text) and len(re.sub(r'\D', '', msg.text)) >= 10)
async def search_client(message: Message):
    if not is_alina(message.from_user.id): return
    phone_digits = re.sub(r'\D', '', message.text)[-10:]
    
    conn = sqlite3.connect("barber.db")
    cursor = conn.cursor()
    cursor.execute("SELECT name, booking_date, service, status FROM bookings WHERE phone LIKE ? AND name != 'ЛИЧНОЕ ВРЕМЯ' ORDER BY id DESC", (f'%{phone_digits}%',))
    visits = cursor.fetchall()
    
    cursor.execute("SELECT COUNT(*), SUM(CAST(price AS INTEGER)) FROM bookings WHERE phone LIKE ? AND status = 'done'", (f'%{phone_digits}%',))
    done_count, total_sum = cursor.fetchone()
    total_sum = total_sum or 0
    conn.close()

    if not visits:
        await message.answer("🤷‍♀️ Клиент с таким номером не найден в базе.", reply_markup=get_main_keyboard())
        return

    client_name = visits[0][0]
    text = f"🔍 <b>Досье клиента: {client_name}</b>\n\n"
    text += f"Успешных визитов: <b>{done_count}</b>\n"
    text += f"Принес выручки: <b>{total_sum} ₽</b>\n\n"
    text += "📜 <b>История записей:</b>\n"
    
    for v in visits[:5]:
        st = "✅" if v[3] == 'done' else "❌" if v[3] == 'missed' else "⏳"
        text += f"{st} {v[1]} | {v[2]}\n"

    await message.answer(text, parse_mode="HTML", reply_markup=get_main_keyboard())

# --- API: ДОСТУПНОЕ ВРЕМЯ ---
@app.get("/api/available_times")
async def get_available_times(date: str = Query(...), type: str = Query(...)):
    conn = sqlite3.connect("barber.db")
    cursor = conn.cursor()
    cursor.execute("SELECT booking_time FROM bookings WHERE booking_date = ? AND status != 'cancelled'", (date,))
    booked_slots = [row[0] for row in cursor.fetchall()]
    conn.close()

    if type == 'evening' or type == 'complex':
        all_slots = ['18:00', '19:00', '20:00']
    else:
        all_slots = ['10:00', '11:00', '12:30', '14:00', '15:30', '17:00', '18:00', '19:30']

    available = [slot for slot in all_slots if slot not in booked_slots]
    return {"available_times": available}

# --- API: СОЗДАНИЕ ЗАПИСИ ---
@app.post("/api/book")
async def create_booking(
    name: str = Form(...), phone: str = Form(...), 
    service: str = Form(...), date: str = Form(...), time: str = Form(...),
    price: str = Form(...), duration: str = Form(...)
):
    phone_clean = re.sub(r'\D', '', phone)[-10:]
    conn = sqlite3.connect("barber.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*), SUM(CAST(price AS INTEGER)) FROM bookings WHERE phone LIKE ? AND status = 'done'", (f'%{phone_clean}%',))
    done_count, total_spent = cursor.fetchone()
    total_spent = total_spent or 0

    cursor.execute("SELECT COUNT(*) FROM bookings WHERE phone LIKE ? AND status = 'missed'", (f'%{phone_clean}%',))
    missed_count = cursor.fetchone()[0]

    if missed_count > 0:
        client_status = f"⚠️ АХТУНГ! Пропустил запись {missed_count} раз!"
    elif done_count >= 5:
        client_status = f"👑 VIP-клиент (был {done_count} раз, принес {total_spent} ₽)"
    elif done_count > 0:
        client_status = f"🌟 Постоянный (был {done_count} раз, принес {total_spent} ₽)"
    else:
        client_status = "🆕 Новый клиент"

    cursor.execute(
        "INSERT INTO bookings (name, phone, service, price, duration, booking_date, booking_time) VALUES (?, ?, ?, ?, ?, ?, ?)", 
        (name, phone, service, price, duration, date, time)
    )
    booking_id = cursor.lastrowid
    conn.commit()
    conn.close()

    message = (
        f"🔥 <b>Новая запись!</b>\n\n"
        f"👤 Клиент: {name}\n"
        f"📞 Телефон: {phone}\n"
        f"📊 {client_status}\n\n"
        f"✂️ Услуга: {service}\n"
        f"💰 Чеком на: <b>{price} ₽</b> (~{duration} мин)\n"
        f"📅 Дата: <b>{date}</b>\n"
        f"⏰ Время: <b>{time}</b>"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Пришел", callback_data=f"done_{booking_id}")
    builder.button(text="❌ Отменить", callback_data=f"cancel_{booking_id}")
    builder.button(text="🏃‍♂️ Не пришел", callback_data=f"missed_{booking_id}")
    builder.adjust(2, 1)

    try:
        await bot.send_message(chat_id=ALINA_TG_ID, text=message, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception as e:
        print(f"Ошибка: {e}")

    return {"status": "success"}

# --- ОБРАБОТКА КНОПОК СТАТУСОВ ---
@dp.callback_query(F.data.startswith(("done_", "cancel_", "missed_")))
async def process_status(callback: CallbackQuery):
    if not is_alina(callback.from_user.id):
        await callback.answer("⛔️ Нет доступа", show_alert=True)
        return

    action, booking_id = callback.data.split("_")
    conn = sqlite3.connect("barber.db")
    cursor = conn.cursor()

    if action == "done":
        status_text = "✅ <b>Успешно обслужен</b> (добавлено в кассу)"
        cursor.execute("UPDATE bookings SET status = 'done' WHERE id = ?", (booking_id,))
    elif action == "cancel":
        status_text = "❌ <b>Запись отменена</b> (время освобождено)"
        cursor.execute("UPDATE bookings SET status = 'cancelled' WHERE id = ?", (booking_id,))
    elif action == "missed":
        status_text = "🏃‍♂️ <b>Не явился</b> (рейтинг понижен)"
        cursor.execute("UPDATE bookings SET status = 'missed' WHERE id = ?", (booking_id,))
    
    conn.commit()
    conn.close()

    new_message_text = callback.message.html_text + f"\n\n{status_text}"
    try:
        await callback.message.edit_text(new_message_text, parse_mode="HTML")
    except:
        pass
    await callback.answer("Статус обновлен!")

# --- ФОНОВЫЕ ЗАДАЧИ ---
async def background_tasks():
    global briefing_sent_today
    while True:
        now = datetime.now()
        conn = sqlite3.connect("barber.db")
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, name, service, booking_time FROM bookings WHERE status = 'new' AND booking_date = ? AND reminder_sent = 0", (now.strftime("%Y-%m-%d"),))
        for row in cursor.fetchall():
            b_id, b_name, b_service, b_time = row
            try:
                booking_dt = datetime.strptime(f"{now.strftime('%Y-%m-%d')} {b_time}", "%Y-%m-%d %H:%M")
                if timedelta(minutes=0) < (booking_dt - now) <= timedelta(minutes=60):
                    await bot.send_message(chat_id=ALINA_TG_ID, text=f"⏰ <b>Скоро клиент!</b>\nЧерез час придет {b_name} на «{b_service}» в {b_time}.", parse_mode="HTML")
                    cursor.execute("UPDATE bookings SET reminder_sent = 1 WHERE id = ?", (b_id,))
            except:
                pass
                
        if now.hour == 9 and now.minute == 0 and briefing_sent_today != now.date():
            cursor.execute("SELECT COUNT(*), SUM(CAST(price AS INTEGER)) FROM bookings WHERE booking_date = ? AND status = 'new'", (now.strftime("%Y-%m-%d"),))
            day_count, day_sum = cursor.fetchone()
            if day_count > 0:
                await bot.send_message(chat_id=ALINA_TG_ID, text=f"☀️ <b>Доброе утро, Алина!</b>\nСегодня у тебя {day_count} записей на {day_sum or 0} ₽.\nОтличного дня! ☕️", parse_mode="HTML", reply_markup=get_main_keyboard())
            briefing_sent_today = now.date()

        conn.commit()
        conn.close()
        await asyncio.sleep(60)

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(dp.start_polling(bot))
    asyncio.create_task(background_tasks())