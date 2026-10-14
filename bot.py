import os, logging, threading, asyncio, sqlite3, urllib.parse
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
def home(): return '<h2>Bot alive!</h2><p><a href="/map">Карта</a></p>'

@app.route('/api/track/<int:courier_id>')
def api_track(courier_id):
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT lat, lon FROM tracks WHERE courier_id=? AND date(ts)=date('now','localtime') ORDER BY ts DESC LIMIT 200",(courier_id,))
    rows=c.fetchall(); c.execute("SELECT last_lat, last_lon FROM couriers WHERE user_id=?",(courier_id,)); cur=c.fetchone(); conn.close()
    points=[{"lat":r[0],"lon":r[1]} for r in reversed(rows)]
    last={"lat":cur[0],"lon":cur[1]} if cur and cur[0] else None
    return jsonify({"points":points,"last":last})

@app.route('/api/order/<int:courier_id>')
def api_order(courier_id):
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT address_to FROM orders WHERE courier_id=? AND status='taken' ORDER BY id DESC LIMIT 1",(courier_id,))
    row=c.fetchone(); conn.close()
    return jsonify({"to":row[0] if row else None})

@app.route('/api/all')
def api_all():
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT user_id, full_name, last_lat, last_lon, last_time FROM couriers WHERE last_lat IS NOT NULL")
    rows=c.fetchall(); conn.close()
    return jsonify([{"id":r[0],"name":r[1],"lat":r[2],"lon":r[3],"time":str(r[4])} for r in rows])

@app.route('/api/online')
def api_online():
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT user_id, full_name, last_lat, last_lon FROM couriers WHERE last_lat IS NOT NULL AND last_time > datetime('now','-30 minutes')")
    rows=c.fetchall(); conn.close()
    return jsonify([{"id":r[0],"name":r[1],"lat":r[2],"lon":r[3]} for r in rows])

@app.route('/live/<int:courier_id>')
def live_page(courier_id):
    return f'''<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LIVE {courier_id}</title><link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>body{{margin:0}}#map{{height:100vh}}#info{{position:absolute;top:10px;left:50%;transform:translateX(-50%);z-index:1000;background:white;padding:10px 18px;border-radius:20px;box-shadow:0 2px 10px rgba(0,0,0,.3);font-family:Arial;font-weight:bold;text-align:center;max-width:90%}}
.nav{{position:absolute;bottom:20px;left:50%;transform:translateX(-50%);z-index:1000;display:flex;gap:8px;flex-wrap:wrap;justify-content:center}}
.nav a{{padding:10px 14px;border-radius:20px;color:white;text-decoration:none;font-family:Arial;font-weight:bold;font-size:13px;box-shadow:0 2px 8px rgba(0,0,0,.3)}}
.g{{background:#4285F4}}.y{{background:#FFCC00;color:black}}.d{{background:#00AA00}}</style>
</head><body><div id="info">Загрузка...</div><div id="map"></div><div class="nav" id="nav" style="display:none"></div>
<script>
var map=L.map('map').setView([52.287,76.967],13);L.tileLayer('https://{{{{s}}}}.tile.openstreetmap.org/{{{{z}}}}/{{{{x}}}}/{{{{y}}}}.png',{{maxZoom:19}}).addTo(map);
var myTrack=L.polyline([],{{color:'red',weight:5}}).addTo(map);var routeLine=L.polyline([],{{color:'blue',weight:6,dashArray:'12,12'}}).addTo(map);var me=null;
async function geocode(a){{try{{let r=await fetch('https://nominatim.openstreetmap.org/search?format=json&q='+encodeURIComponent(a+', Павлодар')+'&limit=1');let j=await r.json();if(j.length>0)return[parseFloat(j[0].lat),parseFloat(j[0].lon)];}}catch(e){{}}return null;}}
async function getRoute(f,t){{try{{let r=await fetch(`https://router.project-osrm.org/route/v1/driving/${{f[1]}},${{f[0]}};${{t[1]}},${{t[0]}}?overview=full&geometries=geojson`);let j=await r.json();if(j.routes&&j.routes[0])return j.routes[0].geometry.coordinates.map(c=>[c[1],c[0]]);}}catch(e){{}}return[f,t];}}
async function upd(){{
 let tr=await fetch('/api/track/{courier_id}');let d=await tr.json();let ord=await fetch('/api/order/{courier_id}');let o=await ord.json();
 if(d.points.length>0){{let ll=d.points.map(p=>[p.lat,p.lon]);myTrack.setLatLngs(ll);let last=ll[ll.length-1];if(!me)me=L.marker(last).addTo(map);else me.setLatLng(last);
   if(o.to){{let dest=await geocode(o.to);if(dest){{let route=await getRoute(last,dest);routeLine.setLatLngs(route);map.fitBounds(L.latLngBounds(route).extend(myTrack.getBounds()),{{padding:[50,50]}});
   document.getElementById('info').innerHTML='🔴 Трек | 🔵 Маршрут до: '+o.to;
   let enc=encodeURIComponent(o.to);
   document.getElementById('nav').style.display='flex';
   document.getElementById('nav').innerHTML=`<a class='g' href='https://www.google.com/maps/dir/${{last[0]}},${{last[1]}}/${{enc}}/' target='_blank'>Google</a><a class='y' href='https://yandex.kz/maps/163/pavlodar/?rtext=${{last[0]}},${{last[1]}}~${{enc}}&rtt=auto' target='_blank'>Яндекс</a><a class='d' href='https://2gis.kz/pavlodar/search/${{enc}}' target='_blank'>2ГИС</a>`;
   }}else{{document.getElementById('info').innerHTML='🔴 LIVE Точек: '+d.points.length;map.fitBounds(myTrack.getBounds(),{{padding:[30,30]}});}}
 }}
}}
upd();setInterval(upd,8000);
</script></body></html>'''

@app.route('/map')
def all_map():
    return '''<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Все курьеры LIVE</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>body{margin:0}#map{height:100vh}.top{position:absolute;top:10px;left:50%;transform:translateX(-50%);z-index:1000;background:white;padding:10px 18px;border-radius:20px;box-shadow:0 2px 10px rgba(0,0,0,.3);font-family:Arial;font-weight:bold;text-align:center}
.leaflet-popup-content a{display:block;margin:4px 0;padding:8px 10px;border-radius:10px;color:white;text-decoration:none;text-align:center;font-weight:bold}
.g{background:#4285F4}.y{background:#FFCC00;color:black}.d{background:#00AA00}</style>
</head><body><div class="top" id="top">Загрузка...</div><div id="map"></div>
<script>var map=L.map('map').setView([52.287,76.967],12);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19}).addTo(map);var markers={};
async function upd(){let r=await fetch('/api/all');let data=await r.json();document.getElementById('top').innerText='Все курьеры: '+data.length+' | LIVE реальное время';data.forEach(c=>{
 if(markers[c.id]) markers[c.id].setLatLng([c.lat,c.lon]);
 else {
  let enc=encodeURIComponent(c.lat+','+c.lon);
  let popup=`<b>${c.name}</b><br><a class='g' href='https://www.google.com/maps/dir/?api=1&destination=${c.lat},${c.lon}' target='_blank'>Google Карты</a><a class='y' href='https://yandex.kz/maps/163/pavlodar/?text=${c.lat},${c.lon}' target='_blank'>Яндекс Карты</a><a class='d' href='https://2gis.kz/pavlodar/search/${c.lat},${c.lon}' target='_blank'>2ГИС - открыть</a><a class='g' href='/live/${c.id}' target='_blank'>🗺 Его маршрут с линией</a>`;
  markers[c.id]=L.marker([c.lat,c.lon]).addTo(map).bindPopup(popup);
 }
});}
upd();setInterval(upd,5000);</script></body></html>'''

@app.route('/online')
def online_map():
    return '''<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>На линии</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>body{margin:0}#map{height:100vh}.top{position:absolute;top:10px;left:50%;transform:translateX(-50%);z-index:1000;background:#00AA00;color:white;padding:10px 18px;border-radius:20px;box-shadow:0 2px 10px rgba(0,0,0,.3);font-family:Arial;font-weight:bold}
.leaflet-popup-content a{display:block;margin:4px 0;padding:8px 10px;border-radius:10px;color:white;text-decoration:none;text-align:center;font-weight:bold}
.g{background:#4285F4}.y{background:#FFCC00;color:black}.d{background:#00AA00}</style>
</head><body><div class="top" id="top">Курьеры на линии</div><div id="map"></div>
<script>var map=L.map('map').setView([52.287,76.967],12);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19}).addTo(map);var markers={};
async function upd(){let r=await fetch('/api/online');let data=await r.json();document.getElementById('top').innerText='🔵 На линии сейчас: '+data.length;data.forEach(c=>{
 if(markers[c.id]) markers[c.id].setLatLng([c.lat,c.lon]);
 else {
  let popup=`<b>${c.name} ONLINE</b><br><a class='g' href='https://www.google.com/maps/dir/?api=1&destination=${c.lat},${c.lon}' target='_blank'>Google</a><a class='y' href='https://yandex.kz/maps/?text=${c.lat},${c.lon}' target='_blank'>Яндекс</a><a class='d' href='https://2gis.kz/pavlodar/search/${c.lat},${c.lon}' target='_blank'>2ГИС - ВЕСТИ</a><a class='g' href='/live/${c.id}' target='_blank'>Маршрут линией</a>`;
  markers[c.id]=L.marker([c.lat,c.lon],{icon:L.icon({iconUrl:'https://maps.google.com/mapfiles/ms/icons/green-dot.png',iconSize:[32,32]})}).addTo(map).bindPopup(popup);
 }
});}
upd();setInterval(upd,5000);</script></body></html>'''

bot=Bot(token=BOT_TOKEN); dp=Dispatcher(storage=MemoryStorage())
live_started=set()

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
def courier_kb(): return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔴 Включить LIVE на 8 часов")],[KeyboardButton(text="🗺 Мой LIVE маршрут"),KeyboardButton(text="✅ Я доставил - фотоотчет")],[KeyboardButton(text="💰 Мой заработок")]],resize_keyboard=True)
def admin_kb(): return ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📦 Сделать заказ")],
    [KeyboardButton(text="🔵 Курьеры на линии"),KeyboardButton(text="🗺 Все на карте LIVE")],
    [KeyboardButton(text="👑 Все заказы"),KeyboardButton(text="👥 Курьеры")],
    [KeyboardButton(text="🆔 Мой ID")]],resize_keyboard=True)

def get_base_url(): return (os.environ.get("RENDER_EXTERNAL_URL") or "https://chas-pik-bot.onrender.com").rstrip("/")

@dp.message(F.text=="🚚 Стать курьером")
async def become_courier(m: Message):
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("INSERT OR IGNORE INTO couriers (user_id, username, full_name) VALUES (?,?,?)",(m.from_user.id, m.from_user.username, m.from_user.first_name))
    c.execute("UPDATE couriers SET username=?, full_name=? WHERE user_id=?",(m.from_user.username, m.from_user.first_name, m.from_user.id))
    conn.commit(); conn.close()
    await m.answer("✅ Ты курьер!", reply_markup=courier_kb())

@dp.message(F.text=="📞 Связаться с оператором")
async def contact_operator(m: Message): await m.answer("📞 @chas_pik_operator", reply_markup=client_kb())
@dp.message(F.text=="🛵 Связаться с курьером")
async def contact_courier(m: Message):
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT courier_id, courier_username FROM orders WHERE client_id=? AND status='taken' ORDER BY id DESC LIMIT 1",(m.from_user.id,))
    row=c.fetchone(); conn.close()
    if row and row[0]: await m.answer(f"Курьер: @{row[1]}" if row[1] else f"ID {row[0]}", reply_markup=client_kb())
    else: await m.answer("Нет активного", reply_markup=client_kb())

@dp.message(F.text=="💰 Мой заработок")
async def my_earn(m: Message):
    conn=sqlite3.connect(DB); cur=conn.cursor()
    cur.execute("SELECT price FROM orders WHERE courier_id=? AND status='done' AND date(created_time)=date('now','localtime')",(m.from_user.id,))
    total=sum(int(''.join(filter(str.isdigit, str(p[0]))) or 0) for p in cur.fetchall()); conn.close()
    await m.answer(f"💰 Сегодня: {total} тг", reply_markup=courier_kb())
@dp.message(F.text=="🆔 Мой ID")
async def my_id(m: Message): await m.answer(f"ID: {m.from_user.id}", reply_markup=admin_kb())
@dp.message(F.text=="🔴 Включить LIVE на 8 часов")
async def ask_live(m: Message): await m.answer("📎 -> Геопозиция -> Транслировать LIVE -> 8 часов", reply_markup=courier_kb())

@dp.edited_message(F.location)
@dp.message(F.location)
async def handle_live_loc(m: Message):
    uid=m.from_user.id; lat=m.location.latitude; lon=m.location.longitude
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("INSERT OR IGNORE INTO couriers (user_id, username, full_name) VALUES (?,?,?)",(uid, m.from_user.username, m.from_user.first_name))
    c.execute("UPDATE couriers SET last_lat=?, last_lon=?, last_time=CURRENT_TIMESTAMP, full_name=?, username=? WHERE user_id=?",(lat,lon,m.from_user.first_name,m.from_user.username,uid))
    c.execute("INSERT INTO tracks (courier_id, lat, lon, ts) VALUES (?,?,?,?)",(uid,lat,lon,datetime.now().isoformat()))
    c.execute("DELETE FROM tracks WHERE ts < datetime('now','-1 day')")
    c.execute("SELECT id, client_id, address_to FROM orders WHERE courier_id=? AND status='taken' ORDER BY id DESC LIMIT 1",(uid,)); row=c.fetchone()
    conn.commit(); conn.close()
    is_new = uid not in live_started
    if m.location.live_period and is_new:
        live_started.add(uid)
        base=get_base_url()
        if row:
            to_addr=row[2]; enc=urllib.parse.quote_plus(to_addr or "")
            kb=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📍 Google маршрут", url=f"https://www.google.com/maps/dir/{lat},{lon}/{enc}/")],
                [InlineKeyboardButton(text="🟡 Яндекс маршрут", url=f"https://yandex.kz/maps/163/pavlodar/?rtext={lat},{lon}~{enc}&rtt=auto")],
                [InlineKeyboardButton(text="🟢 2ГИС маршрут", url=f"https://2gis.kz/pavlodar/search/{enc}")],
                [InlineKeyboardButton(text="🗺 Наша карта с линией", url=f"{base}/live/{uid}")]
            ])
            await m.answer(f"✅ LIVE включен! До: {to_addr}", reply_markup=kb)
        else:
            await m.answer("✅ LIVE включен! Возьми заказ -> Мой LIVE маршрут", reply_markup=courier_kb())
        await m.answer("Меню:", reply_markup=courier_kb())
    if row and not is_new:
        try: await bot.send_location(row[1], lat, lon, live_period=m.location.live_period or 28800)
        except: pass
    if m.location.live_period is None:
        if uid in live_started: live_started.remove(uid)

@dp.message(F.text=="🗺 Мой LIVE маршрут")
async def show_my_route(m: Message):
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT address_to, address_from FROM orders WHERE courier_id=? AND status='taken' ORDER BY id DESC LIMIT 1",(m.from_user.id,))
    order_row=c.fetchone()
    c.execute("SELECT last_lat, last_lon FROM couriers WHERE user_id=?",(m.from_user.id,)); loc=c.fetchone()
    conn.close()
    base=get_base_url(); lat, lon = (loc[0], loc[1]) if loc and loc[0] else (None, None)
    if not order_row:
        await m.answer(f"Нет заказа. Трек: {base}/live/{m.from_user.id}", reply_markup=courier_kb()); return
    to_addr, from_addr=order_row; enc=urllib.parse.quote_plus(to_addr or "")
    if lat and lon:
        g=f"https://www.google.com/maps/dir/{lat},{lon}/{enc}/"
        y=f"https://yandex.kz/maps/163/pavlodar/?rtext={lat},{lon}~{enc}&rtt=auto"
        d=f"https://2gis.kz/pavlodar/directions/points/%7C{enc}?m={lon}%2C{lat}"
    else:
        g=f"https://www.google.com/maps/search/{enc}/"; y=f"https://yandex.kz/maps/163/pavlodar/?text={enc}"; d=f"https://2gis.kz/pavlodar/search/{enc}"
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📍 GOOGLE - ЛИНИЯ МАРШРУТА", url=g)],
        [InlineKeyboardButton(text="🟡 ЯНДЕКС - ЛИНИЯ МАРШРУТА", url=y)],
        [InlineKeyboardButton(text="🟢 2ГИС - ЛИНИЯ МАРШРУТА", url=d)],
        [InlineKeyboardButton(text="🗺 Наша LIVE карта с линией", url=f"{base}/live/{m.from_user.id}")]
    ])
    await m.answer(f"📦 Доставить: {to_addr}\nЖми навигатор - поедешь по линии:", reply_markup=kb)
    await m.answer("Меню:", reply_markup=courier_kb())

# === АДМИН: КУРЬЕРЫ НА ЛИНИИ С ПЕРЕХОДОМ В 2ГИС ===
@dp.message(F.text=="🔵 Курьеры на линии")
async def online_couriers(m: Message):
    if m.from_user.id!=ADMIN_ID: return
    base=get_base_url()
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT user_id, full_name, username, last_lat, last_lon FROM couriers WHERE last_lat IS NOT NULL AND last_time > datetime('now','-30 minutes')")
    rows=c.fetchall(); conn.close()
    if not rows: await m.answer("🔵 Сейчас на линии никого", reply_markup=admin_kb()); return
    await m.answer(f"🔵 На линии: {len(rows)}\nКарта: {base}/online\nВсе маркеры - клик ведет в 2ГИС/Google/Яндекс:", reply_markup=admin_kb())
    for uid,fname,uname,lat,lon in rows:
        name=f"@{uname}" if uname else fname
        g=f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}"
        y=f"https://yandex.kz/maps/163/pavlodar/?text={lat},{lon}"
        d=f"https://2gis.kz/pavlodar/search/{lat},{lon}"
        kb=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"🟢 2ГИС - вести {name}", url=d)],
            [InlineKeyboardButton(text="📍 Google", url=g), InlineKeyboardButton(text="🟡 Яндекс", url=y)],
            [InlineKeyboardButton(text="🗺 Его маршрут линией", url=f"{base}/live/{uid}")]
        ])
        try:
            await bot.send_location(m.chat.id, lat, lon)
            await m.answer(f"{name} - {lat},{lon}", reply_markup=kb)
        except: pass
    await m.answer(f"Общая карта на линии: {base}/online\nВсе на карте: {base}/map", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔵 Открыть карту НА ЛИНИИ с 2ГИС", url=f"{base}/online")],
        [InlineKeyboardButton(text="🗺 Открыть карту ВСЕХ с 2ГИС", url=f"{base}/map")]
    ]))

# === АДМИН: ВСЕ КУРЬЕРЫ НА КАРТЕ РЕАЛЬНОГО ВРЕМЕНИ С 2ГИС ===
@dp.message(F.text=="🗺 Все на карте LIVE")
async def all_couriers_map(m: Message):
    if m.from_user.id!=ADMIN_ID: return
    base=get_base_url()
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT user_id, full_name, username, last_lat, last_lon FROM couriers WHERE last_lat IS NOT NULL")
    rows=c.fetchall(); conn.close()
    if not rows: await m.answer("Нет координат", reply_markup=admin_kb()); return
    await m.answer(f"🗺 Все курьеры LIVE: {len(rows)}\nКарта реального времени: {base}/map\nКаждый клик на маркере = переход в 2ГИС/Google/Яндекс", reply_markup=admin_kb())
    for uid,fname,uname,lat,lon in rows[:15]: # лимит 15 чтобы не спамить
        name=f"@{uname}" if uname else fname
        g=f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}"
        y=f"https://yandex.kz/maps/163/pavlodar/?text={lat},{lon}"
        d=f"https://2gis.kz/pavlodar/search/{lat},{lon}"
        kb=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"🟢 2ГИС {name}", url=d)],
            [InlineKeyboardButton(text="📍 Google", url=g), InlineKeyboardButton(text="🟡 Яндекс", url=y)],
            [InlineKeyboardButton(text="Маршрут линией", url=f"{base}/live/{uid}")]
        ])
        try:
            await bot.send_location(m.chat.id, lat, lon)
            await m.answer(f"{name}", reply_markup=kb)
        except: pass
    await m.answer(f"🗺 Открой общую карту:\n{base}/map - там все курьеры LIVE, клик по маркеру = переход в 2ГИС", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗺 ОТКРЫТЬ КАРТУ ВСЕХ С 2ГИС", url=f"{base}/map")],
        [InlineKeyboardButton(text="🔵 ОТКРЫТЬ КАРТУ НА ЛИНИИ С 2ГИС", url=f"{base}/online")]
    ]))

@dp.message(F.text=="📦 Сделать заказ")
async def order_start(m: Message, state: FSMContext):
    await state.set_state(OrderForm.from_address); await m.answer("Откуда?")
@dp.message(OrderForm.from_address)
async def order_from(m: Message, state: FSMContext):
    await state.update_data(from_addr=m.text); await state.set_state(OrderForm.to_address); await m.answer("Куда?")
@dp.message(OrderForm.to_address)
async def order_to(m: Message, state: FSMContext):
    await state.update_data(to_addr=m.text); await state.set_state(OrderForm.what); await m.answer("Что?")
@dp.message(OrderForm.what)
async def order_what(m: Message, state: FSMContext):
    await state.update_data(what=m.text); await state.set_state(OrderForm.note); await m.answer("Подъезд?")
@dp.message(OrderForm.note)
async def order_note(m: Message, state: FSMContext):
    await state.update_data(note=m.text); await state.set_state(OrderForm.price); await m.answer("Цена?")
@dp.message(OrderForm.price)
async def order_price(m: Message, state: FSMContext):
    data=await state.get_data(); price=m.text.replace("тг","").strip()
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("INSERT INTO orders (client_id, client_username, client_name, address_from, address_to, what, note, price, created_time) VALUES (?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)",(m.from_user.id,m.from_user.username,m.from_user.first_name,data.get("from_addr"),data.get("to_addr"),data.get("what"),data.get("note"),price))
    oid=c.lastrowid; c.execute("SELECT user_id FROM couriers"); cours=c.fetchall(); conn.commit(); conn.close(); await state.clear()
    await m.answer(f"✅ Заказ #{oid} принят!", reply_markup=admin_kb() if m.from_user.id==ADMIN_ID else client_kb())
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
    c.execute("UPDATE orders SET status='taken', courier_id=?, courier_username=?, courier_name=? WHERE id=?",(cq.from_user.id,cq.from_user.username,cq.from_user.first_name,oid)); conn.commit()
    c.execute("SELECT client_id, address_to FROM orders WHERE id=?",(oid,)); client, to_addr=c.fetchone(); conn.close()
    enc=urllib.parse.quote_plus(to_addr or "")
    conn2=sqlite3.connect(DB); c2=conn2.cursor(); c2.execute("SELECT last_lat, last_lon FROM couriers WHERE user_id=?",(cq.from_user.id,)); loc=c2.fetchone(); conn2.close()
    lat,lon=(loc[0],loc[1]) if loc and loc[0] else (None,None)
    if lat and lon:
        g=f"https://www.google.com/maps/dir/{lat},{lon}/{enc}/"; y=f"https://yandex.kz/maps/163/pavlodar/?rtext={lat},{lon}~{enc}&rtt=auto"; d=f"https://2gis.kz/pavlodar/search/{enc}"
    else:
        g=f"https://www.google.com/maps/search/{enc}/"; y=f"https://yandex.kz/maps/163/pavlodar/?text={enc}"; d=f"https://2gis.kz/pavlodar/search/{enc}"
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📍 Google линия", url=g)],
        [InlineKeyboardButton(text="🟡 Яндекс линия", url=y)],
        [InlineKeyboardButton(text="🟢 2ГИС линия", url=d)]
    ])
    await cq.message.edit_text(f"✅ ВЗЯЛ #{oid}\n{to_addr}")
    await bot.send_message(cq.from_user.id, "Навигация:", reply_markup=kb)
    await cq.answer("Взял!")
    try: await bot.send_message(client, f"✅ Курьер взял #{oid}")
    except: pass

@dp.message(F.text=="✅ Я доставил - фотоотчет")
async def ask_photo(m: Message, state: FSMContext):
    await state.set_state(PhotoReport.waiting_photo); await m.answer("Скинь фото", reply_markup=courier_kb())
@dp.message(PhotoReport.waiting_photo, F.photo)
async def handle_photo(m: Message, state: FSMContext):
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT id, client_id FROM orders WHERE courier_id=? AND status='taken' ORDER BY id DESC LIMIT 1",(m.from_user.id,)); row=c.fetchone()
    if not row: await state.clear(); conn.close(); return
    oid,cid=row; c.execute("UPDATE orders SET status='done' WHERE id=?",(oid,)); conn.commit(); conn.close(); await state.clear()
    await m.answer(f"✅ #{oid} закрыт!", reply_markup=courier_kb())
    try: await bot.send_message(cid, f"✅ #{oid} доставлен!")
    except: pass

@dp.message(F.text=="👑 Все заказы")
async def all_orders(m: Message):
    if m.from_user.id!=ADMIN_ID: return
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT id, address_from, address_to, price, status FROM orders ORDER BY id DESC LIMIT 10"); rows=c.fetchall(); conn.close()
    txt="\n".join([f"#{r[0]} {r[1]}->{r[2]} {r[3]}тг [{r[4]}]" for r in rows])
    await m.answer(txt, reply_markup=admin_kb())

@dp.message(F.text=="👥 Курьеры")
async def list_c(m: Message):
    conn=sqlite3.connect(DB); c=conn.cursor(); c.execute("SELECT user_id, username, full_name FROM couriers"); rows=c.fetchall(); conn.close()
    await m.answer(f"Курьеров: {len(rows)}", reply_markup=admin_kb())

@dp.message(Command("start"))
async def start_cmd(m: Message, state: FSMContext):
    await state.clear(); init_db()
    if m.from_user.id==ADMIN_ID: await m.answer("АДМИН", reply_markup=admin_kb())
    else:
        conn=sqlite3.connect(DB); c=conn.cursor(); c.execute("SELECT user_id FROM couriers WHERE user_id=?",(m.from_user.id,)); is_c=c.fetchone(); conn.close()
        if is_c: await m.answer("Привет курьер!", reply_markup=courier_kb())
        else: await m.answer("ЧАС ПИК", reply_markup=client_kb())

def run_flask(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
async def run_bot(): init_db(); await dp.start_polling(bot)
if __name__=="__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(run_bot())
