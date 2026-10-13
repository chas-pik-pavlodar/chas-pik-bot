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

# ===== ВСТАВЬ СВОИ НОМЕРА С +7 БЕЗ ПРОБЕЛОВ =====
OPERATOR_PHONE = "+77001234567"
COURIER_PHONE = "+77001234567"
# ================================================

HARDCODED_COURIER_ID = 7714431728

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
@app.route('/')
def home(): return "Bot alive!"
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

def init_db():
    # Удаляем старую битую базу если она была
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS orders")
    c.execute("DROP TABLE IF EXISTS couriers")
    c.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, client_username TEXT, address_from TEXT, address_to TEXT, what TEXT, note TEXT, price TEXT, status TEXT DEFAULT 'new', courier_id INTEGER)")
    c.execute("CREATE TABLE couriers (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER UNIQUE, username TEXT, phone TEXT)")
    c.execute("INSERT OR IGNORE INTO couriers (user_id, username, phone) VALUES (?,?,?)", (HARDCODED_COURIER_ID, "main_kurier", COURIER_PHONE))
    conn.commit(); conn.close()
    print("DB RESET DONE - курьер добавлен")

def get_earnings(courier_id):
    try:
        conn = sqlite3.connect(DB); c = conn.cursor()
        c.execute("SELECT price FROM orders WHERE courier_id=? AND status='done'", (courier_id,))
        rows = c.fetchall(); conn.close()
        total=0
        for (p,) in rows:
            try:
                digits=''.join(filter(str.isdigit, str(p)))
                if digits: total+=int(digits)
            except: pass
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
        [KeyboardButton(text="📞 Оператор"), KeyboardButton(text="💰 Мой заработок")]
    ], resize_keyboard=True)

def courier_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📍 Обновить где я", request_location=True)],
        [KeyboardButton(text="✅ Я доставил - фотоотчет")],
        [KeyboardButton(text="💰 Мой заработок"), KeyboardButton(text="📞 Оператор")]
    ], resize_keyboard=True)

@dp.message(Command("start"))
async def start(m: Message, state: FSMContext):
    await state.clear()
    init_db()
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT user_id FROM couriers"); has=len(c.fetchall())>0
    conn.close()
    await m.answer(f"ЧАС ПИК Павлодар ⚡️\nТвой ID: {m.from_user.id}\nКурьеров в базе: {has}", reply_markup=client_kb())

@dp.message(F.text=="📞 Оператор")
async def operator_call(m: Message):
    # 2 варианта звонка - кнопка tel и просто номер текстом
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📞 Позвонить оператору {OPERATOR_PHONE}", url=f"tel:{OPERATOR_PHONE}")],
        [InlineKeyboardButton(text=f"🛵 Позвонить курьеру {COURIER_PHONE}", url=f"tel:{COURIER_PHONE}")],
        [InlineKeyboardButton(text="💬 Написать оператору в ТГ", url=f"tg://user?id={ADMIN_ID}")]
    ])
    await m.answer(f"📞 СВЯЗЬ ЧАС ПИК:\n\nОператор: {OPERATOR_PHONE}\nКурьер: {COURIER_PHONE}\n\nНажми кнопку ниже чтобы позвонить (работает только с телефона):\nЕсли не звонит - набери номер вручную: {OPERATOR_PHONE}", reply_markup=kb)

@dp.message(F.text=="🚚 Стать курьером")
async def become(m: Message):
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("INSERT OR IGNORE INTO couriers (user_id, username, phone) VALUES (?,?,?)", (m.from_user.id, m.from_user.username or str(m.from_user.id), COURIER_PHONE))
    conn.commit(); c.execute("SELECT user_id FROM couriers"); rows=c.fetchall(); conn.close()
    await m.answer(f"✅ Ты курьер! Всего курьеров: {len(rows)}\nТвой ID {m.from_user.id}", reply_markup=courier_kb())

@dp.message(F.text=="💰 Мой заработок")
async def earn_my(m: Message):
    total,cnt=get_earnings(m.from_user.id)
    await m.answer(f"💰 ТВОЙ ЗАРАБОТОК:\n\nЗаказов доставлено: {cnt}\nСумма: {total} тг\n\nID: {m.from_user.id}")

@dp.message(Command("couriers"))
async def list_c(m: Message):
    conn=sqlite3.connect(DB); c=conn.cursor(); c.execute("SELECT user_id, username FROM couriers"); rows=c.fetchall(); conn.close()
    if not rows:
        conn=sqlite3.connect(DB); c=conn.cursor()
        c.execute("INSERT OR IGNORE INTO couriers (user_id, username, phone) VALUES (?,?,?)", (HARDCODED_COURIER_ID, "main_kurier", COURIER_PHONE))
        conn.commit(); conn.close()
        await m.answer("База была пустая, восстановил главного курьера. Напиши /couriers еще раз")
        return
    txt="КУРЬЕРЫ ЧАС ПИК:\n\n"
    for uid,uname in rows:
        total,cnt=get_earnings(uid)
        txt+=f"@{uname} ID {uid}\n Заказов: {cnt} / {total} тг\n Тел: {COURIER_PHONE}\n\n"
    await m.answer(txt)

@dp.message(Command("orders"))
async def list_o(m: Message):
    conn=sqlite3.connect(DB); c=conn.cursor(); c.execute("SELECT id, address_from, address_to, what, price, status, courier_id FROM orders ORDER BY id DESC LIMIT 20"); rows=c.fetchall(); conn.close()
    if not rows: await m.answer("Заказов пока 0"); return
    await m.answer("\n".join([f"#{r[0]} {r[1]}->{r[2]} {r[3]} {r[4]} [{r[5]}] курьер {r[6]}" for r in rows]))

@dp.message(Command("earnings"))
async def earn_admin(m: Message):
    if m.from_user.id!=ADMIN_ID: return
    conn=sqlite3.connect(DB); c=conn.cursor(); c.execute("SELECT courier_id, price, status FROM orders"); rows=c.fetchall(); conn.close()
    if not rows: await m.answer("Нет заказов вообще"); return
    txt=f"Всего записей {len(rows)}:\n"
    for r in rows: txt+=f"курьер {r[0]} {r[1]}тг статус {r[2]}\n"
    await m.answer(txt)

@dp.message(F.text=="📦 Сделать заказ")
async def order_start(m: Message, state: FSMContext):
    await state.set_state(OrderForm.from_address); await m.answer("📍 Откуда забрать? Напиши адрес:")

@dp.message(OrderForm.from_address)
async def order_from(m: Message, state: FSMContext):
    await state.update_data(from_addr=m.text); await state.set_state(OrderForm.to_address); await m.answer("🏁 Куда доставить?")

@dp.message(OrderForm.to_address)
async def order_to(m: Message, state: FSMContext):
    await state.update_data(to_addr=m.text); await state.set_state(OrderForm.what); await m.answer("📦 Что везём? (документы, еда, цветы, фурнитура)")

@dp.message(OrderForm.what)
async def order_what(m: Message, state: FSMContext):
    await state.update_data(what=m.text); await state.set_state(OrderForm.note); await m.answer("📝 Уточнение? (этаж, подъезд, кому отдать) Если нет - напиши -")

@dp.message(OrderForm.note)
async def order_note(m: Message, state: FSMContext):
    await state.update_data(note=m.text); await state.set_state(OrderForm.price); await m.answer("💰 Цена доставки? Напиши число, например 2500")

@dp.message(OrderForm.price)
async def order_price(m: Message, state: FSMContext):
    data=await state.get_data()
    from_addr=data.get("from_addr"); to_addr=data.get("to_addr"); what=data.get("what"); note=data.get("note")
    price=m.text
    conn=sqlite3.connect(DB); c=conn.cursor()
    try:
        c.execute("INSERT INTO orders (client_id, client_username, address_from, address_to, what, note, price) VALUES (?,?,?,?,?,?,?)", (m.from_user.id, m.from_user.username, from_addr, to_addr, what, note, price))
        order_id=c.lastrowid
        c.execute("SELECT user_id FROM couriers"); couriers=c.fetchall()
        conn.commit()
    except Exception as e:
        await m.answer(f"Ошибка базы {e}, делаю сброс..."); conn.close(); init_db()
        conn=sqlite3.connect(DB); c=conn.cursor()
        c.execute("INSERT INTO orders (client_id, client_username, address_from, address_to, what, note, price) VALUES (?,?,?,?,?,?,?)", (m.from_user.id, m.from_user.username, from_addr, to_addr, what, note, price))
        order_id=c.lastrowid
        c.execute("SELECT user_id FROM couriers"); couriers=c.fetchall()
        conn.commit()
    conn.close()
    await state.clear()
    await m.answer(f"✅ Заказ #{order_id} принят!\n{from_addr} -> {to_addr}\nЧто: {what}\nУточнение: {note}\nЦена: {price}тг\n\nИщу курьера...", reply_markup=client_kb())

    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"🔥 Взять за {price}тг", callback_data=f"take_{order_id}")]])
    text_c=f"🔥 НОВЫЙ ЗАКАЗ #{order_id}\n\nОт: {from_addr}\nДо: {to_addr}\nЧто: {what}\nУточнение: {note}\nЦена: {price}тг\nКлиент: @{m.from_user.username} ID {m.from_user.id}"
    sent=0
    for (cid,) in couriers:
        try:
            await bot.send_message(cid, text_c, reply_markup=kb)
            sent+=1
        except Exception as e: print(f"Не отправил {cid} {e}")
    await m.answer(f"Отправил {sent} курьерам. Если 0 - курьеры не зарегистрированы, пусть нажмут Стать курьером")
    try: await bot.send_message(ADMIN_ID, f"Заказ #{order_id} отправлен {sent} курьерам")
    except: pass

@dp.callback_query(F.data.startswith("take_"))
async def take_order(cq: CallbackQuery):
    order_id=int(cq.data.split("_")[1])
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT status, client_id, address_from, address_to, what, note, price FROM orders WHERE id=?", (order_id,))
    row=c.fetchone()
    if not row: await cq.answer("Не найден"); conn.close(); return
    status,client_id,from_addr,to_addr,what,note,price=row
    if status!='new': await cq.answer("Уже взяли!", show_alert=True); conn.close(); return
    c.execute("UPDATE orders SET status='taken', courier_id=? WHERE id=?", (cq.from_user.id, order_id)); conn.commit(); conn.close()
    from_q=urllib.parse.quote(f"{from_addr}, Павлодар"); to_q=urllib.parse.quote(f"{to_addr}, Павлодар")
    yandex_url=f"https://yandex.kz/maps/?rtext={from_q}~{to_q}&rtt=auto"
    google_url=f"https://www.google.com/maps/dir/?api=1&origin={from_q}&destination={to_q}"
    kb_route=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚕 Яндекс Маршрут", url=yandex_url)],[InlineKeyboardButton(text="📍 Google", url=google_url)]])
    await cq.message.edit_text(f"ТЫ ВЗЯЛ ЗАКАЗ #{order_id}\n{from_addr}->{to_addr}\nЧто: {what} ({note})\nЦена: {price}тг", reply_markup=kb_route)
    await cq.message.answer("Жми 📍 Обновить где я, в конце ✅ Я доставил", reply_markup=courier_kb())
    await cq.answer("Взял!")
    try:
        kb_client=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"🛵 Курьер {COURIER_PHONE}", url=f"tel:{COURIER_PHONE}")],
            [InlineKeyboardButton(text=f"📞 Оператор {OPERATOR_PHONE}", url=f"tel:{OPERATOR_PHONE}")],
            [InlineKeyboardButton(text="👤 Курьер в ТГ", url=f"tg://user?id={cq.from_user.id}")]
        ])
        await bot.send_message(client_id, f"✅ Заказ #{order_id} взял курьер @{cq.from_user.username}\nТел курьера: {COURIER_PHONE}", reply_markup=kb_client)
    except: pass

@dp.message(F.location)
async def handle_loc(m: Message):
    conn=sqlite3.connect(DB); c=conn.cursor(); c.execute("SELECT id, client_id FROM orders WHERE courier_id=? AND status='taken' ORDER BY id DESC LIMIT 1", (m.from_user.id,)); row=c.fetchone(); conn.close()
    if not row: return
    oid,cid=row
    try: await bot.send_message(cid, f"🚚 Курьер едет #{oid}:"); await bot.send_location(cid, m.location.latitude, m.location.longitude); await m.answer("📍 Отправил клиенту!")
    except: pass

@dp.message(F.text=="✅ Я доставил - фотоотчет")
async def ask_photo(m: Message, state: FSMContext):
    await state.set_state(PhotoReport.waiting_photo); await m.answer("Скинь фото у двери / товара")

@dp.message(PhotoReport.waiting_photo, F.photo)
async def handle_photo(m: Message, state: FSMContext):
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT id, client_id, price FROM orders WHERE courier_id=? AND status='taken' ORDER BY id DESC LIMIT 1", (m.from_user.id,)); row=c.fetchone()
    if not row: await m.answer("Нет активного заказа"); await state.clear(); conn.close(); return
    oid,cid,price=row
    c.execute("UPDATE orders SET status='done' WHERE id=?", (oid,)); conn.commit(); conn.close()
    await state.clear()
    total,cnt=get_earnings(m.from_user.id)
    try: await bot.send_message(cid, f"✅ Заказ #{oid} доставлен!"); await bot.send_photo(cid, m.photo[-1].file_id, caption=f"Фотоотчет #{oid} {price}тг")
    except: pass
    await m.answer(f"🔥 Закрыт #{oid}!\nЗаработок: {total}тг ({cnt} зак)", reply_markup=courier_kb())
    try: await bot.send_message(ADMIN_ID, f"Заказ #{oid} DONE курьер {m.from_user.id} {price}тг. Итого {total}тг")
    except: pass

@dp.message(F.photo)
async def auto_p(m: Message):
    conn=sqlite3.connect(DB); c=conn.cursor(); c.execute("SELECT id, client_id FROM orders WHERE courier_id=? AND status='taken' ORDER BY id DESC LIMIT 1", (m.from_user.id,)); row=c.fetchone(); conn.close()
    if row:
        oid,cid=row
        try: await bot.send_photo(cid, m.photo[-1].file_id, caption=f"Фотоотчет #{oid}"); await m.answer("Фото отправил клиенту!")
        except: pass

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
async def run_bot():
    init_db(); await dp.start_polling(bot)
if __name__=="__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(run_bot())
    
