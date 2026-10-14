import os, logging, threading, asyncio, sqlite3
from flask import Flask, jsonify
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage

BOT_TOKEN = os.environ.get("TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "1218877896"))
DB = "database.db"
logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

@app.route('/')
def home(): return '<h2>Bot alive!</h2><p><a href="/map">LIVE карта</a></p>'
@app.route('/api/track/<int:courier_id>')
def api_track(courier_id):
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT lat, lon, ts FROM tracks WHERE courier_id=? AND date(ts)=date('now','localtime') ORDER BY ts DESC LIMIT 200",(courier_id,))
    rows=c.fetchall()
    c.execute("SELECT last_lat, last_lon, full_name FROM couriers WHERE user_id=?",(courier_id,)); cur=c.fetchone(); conn.close()
    points=[{"lat":r[0],"lon":r[1],"ts":r[2]} for r in reversed(rows)]
    last={"lat":cur[0],"lon":cur[1],"name":cur[2]} if cur else None
    return jsonify({"points":points,"last":last})
@app.route('/api/all')
def api_all():
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT user_id, full_name, last_lat, last_lon, last_time FROM couriers WHERE last_lat IS NOT NULL ORDER BY last_time DESC")
    rows=c.fetchall(); conn.close()
    return jsonify([{"id":r[0],"name":r[1],"lat":r[2],"lon":r[3],"time":r[4]} for r in rows])
@app.route('/live/<int:courier_id>')
def live_page(courier_id):
    return f'''<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LIVE {courier_id}</title><link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>body{{margin:0}}#map{{height:100vh}}.info{{position:absolute;top:10px;left:50%;transform:translateX(-50%);z-index:1000;background:white;padding:10px 18px;border-radius:20px;box-shadow:0 2px 10px rgba(0,0,0,.3);font-family:Arial;font-weight:bold}}</style>
</head><body><div class="info" id="info">Загрузка...</div><div id="map"></div>
<script>var map=L.map('map').setView([52.287,76.967],13);L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{maxZoom:19}}).addTo(map);
var poly=L.polyline([],{{color:'red',weight:5}}).addTo(map);var marker=null;
async function upd(){{let r=await fetch('/api/track/{courier_id}');let d=await r.json();if(d.points.length>0){{let ll=d.points.map(p=>[p.lat,p.lon]);poly.setLatLngs(ll);if(!marker){{marker=L.marker(ll[ll.length-1]).addTo(map);map.fitBounds(poly.getBounds(),{{padding:[40,40]}});}}else marker.setLatLng(ll[ll.length-1]);document.getElementById('info').innerHTML='🔴 LIVE | Точек: '+d.points.length+' | 5с | '+(d.last?.name||'');}}}}
upd();setInterval(upd,5000);</script></body></html>'''
@app.route('/map')
def all_map():
    return '''<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Все курьеры</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>body{margin:0}#map{height:100vh}.info{position:absolute;top:10px;left:50%;transform:translateX(-50%);z-index:1000;background:white;padding:10px 18px;border-radius:20px;box-shadow:0 2px 10px rgba(0,0,0,.3);font-family:Arial;font-weight:bold}}</style>
</head><body><div class="info">Все курьеры LIVE</div><div id="map"></div>
<script>var map=L.map('map').setView([52.287,76.967],12);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19}).addTo(map);var markers={};
async function upd(){let r=await fetch('/api/all');let data=await r.json();data.forEach(c=>{if(markers[c.id]) markers[c.id].setLatLng([c.lat,c.lon]);else markers[c.id]=L.marker([c.lat,c.lon]).addTo(map).bindPopup(c.name+'<br><a href="/live/'+c.id+'">Маршрут</a>');});}
upd();setInterval(upd,5000);</script></body></html>'''

bot=Bot(token=BOT_TOKEN); dp=Dispatcher(storage=MemoryStorage())
last_live_notify={}; last_client_notify={}

def init_db():
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, client_username TEXT, client_name TEXT, address_from TEXT, address_to TEXT, what TEXT, note TEXT, price TEXT, status TEXT DEFAULT 'new', courier_id INTEGER, courier_username TEXT, courier_name TEXT, created DATE DEFAULT CURRENT_DATE, created_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    c.execute("CREATE TABLE IF NOT EXISTS couriers (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER UNIQUE, username TEXT, full_name TEXT, phone TEXT, last_lat REAL, last_lon REAL, last_time TIMESTAMP)")
    c.execute("CREATE TABLE IF NOT EXISTS tracks (id INTEGER PRIMARY KEY AUTOINCREMENT, courier_id INTEGER, lat REAL, lon REAL, ts TEXT)")
    conn.commit(); conn.close()

class OrderForm(StatesGroup):
    from_address=State(); to_address=State(); what=State(); note=State(); price=State()
class PhotoReport(StatesGroup):
    waiting_photo=State()

def client_kb(): return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📦 Сделать заказ")],[KeyboardButton(text="🚚 Стать курьером")],[KeyboardButton(text="📞 Связаться с оператором"),KeyboardButton(text="🛵 Связаться с курьером")],[KeyboardButton(text="💰 Мой заработок")]],resize_keyboard=True)
def courier_kb(): return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔴 Включить LIVE на 8 часов")],[KeyboardButton(text="🗺 Мой LIVE маршрут"),KeyboardButton(text="✅ Я доставил - фотоотчет")],[KeyboardButton(text="💰 Мой заработок"),KeyboardButton(text="📊 Сегодня")]],resize_keyboard=True)
def admin_kb(): return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📦 Сделать заказ")],[KeyboardButton(text="👑 Все заказы"),KeyboardButton(text="🔥 Активные")],[KeyboardButton(text="👥 Курьеры"),KeyboardButton(text="🗺 Курьеры на карте")],[KeyboardButton(text="💰 Заработки"),KeyboardButton(text="📊 Сегодня")],[KeyboardButton(text="🆔 Мой ID")]],resize_keyboard=True)

def get_base_url(): return (os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("BASE_URL") or "https://your-bot.onrender.com").rstrip("/")

@dp.message(F.text=="🚚 Стать курьером")
async def become_courier(m: Message):
    init_db()
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("INSERT OR IGNORE INTO couriers (user_id, username, full_name) VALUES (?,?,?)",(m.from_user.id, m.from_user.username, m.from_user.first_name))
    c.execute("UPDATE couriers SET username=?, full_name=? WHERE user_id=?",(m.from_user.username, m.from_user.first_name, m.from_user.id))
    conn.commit(); conn.close()
    await m.answer("✅ Ты теперь курьер! Теперь включи LIVE:", reply_markup=courier_kb())

@dp.message(F.text=="📞 Связаться с оператором")
async def contact_operator(m: Message):
    await m.answer("📞 Оператор: @chas_pik_operator\nТел: +77771234567")

@dp.message(F.text=="🛵 Связаться с курьером")
async def contact_courier(m: Message):
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT courier_id, courier_username, courier_name FROM orders WHERE client_id=? AND status='taken' ORDER BY id DESC LIMIT 1",(m.from_user.id,))
    row=c.fetchone(); conn.close()
    if row and row[0]:
        cid, cun, cname = row
        if cun: await m.answer(f"Твой курьер: @{cun} ({cname})")
        else: await m.answer(f"Твой курьер: {cname}\nID: {cid}")
    else:
        await m.answer("У тебя нет активного заказа. Сначала сделай заказ.")

@dp.message(F.text=="💰 Мой заработок")
async def my_earn(m: Message):
    conn=sqlite3.connect(DB); cur=conn.cursor()
    cur.execute("SELECT price FROM orders WHERE courier_id=? AND status='done' AND date(created_time)=date('now','localtime')",(m.from_user.id,))
    total=sum(int(''.join(filter(str.isdigit, str(p[0]))) or 0) for p in cur.fetchall()); conn.close()
    await m.answer(f"💰 Сегодня: {total} тг")

@dp.message(F.text=="📊 Сегодня")
async def today_stats(m: Message):
    conn=sqlite3.connect(DB); cur=conn.cursor()
    cur.execute("SELECT COUNT(*), SUM(CAST(price AS INTEGER)) FROM orders WHERE date(created_time)=date('now','localtime')")
    cnt, summ=cur.fetchone(); conn.close()
    await m.answer(f"📊 Сегодня заказов: {cnt or 0}")

@dp.message(F.text=="🆔 Мой ID")
async def my_id(m: Message): await m.answer(f"Твой ID: {m.from_user.id}")

@dp.message(F.text=="🔴 Включить LIVE на 8 часов")
async def ask_live(m: Message): await m.answer("🔴 Нажми Скрепка 📎 -> Геопозиция -> Транслировать LIVE -> 8 часов", reply_markup=courier_kb())

@dp.edited_message(F.location)
@dp.message(F.location)
async def handle_live_loc(m: Message):
    uid=m.from_user.id; lat=m.location.latitude; lon=m.location.longitude; now=datetime.now()
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("INSERT OR IGNORE INTO couriers (user_id, username, full_name) VALUES (?,?,?)",(uid, m.from_user.username, m.from_user.first_name))
    c.execute("UPDATE couriers SET last_lat=?, last_lon=?, last_time=CURRENT_TIMESTAMP, full_name=?, username=? WHERE user_id=?",(lat,lon,m.from_user.first_name,m.from_user.username,uid))
    c.execute("INSERT INTO tracks (courier_id, lat, lon, ts) VALUES (?,?,?,?)",(uid,lat,lon,now.isoformat()))
    c.execute("DELETE FROM tracks WHERE ts < datetime('now','-1 day')")
    c.execute("SELECT id, client_id FROM orders WHERE courier_id=? AND status='taken' ORDER BY id DESC LIMIT 1",(uid,)); row=c.fetchone()
    conn.commit(); conn.close()
    last=last_live_notify.get(uid); is_first=last is None
    if last and (now-last).total_seconds()<300:
        if row:
            last_cli=last_client_notify.get(uid)
            if last_cli is None or (now-last_cli).total_seconds()>60:
                last_client_notify[uid]=now
                try: await bot.send_location(row[1], lat, lon, live_period=m.location.live_period or 28800)
                except: pass
        return
    last_live_notify[uid]=now; base=get_base_url(); live_link=f"{base}/live/{uid}"
    if m.location.live_period and is_first:
        try:
            kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🗺 Открыть мою LIVE карту", url=live_link)]])
            await m.answer(f"✅ LIVE включен! Карта: {live_link}", reply_markup=kb)
        except: pass
    if row:
        oid,cid=row; last_client_notify[uid]=now
        try:
            if is_first:
                kb_cli=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🗺 Следить LIVE", url=live_link)]])
                await bot.send_message(cid, f"Курьер включил LIVE #{oid}", reply_markup=kb_cli)
            await bot.send_location(cid, lat, lon, live_period=m.location.live_period or 28800)
        except: pass

@dp.message(F.text=="🗺 Мой LIVE маршрут")
async def show_my_route(m: Message):
    base=get_base_url(); link=f"{base}/live/{m.from_user.id}"
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🗺 Открыть LIVE карту", url=link)]])
    await m.answer(f"Твоя карта:\n{link}", reply_markup=kb)

@dp.message(F.text=="🗺 Курьеры на карте")
async def couriers_map(m: Message):
    if m.from_user.id!=ADMIN_ID: return
    base=get_base_url(); conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT user_id, full_name, username, last_lat, last_lon FROM couriers WHERE last_lat IS NOT NULL ORDER BY last_time DESC")
    rows=c.fetchall(); conn.close()
    if not rows: await m.answer("Нет локаций"); return
    kb_rows=[]
    for uid,fname,uname,lat,lon in rows:
        name=f"@{uname}" if uname and uname!='None' else fname
        kb_rows.append([InlineKeyboardButton(text=f"🔴 LIVE {name}", url=f"{base}/live/{uid}")])
        try: await bot.send_location(m.chat.id, lat, lon)
        except: pass
    kb_rows.append([InlineKeyboardButton(text="🗺 ВСЕ КУРЬЕРЫ", url=f"{base}/map")])
    await m.answer(f"Все карты: {base}/map", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))

@dp.message(F.text=="📦 Сделать заказ")
async def order_start(m: Message, state: FSMContext):
    await state.set_state(OrderForm.from_address); await m.answer("Откуда забрать?")
@dp.message(OrderForm.from_address)
async def order_from(m: Message, state: FSMContext):
    await state.update_data(from_addr=m.text); await state.set_state(OrderForm.to_address); await m.answer("Куда везти?")
@dp.message(OrderForm.to_address)
async def order_to(m: Message, state: FSMContext):
    await state.update_data(to_addr=m.text); await state.set_state(OrderForm.what); await m.answer("Что везем?")
@dp.message(OrderForm.what)
async def order_what(m: Message, state: FSMContext):
    await state.update_data(what=m.text); await state.set_state(OrderForm.note); await m.answer("Уточнение / подъезд?")
@dp.message(OrderForm.note)
async def order_note(m: Message, state: FSMContext):
    await state.update_data(note=m.text); await state.set_state(OrderForm.price); await m.answer("Цена (тг)?")
@dp.message(OrderForm.price)
async def order_price(m: Message, state: FSMContext):
    data=await state.get_data(); price=m.text.replace("тг","").strip()
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("INSERT INTO orders (client_id, client_username, client_name, address_from, address_to, what, note, price, created_time) VALUES (?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)",(m.from_user.id,m.from_user.username,m.from_user.first_name,data.get("from_addr"),data.get("to_addr"),data.get("what"),data.get("note"),price))
    oid=c.lastrowid; c.execute("SELECT user_id FROM couriers"); cours=c.fetchall(); conn.commit(); conn.close(); await state.clear()
    await m.answer(f"✅ Заказ #{oid} принят! Ищем курьера...")
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"Взять за {price}тг", callback_data=f"take_{oid}")]])
    txt=f"🔥 ЗАКАЗ #{oid}\nОт: {data.get('from_addr')}\nДо: {data.get('to_addr')}\nЧто: {data.get('what')}\nЦена: {price}тг"
    for (cid,) in cours:
        try: await bot.send_message(cid, txt, reply_markup=kb)
        except: pass

@dp.callback_query(F.data.startswith("take_"))
async def take_order(cq: CallbackQuery):
    oid=int(cq.data.split("_")[1]); conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT status FROM orders WHERE id=?",(oid,)); r=c.fetchone()
    if not r or r[0]!='new': await cq.answer("Уже взяли!"); conn.close(); return
    c.execute("UPDATE orders SET status='taken', courier_id=?, courier_username=?, courier_name=? WHERE id=?",(cq.from_user.id,cq.from_user.username,cq.from_user.first_name,oid)); conn.commit(); conn.close()
    await cq.message.edit_text(f"✅ ТЫ ВЗЯЛ #{oid} - включи LIVE!"); await cq.answer("Взял!")

@dp.message(F.text=="✅ Я доставил - фотоотчет")
async def ask_photo(m: Message, state: FSMContext):
    await state.set_state(PhotoReport.waiting_photo); await m.answer("Скинь фото доставки")
@dp.message(PhotoReport.waiting_photo, F.photo)
async def handle_photo(m: Message, state: FSMContext):
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT id, client_id FROM orders WHERE courier_id=? AND status='taken' ORDER BY id DESC LIMIT 1",(m.from_user.id,)); row=c.fetchone()
    if not row: await state.clear(); conn.close(); return
    oid,cid=row; c.execute("UPDATE orders SET status='done' WHERE id=?",(oid,)); conn.commit(); conn.close(); await state.clear()
    await m.answer(f"✅ Закрыт #{oid}!")
    try: await bot.send_message(cid, f"✅ Заказ #{oid} доставлен! Оцени курьера")
    except: pass

@dp.message(F.text=="👑 Все заказы")
async def all_orders(m: Message):
    if m.from_user.id!=ADMIN_ID: return
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT id, address_from, address_to, price, status FROM orders ORDER BY id DESC LIMIT 15"); rows=c.fetchall(); conn.close()
    txt="Заказы:\n"
    for r in rows: txt+=f"#{r[0]} {r[1]}->{r[2]} {r[3]}тг [{r[4]}]\n"
    await m.answer(txt)

@dp.message(F.text=="👥 Курьеры")
async def list_c(m: Message):
    conn=sqlite3.connect(DB); c=conn.cursor(); c.execute("SELECT user_id, username, full_name FROM couriers"); rows=c.fetchall(); conn.close()
    txt=f"Курьеров: {len(rows)}\n"
    for uid,uname,fname in rows: txt+=f"{fname} @{uname} - {uid}\n"
    await m.answer(txt)

@dp.message(Command("start"))
async def start_cmd(m: Message, state: FSMContext):
    await state.clear(); init_db()
    if m.from_user.id==ADMIN_ID: await m.answer("АДМИН ПАНЕЛЬ", reply_markup=admin_kb())
    else:
        conn=sqlite3.connect(DB); c=conn.cursor(); c.execute("SELECT user_id FROM couriers WHERE user_id=?",(m.from_user.id,)); is_courier=c.fetchone(); conn.close()
        if is_courier: await m.answer("Привет, курьер!", reply_markup=courier_kb())
        else: await m.answer("ЧАС ПИК Павлодар - доставка", reply_markup=client_kb())

def run_flask(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
async def run_bot(): init_db(); await dp.start_polling(bot)
if __name__=="__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(run_bot())
