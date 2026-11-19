"""Testes de integração (python3 -m unittest discover tests). Usam banco temporário e servidor local."""
import json, os, sys, tempfile, threading, unittest, urllib.request, urllib.error
from http.server import ThreadingHTTPServer
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["ODAL_DB"] = os.path.join(tempfile.mkdtemp(), "t.db"); os.environ["ODAL_ADMIN_PASSWORD"] = "senha-de-teste"
import db, server

class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db(); cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"; threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
    @classmethod
    def tearDownClass(cls): cls.srv.shutdown()
    def call(self, method, path, body=None, token=None):
        req = urllib.request.Request(self.base + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", **({"Authorization": "Bearer " + token} if token else {})})
        try:
            with urllib.request.urlopen(req) as r: return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
    def login(self, who="gestor"):
        return self.call("POST", "/api/login", {"email": f"{who}@ondedescartar.al", "senha": "senha-de-teste"})[1]["token"]

    # --- dados oficiais de Maceió ---
    def test_contagens_oficiais(self):
        _, r = self.call("GET", "/api/pontos"); c = {}
        for p in r["pontos"]: c[p["modalidade"]] = c.get(p["modalidade"], 0) + 1
        self.assertEqual(c, {"ecoponto": 8, "cooperativa": 5, "pev": 32})
    def test_ecoponto_ficha(self):
        _, r = self.call("GET", "/api/pontos?modalidade=ecoponto&q=pajucara"); p = r["pontos"][0]
        self.assertIn("Campos Teixeira", p["endereco"]); self.assertEqual(p["horario"], "Todos os dias, das 6h às 18h")
        self.assertTrue(p["verificado"]); self.assertTrue(p["fonte_url"].startswith("https://maceio.al.gov.br/"))
    def test_servicos(self):
        _, r = self.call("GET", "/api/servicos"); self.assertEqual([s["tipo"] for s in r["servicos"]], ["ecopontos", "domiciliar", "seletiva", "volumosos"])
        dom = r["servicos"][1]; self.assertIn("Limpeza é Massa", dom["como_acessar"]); self.assertTrue(dom["limitacoes"])
    def test_canais_maceio(self):
        _, r = self.call("GET", "/api/canais?municipio=Macei%C3%B3"); self.assertTrue(any(c["telefone"] == "156" for c in r["canais"]))
    def test_nao_afirma_sem_cadastro(self):  # nenhum ponto cadastrado aceita pilha -> lista vazia, sem inventar
        _, r = self.call("GET", "/api/busca?q=pilha"); self.assertEqual(r["material"]["nome"], "Pilha"); self.assertEqual(r["pontos"], [])
    def test_sofa_ecopontos(self):
        _, r = self.call("GET", "/api/busca?q=sofa"); self.assertEqual(len(r["pontos"]), 8)

    # --- busca ---
    def test_busca_tolerante_a_erros(self):
        _, r = self.call("GET", "/api/busca?q=geladera"); self.assertEqual(r["material"]["nome"], "Geladeira"); self.assertTrue(r["pontos"])
    def test_busca_sinonimo_e_acento(self):
        _, r = self.call("GET", "/api/busca?q=entulho%20de%20obra"); self.assertEqual(r["material"]["nome"], "Entulho")
    def test_busca_sem_resultado(self):
        _, r = self.call("GET", "/api/busca?q=xyzqwk"); self.assertIsNone(r["material"])
    def test_distancia_ordenada_sem_coordenadas_no_fim(self):
        _, r = self.call("GET", "/api/pontos?lat=-9.66&lng=-35.73"); d = [p.get("distancia_km") for p in r["pontos"]]
        self.assertTrue(all(x is None for x in d))  # pontos oficiais ainda não têm coordenadas gravadas

    # --- administração ---
    def test_admin_exige_login(self):
        self.assertEqual(self.call("GET", "/api/admin/pontos")[0], 401)
        self.assertEqual(self.call("POST", "/api/login", {"email": "x@y.z", "senha": "errada"})[0], 401)
    def test_crud_e_permissoes(self):
        g, c = self.login("gestor"), self.login("cooperativa")
        ponto = dict(nome="Teste", modalidade="cooperativa", endereco="Rua A, 1", municipio="Maceió", lat=-9.6, lng=-35.7, materiais=[1, 2], verificado=True)
        s, r = self.call("POST", "/api/admin/pontos", ponto, c); self.assertEqual(s, 201); pid = r["id"]
        _, pt = self.call("GET", f"/api/pontos/{pid}"); self.assertFalse(pt["verificado"])
        self.assertEqual(self.call("PUT", f"/api/admin/pontos/{pid}", ponto, g)[0], 200)
        _, pt = self.call("GET", f"/api/pontos/{pid}"); self.assertTrue(pt["verificado"]); self.assertEqual(len(pt["materiais"]), 2)
        self.assertEqual(self.call("PUT", "/api/admin/pontos/1", ponto, c)[0], 403)
        self.assertEqual(self.call("POST", "/api/admin/pontos", {**ponto, "lat": 10}, g)[0], 400)
        s, _ = self.call("POST", "/api/admin/pontos", {**ponto, "lat": "", "lng": ""}, g); self.assertEqual(s, 201)  # sem coordenadas é permitido
        self.assertEqual(self.call("DELETE", f"/api/admin/pontos/{pid}", None, c)[0], 200)
        self.assertEqual(self.call("GET", f"/api/pontos/{pid}")[0], 404)
    def test_recolhimento(self):
        d = dict(nome="Maria", telefone="(82) 99999-9999", municipio="Pilar", endereco="Rua B, 2", itens="1 sofá")
        s, r = self.call("POST", "/api/recolhimento", d); self.assertEqual(s, 201); self.assertTrue(r["protocolo"].startswith("RV-"))
        self.assertEqual(self.call("POST", "/api/recolhimento", {**d, "telefone": "123"})[0], 400)
        self.assertEqual(self.call("GET", "/api/admin/recolhimentos", None, self.login())[0], 200)
    def test_healthz(self):
        with urllib.request.urlopen(self.base + "/healthz") as r: self.assertEqual((r.status, r.read()), (200, b"ok"))
    def test_estatico_e_traversal(self):
        with urllib.request.urlopen(self.base + "/") as r: self.assertIn(b"Onde Descartar AL", r.read())
        with urllib.request.urlopen(self.base + "/..%2f..%2fserver.py") as r: self.assertNotIn(b"ThreadingHTTPServer", r.read())

if __name__ == "__main__": unittest.main()
