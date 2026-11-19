/* Onde Descartar AL — front-end (SPA sem build). Todo conteúdo dinâmico é inserido via DOM/textContent. */
const $ = (s, r = document) => r.querySelector(s);
const app = $('#app');
const MOD = { ecoponto: 'Ecoponto público', pev: 'Ponto de Entrega Voluntária (PEV)', cooperativa: 'Cooperativa de recicláveis', logistica_reversa: 'Logística reversa (comércio)' };
const S = { cat: null, loc: null, token: sessionStorage.getItem('odal_token'), user: JSON.parse(sessionStorage.getItem('odal_user') || 'null'), map: null, nav: 0 };
const BOUNDS = [-10.6, -8.7, -38.3, -35.1];

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'value') el.value = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat(Infinity)) if (c != null && c !== false) el.append(c.nodeType ? c : document.createTextNode(c));
  return el;
}
async function api(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (S.token) headers.Authorization = 'Bearer ' + S.token;
  let res;
  try { res = await fetch('/api' + path, { ...opts, headers, body: opts.body ? JSON.stringify(opts.body) : undefined }); }
  catch { throw new Error('Sem conexão com o servidor. Verifique sua internet e tente novamente.'); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { if (res.status === 401 && S.token) logout(true); throw new Error(data.erro || 'Erro inesperado.'); }
  return data;
}
const say = m => { $('#live').textContent = ''; setTimeout(() => $('#live').textContent = m, 50); };
const loading = (t = 'Carregando…') => h('p', { role: 'status' }, h('span', { class: 'spin' }), ' ', t);
const errBox = m => h('div', { class: 'error', role: 'alert' }, m);
const fmtDate = d => d ? d.split('-').reverse().join('/') : null;
const catOf = slug => S.cat.categorias.find(c => c.slug === slug);
const link = (href, text) => h('a', { href, target: '_blank', rel: 'noopener' }, text);
const osmSearch = p => 'https://www.openstreetmap.org/search?query=' + encodeURIComponent(p.consulta_geo || `${p.endereco}, ${p.municipio}, Alagoas`);

/* ---------- geocodificação sob demanda (OpenStreetMap/Nominatim, resultado em cache no navegador) ---------- */
const GEO = JSON.parse(localStorage.getItem('odal_geo') || '{}');
async function coordsFor(p, force = false) {
  if (p.lat != null) return [p.lat, p.lng];
  if (GEO[p.id] === undefined && (p.consulta_geo || force)) {
    const q = p.consulta_geo || `${p.endereco}, ${p.municipio}, Alagoas`;
    try {
      const r = await fetch('https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&countrycodes=br&accept-language=pt-BR&q=' + encodeURIComponent(q));
      const d = await r.json(); const x = d[0] && [+d[0].lat, +d[0].lon];
      GEO[p.id] = x && x[0] >= BOUNDS[0] && x[0] <= BOUNDS[1] && x[1] >= BOUNDS[2] && x[1] <= BOUNDS[3] ? x : null;
      localStorage.setItem('odal_geo', JSON.stringify(GEO));
    } catch { return null; }
  }
  if (GEO[p.id]) { p.lat = GEO[p.id][0]; p.lng = GEO[p.id][1]; p.aprox = true; return GEO[p.id]; }
  return null;
}

/* ---------- componentes ---------- */
function muniSelect(id, value, all = 'Todos os municípios') {
  return h('select', { id, 'aria-label': 'Município' }, h('option', { value: '' }, all),
    S.cat.municipios.map(m => h('option', { value: m, selected: m === value }, m)));
}
function badges(p) {
  return [h('span', { class: 'badge' }, MOD[p.modalidade]),
    p.verificado ? h('span', { class: 'badge ok' }, '✔ Conferido em fonte oficial' + (p.ultima_verificacao ? ' em ' + fmtDate(p.ultima_verificacao) : ''))
                 : h('span', { class: 'badge warn' }, '⚠ Ainda não verificado')];
}
function pointCard(p, opts = {}) {
  return h('article', { class: 'card pcard' + (opts.selected ? ' sel' : ''), 'data-id': p.id },
    h('h3', {}, p.nome), h('div', {}, badges(p)),
    h('div', { class: 'meta' }, `${p.endereco} — ${p.municipio}` + (p.distancia_km != null ? ` · ≈ ${p.distancia_km.toString().replace('.', ',')} km em linha reta` : '')),
    p.horario && h('div', { class: 'meta' }, '🕒 ' + p.horario),
    h('div', { class: 'row' },
      h('button', { class: 'btn small ghost', onclick: () => showPoint(p.id) }, 'Ver ficha completa'),
      opts.onmap && h('button', { class: 'btn small ghost', onclick: () => opts.onmap(p) }, 'Mostrar no mapa')));
}
async function showPoint(id) {
  const dlg = $('#dlg'); dlg.replaceChildren(loading()); dlg.showModal();
  try {
    const q = S.loc ? `?lat=${S.loc.lat}&lng=${S.loc.lng}` : '';
    const p = await api('/pontos/' + id + q);
    const nf = h('span', { class: 'muted' }, 'Não informado');
    const row = (k, v) => [h('dt', {}, k), h('dd', {}, v || nf)];
    const byCat = {}; p.materiais.forEach(m => (byCat[m.categoria] ||= []).push(m.nome));
    const dest = p.lat != null ? `${p.lat},${p.lng}` : null;
    const osm = dest ? `https://www.openstreetmap.org/directions?engine=fossgis_osrm_car&route=${S.loc ? S.loc.lat + ',' + S.loc.lng : ''}%3B${dest}` : osmSearch(p);
    dlg.replaceChildren(
      h('h2', { id: 'dlgTitle' }, p.nome), h('div', {}, badges(p)),
      !p.verificado && h('div', { class: 'notice' }, 'Os dados deste ponto ainda não foram validados. Confirme por telefone ou com o responsável antes de ir.'),
      h('dl', { class: 'ficha' },
        row('Endereço', `${p.endereco} — ${p.municipio}/AL`), row('Horário', p.horario), row('Telefone', p.telefone),
        row('Limite por entrega', p.limite_diario), row('Modalidade', MOD[p.modalidade]),
        h('dt', {}, 'Materiais aceitos'),
        h('dd', {}, p.materiais.length ? Object.entries(byCat).map(([c, ns]) => h('p', { style: 'margin:0 0 .4rem' }, h('b', {}, catOf(c).nome + ': '), ns.join(', '))) : nf),
        row('Observações', p.observacoes),
        h('dt', {}, 'Fonte'), h('dd', {}, p.fonte ? (p.fonte_url ? link(p.fonte_url, p.fonte) : p.fonte) : nf),
        row('Última atualização', fmtDate(p.atualizado_em))),
      p.lat == null && h('p', { class: 'small muted' }, 'A localização exata deste ponto ainda não está cadastrada. No mapa, ela é estimada pelo endereço via OpenStreetMap, então confira o endereço.'),
      h('div', { class: 'row', style: 'margin-top:1rem' },
        h('a', { class: 'btn', href: '#/mapa?ponto=' + p.id, onclick: () => dlg.close() }, 'Ver no mapa e traçar rota'),
        h('a', { class: 'btn ghost', href: osm, target: '_blank', rel: 'noopener' }, dest ? 'Abrir rota no OpenStreetMap' : 'Procurar endereço no OpenStreetMap'),
        h('button', { class: 'btn ghost', onclick: () => dlg.close() }, 'Fechar')));
  } catch (e) { dlg.replaceChildren(errBox(e.message), h('button', { class: 'btn', onclick: () => dlg.close() }, 'Fechar')); }
}
function locate(onok, onfail) {
  if (!navigator.geolocation) return onfail('Seu navegador não oferece geolocalização. Escolha um município na lista.');
  navigator.geolocation.getCurrentPosition(pos => { S.loc = { lat: +pos.coords.latitude.toFixed(5), lng: +pos.coords.longitude.toFixed(5) }; onok(); },
    () => onfail('Não foi possível obter sua localização. Você pode escolher um município na lista.'), { timeout: 10000, maximumAge: 60000 });
}
const matDatalist = () => h('datalist', { id: 'matlist' }, S.cat.materiais.map(m => h('option', { value: m.nome })));

/* ---------- páginas ---------- */
const SERV = [['ecopontos', '🏗️', 'Ecopontos', 'Entulho, podas, móveis e recicláveis'], ['domiciliar', '🚛', 'Coleta domiciliar', 'Lixo comum, porta a porta'],
  ['seletiva', '♻️', 'Coleta seletiva', 'Cooperativas e pontos de entrega voluntária'], ['volumosos', '🛋️', 'Coleta de volumosos', 'Sofás, colchões e eletrodomésticos']];

async function pageHome() {
  const form = h('form', { class: 'searchbox', role: 'search', onsubmit: e => { e.preventDefault(); const v = $('#hq').value.trim(); if (v) location.hash = '#/buscar?q=' + encodeURIComponent(v); } },
    h('label', { class: 'sr', for: 'hq' }, 'Qual resíduo você quer descartar?'),
    h('input', { id: 'hq', type: 'search', list: 'matlist', placeholder: 'Ex.: geladeira, pilha, óleo de cozinha, sofá…', autocomplete: 'off' }),
    h('button', { class: 'btn' }, 'Buscar meu resíduo'));
  const stats = h('div', { class: 'stats' }, loading());
  app.replaceChildren(
    h('section', { class: 'hero' }, h('div', { class: 'wrap' },
      h('h1', {}, 'Descartar corretamente começa com a informação certa.'),
      h('p', { class: 'lead' }, 'Encontre pontos de coleta, descubra onde descartar seus resíduos e contribua para um Alagoas mais sustentável.'),
      form, matDatalist(),
      h('div', { class: 'row' }, h('a', { class: 'btn', href: '#/mapa' }, 'Encontrar ponto de descarte'), h('a', { class: 'btn ghost', href: '#/guia' }, 'Consultar tipos de resíduos')))),
    h('section', { class: 'section' }, h('div', { class: 'wrap' }, h('h2', {}, 'Serviços de coleta em Maceió'),
      h('p', { class: 'muted' }, 'Informações oficiais da Alurb / Prefeitura de Maceió.'),
      h('div', { class: 'grid' }, SERV.map(([k, ic, t, d]) => h('a', { class: 'card', href: '#/servicos?tipo=' + k }, h('div', { class: 'ic', 'aria-hidden': 'true' }, ic), h('h3', {}, t), h('p', { class: 'muted small' }, d)))))),
    h('section', { class: 'section alt' }, h('div', { class: 'wrap' }, h('h2', {}, 'Escolha uma categoria de resíduo'),
      h('div', { class: 'grid' }, S.cat.categorias.map(c => h('a', { class: 'card', href: '#/mapa?cat=' + c.slug }, h('div', { class: 'ic', 'aria-hidden': 'true' }, c.icone), h('h3', {}, c.nome), h('p', { class: 'muted small' }, c.orientacao)))))),
    h('section', { class: 'section' }, h('div', { class: 'wrap' }, h('h2', {}, 'Três perguntas antes de descartar'),
      h('div', { class: 'steps' }, h('div', {}, h('h3', {}, 'O que estou descartando?'), h('p', {}, 'Pesquise pelo nome e veja a categoria e como preparar o material.')),
        h('div', {}, h('h3', {}, 'Onde posso levar?'), h('p', {}, 'Veja os pontos no mapa ou em lista, por município ou perto de você.')),
        h('div', {}, h('h3', {}, 'O que verificar antes de ir?'), h('p', {}, 'Confira horário, telefone, limite por entrega e a fonte da informação.'))))),
    h('section', { class: 'section alt' }, h('div', { class: 'wrap' }, h('h2', {}, 'A plataforma em números reais'), stats,
      h('p', { class: 'muted small' }, 'Os números refletem apenas os dados efetivamente cadastrados. Por enquanto, só há dados oficiais de Maceió.'))));
  try { const s = await api('/estatisticas');
    stats.replaceChildren(...[['pontos', 'pontos cadastrados'], ['municipios', 'município com dados'], ['verificados', 'pontos conferidos em fonte oficial'], ['materiais', 'materiais no catálogo']].map(([k, l]) => h('div', {}, h('b', {}, s[k]), l)));
  } catch (e) { stats.replaceChildren(errBox(e.message)); }
}

async function pageServices(q) {
  let tipo = SERV.some(s => s[0] === q.tipo) ? q.tipo : 'ecopontos';
  const body = h('div'), tabs = h('div', { class: 'tabs', role: 'tablist', 'aria-label': 'Tipos de serviço' });
  let info = null;
  const drawTabs = () => tabs.replaceChildren(...SERV.map(([k, ic, t]) => h('button', { role: 'tab', 'aria-selected': String(k === tipo), onclick: () => { tipo = k; history.replaceState(null, '', '#/servicos?tipo=' + k); drawTabs(); render(); } }, `${ic} ${t}`)));
  async function render() {
    const s = info.find(x => x.tipo === tipo); if (!s) return body.replaceChildren(h('div', { class: 'empty' }, 'Informações ainda não cadastradas.'));
    const dl = [['Como acessar', s.como_acessar], ['Horário', s.horario], ['Prazo', s.prazo], ['O que aceita / orientações', s.orientacoes]].filter(x => x[1]);
    const list = h('div');
    body.replaceChildren(h('div', { class: 'card svc' }, h('h2', {}, s.titulo), h('p', {}, s.descricao),
      h('dl', {}, dl.map(([k, v]) => [h('dt', {}, k), h('dd', {}, v)])),
      s.limitacoes && h('div', { class: 'notice' }, h('b', {}, 'Atenção: '), s.limitacoes),
      h('p', { class: 'src' }, 'Fonte: ', s.fonte_url ? link(s.fonte_url, s.fonte_nome) : s.fonte_nome, ` · conferido em ${fmtDate(s.verificado_em)}`),
      tipo === 'volumosos' && h('p', {}, h('a', { class: 'btn small', href: '#/recolhimento' }, 'Ver canais de solicitação'))), list);
    const mods = { ecopontos: 'ecoponto', seletiva: 'cooperativa,pev' }[tipo];
    if (!mods) return;
    list.replaceChildren(loading());
    try {
      const { pontos } = await api('/pontos?municipio=Maceió&modalidade=' + mods);
      const groups = tipo === 'seletiva' ? [['Cooperativas (coleta porta a porta)', pontos.filter(p => p.modalidade === 'cooperativa')], ['Pontos de Entrega Voluntária (PEV)', pontos.filter(p => p.modalidade === 'pev')]] : [['Unidades', pontos]];
      list.replaceChildren(...groups.map(([t, ps]) => h('section', { style: 'margin-top:1.5rem' }, h('h3', {}, `${t} (${ps.length})`),
        h('div', { class: 'grid wide' }, ps.map(p => pointCard(p, { onmap: x => location.hash = '#/mapa?ponto=' + x.id }))),
        h('p', {}, h('a', { href: '#/mapa?modalidade=' + (t.startsWith('Pontos') ? 'pev' : tipo === 'ecopontos' ? 'ecoponto' : 'cooperativa') }, 'Ver no mapa')))));
    } catch (e) { list.replaceChildren(errBox(e.message)); }
  }
  app.replaceChildren(h('div', { class: 'wrap section' }, h('h1', {}, 'Serviços de coleta'), h('p', { class: 'lead muted' }, 'Ecopontos, coleta domiciliar, coleta seletiva e coleta de volumosos em Maceió.'), tabs, body));
  drawTabs(); body.replaceChildren(loading());
  try { info = (await api('/servicos?municipio=Maceió')).servicos; await render(); } catch (e) { body.replaceChildren(errBox(e.message)); }
}

async function pageSearch(q) {
  const out = h('div', { 'aria-live': 'polite' });
  const inp = h('input', { id: 'sq', type: 'search', list: 'matlist', value: q.q || '', placeholder: 'Ex.: bateria, geladeira, papelão…', autocomplete: 'off' });
  const sel = muniSelect('smun', localStorage.getItem('odal_mun') || '', 'Qualquer município');
  const locMsg = h('span', { class: 'muted small', role: 'status' }, S.loc ? 'Usando sua localização.' : '');
  async function run(materialId) {
    const term = inp.value.trim(); if (term.length < 2) return out.replaceChildren(errBox('Digite ao menos 2 caracteres.'));
    localStorage.setItem('odal_mun', sel.value);
    history.replaceState(null, '', '#/buscar?q=' + encodeURIComponent(term));
    out.replaceChildren(loading('Buscando…'));
    const p = new URLSearchParams({ q: term }); if (sel.value) p.set('municipio', sel.value);
    if (S.loc) { p.set('lat', S.loc.lat); p.set('lng', S.loc.lng); } if (materialId) p.set('material_id', materialId);
    try {
      const r = await api('/busca?' + p);
      if (!r.material) return out.replaceChildren(h('div', { class: 'empty' }, h('p', {}, `Não encontramos "${term}" no catálogo.`), h('p', {}, 'Tente outro nome ou consulte o ', h('a', { href: '#/guia' }, 'Guia de resíduos'), '.')));
      const m = r.material, cat = catOf(m.categoria);
      out.replaceChildren(h('div', {},
        r.correspondencias.length > 1 && h('p', {}, 'Você quis dizer: ', r.correspondencias.map(c => h('button', { class: 'badge', style: 'cursor:pointer;font-size:.95rem', 'aria-pressed': String(c.id === m.id), onclick: () => run(c.id) }, c.nome))),
        h('div', { class: 'card' }, h('h2', {}, `${cat.icone} ${m.nome}`), h('p', {}, h('span', { class: 'badge' }, 'Categoria: ' + cat.nome)),
          h('p', {}, h('b', {}, 'Como descartar: '), m.orientacao || cat.orientacao), h('p', {}, h('b', {}, 'Cuidados: '), cat.cuidados),
          m.recolhimento && h('p', {}, h('a', { class: 'btn small', href: '#/servicos?tipo=volumosos' }, 'Ver coleta de volumosos'))),
        h('h2', { style: 'margin-top:1.5rem' }, `Pontos que recebem ${m.nome.toLowerCase()}`),
        r.pontos.length ? h('div', {},
            h('p', { class: 'muted small' }, S.loc ? 'Ordenados pela distância em linha reta quando a localização do ponto é conhecida.' : 'Dica: use "Usar minha localização" para ordenar por distância.'),
            h('div', { class: 'grid wide' }, r.pontos.map(pt => pointCard(pt))),
            h('p', {}, h('a', { href: '#/mapa?mat=' + m.id }, 'Ver estes pontos no mapa')))
          : h('div', { class: 'empty' }, h('p', {}, 'Nenhum ponto cadastrado recebe este material' + (sel.value ? ' em ' + sel.value : '') + '.'),
              h('p', {}, 'Isso não significa que não exista: só há dados oficiais de Maceió por enquanto. Consulte a prefeitura do seu município.'))));
      say(`${r.pontos.length} pontos encontrados.`);
    } catch (e) { out.replaceChildren(errBox(e.message)); }
  }
  app.replaceChildren(h('div', { class: 'wrap section' }, h('h1', {}, 'Buscar descarte'),
    h('form', { onsubmit: e => { e.preventDefault(); run(); } },
      h('label', { for: 'sq' }, 'Qual resíduo você quer descartar?'), h('div', { class: 'row' }, inp, h('button', { class: 'btn' }, 'Buscar meu resíduo')),
      h('label', { for: 'smun' }, 'Onde você está?'), h('div', { class: 'row' }, sel,
        h('button', { type: 'button', class: 'btn ghost small', onclick: () => locate(() => { locMsg.textContent = 'Localização obtida.'; run(); }, m => locMsg.textContent = m) }, 'Usar minha localização'), locMsg)),
    matDatalist(), out));
  if (q.q) run();
}

async function pageMap(q) {
  const nav = S.nav; let points = [], markers = {}, selected = q.ponto ? +q.ponto : null, routeLayer = null;
  const list = h('div', { class: 'maplist', 'aria-label': 'Lista de pontos' });
  const status = h('p', { role: 'status', class: 'muted small' });
  const cat = h('select', { id: 'fcat', 'aria-label': 'Categoria de resíduo' }, h('option', { value: '' }, 'Todas as categorias'), S.cat.categorias.map(c => h('option', { value: c.slug, selected: c.slug === q.cat }, c.nome)));
  const mod = h('select', { id: 'fmod', 'aria-label': 'Tipo de ponto' }, h('option', { value: '' }, 'Todos os tipos'), Object.entries(MOD).map(([k, v]) => h('option', { value: k, selected: k === q.modalidade }, v)));
  const mun = muniSelect('fmun', localStorage.getItem('odal_mun') || '');
  const txt = h('input', { id: 'ftxt', type: 'search', placeholder: 'Nome ou endereço', 'aria-label': 'Buscar por nome ou endereço' });
  const mapEl = h('div', { id: 'map', role: 'region', 'aria-label': 'Mapa interativo. A lista de pontos ao lado traz as mesmas informações.' });
  const layout = h('div', { class: 'maplayout show-list' }), extra = h('div');
  const isMobile = () => matchMedia('(max-width:860px)').matches;
  const tBtn = (v, label) => h('button', { type: 'button', 'data-v': v, 'aria-pressed': String(v === 'list'), onclick: () => setView(v) }, label);
  const toggle = h('div', { class: 'viewtoggle', role: 'group', 'aria-label': 'Alternar entre lista e mapa' }, tBtn('list', '☰ Lista'), tBtn('map', '🗺️ Mapa'));
  function setView(v) {
    layout.classList.toggle('show-list', v === 'list'); layout.classList.toggle('show-map', v === 'map');
    toggle.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.v === v)));
    if (v === 'map') [50, 300].forEach(ms => setTimeout(() => S.map && S.map.invalidateSize(), ms));
  }
  layout.append(h('div', {},
    h('div', { class: 'filters' }, cat, mod, mun, txt,
      h('button', { class: 'btn ghost small full', onclick: () => locate(() => { load(); }, m => status.textContent = m) }, '📍 Usar minha localização (opcional)')),
    status, extra, list), mapEl);
  app.replaceChildren(h('div', { class: 'wrap' }, h('h1', { style: 'margin-top:1rem' }, 'Mapa de pontos de coleta'), toggle, layout));
  if (S.map) { S.map.remove(); S.map = null; }
  const map = S.map = L.map(mapEl).setView([-9.62, -35.73], 11);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' }).addTo(map);
  const layer = L.layerGroup().addTo(map); let me = null;
  [cat, mod, mun].forEach(e => e.addEventListener('change', () => { localStorage.setItem('odal_mun', mun.value); load(); }));
  let t; txt.addEventListener('input', () => { clearTimeout(t); t = setTimeout(load, 300); });
  const alive = () => S.nav === nav && S.map === map;

  function select(p, pan = true) {
    if (pan && isMobile()) setView('map');
    selected = p.id; list.querySelectorAll('.pcard').forEach(c => c.classList.toggle('sel', +c.dataset.id === p.id));
    if (pan && p.lat != null) map.setView([p.lat, p.lng], Math.max(map.getZoom(), 15)); markers[p.id]?.openPopup();
    list.querySelector(`[data-id="${p.id}"]`)?.scrollIntoView({ block: 'nearest' });
  }
  function popup(p) {
    return h('div', {}, h('b', {}, p.nome), h('br'), p.endereco, h('br'), badges(p)[1], p.aprox && h('div', { class: 'small' }, 'Posição aproximada (estimada pelo endereço).'),
      h('button', { class: 'btn small', style: 'margin:.3rem .3rem 0 0', onclick: () => showPoint(p.id) }, 'Ficha'),
      h('button', { class: 'btn small ghost', style: 'margin-top:.3rem', onclick: () => route(p) }, 'Traçar rota'));
  }
  function addMarker(p) {
    if (!alive() || p.lat == null || markers[p.id]) return;
    markers[p.id] = L.marker([p.lat, p.lng], { title: p.nome, alt: p.nome }).addTo(layer).bindPopup(() => popup(p));
    markers[p.id].on('click', () => select(p, false));
  }
  async function showOnMap(p) {
    if (p.lat == null) { status.textContent = 'Localizando endereço…'; const c = await coordsFor(p, true); if (!alive()) return;
      if (!c) { status.replaceChildren('Não foi possível localizar este endereço no mapa. ', link(osmSearch(p), 'Procurar no OpenStreetMap')); return; }
      status.textContent = 'Posição aproximada, estimada pelo endereço.'; addMarker(p); }
    select(p);
  }
  async function route(p) {
    if (p.lat == null) { await showOnMap(p); if (p.lat == null) return; }
    if (!S.loc) return locate(() => { load().then(() => route(p)); }, m => status.textContent = m + ' Use "Abrir rota no OpenStreetMap" na ficha.');
    status.textContent = 'Calculando rota…';
    try {
      const r = await fetch(`https://router.project-osrm.org/route/v1/driving/${S.loc.lng},${S.loc.lat};${p.lng},${p.lat}?overview=full&geometries=geojson`);
      const d = await r.json(); if (d.code !== 'Ok') throw 0;
      routeLayer && map.removeLayer(routeLayer);
      routeLayer = L.geoJSON(d.routes[0].geometry, { style: { color: '#0b57d0', weight: 5 } }).addTo(map); map.fitBounds(routeLayer.getBounds(), { padding: [30, 30] });
      const km = (d.routes[0].distance / 1000).toFixed(1).replace('.', ','), min = Math.round(d.routes[0].duration / 60);
      status.textContent = `Rota de carro até ${p.nome}: ${km} km, cerca de ${min} min (estimativa).`; say(status.textContent);
    } catch { status.replaceChildren('Não foi possível calcular a rota agora. ', link(`https://www.openstreetmap.org/directions?engine=fossgis_osrm_car&route=${S.loc.lat},${S.loc.lng}%3B${p.lat},${p.lng}`, 'Abrir no OpenStreetMap')); }
  }
  async function load() {
    list.replaceChildren(loading()); layer.clearLayers(); markers = {};
    const p = new URLSearchParams(); if (cat.value) p.set('categoria', cat.value); if (mod.value) p.set('modalidade', mod.value);
    if (mun.value) p.set('municipio', mun.value); if (txt.value.trim()) p.set('q', txt.value.trim());
    if (S.loc) { p.set('lat', S.loc.lat); p.set('lng', S.loc.lng); }
    try {
      let pts = (await api('/pontos?' + p)).pontos; if (!alive()) return;
      if (q.mat) pts = pts.filter(x => x.materiais.some(m => m.id === +q.mat));
      points = pts;
      if (S.loc) { me && map.removeLayer(me); me = L.circleMarker([S.loc.lat, S.loc.lng], { radius: 8, color: '#0b57d0', fillOpacity: .9 }).addTo(map).bindTooltip('Você está aqui'); }
      if (!pts.length) { list.replaceChildren(h('div', { class: 'empty' }, h('p', {}, 'Nenhum ponto encontrado com estes filtros.'), h('p', {}, 'Por enquanto só há dados oficiais de Maceió. Tente remover algum filtro.'))); status.textContent = ''; return; }
      status.textContent = `${pts.length} ponto(s)` + (S.loc ? ' — ordenados por distância quando a posição é conhecida' : '');
      list.replaceChildren(...pts.map(pt => pointCard(pt, { selected: pt.id === selected, onmap: showOnMap })));
      pts.forEach(addMarker);
      const sp = pts.find(x => x.id === selected); if (sp) await showOnMap(sp);
      // Endereços de rua sem coordenadas gravadas: posições já em cache aparecem direto; as demais só sob demanda (economiza dados).
      const pend = pts.filter(x => x.lat == null && x.consulta_geo);
      for (const x of pend) if (GEO[x.id]) { await coordsFor(x); addMarker(x); }
      const faltam = pend.filter(x => GEO[x.id] === undefined);
      extra.replaceChildren();
      const fit = () => { const pos = pts.filter(x => x.lat != null); if (pos.length) map.fitBounds(L.latLngBounds(pos.map(x => [x.lat, x.lng])), { padding: [40, 40], maxZoom: 14 }); return pos.length; };
      if (faltam.length) extra.append(h('div', { class: 'notice info small' }, `${faltam.length} endereço(s) ainda não aparecem no mapa. `,
        h('button', { type: 'button', class: 'btn small ghost', onclick: async e => {
          const b = e.currentTarget; b.disabled = true; let n = 0;
          for (const x of faltam) { if (!alive()) return; b.textContent = `Localizando ${++n}/${faltam.length}…`; await coordsFor(x); addMarker(x); await new Promise(r => setTimeout(r, 1100)); }
          if (!alive()) return;
          extra.replaceChildren(h('div', { class: 'notice info small' }, `${fit()} de ${pts.length} ponto(s) no mapa. Posições estimadas pelo endereço: confira antes de ir.`));
        } }, 'Mostrar no mapa')));
      if (!sp) fit();
    } catch (e) { if (alive()) list.replaceChildren(errBox(e.message)); }
  }
  await load();
  [100, 400, 1000].forEach(ms => setTimeout(() => S.map === map && map.invalidateSize(), ms));
  window.addEventListener('resize', () => S.map === map && map.invalidateSize());
}

function pageGuide() {
  const mats = c => S.cat.materiais.filter(m => m.categoria === c.slug);
  app.replaceChildren(h('div', { class: 'wrap section' }, h('h1', {}, 'Guia de resíduos'), h('p', { class: 'lead muted' }, 'Como preparar cada material, quais cuidados tomar e onde procurar um local adequado.'),
    S.cat.categorias.map(c => h('details', { id: c.slug }, h('summary', {}, `${c.icone} ${c.nome}`),
      h('p', {}, c.orientacao), h('p', {}, h('b', {}, 'Cuidados: '), c.cuidados),
      h('ul', {}, mats(c).map(m => h('li', {}, h('b', {}, m.nome), m.orientacao ? ' — ' + m.orientacao : ''))),
      h('div', { class: 'row' }, h('a', { class: 'btn small', href: '#/mapa?cat=' + c.slug }, 'Ver pontos desta categoria'), c.recolhimento && h('a', { class: 'btn small ghost', href: '#/servicos?tipo=volumosos' }, 'Coleta de volumosos'))))));
}

function pageAbout() {
  app.replaceChildren(h('div', { class: 'wrap section' }, h('h1', {}, 'Sobre o projeto'),
    h('p', {}, 'O Onde Descartar AL é uma plataforma digital de interesse público que conecta cidadãos às informações sobre descarte de resíduos sólidos em Alagoas, usando georreferenciamento, pesquisa inteligente e recursos de acessibilidade.'),
    h('h2', {}, 'De onde vêm os dados'),
    h('ul', {}, h('li', {}, 'Maceió: ecopontos, coleta seletiva, coleta domiciliar e coleta de volumosos, conforme páginas oficiais da Prefeitura de Maceió e da Alurb (maceio.al.gov.br), conferidas em 07/11/2026.'),
      h('li', {}, 'Cada ponto mostra a fonte, o link e a data da conferência. Campos sem informação aparecem como "Não informado".'),
      h('li', {}, 'Só afirmamos que um local recebe um material quando isso consta na fonte oficial.'),
      h('li', {}, 'Mapas e rotas usam o OpenStreetMap. As posições no mapa de pontos sem coordenadas cadastradas são estimadas pelo endereço e podem ser aproximadas.')),
    h('div', { class: 'notice' }, 'Os demais municípios de Alagoas ainda não têm dados cadastrados. Gestores e cooperativas podem incluí-los pelo painel de gestão. Horários, prazos e canais podem mudar: na dúvida, confirme com o órgão responsável (em Maceió, Alurb, 156).')));
}

function pagePickup() {
  const res = h('div', { 'aria-live': 'polite' }), chan = h('div');
  const f = {}; const fld = (id, label, el) => [h('label', { for: id }, label), (f[id] = el)];
  const inp = (id, type = 'text', req = true, ph = '') => h('input', { id, type, required: req, placeholder: ph, maxlength: 200, style: 'width:100%' });
  const mun = muniSelect('municipio', 'Maceió', 'Selecione…'); mun.required = true; mun.style.width = '100%';
  const submit = h('button', { class: 'btn' }, 'Enviar solicitação'), note = h('p', { class: 'notice info', hidden: true });
  async function showChannels() {
    chan.replaceChildren(); note.hidden = true; submit.hidden = false; if (!mun.value) return;
    try { const r = await api('/canais?municipio=' + encodeURIComponent(mun.value));
      if (r.canais.length) { submit.hidden = true; note.hidden = false; note.textContent = `Em ${mun.value}, o pedido é feito diretamente pelos canais oficiais acima (gratuito).`;
        chan.replaceChildren(h('div', { class: 'card' }, h('h3', {}, 'Canais oficiais em ' + mun.value), h('ul', {}, r.canais.map(c => h('li', {}, c.nome, c.telefone && ': ', c.telefone && h('b', {}, c.telefone), c.url && [' — ', link(c.url, 'Saiba mais')]))),
          mun.value === 'Maceió' && h('p', { class: 'small muted' }, 'Informe endereço completo com ponto de referência e os itens. Prazo divulgado: até 15 dias úteis. Se puder levar o item, use um ecoponto: ', h('a', { href: '#/servicos?tipo=ecopontos' }, 'ver ecopontos'), '.')));
      } else chan.replaceChildren(h('div', { class: 'notice' }, `Ainda não há canal oficial cadastrado para ${mun.value}. Você pode registrar a solicitação abaixo, que será encaminhada pela gestão, ou procurar a secretaria de meio ambiente/limpeza urbana da prefeitura.`));
    } catch {} }
  mun.addEventListener('change', showChannels);
  const items = h('textarea', { id: 'itens', required: true, maxlength: 500, placeholder: 'Ex.: 1 sofá de 3 lugares e 1 geladeira' }), obs = h('textarea', { id: 'observacao', maxlength: 500 });
  const form = h('form', { onsubmit: async e => { e.preventDefault(); submit.disabled = true; res.replaceChildren(loading('Enviando…'));
      try { const r = await api('/recolhimento', { method: 'POST', body: { nome: f.nome.value, telefone: f.telefone.value, email: f.email.value, municipio: mun.value, endereco: f.endereco.value, itens: items.value, observacao: obs.value } });
        form.reset(); res.replaceChildren(h('div', { class: 'notice info' }, h('b', {}, 'Solicitação registrada! '), `Protocolo ${r.protocolo}. A solicitação será encaminhada aos responsáveis; o agendamento depende do órgão ou da cooperativa do seu município.`)); say('Solicitação enviada.');
      } catch (er) { res.replaceChildren(errBox(er.message)); } submit.disabled = false; } },
    h('label', { for: 'municipio' }, 'Município'), mun, chan, note,
    fld('nome', 'Nome completo', inp('nome')), fld('telefone', 'Telefone com DDD', inp('telefone', 'tel', true, '(82) 9XXXX-XXXX')), fld('email', 'E-mail (opcional)', inp('email', 'email', false)),
    fld('endereco', 'Endereço de retirada', inp('endereco')),
    h('label', { for: 'itens' }, 'Itens a recolher'), items, h('label', { for: 'observacao' }, 'Observações (opcional)'), obs,
    h('p', { class: 'muted small' }, 'Usamos seus dados apenas para encaminhar esta solicitação.'), submit);
  app.replaceChildren(h('div', { class: 'wrap section', style: 'max-width:720px' }, h('h1', {}, 'Recolhimento de resíduos volumosos'),
    h('p', {}, 'Para móveis, colchões e eletrodomésticos. Selecione seu município para ver os canais oficiais.'),
    h('div', { class: 'notice' }, 'Antes de solicitar: se o item estiver em bom estado, considere doá-lo. Não deixe volumosos em calçadas ou terrenos.'), form, res));
  showChannels();
}

/* ---------- administração ---------- */
function logout(silent) { if (S.token && !silent) api('/logout', { method: 'POST' }).catch(() => {}); S.token = null; S.user = null; sessionStorage.clear(); if (location.hash.startsWith('#/admin')) route(); }
function pageAdmin() { S.token ? adminPanel() : adminLogin(); }
function adminLogin() {
  const msg = h('div', { 'aria-live': 'polite' });
  app.replaceChildren(h('div', { class: 'wrap section', style: 'max-width:440px' }, h('h1', {}, 'Área de gestão'), h('p', { class: 'muted' }, 'Acesso para gestores institucionais e representantes de cooperativas.'),
    h('form', { onsubmit: async e => { e.preventDefault(); msg.replaceChildren(loading('Entrando…'));
        try { const r = await api('/login', { method: 'POST', body: { email: $('#em').value, senha: $('#pw').value } });
          S.token = r.token; S.user = r.usuario; sessionStorage.setItem('odal_token', r.token); sessionStorage.setItem('odal_user', JSON.stringify(r.usuario)); adminPanel();
        } catch (er) { msg.replaceChildren(errBox(er.message)); } } },
      h('label', { for: 'em' }, 'E-mail'), h('input', { id: 'em', type: 'email', required: true, autocomplete: 'username', style: 'width:100%' }),
      h('label', { for: 'pw' }, 'Senha'), h('input', { id: 'pw', type: 'password', required: true, autocomplete: 'current-password', style: 'width:100%' }),
      h('p', {}, h('button', { class: 'btn' }, 'Entrar')), msg)));
}
async function adminPanel() {
  const body = h('div'); let tab = 'pontos';
  const tabs = h('div', { class: 'tabs', role: 'tablist' });
  const draw = () => { tabs.replaceChildren(...[['pontos', 'Pontos de coleta'], ['solic', 'Solicitações de recolhimento']].map(([k, l]) => h('button', { role: 'tab', 'aria-selected': String(tab === k), onclick: () => { tab = k; draw(); (k === 'pontos' ? adminPoints : adminPickups)(body); } }, l))); };
  app.replaceChildren(h('div', { class: 'wrap section' }, h('div', { class: 'row', style: 'justify-content:space-between;align-items:center' },
    h('h1', { style: 'margin:0' }, 'Painel de gestão'), h('div', {}, `${S.user.nome} (${S.user.papel}) `, h('button', { class: 'btn small ghost', onclick: () => logout() }, 'Sair'))), tabs, body));
  draw(); adminPoints(body);
}
async function adminPoints(box) {
  box.replaceChildren(loading());
  try {
    const { pontos } = await api('/admin/pontos');
    const total = pontos.length, ver = pontos.filter(p => p.verificado).length, old = pontos.filter(p => !p.verificado || (!p.horario && p.modalidade === 'ecoponto')).length;
    box.replaceChildren(
      h('div', { class: 'stats', style: 'margin-bottom:1rem' }, h('div', {}, h('b', {}, total), 'pontos'), h('div', {}, h('b', {}, new Set(pontos.map(p => p.municipio)).size), 'municípios'), h('div', {}, h('b', {}, ver), 'verificados'), h('div', {}, h('b', {}, old), 'precisam de atualização')),
      h('p', {}, h('button', { class: 'btn', onclick: () => pointForm(box) }, '+ Cadastrar ponto')),
      h('div', { class: 'tablewrap' }, h('table', {}, h('thead', {}, h('tr', {}, ['Nome', 'Município', 'Tipo', 'Situação', 'Ações'].map(t => h('th', {}, t)))),
        h('tbody', {}, pontos.map(p => h('tr', {}, h('td', {}, p.nome), h('td', {}, p.municipio), h('td', {}, MOD[p.modalidade]),
          h('td', {}, p.ativo ? '' : h('span', { class: 'badge' }, 'Inativo'), p.verificado ? h('span', { class: 'badge ok' }, '✔ Verificado') : h('span', { class: 'badge warn' }, '⚠ Não verificado'), p.lat == null && h('span', { class: 'badge' }, 'Sem coordenadas')),
          h('td', {}, h('button', { class: 'btn small ghost', onclick: () => pointForm(box, p) }, 'Editar'), ' ',
            h('button', { class: 'btn small danger', onclick: async () => { if (confirm(`Excluir "${p.nome}"? Esta ação não pode ser desfeita. (Para apenas ocultar, desmarque "Publicado" ao editar.)`)) { try { await api('/admin/pontos/' + p.id, { method: 'DELETE' }); adminPoints(box); } catch (e) { alert(e.message); } } } }, 'Excluir'))))))));
  } catch (e) { box.replaceChildren(errBox(e.message)); }
}
function pointForm(box, p = null) {
  const gestor = S.user.papel === 'gestor', f = {}, msg = h('div', { 'aria-live': 'polite' });
  const t = (id, label, v, extra = {}) => [h('label', { for: id }, label), (f[id] = h('input', { id, value: v ?? '', style: 'width:100%', ...extra }))];
  const ta = (id, label, v, extra = {}) => [h('label', { for: id }, label), (f[id] = h('textarea', { id, maxlength: 600, ...extra }, v ?? ''))];
  f.municipio = h('select', { id: 'pm', style: 'width:100%' }, S.cat.municipios.map(m => h('option', { value: m, selected: p ? m === p.municipio : m === 'Maceió' })));
  f.modalidade = h('select', { id: 'pmod', style: 'width:100%' }, Object.entries(MOD).map(([k, v]) => h('option', { value: k, selected: p?.modalidade === k }, v)));
  const have = new Set((p?.materiais || []).map(m => m.id));
  const checks = S.cat.categorias.map(c => h('fieldset', {}, h('legend', {}, c.icone + ' ' + c.nome), h('div', { class: 'checks' }, S.cat.materiais.filter(m => m.categoria === c.slug).map(m => h('label', {}, h('input', { type: 'checkbox', value: m.id, checked: have.has(m.id) }), m.nome)))));
  const pickEl = h('div', { id: 'pick', role: 'application', 'aria-label': 'Mapa para escolher a localização. Alternativamente, digite latitude e longitude.' });
  const pub = h('input', { type: 'checkbox', id: 'pub', checked: p ? !!p.ativo : true }), ver = h('input', { type: 'checkbox', id: 'ver', checked: !!p?.verificado });
  const form = h('form', { onsubmit: async e => { e.preventDefault(); msg.replaceChildren(loading('Salvando…'));
      const body = { nome: f.nome.value, modalidade: f.modalidade.value, endereco: f.endereco.value, municipio: f.municipio.value, lat: f.lat.value.replace(',', '.'), lng: f.lng.value.replace(',', '.'),
        consulta_geo: f.consulta_geo.value, horario: f.horario.value, telefone: f.telefone.value, limite_diario: f.limite_diario.value, observacoes: f.observacoes.value,
        fonte: f.fonte.value, fonte_url: f.fonte_url.value, ativo: pub.checked, verificado: gestor && ver.checked,
        materiais: [...form.querySelectorAll('.checks input:checked')].map(i => +i.value) };
      try { await api('/admin/pontos' + (p ? '/' + p.id : ''), { method: p ? 'PUT' : 'POST', body }); adminPoints(box); } catch (er) { msg.replaceChildren(errBox(er.message)); } } },
    h('h2', {}, p ? 'Editar ponto' : 'Novo ponto de coleta'),
    t('nome', 'Nome do ponto', p?.nome, { required: true, maxlength: 120 }), h('label', { for: 'pmod' }, 'Modalidade'), f.modalidade,
    t('endereco', 'Endereço completo', p?.endereco, { required: true, maxlength: 250 }), h('label', { for: 'pm' }, 'Município'), f.municipio,
    h('p', { class: 'muted small' }, 'Clique no mapa para preencher latitude e longitude. Se deixar em branco, o mapa estimará a posição pelo endereço.'), pickEl,
    h('div', { class: 'row' }, h('div', {}, ...t('lat', 'Latitude', p?.lat, { inputmode: 'decimal' })), h('div', {}, ...t('lng', 'Longitude', p?.lng, { inputmode: 'decimal' }))),
    t('consulta_geo', 'Texto para localizar no mapa (opcional)', p?.consulta_geo, { maxlength: 200, placeholder: 'Ex.: Rua X 123, Bairro, Cidade, Alagoas' }),
    t('horario', 'Horário de funcionamento', p?.horario, { maxlength: 200, placeholder: 'Ex.: Seg a Sex, 8h–17h' }), t('telefone', 'Telefone', p?.telefone, { maxlength: 60 }),
    t('limite_diario', 'Limite por entrega/cidadão', p?.limite_diario, { maxlength: 120, placeholder: 'Ex.: até 1 m³' }),
    ta('observacoes', 'Observações (dias de coleta, regras, avisos)', p?.observacoes),
    t('fonte', 'Fonte da informação', p?.fonte, { maxlength: 200, placeholder: 'Ex.: Prefeitura — página oficial' }), t('fonte_url', 'Link da fonte (opcional)', p?.fonte_url, { maxlength: 300, type: 'url' }),
    h('h3', { style: 'margin-top:1rem' }, 'Materiais aceitos'), checks,
    h('label', { for: 'pub', style: 'font-weight:400' }, pub, ' Publicado (visível ao público)'),
    gestor ? h('label', { for: 'ver', style: 'font-weight:400' }, ver, ' Informações verificadas em fonte oficial (registra a data de hoje)') : h('p', { class: 'muted small' }, 'Pontos editados por cooperativas passam por verificação do gestor antes de receber o selo de verificado.'),
    h('div', { class: 'row', style: 'margin-top:1rem' }, h('button', { class: 'btn' }, 'Salvar'), h('button', { type: 'button', class: 'btn ghost', onclick: () => adminPoints(box) }, 'Cancelar')), msg);
  box.replaceChildren(form);
  const m = L.map(pickEl).setView(p && p.lat != null ? [p.lat, p.lng] : [-9.6658, -35.7353], p && p.lat != null ? 15 : 11);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OpenStreetMap' }).addTo(m);
  let mk = p && p.lat != null ? L.marker([p.lat, p.lng]).addTo(m) : null;
  m.on('click', e => { mk ? mk.setLatLng(e.latlng) : mk = L.marker(e.latlng).addTo(m); f.lat.value = e.latlng.lat.toFixed(6); f.lng.value = e.latlng.lng.toFixed(6); });
}
async function adminPickups(box) {
  box.replaceChildren(loading());
  try {
    const { solicitacoes } = await api('/admin/recolhimentos');
    const st = ['recebida', 'encaminhada', 'agendada', 'concluida', 'cancelada'];
    box.replaceChildren(solicitacoes.length ? h('div', { class: 'tablewrap' }, h('table', {}, h('thead', {}, h('tr', {}, ['Protocolo', 'Solicitante', 'Local', 'Itens', 'Status'].map(x => h('th', {}, x)))),
      h('tbody', {}, solicitacoes.map(s => h('tr', {}, h('td', {}, `RV-${s.criado_em.slice(0, 4)}-${String(s.id).padStart(5, '0')}`, h('br'), h('span', { class: 'small muted' }, s.criado_em.replace('T', ' '))),
        h('td', {}, s.nome, h('br'), s.telefone, s.email && h('br'), s.email), h('td', {}, s.endereco, h('br'), s.municipio), h('td', {}, s.itens, s.observacao && h('p', { class: 'small muted' }, 'Obs.: ' + s.observacao)),
        h('td', {}, h('select', { 'aria-label': 'Status da solicitação ' + s.id, onchange: async e => { try { await api('/admin/recolhimentos/' + s.id, { method: 'PUT', body: { status: e.target.value } }); say('Status atualizado.'); } catch (er) { alert(er.message); } } }, st.map(x => h('option', { value: x, selected: x === s.status }, x))))))))) : h('div', { class: 'empty' }, 'Nenhuma solicitação recebida.'));
  } catch (e) { box.replaceChildren(errBox(e.message)); }
}

/* ---------- roteador ---------- */
function parseHash() { const [p, qs] = (location.hash.slice(1) || '/').split('?'); return [p, Object.fromEntries(new URLSearchParams(qs || ''))]; }
const ROUTES = { '/': pageHome, '/buscar': pageSearch, '/servicos': pageServices, '/mapa': pageMap, '/guia': pageGuide, '/recolhimento': pagePickup, '/sobre': pageAbout, '/admin': pageAdmin };
const TITLES = { '/buscar': 'Buscar descarte', '/servicos': 'Serviços de coleta', '/mapa': 'Mapa de pontos', '/guia': 'Guia de resíduos', '/recolhimento': 'Recolhimento', '/sobre': 'Sobre', '/admin': 'Gestão' };
async function route() {
  const [path, q] = parseHash(); S.nav++; if (S.map) { S.map.remove(); S.map = null; }
  document.querySelectorAll('nav a').forEach(a => a.removeAttribute('aria-current'));
  document.querySelector(`nav a[href="#${path}"]`)?.setAttribute('aria-current', 'page');
  $('#nav').classList.remove('open'); $('#menuBtn').setAttribute('aria-expanded', 'false');
  try { await (ROUTES[path] || pageHome)(q); } catch (e) { app.replaceChildren(h('div', { class: 'wrap section' }, errBox(e.message))); }
  document.title = (TITLES[path] || 'Início') + ' — Onde Descartar AL';
  if (!(path === '/buscar' && q.q)) window.scrollTo(0, 0); app.focus({ preventScroll: true });
}

/* ---------- inicialização e acessibilidade ---------- */
function prefs() {
  const p = JSON.parse(localStorage.getItem('odal_prefs') || '{}');
  document.body.classList.toggle('fs-lg', !!p.fs); document.body.classList.toggle('hc', !!p.hc);
  $('#fontBtn').setAttribute('aria-pressed', !!p.fs); $('#contrastBtn').setAttribute('aria-pressed', !!p.hc);
  return p;
}
$('#fontBtn').onclick = () => { const p = prefs(); p.fs = !p.fs; localStorage.setItem('odal_prefs', JSON.stringify(p)); prefs(); };
$('#contrastBtn').onclick = () => { const p = prefs(); p.hc = !p.hc; localStorage.setItem('odal_prefs', JSON.stringify(p)); prefs(); };
$('#menuBtn').onclick = e => { const o = $('#nav').classList.toggle('open'); e.currentTarget.setAttribute('aria-expanded', o); };
prefs();
(async () => {
  app.replaceChildren(h('div', { class: 'wrap section' }, loading()));
  try { S.cat = await api('/catalogo'); } catch (e) { return app.replaceChildren(h('div', { class: 'wrap section' }, errBox(e.message), h('div', { class: 'notice' }, 'Não abra o index.html diretamente nem por Live Server. Inicie o servidor com "python3 server.py" e acesse http://127.0.0.1:8000'), h('button', { class: 'btn', onclick: () => location.reload() }, 'Tentar novamente'))); }
  window.addEventListener('hashchange', route); route();
})();
