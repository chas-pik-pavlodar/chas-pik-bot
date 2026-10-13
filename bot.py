import os, logging, threading, asyncio, sqlite3, urllib.parse
from flask import Flask
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage

BOT_TOKEN = os.environ.get("TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "1218877896"))
DB = "database.db"

HARDCODED_COURIERS = [
    (7714431728, "main_kurier"),
]

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
@app.route('/')
def home(): return "Bot alive!"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, client_username TEXT, address_from TEXT, address_to TEXT, price TEXT, status TEXT DEFAULT 'new', courier_id INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS couriers (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER UNIQUE, username TEXT)")
    for uid, uname in HARDCODED_COURIERS:
        c.execute("INSERT OR IGNORE INTO couriers (user_id, username) VALUES (?,?)", (uid, uname))
    conn.commit(); conn.close()

def get_earnings(courier_id):
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("SELECT price FROM orders WHERE courier_id=? AND status='done'", (courier_id,))
    rows = c.fetchall(); conn.close()
    total = 0
    for (p,) in rows:
        try: total += int(''.join(filter(str.isdigit, str(p))) or 0)
        except: pass
    return total, len(rows)

class OrderForm(StatesGroup):
    from_address = State()
    to_address = State()
    price = State()
class PhotoReport(StatesGroup):
    waiting_photo = State()

def client_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📦 Сделать заказ")],[KeyboardButton(text="🚚 Стать курьером")],[KeyboardButton(text="💰 Мой заработок")]], resize_keyboard=True)
def courier_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📍 Обновить где я", request_location=True)],
        [KeyboardButton(text="✅ Я доставил - фотоотчет")],
        [KeyboardButton(text="💰 Мой заработок")],
        [KeyboardButton(text="📦 Сделать заказ")]
    ], resize_keyboard=True)

@dp.message(Command("start"))
async def start(m: Message, state: FSMContext):
    await state.clear(); init_db()
    await m.answer("ЧАС ПИК Павлодар ⚡️", reply_markup=client_kb())

@dp.message(F.text == "🚚 Стать курьером")
async def become_courier(m: Message):
    init_db()
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO couriers (user_id, username) VALUES (?,?)", (m.from_user.id, m.from_user.username or m.from_user.first_name))
    conn.commit(); conn.close()
    await m.answer(f"✅ Ты курьер! ID {m.from_user.id}", reply_markup=courier_kb())

@dp.message(F.text == "💰 Мой заработок")
async def my_earnings(m: Message):
    total, count = get_earnings(m.from_user.id)
    await m.answer(f"💰 Заработок:\nЗаказов: {count}\nСумма: {total} тг", reply_markup=courier_kb())

@dp.message(Command("earnings"))
async def admin_earnings(m: Message):
    if m.from_user.id!= ADMIN_ID: return
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("SELECT courier_id, price FROM orders WHERE status='done'")
    rows = c.fetchall()
    c.execute("SELECT user_id, username FROM couriers"); couriers = c.fetchall()
    conn.close()
    if not rows: await m.answer("Нет доставок"); return
    from collections import defaultdict
    stat = defaultdict(lambda: [0,0])
    for cid, price in rows:
        try: p = int(''.join(filter(str.isdigit, str(price))) or 0)
        except: p=0
        stat[cid][0]+=p; stat[cid][1]+=1
    text = f"📊 Всего {len(rows)} доставок:\n\n"
    for uid, uname in couriers:
        earn, cnt = stat.get(uid, [0,0])
        text+=f"@{uname} {uid}: {cnt} зак / {earn}тг\n"
    await m.answer(text)

@dp.message(F.text == "📦 Сделать заказ")
async def order_start(m: Message, state: FSMContext):
    await state.set_state(OrderForm.from_address)
    await m.answer("Откуда забрать? Адрес:")

@dp.message(OrderForm.from_address)
async def order_from(m: Message, state: FSMContext):
    await state.update_data(from_addr=m.text)
    await state.set_state(OrderForm.to_address)
    await m.answer("Куда доставить?")

@dp.message(OrderForm.to_address)
async def order_to(m: Message, state: FSMContext):
    await state.update_data(to_addr=m.text)
    await state.set_state(OrderForm.price)
    await m.answer("💰 Какую цену предлагаешь?")

@dp.message(OrderForm.price)
async def order_price(m: Message, state: FSMContext):
    data = await state.get_data()
    from_addr = data.get("from_addr"); to_addr = data.get("to_addr")
    price = m.text.replace("тг","").strip()
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("INSERT INTO orders (client_id, client_username, address_from, address_to, price) VALUES (?,?,?,?,?)", (m.from_user.id, m.from_user.username, from_addr, to_addr, price))
    order_id = c.lastrowid
    c.execute("SELECT user_id FROM couriers"); couriers = c.fetchall()
    conn.commit(); conn.close()
    await state.clear()
    await m.answer(f"Заказ #{order_id} принят! {from_addr} -> {to_addr} за {price}тг", reply_markup=client_kb())
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"Взять за {price}тг", callback_data=f"take_{order_id}")]])
    text_c = f"ЗАКАЗ #{order_id}\nОт: {from_addr}\nДо: {to_addr}\nЦена: {price}тг\nКлиент: @{m.from_user.username}"
    for (cid,) in couriers:
        try: await bot.send_message(cid, text_c, reply_markup=kb)
        except: pass

@dp.callback_query(F.data.startswith("take_"))
async def take_order(cq: CallbackQuery):
    order_id = int(cq.data.split("_")[1])
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("SELECT status, client_id, address_from, address_to, price FROM orders WHERE id=?", (order_id,))
    row = c.fetchone()
    if not row: await cq.answer("Не найден"); conn.close(); return
    status, client_id, from_addr, to_addr, price = row
    if status!='new': await cq.answer("Уже взяли!", show_alert=True); conn.close(); return
    c.execute("UPDATE orders SET status='taken', courier_id=? WHERE id=?", (cq.from_user.id, order_id))
    conn.commit(); conn.close()

    # ИСПРАВЛЕННЫЕ МАРШРУТЫ
    from_q = urllib.parse.quote(f"{from_addr}, Павлодар")
    to_q = urllib.parse.quote(f"{to_addr}, Павлодар")

    yandex_url = f"https://yandex.kz/maps/?rtext={from_q}~{to_q}&rtt=auto"
    google_url = f"https://www.google.com/maps/dir/?api=1&origin={from_q}&destination={to_q}&travelmode=driving"
    gis_from = f"https://2gis.kz/pavlodar/search/{from_q}"
    gis_to = f"https://2gis.kz/pavlodar/search/{to_q}"

    kb_route = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚕 Яндекс Маршрут (лучший)", url=yandex_url)],
        [InlineKeyboardButton(text="📍 Google Маршрут", url=google_url)],
        [InlineKeyboardButton(text="🏠 2GIS Откуда", url=gis_from), InlineKeyboardButton(text="🏁 2GIS Куда", url=gis_to)]
    ])

    await cq.message.edit_text(f"ТЫ ВЗЯЛ ЗАКАЗ #{order_id} за {price}тг\n\nОт: {from_addr}\nДо: {to_addr}\n\nЖми кнопку маршрута ниже:", reply_markup=kb_route)
    await cq.message.answer("Когда поедешь - жми 📍 Обновить где я. В конце ✅ Я доставил", reply_markup=courier_kb())
    await cq.answer("Взял!")
    try: await bot.send_message(client_id, f"✅ Заказ #{order_id} взял курьер @{cq.from_user.username}")
    except: pass

@dp.message(F.location)
async def handle_location(m: Message):
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("SELECT id, client_id FROM orders WHERE courier_id=? AND status='taken' ORDER BY id DESC LIMIT 1", (m.from_user.id,))
    row = c.fetchone(); conn.close()
    if not row: return
    order_id, client_id = row
    try:
        await bot.send_message(client_id, f"🚚 Курьер едет с заказом #{order_id}:")
        await bot.send_location(client_id, latitude=m.location.latitude, longitude=m.location.longitude)
        await m.answer("📍 Отправил клиенту!", reply_markup=courier_kb())
    except: pass

@dp.message(F.text == "✅ Я доставил - фотоотчет")
async def ask_photo(m: Message, state: FSMContext):
    await state.set_state(PhotoReport.waiting_photo)
    await m.answer("Скинь фото у двери")

@dp.message(PhotoReport.waiting_photo, F.photo)
async def handle_photo_report(m: Message, state: FSMContext):
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("SELECT id, client_id, address_to, price FROM orders WHERE courier_id=? AND status='taken' ORDER BY id DESC LIMIT 1", (m.from_user.id,))
    row = c.fetchone()
    if not row: await m.answer("Нет активного"); await state.clear(); conn.close(); return
    order_id, client_id, to_addr, price = row
    c.execute("UPDATE orders SET status='done' WHERE id=?", (order_id,))
    conn.commit(); conn.close()
    await state.clear()
    total, count = get_earnings(m.from_user.id)
    try:
        await bot.send_message(client_id, f"✅ Заказ #{order_id} доставлен!")
        await bot.send_photo(client_id, m.photo[-1].file_id, caption=f"Фотоотчет #{order_id} {price}тг")
    except: pass
    await m.answer(f"Заказ #{order_id} закрыт! Заработок: {total}тг ({count} зак)", reply_markup=courier_kb())

@dp.message(F.photo)
async def auto_photo(m: Message):
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("SELECT id, client_id FROM orders WHERE courier_id=? AND status='taken' ORDER BY id DESC LIMIT 1", (m.from_user.id,))
    row = c.fetchone(); conn.close()
    if row:
        order_id, client_id = row
        try:
            await bot.send_photo(client_id, m.photo[-1].file_id, caption=f"Фотоотчет #{order_id}")
            await m.answer("Фото отправил!", reply_markup=courier_kb())
        except: pass

@dp.message(Command("couriers"))
async def list_couriers(m: Message):
    conn = sqlite3.connect(DB); c = conn.cursor(); c.execute("SELECT user_id, username FROM couriers"); rows=c.fetchall(); conn.close()
    if not rows: await m.answer("Курьеров нет"); return
    txt=""
    for uid, uname in rows:
        earn, cnt = get_earnings(uid)
        txt+=f"@{uname} {uid} - {cnt}/{earn}тг\n"
    await m.answer(txt)

@dp.message(Command("orders"))
async def list_orders(m: Message):
    conn = sqlite3.connect(DB); c = conn.cursor(); c.execute("SELECT id, address_from, address_to, price, status FROM orders ORDER BY id DESC LIMIT 10"); rows=c.fetchall(); conn.close()
    await m.answer("\n".join([f"#{o} {f}->{t} {p}[{s}]" for o,f,t,p,s in rows]) if rows else "Нет заказов")

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
async def run_bot():
    init_db(); await dp.start_polling(bot)
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(run_bot())
    
