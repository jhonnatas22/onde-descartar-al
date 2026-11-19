# Onde Descartar AL

Plataforma web georreferenciada para localizar pontos de descarte de resíduos sólidos em Alagoas.
Sem dependências no servidor: **apenas Python 3.9+** (biblioteca padrão + SQLite).

## Executar
> Abra sempre pelo servidor Python. Abrir `static/index.html` direto (ou por Live Server) não funciona: não há API nem banco.
```bash
python3 server.py            # http://127.0.0.1:8000   (Windows: python server.py)
PORT=8001 python3 server.py  # outra porta, se a 8000 estiver ocupada (Windows PowerShell: $env:PORT=8001; python server.py)
```
Variáveis: `PORT`, `HOST`, `ODAL_DB` (caminho do banco), `ODAL_ADMIN_PASSWORD` (senha inicial; defina **antes da 1ª execução**).
Usuários iniciais: `gestor@ondedescartar.al` e `cooperativa@ondedescartar.al`, senha padrão `troque-esta-senha` (troque antes de publicar).

**Atualizando da versão anterior:** na primeira execução, o banco antigo (só dados de demonstração) é movido para `data/ondedescartar.db.antigo` e um novo é criado com os dados oficiais.
O navegador precisa de internet (Leaflet/unpkg, tiles e geocodificação do OpenStreetMap, fontes e rotas OSRM).

## Dados oficiais incluídos (Maceió, conferidos em 07/11/2026)
Fonte: Prefeitura de Maceió / Alurb — https://maceio.al.gov.br/secretarias-e-orgaos/alurb

| Serviço | O que há no sistema |
|---|---|
| **Ecopontos** | 8 unidades (7 ecopontos + PDR Feitosa): endereço, horário (todos os dias, 6h–18h), limite de 1 m³, materiais aceitos |
| **Coleta domiciliar** | Operação (Viambiental/Naturalle), cobertura (IBGE/PNAD 2024) e como consultar dias e horários (app *Limpeza é Massa*, 156) |
| **Coleta seletiva** | 5 cooperativas (dias, turnos, endereços, contatos) e 32 PEVs, com materiais aceitos |
| **Volumosos** | Canais (156, 0800 082 2600, WhatsApp 98802-4834, app), prazo divulgado (até 15 dias úteis) e alternativa dos ecopontos |

Limitações assumidas (o sistema as exibe ao usuário):
- **Dias e horários da coleta domiciliar por bairro** não foram encontrados em página oficial atual (a lista que circula é de 2016); por isso o sistema remete ao aplicativo oficial em vez de exibir dados possivelmente defasados.
- **Coordenadas**: a Prefeitura publica endereços, não coordenadas. O mapa estima a posição pelo OpenStreetMap (Nominatim) a partir do endereço, em cache no navegador, e avisa que é aproximada. Para precisão, o gestor pode marcar a posição exata no painel (clique no mapa).
- A Alurb anunciou horários diferentes em notícias antigas (8h–18h); prevalece o da página oficial de Ecopontos e da notícia mais recente (6h–18h). O sistema orienta confirmar pelo 156.
- Cooprel Antares: a página oficial cita só o Cond. Aldebaran e adjacências. Coopmundaú: sem dias informados.
- **Outros municípios de Alagoas**: ainda sem dados. Cadastre-os pelo painel `#/admin`, preenchendo fonte, link e marcando "verificado" só após conferir em fonte oficial.

## Hospedar no Render
1. Coloque o **conteúdo desta pasta** (com `render.yaml` na raiz) em um repositório do GitHub.
2. No Render: **New → Blueprint**, escolha o repositório e confirme. (Ou **New → Web Service** com Runtime *Python*, Build `echo ok`, Start `python server.py`, Health Check `/healthz` e as variáveis do `render.yaml`.)
3. Em **Environment**, copie o valor de `ODAL_ADMIN_PASSWORD`: é a senha inicial de `gestor@ondedescartar.al` e `cooperativa@ondedescartar.al`. Entre em `/#/admin`.
4. O Render fornece HTTPS, então o GPS do navegador funciona.

**Atenção ao banco de dados:** o SQLite fica em arquivo. No plano *free* o disco é temporário: a cada novo deploy ou reinício (inclusive ao "acordar" após inatividade) o banco volta ao estado inicial, então **cadastros feitos no painel, solicitações de recolhimento e senhas alteradas se perdem**. Os dados oficiais de Maceió voltam sempre, pois fazem parte do código. Para uso real, use um plano pago com **disco persistente**: descomente `ODAL_DB` e `disk` no `render.yaml` (ou crie o disco em *Disks* com mount `/var/data` e defina `ODAL_DB=/var/data/ondedescartar.db`).
O plano free também "dorme" após alguns minutos sem acesso, e o primeiro acesso depois disso demora.
Se não definir `ODAL_ADMIN_PASSWORD`, em hospedagem o sistema gera uma senha aleatória e a imprime nos *Logs* (nunca usa a senha padrão).

## Requisitos funcionais
| RF | Onde |
|----|------|
| RF01 Busca por resíduo (tolerante a erros, sinônimos) e pontos compatíveis | `#/buscar` |
| RF02 Mapa OpenStreetMap/Leaflet e rotas a partir da localização do usuário (OSRM; fallback para openstreetmap.org) | `#/mapa` |
| RF03 Ficha técnica: endereço, horário, telefone, limite, modalidade (ecoponto, PEV, cooperativa, logística reversa), materiais, observações, fonte | diálogo "Ver ficha completa" |
| RF04 Painel administrativo com autenticação e papéis (gestor / cooperativa) | `#/admin` |
| RF05 Recolhimento de volumosos: canais oficiais por município + formulário para municípios sem canal | `#/recolhimento`, `#/servicos?tipo=volumosos` |

Canais oficiais de outros municípios: `INSERT INTO channels(municipio,nome,url,telefone) VALUES('Cidade','Nome','https://...','(82) ...');`
Em municípios com canal cadastrado, o formulário é ocultado e o usuário é direcionado ao canal oficial.

## Regras
- Nada é afirmado sem cadastro; campos ausentes aparecem como "Não informado".
- "Verificado" = conferido em fonte oficial publicada (data e link exibidos). Edições por cooperativas voltam a "não verificado".
- Estatísticas da página inicial vêm do banco.

## Celulares
Layout responsivo: menu recolhível, chave **Lista | Mapa** na tela do mapa, alvos de toque de 44 px, cartões que cabem em 320 px e posições estimadas de endereços só sob demanda (economiza dados).
Teste: F12 → Ctrl+Shift+M, ou `HOST=0.0.0.0 python server.py` e abra o IP do computador no celular (o GPS do navegador exige HTTPS fora de `localhost`).

## Segurança e acessibilidade
PBKDF2-SHA256, sessões de 8 h, bloqueio após 5 logins falhos/IP, SQL parametrizado, DOM sem `innerHTML`, CSP. Em produção use HTTPS (Nginx/Caddy) e faça backup de `data/`.
Link "pular conteúdo", foco visível, teclado, `aria-live`, lista alternativa ao mapa, texto maior, alto contraste, `prefers-reduced-motion`.

## Testes e estrutura
```bash
python3 -m unittest discover tests -v
```
`server.py` API + estáticos · `db.py` esquema e dados oficiais · `static/` SPA · `tests/`
