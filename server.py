#!/usr/bin/env python3
"""Servidor do Onde Descartar AL — apenas biblioteca padrão do Python (3.9+)."""
import difflib, json, math, mimetypes, os, re, secrets, sys, time, traceback, unicodedata
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import db

STATIC = Path(__file__).parent / "static"
SESSION_TTL = 8 * 3600
MODALIDADES = {"ecoponto", "pev", "cooperativa", "logistica_reversa"}
BOUNDS = (-10.6, -8.7, -38.3, -35.1)  # lat_min, lat_max, lng_min, lng_max (Alagoas, aprox.)
FAILS = {}  # ip -> [contagem, desde]

def norm(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    return re.sub(r"\s+", " ", "".join(c for c in s if unicodedata.category(c) != "Mn")).strip()

def haversine(a, b, c, d):
    p = math.pi / 180
    x = math.sin((c - a) * p / 2) ** 2 + math.cos(a * p) * math.cos(c * p) * math.sin((d - b) * p / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(x))

class ApiError(Exception):
    def __init__(self, status, msg): self.status, self.msg = status, msg

def bad(msg): return ApiError(400, msg)

def txt(v, name, maxlen, required=False):
    v = (v or "").strip() if isinstance(v, str) or v is None else str(v).strip()
    if required and not v: raise bad(f"Campo obrigatório: {name}.")
    if len(v) > maxlen: raise bad(f"Campo '{name}' excede {maxlen} caracteres.")
    return v or None

# ---------- serialização ----------
POINT_FIELDS = ("id","nome","modalidade","endereco","municipio","lat","lng","consulta_geo","horario","telefone","limite_diario",
                "observacoes","fonte","fonte_url","ultima_verificacao","atualizado_em","ativo")

def point_dict(con, r, origin=None):
    mats = [dict(m) for m in con.execute("""SELECT m.id,m.nome,c.slug categoria FROM point_materials pm
        JOIN materials m ON m.id=pm.material_id JOIN categories c ON c.id=m.category_id
        WHERE pm.point_id=? ORDER BY m.nome""", (r["id"],))]
    d = {k: r[k] for k in POINT_FIELDS}
    d["verificado"] = bool(r["verificado"]); d["materiais"] = mats
    d["categorias"] = sorted({m["categoria"] for m in mats})
    if origin and r["lat"] is not None: d["distancia_km"] = round(haversine(origin[0], origin[1], r["lat"], r["lng"]), 1)
    return d

def parse_origin(q):
    try:
        lat, lng = float(q["lat"][0]), float(q["lng"][0])
        if -90 <= lat <= 90 and -180 <= lng <= 180: return lat, lng
    except (KeyError, ValueError, IndexError): pass
    return None

def query_points(con, q, material_id=None):
    sql, args = "SELECT DISTINCT p.* FROM points p", []
    if material_id or q.get("categoria"):
        sql += " JOIN point_materials pm ON pm.point_id=p.id JOIN materials m ON m.id=pm.material_id JOIN categories c ON c.id=m.category_id"
    sql += " WHERE p.ativo=1"
    if material_id: sql += " AND m.id=?"; args.append(material_id)
    if q.get("categoria"): sql += " AND c.slug=?"; args.append(q["categoria"][0])
    if q.get("municipio") and q["municipio"][0]: sql += " AND p.municipio=?"; args.append(q["municipio"][0])
    if q.get("modalidade") and q["modalidade"][0]:
        mods = [m for m in q["modalidade"][0].split(",") if m in MODALIDADES]
        if mods: sql += f" AND p.modalidade IN ({','.join('?'*len(mods))})"; args += mods
    origin = parse_origin(q)
    pts = [point_dict(con, r, origin) for r in con.execute(sql, args)]
    if q.get("q") and q["q"][0].strip():
        t = norm(q["q"][0]); pts = [p for p in pts if t in norm(p["nome"] + " " + p["endereco"] + " " + p["municipio"])]
    pts.sort(key=lambda p: (p.get("distancia_km", 1e9), p["nome"]))
    return pts

# ---------- rotas públicas ----------
def r_catalog(con, **_):
    cats = [dict(r) for r in con.execute("SELECT * FROM categories ORDER BY id")]
    mats = [dict(r) for r in con.execute("""SELECT m.id,m.nome,m.orientacao,c.slug categoria FROM materials m
        JOIN categories c ON c.id=m.category_id ORDER BY m.nome""")]
    return {"categorias": cats, "materiais": mats, "municipios": db.MUNICIPIOS, "modalidades": sorted(MODALIDADES)}

def r_search(con, q, **_):
    term = norm(q.get("q", [""])[0])
    if len(term) < 2: raise bad("Digite ao menos 2 caracteres.")
    scored = []
    for m in con.execute("""SELECT m.*,c.slug cslug,c.nome cnome,c.icone,c.recolhimento FROM materials m JOIN categories c ON c.id=m.category_id"""):
        terms = [norm(m["nome"])] + [norm(s) for s in m["sinonimos"].split(";") if s]
        best = 0.0
        for t in terms:
            if term == t: s = 1.0
            elif term in t or t in term: s = 0.9
            else: s = max(difflib.SequenceMatcher(None, term, x).ratio() for x in [t] + t.split())
            best = max(best, s)
        if best >= 0.62:
            scored.append((best, dict(id=m["id"], nome=m["nome"], orientacao=m["orientacao"], categoria=m["cslug"],
                                      categoria_nome=m["cnome"], icone=m["icone"], recolhimento=bool(m["recolhimento"]))))
    scored.sort(key=lambda x: (-x[0], x[1]["nome"]))
    matches = [m for _, m in scored[:6]]
    out = {"termo": q["q"][0], "correspondencias": matches, "material": None, "pontos": []}
    if matches:
        mid = int(q["material_id"][0]) if q.get("material_id") and q["material_id"][0].isdigit() else matches[0]["id"]
        out["material"] = next((m for m in matches if m["id"] == mid), matches[0])
        out["pontos"] = query_points(con, {k: v for k, v in q.items() if k != "q"}, out["material"]["id"])
    return out

def r_points(con, q, **_): return {"pontos": query_points(con, q)}

def r_point(con, m, q, **_):
    r = con.execute("SELECT * FROM points WHERE id=? AND ativo=1", (int(m[1]),)).fetchone()
    if not r: raise ApiError(404, "Ponto não encontrado.")
    return point_dict(con, r, parse_origin(q))

def r_services(con, q, **_):
    mun = q.get("municipio", ["Maceió"])[0]
    return {"servicos": [dict(r) for r in con.execute("SELECT * FROM services_info WHERE municipio=? ORDER BY id", (mun,))]}

def r_stats(con, **_):
    g = lambda s: con.execute(s).fetchone()[0]
    return {"pontos": g("SELECT COUNT(*) FROM points WHERE ativo=1"),
            "verificados": g("SELECT COUNT(*) FROM points WHERE ativo=1 AND verificado=1"),
            "municipios": g("SELECT COUNT(DISTINCT municipio) FROM points WHERE ativo=1"),
            "materiais": g("SELECT COUNT(*) FROM materials")}

def r_channels(con, q, **_):
    mun = q.get("municipio", [""])[0]
    return {"canais": [dict(r) for r in con.execute("SELECT nome,url,telefone FROM channels WHERE municipio=?", (mun,))]}

def r_pickup(con, body, **_):
    mun = txt(body.get("municipio"), "município", 60, True)
    if mun not in db.MUNICIPIOS: raise bad("Município inválido.")
    tel = txt(body.get("telefone"), "telefone", 30, True)
    if len(re.sub(r"\D", "", tel)) < 10: raise bad("Informe um telefone com DDD.")
    email = txt(body.get("email"), "e-mail", 120)
    if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email): raise bad("E-mail inválido.")
    cur = con.execute("INSERT INTO pickup_requests(nome,telefone,email,municipio,endereco,itens,observacao,criado_em) VALUES(?,?,?,?,?,?,?,?)",
        (txt(body.get("nome"), "nome", 100, True), tel, email, mun, txt(body.get("endereco"), "endereço", 200, True),
         txt(body.get("itens"), "itens", 500, True), txt(body.get("observacao"), "observação", 500), datetime.now().isoformat(timespec="seconds")))
    return {"protocolo": f"RV-{date.today().year}-{cur.lastrowid:05d}"}, 201

# ---------- autenticação ----------
def r_login(con, body, ip, **_):
    f = FAILS.get(ip)
    if f and time.time() - f[1] < 300 and f[0] >= 5: raise ApiError(429, "Muitas tentativas. Aguarde alguns minutos.")
    u = con.execute("SELECT * FROM users WHERE email=? AND ativo=1", (str(body.get("email", "")).lower().strip(),)).fetchone()
    ok = u and secrets.compare_digest(db.hash_pw(str(body.get("senha", "")), u["salt"]), u["senha_hash"])
    if not ok:
        c = FAILS.get(ip, [0, time.time()]); FAILS[ip] = [c[0] + 1, c[1] if time.time() - c[1] < 300 else time.time()]
        raise ApiError(401, "E-mail ou senha incorretos.")
    FAILS.pop(ip, None)
    tok = secrets.token_urlsafe(32)
    con.execute("DELETE FROM sessions WHERE expira<?", (time.time(),))
    con.execute("INSERT INTO sessions VALUES(?,?,?)", (tok, u["id"], time.time() + SESSION_TTL))
    return {"token": tok, "usuario": {"nome": u["nome"], "papel": u["papel"]}}

def r_logout(con, token, **_):
    con.execute("DELETE FROM sessions WHERE token=?", (token,)); return {"ok": True}

def r_me(con, user, **_): return {"nome": user["nome"], "papel": user["papel"]}

# ---------- administração ----------
def point_payload(body, user, existing=None):
    mod = body.get("modalidade")
    if mod not in MODALIDADES: raise bad("Modalidade inválida.")
    mun = body.get("municipio")
    if mun not in db.MUNICIPIOS: raise bad("Município inválido.")
    lat = lng = None
    if str(body.get("lat") or "").strip() or str(body.get("lng") or "").strip():
        try: lat, lng = float(body.get("lat")), float(body.get("lng"))
        except (TypeError, ValueError): raise bad("Latitude e longitude devem ser números (ou deixe ambas em branco).")
        if not (BOUNDS[0] <= lat <= BOUNDS[1] and BOUNDS[2] <= lng <= BOUNDS[3]): raise bad("Coordenadas fora de Alagoas.")
    url = txt(body.get("fonte_url"), "link da fonte", 300)
    if url and not re.match(r"^https?://", url): raise bad("O link da fonte deve começar com http:// ou https://.")
    verificado = 1 if (user["papel"] == "gestor" and body.get("verificado")) else 0
    if existing is not None and user["papel"] != "gestor": verificado = 0  # edição por cooperativa exige nova validação
    prev_v = existing["ultima_verificacao"] if existing else None
    ult = date.today().isoformat() if verificado and not (existing and existing["verificado"]) else (prev_v if verificado else None)
    mats = body.get("materiais") or []
    if not isinstance(mats, list) or not all(isinstance(i, int) for i in mats): raise bad("Lista de materiais inválida.")
    return dict(nome=txt(body.get("nome"), "nome", 120, True), modalidade=mod, endereco=txt(body.get("endereco"), "endereço", 250, True),
        municipio=mun, lat=lat, lng=lng, consulta_geo=txt(body.get("consulta_geo"), "consulta de localização", 200),
        horario=txt(body.get("horario"), "horário", 200), telefone=txt(body.get("telefone"), "telefone", 60),
        limite_diario=txt(body.get("limite_diario"), "limite diário", 120), observacoes=txt(body.get("observacoes"), "observações", 600),
        fonte=txt(body.get("fonte"), "fonte", 200), fonte_url=url, verificado=verificado, ultima_verificacao=ult,
        ativo=1 if body.get("ativo", True) else 0), mats

def check_owner(user, row):
    if not row: raise ApiError(404, "Ponto não encontrado.")
    if user["papel"] != "gestor" and row["owner_id"] != user["id"]: raise ApiError(403, "Você só pode gerenciar seus próprios pontos.")

def set_materials(con, pid, mats):
    valid = {r[0] for r in con.execute("SELECT id FROM materials")}
    if not set(mats) <= valid: raise bad("Material inexistente.")
    con.execute("DELETE FROM point_materials WHERE point_id=?", (pid,))
    con.executemany("INSERT INTO point_materials VALUES(?,?)", [(pid, i) for i in set(mats)])

def a_list(con, user, **_):
    sql, args = "SELECT * FROM points", []
    if user["papel"] != "gestor": sql += " WHERE owner_id=?"; args.append(user["id"])
    return {"pontos": [point_dict(con, r) for r in con.execute(sql + " ORDER BY municipio,modalidade,nome", args)]}

def a_create(con, body, user, **_):
    p, mats = point_payload(body, user)
    p.update(owner_id=user["id"] if user["papel"] != "gestor" else None, atualizado_em=date.today().isoformat())
    cur = con.execute(f"INSERT INTO points({','.join(p)}) VALUES({','.join('?'*len(p))})", list(p.values()))
    set_materials(con, cur.lastrowid, mats)
    return {"id": cur.lastrowid}, 201

def a_update(con, m, body, user, **_):
    pid = int(m[1]); row = con.execute("SELECT * FROM points WHERE id=?", (pid,)).fetchone(); check_owner(user, row)
    p, mats = point_payload(body, user, row); p["atualizado_em"] = date.today().isoformat()
    con.execute(f"UPDATE points SET {','.join(k+'=?' for k in p)} WHERE id=?", list(p.values()) + [pid])
    set_materials(con, pid, mats); return {"ok": True}

def a_delete(con, m, user, **_):
    pid = int(m[1]); row = con.execute("SELECT * FROM points WHERE id=?", (pid,)).fetchone(); check_owner(user, row)
    con.execute("DELETE FROM points WHERE id=?", (pid,)); return {"ok": True}

def a_pickups(con, **_):
    return {"solicitacoes": [dict(r) for r in con.execute("SELECT * FROM pickup_requests ORDER BY id DESC LIMIT 300")]}

def a_pickup_status(con, m, body, **_):
    if body.get("status") not in ("recebida", "encaminhada", "agendada", "concluida", "cancelada"): raise bad("Status inválido.")
    con.execute("UPDATE pickup_requests SET status=? WHERE id=?", (body["status"], int(m[1]))); return {"ok": True}

ROUTES = [  # método, regex, função, exige autenticação
 ("GET", r"/api/catalogo", r_catalog, False), ("GET", r"/api/busca", r_search, False),
 ("GET", r"/api/pontos", r_points, False), ("GET", r"/api/pontos/(\d+)", r_point, False),
 ("GET", r"/api/servicos", r_services, False),
 ("GET", r"/api/estatisticas", r_stats, False), ("GET", r"/api/canais", r_channels, False),
 ("POST", r"/api/recolhimento", r_pickup, False),
 ("POST", r"/api/login", r_login, False), ("POST", r"/api/logout", r_logout, True), ("GET", r"/api/me", r_me, True),
 ("GET", r"/api/admin/pontos", a_list, True), ("POST", r"/api/admin/pontos", a_create, True),
 ("PUT", r"/api/admin/pontos/(\d+)", a_update, True), ("DELETE", r"/api/admin/pontos/(\d+)", a_delete, True),
 ("GET", r"/api/admin/recolhimentos", a_pickups, True), ("PUT", r"/api/admin/recolhimentos/(\d+)", a_pickup_status, True),
]
CSP = ("default-src 'self'; script-src 'self' https://unpkg.com; style-src 'self' 'unsafe-inline' https://unpkg.com https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com; img-src 'self' data: https://tile.openstreetmap.org https://*.tile.openstreetmap.org https://unpkg.com; "
       "connect-src 'self' https://router.project-osrm.org https://nominatim.openstreetmap.org; frame-ancestors 'none'")

class Handler(BaseHTTPRequestHandler):
    server_version = "OndeDescartarAL/2.0"
    def log_message(self, fmt, *a): sys.stderr.write("%s %s\n" % (self.address_string(), fmt % a))
    def _send(self, status, data, ctype="application/json; charset=utf-8", extra=None):
        body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff"); self.send_header("Content-Security-Policy", CSP)
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        if self.headers.get("X-Forwarded-Proto") == "https": self.send_header("Strict-Transport-Security", "max-age=31536000")
        for k, v in (extra or {}).items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(body)

    def client_ip(self):
        """Atrás de proxy (Render), o IP real vem em X-Forwarded-For; só é usado com ODAL_TRUST_PROXY=1."""
        if os.environ.get("ODAL_TRUST_PROXY") == "1":
            xf = self.headers.get("X-Forwarded-For", "")
            if xf: return xf.split(",")[0].strip()
        return self.client_address[0]

    def handle_any(self, method):
        url = urlparse(self.path)
        if url.path == "/healthz":  # verificação de saúde da hospedagem
            return self._send(200, b"ok", "text/plain; charset=utf-8", {"Cache-Control": "no-store"})
        if not url.path.startswith("/api/"):
            return self.static(url.path) if method == "GET" else self._send(405, {"erro": "Método não permitido."})
        con = db.connect()
        try:
            for mth, rx, fn, auth in ROUTES:
                mm = re.fullmatch(rx, url.path)
                if mth != method or not mm: continue
                user, token = None, ""
                if auth:
                    token = self.headers.get("Authorization", "")[7:]
                    user = con.execute("""SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id
                        WHERE s.token=? AND s.expira>? AND u.ativo=1""", (token, time.time())).fetchone()
                    if not user: raise ApiError(401, "Sessão expirada ou inválida.")
                body = {}
                if method in ("POST", "PUT"):
                    n = int(self.headers.get("Content-Length") or 0)
                    if n > 100_000: raise ApiError(413, "Requisição muito grande.")
                    try: body = json.loads(self.rfile.read(n) or b"{}")
                    except ValueError: raise bad("JSON inválido.")
                    if not isinstance(body, dict): raise bad("JSON inválido.")
                res = fn(con=con, m=(None, *mm.groups()), q=parse_qs(url.query), body=body, user=user, token=token, ip=self.client_ip())
                con.commit()
                payload, status = res if isinstance(res, tuple) else (res, 200)
                return self._send(status, payload, extra={"Cache-Control": "no-store"})
            raise ApiError(404, "Rota não encontrada.")
        except ApiError as e:
            con.rollback(); self._send(e.status, {"erro": e.msg})
        except Exception as e:  # noqa
            con.rollback(); traceback.print_exc(); self._send(500, {"erro": "Erro interno do servidor."})
        finally: con.close()

    def static(self, path):
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        f = (STATIC / rel).resolve()
        if STATIC.resolve() not in f.parents or not f.is_file(): f = STATIC / "index.html"  # SPA fallback
        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"): ctype += "; charset=utf-8"
        self._send(200, f.read_bytes(), ctype, {"Cache-Control": "no-cache"})

    def do_GET(self): self.handle_any("GET")
    def do_POST(self): self.handle_any("POST")
    def do_PUT(self): self.handle_any("PUT")
    def do_DELETE(self): self.handle_any("DELETE")

def main():
    db.init_db()
    port = int(os.environ.get("PORT", 8000)); host = os.environ.get("HOST") or ("0.0.0.0" if os.environ.get("RENDER") else "127.0.0.1")
    print(f"Onde Descartar AL em http://{host}:{port}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()

if __name__ == "__main__": main()
