import os, sqlite3, time, secrets, string, hmac
from flask import Flask, request, session, jsonify, send_from_directory, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import timedelta

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cambia-esta-clave")
app.permanent_session_lifetime = timedelta(days=30)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_MB", "500")) * 1024 * 1024

# ====== CONFIG ======
ADMIN_NAME = os.environ.get("ADMIN_NAME", "SKYWEEB3.0")
ADMIN_PHONE = os.environ.get("ADMIN_PHONE", "2321207765")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "")   # opcional: si la pones en Render, también funciona
# Aquí solo va el hash (código cifrado), la contraseña real no se puede leer
ADMIN_HASH = "pbkdf2:sha256:1000000$BkCdYsZL8J2AQKNn$e76bfe76e17afa37089f9ae1b81ba7b74705909b866c9bffc7414a61f0c62bae"
WHATSAPP_NUM = "523342699274"
GROUP_LINK = "https://chat.whatsapp.com/GdhRsNw3GdWJHzQrDtJRUV?s=cl&p=a&iam=2"
# ====================

DB = os.environ.get("DB_PATH", "skyweeb.db")
UP = os.environ.get("UPLOAD_DIR", "uploads")
os.makedirs(UP, exist_ok=True)
VID, IMG = {"mp4", "webm", "mov", "mkv"}, {"png", "jpg", "jpeg", "gif", "webp"}
APPX = {"apk", "xapk", "zip", "rar", "7z", "exe", "msi", "ipa"}
T = {"posts": "media", "tutorials": "url", "apps": "url", "projects": "url"}
PRJ = APPX | {"html", "htm"}

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init():
    c = db()
    nuevo = not c.execute("SELECT 1 FROM sqlite_master WHERE name='projects'").fetchone()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT, phone TEXT UNIQUE, ts REAL);
    CREATE TABLE IF NOT EXISTS posts(id INTEGER PRIMARY KEY, kind TEXT, title TEXT, body TEXT, media TEXT, ts REAL);
    CREATE TABLE IF NOT EXISTS tutorials(id INTEGER PRIMARY KEY, title TEXT, url TEXT, ts REAL);
    CREATE TABLE IF NOT EXISTS apps(id INTEGER PRIMARY KEY, name TEXT, info TEXT, url TEXT, ts REAL);
    CREATE TABLE IF NOT EXISTS projects(id INTEGER PRIMARY KEY, name TEXT, info TEXT, url TEXT, ts REAL);
    """)
    if nuevo:
        c.execute("INSERT INTO projects(name,info,url,ts) VALUES(?,?,?,?)",
                  ("Consola de prueba", "", "https://cobrahsr.onrender.com/", time.time()))
    try:
        c.execute("ALTER TABLE users ADD COLUMN pw TEXT")
    except sqlite3.OperationalError:
        pass
    if not c.execute("SELECT 1 FROM tutorials LIMIT 1").fetchone():
        now = time.time()
        c.execute("INSERT INTO tutorials(title,url,ts) VALUES(?,?,?)",
                  ("Mi canal de YouTube", "https://youtube.com/@hsrramses?si=p5n26GAy6x3KFYvV", now))
        c.execute("INSERT INTO tutorials(title,url,ts) VALUES(?,?,?)",
                  ("Mi TikTok", "https://www.tiktok.com/@hsrramses", now + 1))
    c.commit(); c.close()
init()

def digits(s):
    return "".join(ch for ch in (s or "") if ch.isdigit())[:15]

def okurl(u):
    u = (u or "").strip()
    return u if u.startswith(("http://", "https://")) else ""

def save(f, allowed):
    if not f or not f.filename:
        return ""
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in allowed:
        raise ValueError("Tipo de archivo no permitido (.%s)." % ext)
    name = secrets.token_hex(6) + "_" + (secure_filename(f.filename) or "archivo." + ext)
    f.save(os.path.join(UP, name))
    return "/files/" + name

def rmfile(p):
    if p and p.startswith("/files/"):
        try:
            os.remove(os.path.join(UP, os.path.basename(p)))
        except OSError:
            pass

FAILS = {}
def who():
    return (request.headers.get("X-Forwarded-For") or request.remote_addr or "?").split(",")[0].strip()

def blocked():
    now, ip = time.time(), who()
    FAILS[ip] = [t for t in FAILS.get(ip, []) if now - t < 600]
    return len(FAILS[ip]) >= 10

def genpw():
    l = [secrets.choice(string.digits) for _ in range(3)] + [secrets.choice(string.ascii_letters) for _ in range(4)]
    secrets.SystemRandom().shuffle(l)
    return "".join(l)

def need_admin():
    if not session.get("admin"):
        abort(403)

@app.errorhandler(403)
def e403(e):
    return jsonify(ok=False, msg="Solo el administrador puede hacer eso."), 403

@app.errorhandler(413)
def e413(e):
    return jsonify(ok=False, msg="El archivo es demasiado grande."), 413

@app.get("/files/<path:name>")
def files(name):
    return send_from_directory(UP, name)

@app.get("/api/data")
def data():
    c = db()
    out = {t: [dict(r) for r in c.execute(f"SELECT * FROM {t} ORDER BY ts DESC")] for t in T}
    c.close()
    out["group"], out["wa"] = GROUP_LINK, WHATSAPP_NUM
    return jsonify(out)

@app.get("/api/me")
def me():
    return jsonify(logged=bool(session.get("name")), name=session.get("name", ""), admin=bool(session.get("admin")))

@app.post("/api/register")
def register():
    j = request.get_json(silent=True) or {}
    name, phone = (j.get("name") or "").strip()[:60], digits(j.get("phone"))
    if not name or len(phone) < 7:
        return jsonify(ok=False, msg="Escribe tu nombre y un número válido."), 400
    c = db()
    row = c.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    if row and row["pw"]:
        c.close()
        return jsonify(ok=False, msg="Ese número ya está registrado. Inicia sesión."), 400
    pw = genpw()
    if row:
        c.execute("UPDATE users SET name=?, pw=? WHERE id=?", (name, generate_password_hash(pw), row["id"]))
    else:
        c.execute("INSERT INTO users(name,phone,pw,ts) VALUES(?,?,?,?)", (name, phone, generate_password_hash(pw), time.time()))
    c.commit(); c.close()
    session.permanent = True
    session["name"], session["admin"], session["phone"] = name, False, phone
    return jsonify(ok=True, name=name, password=pw)

@app.post("/api/login")
def login():
    if blocked():
        return jsonify(ok=False, msg="Demasiados intentos. Espera 10 minutos."), 429
    j = request.get_json(silent=True) or {}
    name, phone, pw = (j.get("name") or "").strip(), digits(j.get("phone")), j.get("password") or ""
    if name.lower() == ADMIN_NAME.lower() and phone == digits(ADMIN_PHONE):
        if check_password_hash(ADMIN_HASH, pw) or (ADMIN_PASS and hmac.compare_digest(pw.encode(), ADMIN_PASS.encode())):
            session.permanent = True
            session["name"], session["admin"] = ADMIN_NAME, True
            return jsonify(ok=True, admin=True)
        FAILS.setdefault(who(), []).append(time.time())
        return jsonify(ok=False, msg="Datos incorrectos."), 400
    c = db()
    row = c.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    c.close()
    if row and row["pw"] and check_password_hash(row["pw"], pw):
        session.permanent = True
        session["name"], session["admin"], session["phone"] = row["name"], False, phone
        return jsonify(ok=True, admin=False)
    FAILS.setdefault(who(), []).append(time.time())
    return jsonify(ok=False, msg="Número o contraseña incorrectos."), 400

@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)

@app.get("/api/users")
def users():
    need_admin()
    c = db()
    rows = [dict(id=r["id"], name=r["name"], phone=r["phone"],
                 fecha=time.strftime("%d/%m/%Y %H:%M", time.localtime(r["ts"] or 0)))
            for r in c.execute("SELECT * FROM users ORDER BY ts DESC")]
    c.close()
    return jsonify(rows)

@app.post("/api/resetpw/<int:i>")
def resetpw(i):
    need_admin()
    pw = genpw()
    c = db()
    c.execute("UPDATE users SET pw=? WHERE id=?", (generate_password_hash(pw), i))
    c.commit(); c.close()
    return jsonify(ok=True, password=pw)

@app.post("/api/add/<t>")
def add(t):
    need_admin()
    if t not in T:
        abort(404)
    f, now = request.form, time.time()
    try:
        if t == "posts":
            title = (f.get("title") or "").strip()
            if not title:
                raise ValueError("Falta el título.")
            m = save(request.files.get("file"), VID | IMG) or okurl(f.get("link"))
            sql, args = "INSERT INTO posts(kind,title,body,media,ts) VALUES(?,?,?,?,?)", (f.get("kind", "post"), title, f.get("body", ""), m, now)
        elif t == "tutorials":
            title = (f.get("title") or "").strip()
            u = save(request.files.get("file"), VID) or okurl(f.get("link"))
            if not title or not u:
                raise ValueError("Pon título y un video o un link.")
            sql, args = "INSERT INTO tutorials(title,url,ts) VALUES(?,?,?)", (title, u, now)
        else:
            name = (f.get("name") or "").strip()
            u = save(request.files.get("file"), PRJ if t == "projects" else APPX) or okurl(f.get("link"))
            if not name or not u:
                raise ValueError("Pon nombre y un archivo o un link.")
            sql, args = f"INSERT INTO {t}(name,info,url,ts) VALUES(?,?,?,?)", (name, f.get("info", ""), u, now)
    except ValueError as e:
        return jsonify(ok=False, msg=str(e)), 400
    c = db(); c.execute(sql, args); c.commit(); c.close()
    return jsonify(ok=True)

@app.post("/api/del/<t>/<int:i>")
def delete(t, i):
    need_admin()
    if t not in T:
        abort(404)
    c = db()
    r = c.execute(f"SELECT {T[t]} AS f FROM {t} WHERE id=?", (i,)).fetchone()
    if r:
        rmfile(r["f"])
        c.execute(f"DELETE FROM {t} WHERE id=?", (i,))
        c.commit()
    c.close()
    return jsonify(ok=True)

PAGE = r"""
<!doctype html><html lang=es><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>SKY WEEB</title>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@500;800&family=Nunito:wght@400;700&display=swap" rel=stylesheet>
<style>
:root{--acc:#facc15;--acc2:#f59e0b;--on:#15120a;--glow:250,204,21;--bg:#f6f4ee;--card:#fff;--tx:#1a1a1f;--mut:#6b6b76;--ln:#e6e2d6;--inp:#f6f4ee}
:root[data-t=dark]{--bg:#08080c;--card:rgba(20,20,26,.72);--tx:#f5f5f7;--mut:#a1a1aa;--ln:rgba(255,255,255,.1);--inp:rgba(0,0,0,.4)}
:root[data-c=morado]{--acc:#8b5cf6;--acc2:#6d28d9;--on:#fff;--glow:139,92,246}
:root[data-c=azul]{--acc:#3b82f6;--acc2:#2563eb;--on:#fff;--glow:59,130,246}
:root[data-c=verde]{--acc:#10b981;--acc2:#059669;--on:#fff;--glow:16,185,129}
:root[data-t=dark] body{background:radial-gradient(900px 420px at 90% -5%,rgba(var(--glow),.30),transparent 62%),radial-gradient(700px 460px at -15% 45%,rgba(var(--glow),.16),transparent 60%),conic-gradient(from 210deg at 75% 95%,#08080c,#17120a,#08080c 38%,#241a08 58%,#08080c);background-attachment:fixed}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:16px/1.5 Nunito,sans-serif}
h1,h2,h3{font-family:'Bricolage Grotesque',sans-serif;margin:0}
header{position:sticky;top:0;z-index:5;display:flex;align-items:center;gap:12px;padding:12px 16px;background:var(--card);border-bottom:1px solid var(--ln);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px)}
#burger{width:44px;height:44px;border:0;border-radius:12px;background:linear-gradient(180deg,var(--acc),var(--acc2));color:var(--on);font-size:26px;cursor:pointer;box-shadow:0 4px 16px rgba(var(--glow),.35)}
.logo{font:800 22px 'Bricolage Grotesque';letter-spacing:.5px}.logo b{color:var(--acc)}
nav{position:fixed;inset:0 auto 0 0;width:260px;max-width:80vw;background:var(--card);border-right:1px solid var(--ln);padding:72px 12px 12px;transform:translateX(-100%);transition:transform .25s;z-index:4}
nav.open{transform:none}#veil{position:fixed;inset:0;background:#0006;display:none;z-index:3}#veil.on{display:block}
nav a{display:block;padding:12px 14px;margin:4px 0;border-radius:12px;color:var(--tx);text-decoration:none;font-weight:700}
nav a.on,nav a:hover{background:linear-gradient(180deg,var(--acc),var(--acc2));color:var(--on)}
main{max-width:720px;margin:auto;padding:16px}section{display:none}section.on{display:block}
.card{background:var(--card);border:1px solid var(--ln);border-radius:16px;padding:14px;margin:12px 0;backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px)}
.card img,.card video{width:100%;border-radius:12px;margin-top:8px}.tag{color:var(--acc);font-weight:700;font-size:14px}
.btn{display:inline-block;padding:12px 20px;border:0;border-radius:12px;background:linear-gradient(180deg,var(--acc),var(--acc2));color:var(--on);font:800 16px Nunito;text-decoration:none;cursor:pointer;box-shadow:0 6px 20px rgba(var(--glow),.35);transition:transform .15s,filter .15s}.btn:hover{filter:brightness(1.08);transform:translateY(-1px)}
.btn.del{background:#d33;color:#fff;box-shadow:none;padding:7px 12px;font-size:14px;margin-top:8px}.btn.ghost{background:none;color:var(--acc);border:2px solid var(--acc);box-shadow:none}
input,select,textarea{width:100%;padding:12px;margin:6px 0;border-radius:12px;border:1px solid var(--ln);background:var(--inp);color:var(--tx);font:inherit}
.mut{color:var(--mut)}.row{display:flex;gap:10px;flex-wrap:wrap;margin:8px 0}
.dot{width:38px;height:38px;border-radius:50%;border:3px solid transparent;cursor:pointer}.dot.on{border-color:var(--tx)}
#chat{height:300px;overflow:auto;display:flex;flex-direction:column;gap:8px}
.m{padding:9px 13px;border-radius:14px;max-width:85%}.bot{background:var(--inp);align-self:flex-start}.me{background:var(--acc);color:var(--on);align-self:flex-end}
.q{padding:8px 12px;border-radius:20px;border:1px solid var(--acc);background:none;color:var(--acc);font:700 14px Nunito;cursor:pointer}
.adm,.adm-l{display:none}body.isadm .adm{display:block}body.isadm .adm-l{display:block}
.pw{font:800 30px 'Bricolage Grotesque';letter-spacing:3px;text-align:center;padding:14px;border:2px dashed var(--acc);border-radius:14px;margin:10px 0;user-select:all}
.glass{padding:28px 22px;background:linear-gradient(145deg,rgba(255,255,255,.10),rgba(255,255,255,.03));background-color:var(--card);border:1px solid rgba(255,255,255,.12);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);clip-path:polygon(30px 0,100% 0,100% calc(100% - 30px),calc(100% - 30px) 100%,0 100%,0 30px);box-shadow:0 24px 60px #0007;margin:14px 0}
.glass h2{font-size:30px;line-height:1.1}.glass h2 span{color:var(--acc)}.glass p{margin:6px 0}
.glass label{display:block;margin-top:12px;font-weight:700;font-size:14px}
.fld{position:relative}.eye{position:absolute;right:6px;top:10px;border:0;background:none;color:var(--mut);font-size:19px;cursor:pointer;padding:4px 8px}
.btn.wide{width:100%;margin-top:16px;text-align:center}.c{text-align:center}.c a{color:var(--acc);font-weight:800}
:focus-visible{outline:3px solid var(--acc);outline-offset:2px}
</style></head><body>
<header><button id=burger aria-label="Menú">&#9776;</button><div class=logo>SKY <b>WEEB</b></div></header>
<div id=veil></div>
<nav id=nav>
<a href="#home">Home</a><a href="#login">Login</a><a href="#config">Configuración</a><a href="#comunidad">Comunidad</a>
<a href="#tutoriales">Tutoriales</a><a href="#apps">Apps</a><a href="#proyectos">Proyectos</a><a href="#ayuda">Ayuda</a><a href="#panel" class=adm-l>Usuarios</a></nav>
<main>
<section id=home><h2>Novedades</h2>
<form class="card adm" data-t=posts><h3>Nueva publicación</h3>
<select name=kind><option value=post>Publicación</option><option value=update>Actualización</option><option value=reel>Reel</option></select>
<input name=title placeholder="Título" required><textarea name=body rows=3 placeholder="Texto"></textarea>
<input type=file name=file accept="image/*,video/*"><input name=link placeholder="o pega un link de imagen o video">
<button class=btn>Publicar</button><p class=mut></p></form>
<div id=posts></div></section>

<section id=login><h2>SKY WEEB</h2><div id=lbox></div></section>

<section id=config><h2>Configuración</h2>
<div class=card><h3>Color de botones e icono</h3><div class=row>
<div class=dot data-c=dorado style="background:#facc15" title=Dorado></div>
<div class=dot data-c=morado style="background:#8b5cf6" title=Morado></div>
<div class=dot data-c=azul style="background:#3b82f6" title=Azul></div>
<div class=dot data-c=verde style="background:#10b981" title=Verde></div></div></div>
<div class=card><h3>Modo</h3><div class=row><button class=btn data-t=light>Claro</button><button class=btn data-t=dark>Oscuro</button></div></div></section>

<section id=comunidad><h2>Comunidad</h2><div class=card><p>Únete al grupo de SkyWeeb en WhatsApp.</p><a class=btn id=grp target=_blank rel=noopener>Unirme al grupo</a></div></section>

<section id=tutoriales><h2>Tutoriales</h2>
<form class="card adm" data-t=tutorials><h3>Nuevo tutorial</h3>
<input name=title placeholder="Título" required><input type=file name=file accept="video/*"><input name=link placeholder="o pega un link (YouTube, TikTok...)">
<button class=btn>Agregar</button><p class=mut></p></form>
<div id=tuts></div></section>

<section id=apps><h2>Apps</h2>
<form class="card adm" data-t=apps><h3>Nueva app</h3>
<input name=name placeholder="Nombre" required><input name=info placeholder="Descripción corta">
<input type=file name=file accept=".apk,.xapk,.zip,.rar,.7z,.exe,.msi,.ipa"><input name=link placeholder="o pega un link de descarga">
<button class=btn>Agregar</button><p class=mut></p></form>
<div id=applist></div></section>

<section id=proyectos><h2>Proyectos</h2>
<form class="card adm" data-t=projects><h3>Nuevo proyecto</h3>
<input name=name placeholder="Nombre del botón" required><input name=info placeholder="Descripción corta (opcional)">
<input type=file name=file accept=".html,.htm,.apk,.xapk,.zip,.rar,.7z,.exe,.msi,.ipa"><input name=link placeholder="o pega el link de la página o app">
<button class=btn>Agregar</button><p class=mut></p></form>
<div id=projlist></div></section>

<section id=ayuda><h2>Ayuda</h2><div class=card><div id=chat></div><div class=row id=qs></div></div>
<a class=btn id=wa target=_blank rel=noopener>Escribirme por WhatsApp</a></section>

<section id=panel><h2>Usuarios dentro</h2><div id=ulist></div></section>
</main>
<script>
const $=s=>document.querySelector(s),R=document.documentElement;
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const ls={get(k,d){try{return localStorage.getItem(k)||d}catch(e){return d}},set(k,v){try{localStorage.setItem(k,v)}catch(e){}}};
const J=(u,b)=>fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})}).then(r=>r.json());
let ME={},D={},WA='';
function setC(c){R.dataset.c=c;ls.set('c',c);document.querySelectorAll('.dot').forEach(d=>d.classList.toggle('on',d.dataset.c==c))}
function setT(t){R.dataset.t=t;ls.set('t',t)}
setC(ls.get('c','dorado'));setT(ls.get('t','dark'));
document.querySelectorAll('.dot').forEach(d=>d.onclick=()=>setC(d.dataset.c));
document.querySelectorAll('button[data-t]').forEach(b=>b.onclick=()=>setT(b.dataset.t));
const nav=$('#nav'),veil=$('#veil');
function menu(o){nav.classList.toggle('open',o);veil.classList.toggle('on',o)}
$('#burger').onclick=()=>menu(!nav.classList.contains('open'));veil.onclick=()=>menu(false);
function route(){const h=(location.hash||'#home').slice(1);
document.querySelectorAll('section').forEach(s=>s.classList.toggle('on',s.id==h));
document.querySelectorAll('nav a').forEach(a=>a.classList.toggle('on',a.hash=='#'+h));menu(false);scrollTo(0,0);
if(h=='panel'&&ME.admin)loadUsers()}
addEventListener('hashchange',route);

const L={post:'Publicación',update:'Actualización',reel:'Reel'};
const loc=u=>u&&u.startsWith('/files/');
const empty=t=>`<p class=mut>${t}</p>`;
const delb=(t,id)=>ME.admin?`<button class="btn del" onclick="del('${t}',${id})">Borrar</button>`:'';
function media(u){if(!u)return'';return /\.(mp4|webm|mov|mkv)$/i.test(u)?`<video src="${esc(u)}" controls playsinline preload=metadata></video>`:
/\.(png|jpe?g|gif|webp)$/i.test(u)?`<img src="${esc(u)}" alt="">`:`<p><a class=btn href="${esc(u)}" target=_blank rel=noopener>Ver</a></p>`}
function draw(){
$('#posts').innerHTML=(D.posts||[]).map(p=>`<div class=card><span class=tag>${L[p.kind]||'Publicación'}</span><h3>${esc(p.title)}</h3><p>${esc(p.body)}</p>${media(p.media)}${delb('posts',p.id)}</div>`).join('')||empty('Aún no hay publicaciones.');
$('#tuts').innerHTML=(D.tutorials||[]).map(t=>`<div class=card><h3>${esc(t.title)}</h3>${loc(t.url)?media(t.url):`<p><a class=btn href="${esc(t.url)}" target=_blank rel=noopener>Ver video</a></p>`}${delb('tutorials',t.id)}</div>`).join('')||empty('Aún no hay tutoriales.');
$('#applist').innerHTML=(D.apps||[]).map(a=>`<div class=card><h3>${esc(a.name)}</h3><p class=mut>${esc(a.info)}</p><a class=btn href="${esc(a.url)}" ${loc(a.url)?'download':'target=_blank rel=noopener'}>Descargar</a><br>${delb('apps',a.id)}</div>`).join('')||empty('Aún no hay apps.');
$('#projlist').innerHTML=(D.projects||[]).map(p=>`<div class=card>${p.info?`<p class=mut>${esc(p.info)}</p>`:''}<a class=btn href="${esc(p.url)}" ${loc(p.url)&&!/\.html?$/i.test(p.url)?'download':'target=_blank rel=noopener'}>${esc(p.name)}</a><br>${delb('projects',p.id)}</div>`).join('')||empty('Aún no hay proyectos.')}
async function loadData(){D=await fetch('/api/data').then(r=>r.json());$('#grp').href=D.group;$('#wa').href='https://wa.me/'+D.wa;WA=D.wa;draw()}
async function del(t,id){if(!confirm('¿Borrar esto?'))return;await J(`/api/del/${t}/${id}`);loadData()}
async function loadUsers(){const r=await fetch('/api/users');if(!r.ok)return;const u=await r.json();
document.querySelector('.adm-l').textContent='Usuarios ('+u.length+')';
$('#ulist').innerHTML=`<div class=card><h3>Total registrados: ${u.length}</h3></div>`+u.map(x=>`<div class=card><b>${esc(x.name)}</b> · ${esc(x.phone)}<br><span class=mut>${esc(x.fecha)}</span><br>
<button class="btn ghost" style="margin-top:8px" onclick="resetpw(${x.id})">Nueva contraseña</button><div id=rp${x.id}></div></div>`).join('')||empty('Aún nadie.')}
async function resetpw(id){const j=await J('/api/resetpw/'+id);$('#rp'+id).innerHTML=j.ok?`<div class=pw>${esc(j.password)}</div><p class=mut>Pásasela a esa persona.</p>`:''}

document.querySelectorAll('form.adm').forEach(f=>f.onsubmit=e=>{e.preventDefault();
const msg=f.querySelector('p.mut'),x=new XMLHttpRequest();x.open('POST','/api/add/'+f.dataset.t);
x.upload.onprogress=ev=>{if(ev.lengthComputable)msg.textContent='Subiendo '+Math.round(ev.loaded/ev.total*100)+'%'};
x.onload=()=>{let j={};try{j=JSON.parse(x.responseText)}catch(_){}
if(j.ok){msg.textContent='Listo.';f.reset();loadData()}else msg.textContent=j.msg||'Error al subir.'};
x.onerror=()=>msg.textContent='Se cortó la conexión.';x.send(new FormData(f));msg.textContent='Subiendo 0%'});

function loginView(tab){
if(ME.logged){$('#lbox').innerHTML=`<div class=glass><h2>Hola, <span>${esc(ME.name)}</span></h2><p class=mut>${ME.admin?'Eres administrador: ya puedes subir y borrar contenido.':'Tu sesión está iniciada.'}</p><button class="btn wide" id=out>Cerrar sesión</button></div>`;
$('#out').onclick=async()=>{await J('/api/logout');await boot()};return}
const up=tab=='up';
$('#lbox').innerHTML=`<div class=glass><h2>${up?'Crear <span>cuenta</span>':'Bienvenido <span>de vuelta</span>'}</h2>
<p class=mut>${up?'Únete hoy a SKY WEEB.':'Ingresa tus datos para acceder a tu cuenta.'}</p>
<label for=a1>Nombre</label><div class=fld><input id=a1 placeholder="Tu nombre" autocomplete=${up?'name':'username'}></div>
<label for=a2>Número</label><div class=fld><input id=a2 placeholder="Tu número" inputmode=tel autocomplete=tel></div>
${up?'':`<label for=a3>Contraseña</label><div class=fld><input id=a3 type=password placeholder="••••••••" autocomplete=current-password><button type=button class=eye id=eye aria-label="Ver contraseña">&#128065;</button></div>`}
<button class="btn wide" id=go>${up?'Crear cuenta':'Iniciar sesión'} &rarr;</button><p id=msg class=mut></p>
<p class="mut c">${up?'¿Ya tienes cuenta? <a href="#" id=sw>Inicia sesión</a>':'¿No tienes cuenta? <a href="#" id=sw>Regístrate</a>'}</p></div>`;
$('#sw').onclick=e=>{e.preventDefault();loginView(up?'in':'up')};
if(!up)$('#eye').onclick=()=>{const i=$('#a3');i.type=i.type=='password'?'text':'password'};
$('#go').onclick=async()=>{const m=$('#msg');
if(!up){const j=await J('/api/login',{name:$('#a1').value,phone:$('#a2').value,password:$('#a3').value});
if(j.ok)await boot();else m.textContent=j.msg}
else{const j=await J('/api/register',{name:$('#a1').value,phone:$('#a2').value});
if(j.ok){await boot();$('#lbox').insertAdjacentHTML('afterbegin',`<div class=glass><h2>¡Registro <span>listo</span>, ${esc(j.name)}!</h2><p>Tu contraseña es:</p><div class=pw>${esc(j.password)}</div><p class=mut>Guárdala o toma captura. No se vuelve a mostrar. Si la pierdes, pídeme una nueva por WhatsApp.</p></div>`)}else m.textContent=j.msg}}}
async function boot(){ME=await fetch('/api/me').then(r=>r.json());document.body.classList.toggle('isadm',!!ME.admin);loginView('in');await loadData();if(ME.admin)await loadUsers();route()}
boot();

const FAQ=[['¿Cómo me registro?','En Login toca Registrarse, pon tu nombre y número y te damos tu contraseña.'],
['¿Olvidé mi contraseña?','Escríbeme por WhatsApp y te genero una nueva.'],
['¿Dónde descargo las apps?','En el menú, sección Apps.'],
['¿Cómo entro al grupo?','En el menú, sección Comunidad, toca "Unirme al grupo".'],
['¿Cambiar el color?','En Configuración eliges morado, azul o verde, y modo claro u oscuro.']];
function say(t,c){const m=document.createElement('div');m.className='m '+c;m.innerHTML=t;$('#chat').append(m);$('#chat').scrollTop=1e9}
say('Hola, soy el asistente de SKY WEEB. Elige una pregunta.','bot');
FAQ.forEach(([q,a])=>{const b=document.createElement('button');b.className='q';b.textContent=q;
b.onclick=()=>{say(esc(q),'me');setTimeout(()=>say(esc(a),'bot'),300)};$('#qs').append(b)});
const o=document.createElement('button');o.className='q';o.textContent='Otra duda';
o.onclick=()=>{say('Otra duda','me');setTimeout(()=>say(`Escríbeme directo: <a href="https://wa.me/${WA}" target=_blank rel=noopener>abrir WhatsApp</a>`,'bot'),300)};$('#qs').append(o);
</script></body></html>
"""

@app.get("/")
def home():
    return PAGE

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
