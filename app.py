import os, sqlite3, time
from flask import Flask, request, session, redirect, jsonify, render_template_string

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cambia-esta-clave")

# ====== CAMBIA ESTO ======
ADMIN_PASS = os.environ.get("ADMIN_PASS", "cambia-esta-clave-admin")
WHATSAPP_NUM = "523342699274"                        # tu número con código de país, sin +
GROUP_LINK = "https://chat.whatsapp.com/GdhRsNw3GdWJHzQrDtJRUV?s=cl&p=a&iam=2"   # grupo de SkyWeeb
# =========================

DB = os.environ.get("DB_PATH", "skyweeb.db")

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init():
    c = db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT, phone TEXT UNIQUE, ts REAL);
    CREATE TABLE IF NOT EXISTS posts(id INTEGER PRIMARY KEY, kind TEXT, title TEXT, body TEXT, media TEXT, ts REAL);
    CREATE TABLE IF NOT EXISTS tutorials(id INTEGER PRIMARY KEY, title TEXT, url TEXT, ts REAL);
    CREATE TABLE IF NOT EXISTS apps(id INTEGER PRIMARY KEY, name TEXT, info TEXT, url TEXT, ts REAL);
    """)
    if not c.execute("SELECT 1 FROM tutorials LIMIT 1").fetchone():
        now = time.time()
        c.execute("INSERT INTO tutorials(title,url,ts) VALUES(?,?,?)",
                  ("Mi canal de YouTube", "https://youtube.com/@hsrramses?si=p5n26GAy6x3KFYvV", now))
        c.execute("INSERT INTO tutorials(title,url,ts) VALUES(?,?,?)",
                  ("Mi TikTok", "https://www.tiktok.com/@hsrramses", now + 1))
    c.commit(); c.close()
init()

def okurl(u):
    u = (u or "").strip()
    return u if u.startswith(("http://", "https://")) else ""

@app.get("/api/data")
def data():
    c = db()
    out = {t: [dict(r) for r in c.execute(f"SELECT * FROM {t} ORDER BY ts DESC")]
           for t in ("posts", "tutorials", "apps")}
    c.close()
    out["group"] = GROUP_LINK
    out["wa"] = WHATSAPP_NUM
    return jsonify(out)

@app.post("/api/login")
def login():
    j = request.get_json(silent=True) or {}
    name = (j.get("name") or "").strip()[:60]
    phone = "".join(ch for ch in (j.get("phone") or "") if ch.isdigit() or ch == "+")[:20]
    if not name or len(phone) < 7:
        return jsonify(ok=False, msg="Escribe tu nombre y un número válido."), 400
    c = db()
    c.execute("INSERT INTO users(name,phone,ts) VALUES(?,?,?) ON CONFLICT(phone) DO UPDATE SET name=excluded.name",
              (name, phone, time.time()))
    c.commit(); c.close()
    return jsonify(ok=True, name=name)

# ---------- ADMIN (solo tú) ----------
ADMIN = """
<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Admin SKY WEEB</title>
<style>body{font-family:system-ui;background:#0f1226;color:#eef;max-width:720px;margin:auto;padding:16px}
input,textarea,select{width:100%;padding:10px;margin:4px 0;border-radius:8px;border:1px solid #445;background:#1a1f3d;color:#fff;box-sizing:border-box}
button{padding:10px 16px;border:0;border-radius:8px;background:#7c5cff;color:#fff;font-weight:700}
form,.box{background:#171b36;padding:12px;border-radius:12px;margin:12px 0}a{color:#8cf}small{opacity:.7}
.del{background:#c33;padding:4px 10px;margin-left:8px}</style>
<h1>Panel SKY WEEB</h1><a href="/">Ver página</a> · <a href="/admin/salir">Salir</a>
<div class=box><h3>Usuarios dentro ({{users|length}})</h3>
{% for u in users %}<div>{{u.name}} — {{u.phone}} <small>{{u.fecha}}</small></div>{% else %}<small>Aún nadie.</small>{% endfor %}</div>
<form method=post action="/admin/add/posts"><h3>Nueva publicación</h3>
<select name=kind><option value=post>Publicación</option><option value=update>Actualización</option><option value=reel>Reel</option></select>
<input name=title placeholder="Título" required><textarea name=body placeholder="Texto"></textarea>
<input name=media placeholder="Link de imagen o video .mp4 (opcional)"><button>Publicar</button></form>
<form method=post action="/admin/add/tutorials"><h3>Nuevo tutorial</h3>
<input name=title placeholder="Título" required><input name=url placeholder="Link de video, TikTok o YouTube" required><button>Agregar</button></form>
<form method=post action="/admin/add/apps"><h3>Nueva app</h3>
<input name=name placeholder="Nombre" required><input name=info placeholder="Descripción corta">
<input name=url placeholder="Link de descarga" required><button>Agregar</button></form>
{% for t,rows in lists.items() %}<div class=box><h3>{{t}}</h3>
{% for r in rows %}<div>{{r.title or r.name}}<form style="display:inline;background:none;padding:0" method=post action="/admin/del/{{t}}/{{r.id}}"><button class=del>Borrar</button></form></div>{% else %}<small>Vacío</small>{% endfor %}</div>{% endfor %}
"""
ADMIN_LOGIN = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<body style="font-family:system-ui;background:#0f1226;color:#fff;display:grid;place-items:center;height:100vh">
<form method=post><h2>Admin SKY WEEB</h2><input type=password name=p placeholder="Contraseña" style="padding:10px;border-radius:8px">
<button style="padding:10px;border-radius:8px;background:#7c5cff;color:#fff;border:0">Entrar</button>
{% if err %}<p>Contraseña incorrecta</p>{% endif %}</form>"""

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST" and request.form.get("p") == ADMIN_PASS:
        session["adm"] = True
        return redirect("/admin")
    if not session.get("adm"):
        return render_template_string(ADMIN_LOGIN, err=request.method == "POST")
    c = db()
    users = [dict(r, fecha=time.strftime("%d/%m/%Y %H:%M", time.localtime(r["ts"])))
             for r in c.execute("SELECT * FROM users ORDER BY ts DESC")]
    lists = {t: [dict(r) for r in c.execute(f"SELECT * FROM {t} ORDER BY ts DESC")]
             for t in ("posts", "tutorials", "apps")}
    c.close()
    return render_template_string(ADMIN, users=users, lists=lists)

@app.get("/admin/salir")
def salir():
    session.clear()
    return redirect("/")

@app.post("/admin/add/<t>")
def add(t):
    if not session.get("adm") or t not in ("posts", "tutorials", "apps"):
        return redirect("/admin")
    f, now = request.form, time.time()
    c = db()
    if t == "posts":
        c.execute("INSERT INTO posts(kind,title,body,media,ts) VALUES(?,?,?,?,?)",
                  (f.get("kind", "post"), f["title"], f.get("body", ""), okurl(f.get("media")), now))
    elif t == "tutorials":
        c.execute("INSERT INTO tutorials(title,url,ts) VALUES(?,?,?)", (f["title"], okurl(f["url"]), now))
    else:
        c.execute("INSERT INTO apps(name,info,url,ts) VALUES(?,?,?,?)",
                  (f["name"], f.get("info", ""), okurl(f["url"]), now))
    c.commit(); c.close()
    return redirect("/admin")

@app.post("/admin/del/<t>/<int:i>")
def delete(t, i):
    if session.get("adm") and t in ("posts", "tutorials", "apps"):
        c = db(); c.execute(f"DELETE FROM {t} WHERE id=?", (i,)); c.commit(); c.close()
    return redirect("/admin")

# ---------- PÁGINA ----------
PAGE = r"""
<!doctype html><html lang=es><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>SKY WEEB</title>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@500;800&family=Nunito:wght@400;700&display=swap" rel=stylesheet>
<style>
:root{--acc:#8b5cf6;--bg:#f4f6ff;--card:#fff;--tx:#1a1d3a;--mut:#6b6f93;--ln:#dfe3f7}
:root[data-t=dark]{--bg:#0e1124;--card:#171b36;--tx:#eef0ff;--mut:#9ca1c9;--ln:#272c52}
:root[data-c=azul]{--acc:#3b82f6}:root[data-c=verde]{--acc:#10b981}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:16px/1.5 Nunito,sans-serif}
h1,h2,h3{font-family:'Bricolage Grotesque',sans-serif;margin:0}
header{position:sticky;top:0;z-index:5;display:flex;align-items:center;gap:12px;padding:12px 16px;background:var(--card);border-bottom:1px solid var(--ln)}
#burger{width:44px;height:44px;border:0;border-radius:12px;background:var(--acc);color:#fff;font-size:26px;cursor:pointer}
.logo{font:800 22px 'Bricolage Grotesque';letter-spacing:.5px}.logo b{color:var(--acc)}
nav{position:fixed;inset:0 auto 0 0;width:260px;max-width:80vw;background:var(--card);border-right:1px solid var(--ln);padding:72px 12px 12px;transform:translateX(-100%);transition:transform .25s;z-index:4}
nav.open{transform:none}#veil{position:fixed;inset:0;background:#0006;display:none;z-index:3}#veil.on{display:block}
nav a{display:block;padding:12px 14px;margin:4px 0;border-radius:12px;color:var(--tx);text-decoration:none;font-weight:700}
nav a.on,nav a:hover{background:var(--acc);color:#fff}
main{max-width:720px;margin:auto;padding:16px}section{display:none}section.on{display:block}
.card{background:var(--card);border:1px solid var(--ln);border-radius:16px;padding:14px;margin:12px 0}
.card img,.card video{width:100%;border-radius:12px;margin-top:8px}.tag{color:var(--acc);font-weight:700;font-size:14px}
.btn{display:inline-block;padding:11px 18px;border:0;border-radius:12px;background:var(--acc);color:#fff;font:700 16px Nunito;text-decoration:none;cursor:pointer}
input{width:100%;padding:12px;margin:6px 0;border-radius:12px;border:1px solid var(--ln);background:var(--bg);color:var(--tx);font:inherit}
.mut{color:var(--mut)}.row{display:flex;gap:10px;flex-wrap:wrap;margin:8px 0}
.dot{width:38px;height:38px;border-radius:50%;border:3px solid transparent;cursor:pointer}.dot.on{border-color:var(--tx)}
#chat{height:300px;overflow:auto;display:flex;flex-direction:column;gap:8px}
.m{padding:9px 13px;border-radius:14px;max-width:85%}.bot{background:var(--bg);align-self:flex-start}.me{background:var(--acc);color:#fff;align-self:flex-end}
.q{padding:8px 12px;border-radius:20px;border:1px solid var(--acc);background:none;color:var(--acc);font:700 14px Nunito;cursor:pointer}
:focus-visible{outline:3px solid var(--acc);outline-offset:2px}
</style></head><body>
<header><button id=burger aria-label="Menú">&#9776;</button><div class=logo>SKY <b>WEEB</b></div></header>
<div id=veil></div>
<nav id=nav>
<a href="#home">Home</a><a href="#login">Login</a><a href="#config">Configuración</a><a href="#comunidad">Comunidad</a>
<a href="#tutoriales">Tutoriales</a><a href="#apps">Apps</a><a href="#ayuda">Ayuda</a></nav>
<main>
<section id=home><h2>Novedades</h2><div id=posts></div></section>
<section id=login><h2>Entra a SKY WEEB</h2><p class=mut>Pon tu nombre y tu número para registrarte.</p>
<div class=card><input id=ln placeholder="Tu nombre" autocomplete=name><input id=lp placeholder="Tu número" inputmode=tel autocomplete=tel>
<button class=btn id=lgo>Entrar</button><p id=lmsg></p></div></section>
<section id=config><h2>Configuración</h2>
<div class=card><h3>Color de botones e icono</h3><div class=row>
<div class=dot data-c=morado style="background:#8b5cf6" title=Morado></div>
<div class=dot data-c=azul style="background:#3b82f6" title=Azul></div>
<div class=dot data-c=verde style="background:#10b981" title=Verde></div></div></div>
<div class=card><h3>Modo</h3><div class=row><button class=btn data-t=light>Claro</button><button class=btn data-t=dark>Oscuro</button></div></div></section>
<section id=comunidad><h2>Comunidad</h2><div class=card><p>Únete al grupo de SkyWeeb en WhatsApp.</p><a class=btn id=grp target=_blank rel=noopener>Unirme al grupo</a></div></section>
<section id=tutoriales><h2>Tutoriales</h2><div id=tuts></div></section>
<section id=apps><h2>Apps</h2><div id=applist></div></section>
<section id=ayuda><h2>Ayuda</h2><div class=card><div id=chat></div><div class=row id=qs></div></div>
<a class=btn id=wa target=_blank rel=noopener>Escribirme por WhatsApp</a></section>
</main>
<script>
const $=s=>document.querySelector(s),R=document.documentElement;
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const ls={get(k,d){try{return localStorage.getItem(k)||d}catch(e){return d}},set(k,v){try{localStorage.setItem(k,v)}catch(e){}}};
function setC(c){R.dataset.c=c;ls.set('c',c);document.querySelectorAll('.dot').forEach(d=>d.classList.toggle('on',d.dataset.c==c))}
function setT(t){R.dataset.t=t;ls.set('t',t)}
setC(ls.get('c','morado'));setT(ls.get('t',matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light'));
document.querySelectorAll('.dot').forEach(d=>d.onclick=()=>setC(d.dataset.c));
document.querySelectorAll('[data-t]').forEach(b=>{if(b.tagName=='BUTTON')b.onclick=()=>setT(b.dataset.t)});
const nav=$('#nav'),veil=$('#veil');
function menu(o){nav.classList.toggle('open',o);veil.classList.toggle('on',o)}
$('#burger').onclick=()=>menu(!nav.classList.contains('open'));veil.onclick=()=>menu(false);
function route(){const h=(location.hash||'#home').slice(1);
document.querySelectorAll('section').forEach(s=>s.classList.toggle('on',s.id==h));
document.querySelectorAll('nav a').forEach(a=>a.classList.toggle('on',a.hash=='#'+h));menu(false);scrollTo(0,0)}
addEventListener('hashchange',route);route();
const L={post:'Publicación',update:'Actualización',reel:'Reel'};
function media(u){if(!u)return'';return /\.(mp4|webm)$/i.test(u)?`<video src="${esc(u)}" controls playsinline></video>`:
/\.(png|jpe?g|gif|webp)$/i.test(u)?`<img src="${esc(u)}" alt="">`:`<p><a class=btn href="${esc(u)}" target=_blank rel=noopener>Ver</a></p>`}
const empty=t=>`<p class=mut>${t}</p>`;
fetch('/api/data').then(r=>r.json()).then(d=>{
$('#posts').innerHTML=d.posts.map(p=>`<div class=card><span class=tag>${L[p.kind]||'Publicación'}</span><h3>${esc(p.title)}</h3><p>${esc(p.body)}</p>${media(p.media)}</div>`).join('')||empty('Aún no hay publicaciones.');
$('#tuts').innerHTML=d.tutorials.map(t=>`<div class=card><h3>${esc(t.title)}</h3><p><a class=btn href="${esc(t.url)}" target=_blank rel=noopener>Ver video</a></p></div>`).join('')||empty('Aún no hay tutoriales.');
$('#applist').innerHTML=d.apps.map(a=>`<div class=card><h3>${esc(a.name)}</h3><p class=mut>${esc(a.info)}</p><a class=btn href="${esc(a.url)}" target=_blank rel=noopener>Descargar</a></div>`).join('')||empty('Aún no hay apps.');
$('#grp').href=d.group;$('#wa').href='https://wa.me/'+d.wa;WA=d.wa}).catch(()=>{});
let WA='';
$('#lgo').onclick=async()=>{const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({name:$('#ln').value,phone:$('#lp').value})});const j=await r.json();
$('#lmsg').textContent=j.ok?`Listo, ${j.name}. Ya estás dentro.`:j.msg;if(j.ok)ls.set('u',j.name)};
if(ls.get('u',''))$('#lmsg').textContent='Sesión iniciada como '+ls.get('u')+'.';
const FAQ=[['¿Cómo me registro?','Abre el menú, entra a Login y pon tu nombre y número.'],
['¿Dónde descargo las apps?','En el menú, sección Apps. Ahí están todas las que se suben.'],
['¿Cómo entro al grupo?','En el menú, sección Comunidad, toca "Unirme al grupo".'],
['¿Cambiar el color?','En Configuración eliges morado, azul o verde, y modo claro u oscuro.'],
['¿Dónde veo los tutoriales?','En el menú, sección Tutoriales.']];
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
    return render_template_string(PAGE)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
