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

# === ТВОИ НОМЕРА - СЮДА ВСТАВЬ ===
OPERATOR_PHONE = "+77771234567"
COURIER_PHONE = "+77771234567"
MAIN_COURIER_ID = 7714431728
# =================================

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
@app.route('/')
def home(): return "Bot alive!"
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, client_username TEXT, address_from TEXT, address_to TEXT, what TEXT, note TEXT, price TEXT, status TEXT DEFAULT 'new', courier_id INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS couriers (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER UNIQUE, username TEXT, phone TEXT)")
    # добавляем колонки если старой базы
    for q in ["ALTER TABLE orders ADD COLUMN what TEXT", "ALTER TABLE orders ADD COLUMN note TEXT", "ALTER TABLE couriers ADD COLUMN phone TEXT"]:
        try: c.execute(q)
        except: pass
    # ВСЕГДА добавляем главного курьера
    c.execute("INSERT OR IGNORE INTO couriers (user_id, username, phone) VALUES (?,?,?)", (MAIN_COURIER_ID, "main_kurier", COURIER_PHONE))
    c.execute("INSERT OR IGNORE INTO couriers (user_id, username, phone) VALUES (?,?,?)", (ADMIN_ID, "operator", OPERATOR_PHONE))
    conn.commit(); conn.close()

def get_earnings(cid):
    try:
        conn=sqlite3.connect(DB); c=conn.cursor()
        c.execute("SELECT price FROM orders WHERE courier_id=? AND status='done'", (cid,))
        total=0; rows=c.fetchall()
        for (p,) in rows:
            try: total+=int(''.join(filter(str.isdigit, str(p))) or 0)
            except: pass
        conn.close()
        return total, len(rows)
    except: return 0,0

class OrderForm(StatesGroup):
    from_address=State(); to_address=State(); what=State(); note=State(); price=State()
class PhotoReport(StatesGroup):
    waiting_photo=State()

def client_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📦 Сделать заказ")],
        [KeyboardButton(text="🚚 Стать курьером")],
        [KeyboardButton(text="📞 Связаться с оператором"), KeyboardButton(text="🛵 Связаться с курьером")],
        [KeyboardButton(text="💰 Мой заработок")]
    ], resize_keyboard=True)

def courier_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📍 Обновить где я", request_location=True)],
        [KeyboardButton(text="✅ Я доставил - фотоотчет")],
        [KeyboardButton(text="📞 Связаться с оператором"), KeyboardButton(text="💰 Мой заработок")]
    ], resize_keyboard=True)

@dp.message(Command("start"))
async def start(m: Message, state: FSMContext):
    await state.clear(); init_db()
    await m.answer(f"ЧАС ПИК Павлодар ⚡️\nID: {m.from_user.id}", reply_markup=client_kb())

# === ФИКС КНОПОК СВЯЗИ - ТЕКСТОМ, РАБОТАЕТ ВЕЗДЕ ===
@dp.message(F.text=="📞 Связаться с оператором")
async def contact_op(m: Message):
    await m.answer(f"📞 Оператор ЧАС ПИК:\n\n{OPERATOR_PHONE}\n\nНажми на номер чтобы позвонить 👆\nЕсли не звонит - скопируй и набери вручную.", reply_markup=client_kb())
    # доп кнопки для телефона
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📞 Позвонить оператору", url=f"tel:{OPERATOR_PHONE}")],
        [InlineKeyboardButton(text="💬 Написать оператору", url=f"tg://user?id={ADMIN_ID}")]
    ])
    await m.answer("Или жми кнопку:", reply_markup=kb)

@dp.message(F.text=="🛵 Связаться с курьером")
async def contact_kur(m: Message):
    await m.answer(f"🛵 Курьер ЧАС ПИК:\n\n{COURIER_PHONE}\n\nНажми на номер чтобы позвонить 👆", reply_markup=client_kb())
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📞 Позвонить курьеру", url=f"tel:{COURIER_PHONE}")]
    ])
    await m.answer("Или жми кнопку:", reply_markup=kb)

@dp.message(F.text=="🚚 Стать курьером")
async def become(m: Message):
    init_db()
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("INSERT OR IGNORE INTO couriers (user_id, username, phone) VALUES (?,?,?)", (m.from_user.id, m.from_user.username or "kurier", COURIER_PHONE))
    conn.commit(); conn.close()
    await m.answer("✅ Ты теперь курьер! Теперь заказы будут приходить сюда.", reply_markup=courier_kb())

@dp.message(F.text=="💰 Мой заработок")
async def my_earn(m: Message):
    total,cnt=get_earnings(m.from_user.id)
    await m.answer(f"💰 Заработок: {cnt} заказов / {total} тг")

@dp.message(Command("couriers"))
async def list_c(m: Message):
    init_db()
    conn=sqlite3.connect(DB); c=conn.cursor(); c.execute("SELECT user_id, username FROM couriers"); rows=c.fetchall(); conn.close()
    txt="Курьеры в базе:\n"
    for uid,uname in rows:
        t,cnt=get_earnings(uid)
        txt+=f"{uid} @{uname} - {cnt}/{t}тг\n"
    await m.answer(txt)

@dp.message(Command("debug"))
async def debug(m: Message):
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT COUNT(*) FROM couriers"); cc=c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM orders"); oc=c.fetchone()[0]
    conn.close()
    await m.answer(f"DEBUG: курьеров {cc}, заказов {oc}\nТвой ID {m.from_user.id}\nАдмин ID {ADMIN_ID}\nОператор {OPERATOR_PHONE}\nКурьер {COURIER_PHONE}")

@dp.message(F.text=="📦 Сделать заказ")
async def order_start(m: Message, state: FSMContext):
    await state.set_state(OrderForm.from_address); await m.answer("📍 Откуда забрать?")

@dp.message(OrderForm.from_address)
async def order_from(m: Message, state: FSMContext):
    await state.update_data(from_addr=m.text); await state.set_state(OrderForm.to_address); await m.answer("🏁 Куда доставить?")

@dp.message(OrderForm.to_address)
async def order_to(m: Message, state: FSMContext):
    await state.update_data(to_addr=m.text); await state.set_state(OrderForm.what); await m.answer("📦 Что везём?")

@dp.message(OrderForm.what)
async def order_what(m: Message, state: FSMContext):
    await state.update_data(what=m.text); await state.set_state(OrderForm.note); await m.answer("📝 Уточнение? Этаж, кому, подъезд. Если нет - пиши -")

@dp.message(OrderForm.note)
async def order_note(m: Message, state: FSMContext):
    await state.update_data(note=m.text); await state.set_state(OrderForm.price); await m.answer("💰 Цена?")

@dp.message(OrderForm.price)
async def order_price(m: Message, state: FSMContext):
    data=await state.get_data()
    from_addr=data.get("from_addr"); to_addr=data.get("to_addr"); what=data.get("what"); note=data.get("note")
    price=m.text
    init_db()
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("INSERT INTO orders (client_id, client_username, address_from, address_to, what, note, price) VALUES (?,?,?,?,?,?,?)", (m.from_user.id, m.from_user.username, from_addr, to_addr, what, note, price))
    order_id=c.lastrowid
    c.execute("SELECT user_id FROM couriers"); couriers=c.fetchall()
    conn.commit(); conn.close()
    await state.clear()
    await m.answer(f"✅ Заказ #{order_id} принят!\n{from_addr} -> {to_addr}\nЧто: {what}\n{note}\nЦена: {price}тг", reply_markup=client_kb())

    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"🔥 Взять за {price}тг", callback_data=f"take_{order_id}")]])
    text=f"🔥 ЗАКАЗ #{order_id}\nОт: {from_addr}\nДо: {to_addr}\nЧто: {what}\nУточнение: {note}\nЦена: {price}тг\nКлиент: @{m.from_user.username} ID:{m.from_user.id}"

    sent=0
    for (cid,) in couriers:
        try:
            await bot.send_message(cid, text, reply_markup=kb)
            sent+=1
        except Exception as e:
            print(f"Ошибка отправки {cid}: {e}")
    # ОБЯЗАТЕЛЬНО шлем админу тоже
    try:
        await bot.send_message(ADMIN_ID, f"[АДМИН] Заказ #{order_id} разослан {sent} курьерам\n{text}", reply_markup=kb)
    except: pass
    await m.answer(f"Разослал {sent} курьерам. Связь:\nОператор: {OPERATOR_PHONE}\nКурьер: {COURIER_PHONE}")

@dp.callback_query(F.data.startswith("take_"))
async def take_order(cq: CallbackQuery):
    order_id=int(cq.data.split("_")[1])
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT status, client_id, address_from, address_to, what, note, price FROM orders WHERE id=?", (order_id,))
    row=c.fetchone()
    if not row: await cq.answer("Не найден"); conn.close(); return
    status,client_id,from_addr,to_addr,what,note,price=row
    if status!='new': await cq.answer("Уже взяли!"); conn.close(); return
    c.execute("UPDATE orders SET status='taken', courier_id=? WHERE id=?", (cq.from_user.id, order_id)); conn.commit(); conn.close()
    from_q=urllib.parse.quote(f"{from_addr}, Павлодар"); to_q=urllib.parse.quote(f"{to_addr}, Павлодар")
    yandex_url=f"https://yandex.kz/maps/?rtext={from_q}~{to_q}&rtt=auto"
    kb_route=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚕 Яндекс Маршрут", url=yandex_url)],
        [InlineKeyboardButton(text=f"📞 Клиент {client_id}", url=f"tg://user?id={client_id}")]
    ])
    await cq.message.edit_text(f"ТЫ ВЗЯЛ #{order_id} {price}тг\n{from_addr}->{to_addr}\n{what}", reply_markup=kb_route)
    await cq.message.answer("Жми Обновить где я", reply_markup=courier_kb())
    await cq.answer("Взял!")
    try:
        await bot.send_message(client_id, f"✅ Заказ #{order_id} взял курьер @{cq.from_user.username}\nТел курьера: {COURIER_PHONE}\nНажми чтобы позвонить: {COURIER_PHONE}\nОператор: {OPERATOR_PHONE}")
    except: pass

@dp.message(F.location)
async def handle_loc(m: Message):
    conn=sqlite3.connect(DB); c=conn.cursor(); c.execute("SELECT id, client_id FROM orders WHERE courier_id=? AND status='taken' ORDER BY id DESC LIMIT 1", (m.from_user.id,)); row=c.fetchone(); conn.close()
    if not row: return
    oid,cid=row
    try: await bot.send_message(cid, f"🚚 Курьер едет #{oid}:"); await bot.send_location(cid, m.location.latitude, m.location.longitude)
    except: pass

@dp.message(F.text=="✅ Я доставил - фотоотчет")
async def ask_photo(m: Message, state: FSMContext):
    await state.set_state(PhotoReport.waiting_photo); await m.answer("Скинь фото")

@dp.message(PhotoReport.waiting_photo, F.photo)
async def handle_photo(m: Message, state: FSMContext):
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT id, client_id FROM orders WHERE courier_id=? AND status='taken' ORDER BY id DESC LIMIT 1", (m.from_user.id,)); row=c.fetchone()
    if not row: await state.clear(); conn.close(); return
    oid,cid=row
    c.execute("UPDATE orders SET status='done' WHERE id=?", (oid,)); conn.commit(); conn.close()
    await state.clear()
    total,cnt=get_earnings(m.from_user.id)
    try: await bot.send_message(cid, f"✅ Заказ #{oid} доставлен!"); await bot.send_photo(cid, m.photo[-1].file_id)
    except: pass
    await m.answer(f"Закрыт #{oid}! Итого {total}тг ({cnt})", reply_markup=courier_kb())

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
async def run_bot():
    init_db(); await dp.start_polling(bot)
if __name__=="__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(run_bot())
