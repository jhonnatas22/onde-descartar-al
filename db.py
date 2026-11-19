"""Banco de dados (SQLite) e dados do Onde Descartar AL.

Dados oficiais: Prefeitura de Maceió / Alurb (https://maceio.al.gov.br/secretarias-e-orgaos/alurb),
conferidos em 07/11/2026. Outros municípios de Alagoas ainda não têm dados cadastrados.
"""
import hashlib, json, os, secrets, sqlite3
from datetime import date
from pathlib import Path

BASE = Path(__file__).parent
DB_PATH = Path(os.environ.get("ODAL_DB", BASE / "data" / "ondedescartar.db"))
DATA_CONFERENCIA = "2026-11-07"

MUNICIPIOS = """Água Branca;Anadia;Arapiraca;Atalaia;Barra de Santo Antônio;Barra de São Miguel;Batalha;Belém;Belo Monte;Boca da Mata;Branquinha;Cacimbinhas;Cajueiro;Campestre;Campo Alegre;Campo Grande;Canapi;Capela;Carneiros;Chã Preta;Coité do Nóia;Colônia Leopoldina;Coqueiro Seco;Coruripe;Craíbas;Delmiro Gouveia;Dois Riachos;Estrela de Alagoas;Feira Grande;Feliz Deserto;Flexeiras;Girau do Ponciano;Ibateguara;Igaci;Igreja Nova;Inhapi;Jacaré dos Homens;Jacuípe;Japaratinga;Jaramataia;Jequiá da Praia;Joaquim Gomes;Jundiá;Junqueiro;Lagoa da Canoa;Limoeiro de Anadia;Maceió;Major Isidoro;Mar Vermelho;Maragogi;Maravilha;Marechal Deodoro;Maribondo;Mata Grande;Matriz de Camaragibe;Messias;Minador do Negrão;Monteirópolis;Murici;Novo Lino;Olho d'Água das Flores;Olho d'Água do Casado;Olho d'Água Grande;Olivença;Ouro Branco;Palestina;Palmeira dos Índios;Pão de Açúcar;Pariconha;Paripueira;Passo de Camaragibe;Paulo Jacinto;Penedo;Piaçabuçu;Pilar;Pindoba;Piranhas;Poço das Trincheiras;Porto Calvo;Porto de Pedras;Porto Real do Colégio;Quebrangulo;Rio Largo;Roteiro;Santa Luzia do Norte;Santana do Ipanema;Santana do Mundaú;São Brás;São José da Laje;São José da Tapera;São Luís do Quitunde;São Miguel dos Campos;São Miguel dos Milagres;São Sebastião;Satuba;Senador Rui Palmeira;Tanque d'Arca;Taquarana;Teotônio Vilela;Traipu;União dos Palmares;Viçosa""".split(";")

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories(
  id INTEGER PRIMARY KEY, slug TEXT UNIQUE NOT NULL, nome TEXT NOT NULL, icone TEXT,
  orientacao TEXT, cuidados TEXT, recolhimento INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS materials(
  id INTEGER PRIMARY KEY, nome TEXT NOT NULL, sinonimos TEXT DEFAULT '',
  category_id INTEGER NOT NULL REFERENCES categories(id), orientacao TEXT);
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, nome TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
  salt TEXT NOT NULL, senha_hash TEXT NOT NULL, papel TEXT NOT NULL CHECK(papel IN ('gestor','cooperativa')),
  ativo INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), expira REAL NOT NULL);
CREATE TABLE IF NOT EXISTS points(
  id INTEGER PRIMARY KEY, nome TEXT NOT NULL,
  modalidade TEXT NOT NULL CHECK(modalidade IN ('ecoponto','pev','cooperativa','logistica_reversa')),
  endereco TEXT NOT NULL, municipio TEXT NOT NULL, lat REAL, lng REAL, consulta_geo TEXT,
  horario TEXT, telefone TEXT, limite_diario TEXT, observacoes TEXT, fonte TEXT, fonte_url TEXT,
  verificado INTEGER DEFAULT 0, ultima_verificacao TEXT, ativo INTEGER DEFAULT 1,
  owner_id INTEGER REFERENCES users(id), atualizado_em TEXT);
CREATE TABLE IF NOT EXISTS point_materials(
  point_id INTEGER NOT NULL REFERENCES points(id) ON DELETE CASCADE,
  material_id INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
  PRIMARY KEY(point_id, material_id));
CREATE TABLE IF NOT EXISTS pickup_requests(
  id INTEGER PRIMARY KEY, nome TEXT NOT NULL, telefone TEXT NOT NULL, email TEXT,
  municipio TEXT NOT NULL, endereco TEXT NOT NULL, itens TEXT NOT NULL, observacao TEXT,
  status TEXT NOT NULL DEFAULT 'recebida', criado_em TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS channels(
  id INTEGER PRIMARY KEY, municipio TEXT NOT NULL, nome TEXT NOT NULL, url TEXT, telefone TEXT);
CREATE TABLE IF NOT EXISTS services_info(
  id INTEGER PRIMARY KEY, municipio TEXT NOT NULL, tipo TEXT NOT NULL, titulo TEXT NOT NULL, descricao TEXT,
  como_acessar TEXT, horario TEXT, prazo TEXT, orientacoes TEXT, limitacoes TEXT,
  fonte_nome TEXT, fonte_url TEXT, verificado_em TEXT);
"""

CATEGORIES = [
 ("reciclaveis","Recicláveis","♻️","Papel, papelão, plástico, metal e vidro limpos e secos podem ser reaproveitados.","Lave e seque as embalagens, retire restos de comida e separe por tipo de material. Vidro quebrado deve ir embalado e identificado.",0),
 ("eletronicos","Eletrônicos","💻","Equipamentos eletrônicos contêm metais e componentes que não devem ir ao lixo comum.","Apague seus dados pessoais, retire pilhas/baterias e não desmonte o aparelho.",0),
 ("pilhas-baterias","Pilhas e baterias","🔋","Contêm metais pesados. O descarte deve ser feito em pontos de logística reversa.","Não perfure, não queime e guarde em recipiente seco e não metálico até levar ao ponto.",0),
 ("oleo","Óleo de cozinha","🛢️","Nunca descarte óleo na pia ou no solo: ele contamina a água e entope a rede de esgoto.","Deixe esfriar, filtre restos de comida e guarde em garrafa PET bem fechada.",0),
 ("volumosos","Móveis e eletrodomésticos","🛋️","Itens de grande porte exigem recolhimento ou entrega em local autorizado.","Não deixe na calçada. Verifique se o item está em condições de doação. Geladeiras e similares exigem cuidado com gases refrigerantes: não os desmonte.",1),
 ("organicos","Resíduos orgânicos","🍂","Restos de alimentos e podas podem virar adubo por compostagem.","Separe de recicláveis e rejeitos. Podas volumosas podem exigir serviço específico da prefeitura.",0),
 ("especiais","Materiais especiais","⚠️","Lâmpadas, pneus, entulho e outros materiais que exigem destinação própria.","Armazene em local seguro, sem quebrar, e confirme com o ponto se ele aceita o material antes de ir.",0),
]
MATERIALS = [
 ("Garrafa PET","pet;garrafa plastica;refrigerante;garrafa de plastico","reciclaveis","Esvazie, enxágue e amasse a garrafa. Mantenha a tampa."),
 ("Papelão","caixa de papelao;caixa;embalagem de papelao","reciclaveis","Mantenha seco e desmonte as caixas."),
 ("Papel","jornal;revista;folha;caderno;tetra pak","reciclaveis","Mantenha seco e limpo. Papel engordurado não é reciclável."),
 ("Lata de alumínio","latinha;lata de refrigerante;lata de cerveja;aluminio;lata de aco;metal","reciclaveis","Enxágue e amasse."),
 ("Vidro","garrafa de vidro;pote de vidro;frasco","reciclaveis","Enxágue; vidro quebrado deve ser embalado com segurança."),
 ("Plástico","sacola;embalagem plastica;pote plastico","reciclaveis","Enxágue e seque antes de entregar."),
 ("Celular","telefone;smartphone;aparelho celular","eletronicos","Apague seus dados e retire a bateria quando possível."),
 ("Computador","notebook;pc;laptop;cpu;monitor;teclado;mouse","eletronicos","Apague seus dados antes de entregar."),
 ("Televisão","tv;televisor;tela","eletronicos","Não quebre a tela. Entregue inteira."),
 ("Carregador","cabo;fonte;fio","eletronicos","Agrupe cabos e carregadores em um saco."),
 ("Pilha","pilhas;pilha aa;pilha aaa;pilha alcalina","pilhas-baterias","Guarde em pote seco e entregue em ponto de logística reversa."),
 ("Bateria","baterias;bateria de celular;bateria de notebook;bateria de carro","pilhas-baterias","Não perfure nem queime. Entregue em ponto de logística reversa."),
 ("Óleo de cozinha","oleo;oleo usado;oleo de fritura","oleo","Armazene em garrafa PET fechada e leve a um ponto de coleta."),
 ("Sofá","sofa;poltrona;estofado","volumosos","Entregue em um ecoponto (até 1 m³) ou solicite a coleta de volumosos."),
 ("Colchão","colchao;cama","volumosos","Entregue em um ecoponto ou solicite a coleta de volumosos; não abandone em vias públicas."),
 ("Guarda-roupa","armario;roupeiro;movel;moveis;mesa;cadeira","volumosos","Entregue em um ecoponto ou solicite a coleta de volumosos; doe se estiver em bom estado."),
 ("Geladeira","refrigerador;freezer;frigobar;eletrodomestico","volumosos","Não desmonte (gases refrigerantes). Entregue em ecoponto ou solicite a coleta de volumosos."),
 ("Fogão","fogao;cooktop","volumosos","Entregue em ecoponto ou solicite a coleta de volumosos."),
 ("Máquina de lavar","maquina de lavar roupa;lavadora;tanquinho","volumosos","Entregue em ecoponto ou solicite a coleta de volumosos."),
 ("Restos de alimentos","comida;casca de fruta;sobra de comida;borra de cafe;composto","organicos","Separe para compostagem, se houver serviço disponível."),
 ("Poda de árvore","poda;galhos;folhas;grama;jardim","organicos","Podas podem ser entregues em ecopontos (até 1 m³ em Maceió)."),
 ("Lâmpada fluorescente","lampada;lampada led;lampada fluorescente;lampada queimada","especiais","Não quebre. Guarde na embalagem original e leve a ponto de logística reversa."),
 ("Pneu","pneus;pneu velho;camara de ar","especiais","Leve a borracharias/revendas que recebem pneus inservíveis ou ao ponto indicado."),
 ("Entulho","restos de obra;construcao;tijolo;cimento;caliça;residuo de construcao civil","especiais","Pequenos volumes (até 1 m³) podem ser entregues em ecopontos de Maceió. Não descarte em terrenos baldios."),
]
RECICLAVEIS = ["Garrafa PET", "Papelão", "Papel", "Lata de alumínio", "Vidro", "Plástico"]
ECO_MATERIAIS = ["Entulho", "Poda de árvore", "Sofá", "Colchão", "Guarda-roupa", "Geladeira", "Fogão", "Máquina de lavar"] + RECICLAVEIS

F_ECO = ("Alurb / Prefeitura de Maceió — Ecopontos", "https://maceio.al.gov.br/p/alurb/ecopontos")
F_SEL = ("Alurb / Prefeitura de Maceió — Coleta Seletiva", "https://maceio.al.gov.br/p/alurb/coleta-seletiva")
OBS_ECO = ("Gratuito. Recebe resíduos da construção civil (até 1 m³), restos de poda, móveis e eletrodomésticos inservíveis e recicláveis. "
           "A Alurb divulga o horário padrão para todos os ecopontos; em feriados e eleições podem fechar. Confirme pelo 156 antes de ir.")
# (nome, endereco, consulta de geocodificação, observação extra)
ECOPONTOS = [
 ("Ecoponto Pajuçara", "Rua Campos Teixeira, nº 476, Pajuçara", "Rua Campos Teixeira 476, Pajuçara, Maceió, Alagoas", None),
 ("Ecoponto Tabuleiro", "Rua Botafogo, por trás do Posto de Saúde Dr. Ib Gatto Falcão, Tabuleiro do Martins", "Rua Botafogo, Tabuleiro do Martins, Maceió, Alagoas", None),
 ("Ecoponto Dique Estrada", "Av. Governador Teobaldo Barbosa, Vergel do Lago", "Avenida Governador Teobaldo Barbosa, Vergel do Lago, Maceió, Alagoas", None),
 ("Ecoponto Santa Lúcia", "Avenida Oswaldo Ramos, 912, Jardim Petrópolis (Santa Lúcia)", "Avenida Oswaldo Ramos 912, Maceió, Alagoas", None),
 ("Ecoponto Gruta de Lourdes", "Rua Antônio Menezes de Araújo Lemos, 143, Gruta de Lourdes", "Rua Antônio Menezes de Araújo Lemos 143, Gruta de Lourdes, Maceió, Alagoas", None),
 ("Ecoponto Santa Maria", "Av. Lourival Melo Mota, Conjunto Santa Maria, s/n, Cidade Universitária", "Avenida Lourival Melo Mota, Cidade Universitária, Maceió, Alagoas", None),
 ("PDR Feitosa (Ponto de Descarte Rápido)", "Rua André Cardoso Borba, 366/394, Feitosa", "Rua André Cardoso Borba 366, Feitosa, Maceió, Alagoas", "A Alurb lista este equipamento entre os ecopontos, identificado como PDR."),
 ("Ecoponto Petrópolis", "Avenida Jorge de Lima, por trás do Residencial Parque Petrópolis III, Petrópolis", "Avenida Jorge de Lima, Petrópolis, Maceió, Alagoas", "Inaugurado em 2026 (oitavo equipamento da capital)."),
]
# (nome, endereco, dias/turnos, telefones, consulta geocodificação)
COOPERATIVAS = [
 ("Coopvila", "Vila Emater, R. A, S/N, Jacarecica", "Porta a porta em Pontal da Barra: terça e quinta (manhã).", "99838-0894 (Gil)", "Vila Emater, Jacarecica, Maceió, Alagoas"),
 ("Cooprel Antares", "Av. Menino Marcelo, 6001, Antares", "Porta a porta no Cond. Aldebaran e adjacências: quarta (manhã).", "99816-5444 (Virgínia); 99933-2478 (Meury)", "Avenida Menino Marcelo 6001, Antares, Maceió, Alagoas"),
 ("Cooplum", "Av. Comendador Gustavo Paiva, S/N, Jacarecica", "Porta a porta em Cruz das Almas, Jacarecica, Jatiúca, Mangabeiras e Ponta Verde: segunda e quarta (turno não informado).", "99106-9955 (Maria)", "Avenida Comendador Gustavo Paiva, Jacarecica, Maceió, Alagoas"),
 ("Cooprel Benedito Bentes", "R. B 9, Cj. Benedito Bentes I, 39, Benedito Bentes", "Porta a porta: Av. Garça Torta na terça; Av. Pratagy na quinta (manhã).", "98883-9930 (Patrícia); 98879-9930 (Ivana)", "Conjunto Benedito Bentes I, Maceió, Alagoas"),
 ("Coopmundaú", "Av. Gov. Teobaldo Barbosa, Ponta Grossa", "Dias e turnos da coleta porta a porta não informados na página oficial.", "98721-0802 (Jane); 98818-3087 (Socorro)", "Avenida Governador Teobaldo Barbosa, Ponta Grossa, Maceió, Alagoas"),
]
PEVS = """Praça em frente ao 5º Batalhão da PM, Lot. Celly Loureiro – Benedito Bentes
Paulo Bandeira – Benedito Bentes
Calçada do Terminal do Graciliano Ramos
Próximo ao terminal – Petrópolis
Conjunto Village Campestre I – próximo à associação de moradores
Praça em frente ao terminal da Colina
Praça do Rosane Collor – Clima Bom
Praça do Mirante da Gruta
Praça 200 anos – Zé Tenório
Praça Raimundo de Aguiar Peixoto – Antares
Guaxuma
Mirante do Jacintinho
Terminal do Trapiche
Praça em frente à USF da Pitanguinha
Vergel – praça próxima à guarda municipal
Praça da Bíblia – Jatiúca
Praça da Faculdade – Prado
Em frente ao Instituto Mandaver – Dique Estrada
Praça Nossa Senhora de Fátima – Feitosa
Medeiros Neto – Santa Amélia
Praça do Skate – Ponta Verde
Ponta Verde – Corredor Vera Arruda
Cruz das Almas – terminal de ônibus
Farol – Mirante da Igreja São Gonçalo
Pontal da Barra – Praça São Sebastião
Gruta de Lourdes – Terminal da Rotary
Antares – Praça do Cond. Bela Vista
Eustáquio Gomes – Praça do INOCOOP
Santa Lúcia – Av. Nações Unidas
Serraria – Rua Projetada (antigo São João da Serraria), próximo à Fundação Bradesco
Garça Torta – Praça São Pedro
Cidade Universitária – Rua K Um, Eustáquio Gomes, próximo à antiga Telasa""".split("\n")

SERVICOS = [
 ("ecopontos", "Ecopontos de Maceió",
  "Equipamentos públicos gratuitos administrados pela Alurb para o descarte regular de resíduos e para reduzir o descarte irregular. Há 8 unidades (7 ecopontos e o PDR Feitosa).",
  "Vá diretamente a uma das unidades listadas abaixo. Não é necessário agendar.",
  "Todos os dias, das 6h às 18h (horário divulgado pela Alurb para todas as unidades).", None,
  "Aceita gratuitamente: resíduos da construção civil (até 1 m³), restos de poda, móveis e eletrodomésticos inservíveis e materiais recicláveis. Carroceiros podem se cadastrar no projeto Carroceiro Legal na unidade mais próxima, levando documentos pessoais e comprovante de residência.",
  "O limite informado é de 1 m³ por entrega. Em feriados e eleições os ecopontos podem fechar; confirme antes.", F_ECO),
 ("domiciliar", "Coleta domiciliar",
  "Coleta porta a porta de resíduos residenciais, realizada pelas empresas Viambiental (parte alta) e Naturalle (parte baixa), contratadas pela Prefeitura e fiscalizadas pela Alurb. Segundo a PNAD 2024/IBGE, 98,5% dos domicílios de Maceió são atendidos e 92,1% têm coleta na porta.",
  "Consulte os dias e horários da sua região no aplicativo Limpeza é Massa (Android e iOS), que também avisa quando o caminhão começa a coleta na sua área. Atendimento pelo chat do app de segunda a sexta, das 7h às 17h, ou pelo 156.",
  "Varia por região; veja no aplicativo.", None,
  "Disponibilize o lixo somente nos dias e horários da sua região, para evitar acúmulo nas ruas e a formação de pontos de lixo.",
  "A tabela de dias e horários por bairro não foi encontrada em página oficial atualizada, por isso não é exibida aqui. Não use listas antigas: consulte o aplicativo ou o 156.",
  ("Alurb / Prefeitura de Maceió — aplicativo Limpeza é Massa", "https://maceio.al.gov.br/noticias/alurb/chat-do-aplicativo-limpeza-e-massa-passa-a-ser-o-principal-canal-de-atendimento-da-alurb")),
 ("seletiva", "Coleta seletiva",
  "Cinco cooperativas parceiras fazem a coleta porta a porta em áreas definidas (Cooprel Benedito Bentes, Cooprel Antares, Coopvila, Cooplum e Coopmundaú). Onde não há coleta porta a porta, o cidadão leva os recicláveis a um dos 32 Pontos de Entrega Voluntária (PEV), e as cooperativas recolhem o material.",
  "Separe os recicláveis e aguarde a cooperativa na sua área (veja dias e turnos nas fichas) ou leve ao PEV mais próximo.",
  "Veja dias e turnos na ficha de cada cooperativa.", None,
  "Papel (jornais, revistas, caixas, papelão, Tetra Pak); metal (latas de alumínio e aço, ferragens, canos, arame); vidro (potes, copos, garrafas, frascos); plástico (PET, tampas, potes, recipientes de limpeza, PVC, sacos, baldes). Entregue limpo e seco.",
  "Os endereços dos PEVs são divulgados como locais de referência (praças, terminais), sem número; a posição no mapa é aproximada.", F_SEL),
 ("volumosos", "Coleta de volumosos",
  "A Alurb recolhe gratuitamente na porta do cidadão sofás, camas, colchões, geladeiras e outros móveis e eletrodomésticos inservíveis.",
  "Ligue 156 ou 0800 082 2600, envie WhatsApp para 98802-4834 ou use o aplicativo Limpeza é Massa. Informe endereço completo com ponto de referência e os itens.",
  None, "Até 15 dias úteis para pedidos feitos a partir de janeiro de 2026 (antes eram 7 dias úteis). Para ser mais rápido, leve o item a um ecoponto.",
  "Se puder levar o item, use um ecoponto: é gratuito, funciona todos os dias e aceita até 1 m³. Itens em bom estado podem ser doados.",
  "O prazo e os canais podem mudar; confirme com a Alurb. Entulho de obras não entra na coleta de volumosos: use os ecopontos.",
  ("Alurb / Prefeitura de Maceió — Coleta de Volumosos", "https://maceio.al.gov.br/p/alurb/coleta-de-volumosos")),
]
CANAIS = [
 ("Maceió", "Central 156 (Alurb)", None, "156"),
 ("Maceió", "Telefone da coleta de volumosos", None, "0800 082 2600"),
 ("Maceió", "WhatsApp da Central de Monitoramento da Alurb", None, "98802-4834"),
 ("Maceió", "Atendimento presencial da Alurb: Rua Cel. Pedro Lima, 69, Jaraguá (segunda a sexta, 8h às 14h)", None, "(82) 3312-5380"),
 ("Maceió", "Aplicativo Limpeza é Massa (Android e iOS)", "https://maceio.al.gov.br/noticias/alurb/chat-do-aplicativo-limpeza-e-massa-passa-a-ser-o-principal-canal-de-atendimento-da-alurb", None),
]

def hash_pw(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()

def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con

def add_user(con, nome, email, senha, papel):
    salt = secrets.token_hex(16)
    con.execute("INSERT INTO users(nome,email,salt,senha_hash,papel) VALUES(?,?,?,?,?)", (nome, email.lower(), salt, hash_pw(senha, salt), papel))

def _migrate_old_db():
    """Bancos da versão 1 (dados de demonstração) são movidos para .antigo e recriados."""
    if not DB_PATH.exists(): return
    con = sqlite3.connect(DB_PATH)
    cols = [r[1] for r in con.execute("PRAGMA table_info(points)")]
    con.close()
    if cols and "observacoes" not in cols:
        DB_PATH.replace(DB_PATH.with_suffix(".db.antigo"))
        print("Banco antigo (dados de demonstração) movido para", DB_PATH.with_suffix(".db.antigo"))

def init_db(seed=True):
    _migrate_old_db()
    con = connect()
    con.executescript(SCHEMA)
    if seed and con.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
        for slug, nome, ic, ori, cui, rec in CATEGORIES:
            con.execute("INSERT INTO categories(slug,nome,icone,orientacao,cuidados,recolhimento) VALUES(?,?,?,?,?,?)", (slug, nome, ic, ori, cui, rec))
        cat = {r["slug"]: r["id"] for r in con.execute("SELECT id,slug FROM categories")}
        for nome, sin, c, ori in MATERIALS:
            con.execute("INSERT INTO materials(nome,sinonimos,category_id,orientacao) VALUES(?,?,?,?)", (nome, sin, cat[c], ori))
        mat = {r["nome"]: r["id"] for r in con.execute("SELECT id,nome FROM materials")}
        pw = os.environ.get("ODAL_ADMIN_PASSWORD")
        if not pw:
            if os.environ.get("RENDER"):  # em hospedagem nunca usa a senha padrão
                pw = secrets.token_urlsafe(12)
                print(f"[ODAL] ODAL_ADMIN_PASSWORD não definida. Senha inicial gerada para gestor@ondedescartar.al e cooperativa@ondedescartar.al: {pw}", flush=True)
            else: pw = "troque-esta-senha"
        add_user(con, "Gestor Municipal", "gestor@ondedescartar.al", pw, "gestor")
        add_user(con, "Cooperativa Exemplo", "cooperativa@ondedescartar.al", pw, "cooperativa")

        def ponto(nome, mod, end, geo, hor, tel, lim, obs, fonte, mats):
            cur = con.execute("""INSERT INTO points(nome,modalidade,endereco,municipio,consulta_geo,horario,telefone,limite_diario,observacoes,
                fonte,fonte_url,verificado,ultima_verificacao,ativo,atualizado_em) VALUES(?,?,?,?,?,?,?,?,?,?,?,1,?,1,?)""",
                (nome, mod, end, "Maceió", geo, hor, tel, lim, obs, fonte[0], fonte[1], DATA_CONFERENCIA, DATA_CONFERENCIA))
            con.executemany("INSERT INTO point_materials VALUES(?,?)", [(cur.lastrowid, mat[m]) for m in mats])
        for nome, end, geo, extra in ECOPONTOS:
            ponto(nome, "ecoponto", end, geo, "Todos os dias, das 6h às 18h", None, "Até 1 m³ por entrega",
                  OBS_ECO + (" " + extra if extra else ""), F_ECO, ECO_MATERIAIS)
        for nome, end, dias, tel, geo in COOPERATIVAS:
            ponto(nome + " (cooperativa)", "cooperativa", end, geo, None, tel, None, dias + " Recebe papel, metal, vidro e plástico.", F_SEL, RECICLAVEIS)
        for desc in PEVS:
            ponto("PEV — " + desc, "pev", desc, None, None, None, None,
                  "Ponto de Entrega Voluntária de recicláveis (papel, metal, vidro e plástico). O material é recolhido pelas cooperativas parceiras.", F_SEL, RECICLAVEIS)
        for tipo, titulo, desc, acesso, hor, prazo, ori, lim, fonte in SERVICOS:
            con.execute("""INSERT INTO services_info(municipio,tipo,titulo,descricao,como_acessar,horario,prazo,orientacoes,limitacoes,fonte_nome,fonte_url,verificado_em)
                VALUES('Maceió',?,?,?,?,?,?,?,?,?,?,?)""", (tipo, titulo, desc, acesso, hor, prazo, ori, lim, fonte[0], fonte[1], DATA_CONFERENCIA))
        con.executemany("INSERT INTO channels(municipio,nome,url,telefone) VALUES(?,?,?,?)", CANAIS)
    con.commit(); con.close()
