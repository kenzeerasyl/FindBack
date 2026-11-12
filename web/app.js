'use strict';

const get = id => document.getElementById(id);
const element = (tag, text, className) => {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
};
const placeNames = {
  Library: 'Библиотека', Cafeteria: 'Кафе', Classroom: 'Аудитория',
  Office: 'Офис', Lab: 'Лаборатория',
};
const symbols = {Library:'≡', Cafeteria:'◒', Classroom:'▤', Office:'□', Lab:'✧'};
const scenarioNames = {
  baseline:'Обычный поиск', weak_reports:'Ненадёжные подсказки',
  urgent:'Мало времени', isolated_library:'Библиотека недоступна',
};
const scenarioHelp = {
  baseline:'Карта открыта. Подсказки обычно полезны, но могут быть ошибочными.',
  weak_reports:'Сообщения очевидцев менее надёжны.',
  urgent:'Доступно 10 единиц времени.',
  isolated_library:'Оба прохода к библиотеке закрыты.',
};
const statuses = {active:'Поиск идёт', found:'Вещь найдена', stopped:'Поиск завершён', exhausted:'Время истекло'};
const outcomes = {yes:'Могли видеть вещь', no:'Вещь не видели', found:'Вещь найдена', not_found:'Вещь не найдена'};
const policies = {planner:'Планировщик Беллмана', nearest:'Ближайшее место', highest_belief:'Самое вероятное место'};
const place = key => placeNames[key] || key;
const pct = value => new Intl.NumberFormat('ru', {style:'percent',maximumFractionDigits:2}).format(value);
const decimal = value => Number(value).toFixed(3);
const cellKey = cell => cell.join(',');
const storageKey = 'findback.searches.v2';
const makeId = () => globalThis.crypto.randomUUID();
const actName = action => action.kind === 'stop' ? 'Завершить поиск' :
  (action.kind === 'search' ? 'Проверить: ' : 'Уточнить: ') + place(action.target);

let config, state, sessionToken, scenarioId, activeId, preview, branchLabel;
let editing = false;
let busy = false;
let saved = {active:null, cases:{}};

function table(headers, rows, highlighted = -1) {
  const wrap = element('div', undefined, 'table-wrap');
  const result = element('table');
  const head = result.createTHead().insertRow();
  for (const header of headers) {
    const th = element('th', header);
    th.scope = 'col';
    head.append(th);
  }
  const body = result.createTBody();
  rows.forEach((row,index) => {
    const tr = body.insertRow();
    if (index === highlighted) tr.className = 'selected-row';
    row.forEach(value => tr.insertCell().append(value));
  });
  wrap.append(result);
  return wrap;
}

function selectOptions(id, entries, selected) {
  const field = get(id);
  field.replaceChildren(...entries.map(([value,label]) => new Option(label,value)));
  if (entries.some(([value]) => value === selected)) field.value = selected;
}

function notice(id, message) {
  get(id).textContent = message;
  get(id).hidden = !message;
}

function readSaved() {
  try {
    const data = JSON.parse(localStorage.getItem(storageKey));
    if (data && typeof data.cases === 'object' && data.cases !== null) saved = data;
  } catch {
    notice('message','Хранилище браузера недоступно. Историю можно скачать в файл.');
  }
}

function saveCurrent() {
  const settings = {
    scenario:scenarioId, item:state.item, description:state.description,
    mode:state.mode, seed:state.seed ?? 42, depth:state.depth,
    budget:state.initial_budget, start_at:state.start_at, last_seen:state.last_seen,
  };
  const events = state.history.map(event => {
    const {type, target, outcome, event_id, note, cell} = event;
    return {type,target,outcome,event_id,note,cell};
  });
  saved.active = activeId;
  saved.cases[activeId] = {settings, events, status:state.status, budget:state.budget, modified:Date.now()};
  try {
    localStorage.setItem(storageKey, JSON.stringify(saved));
    get('storage-status').textContent = 'Сохранено в этом браузере';
  } catch {
    get('storage-status').textContent = 'Сохранение недоступно';
  }
  renderSaved();
}

function renderSaved() {
  const cases = Object.entries(saved.cases).sort((a,b) => b[1].modified - a[1].modified);
  get('saved-count').textContent = cases.length ? String(cases.length) : '';
  const list = get('saved-list');
  if (!cases.length) {
    list.replaceChildren(element('p','Создай поиск, чтобы он появился здесь.','empty'));
    return;
  }
  list.replaceChildren(...cases.map(([id,entry]) => {
    const card = element('article',undefined,'card saved-item');
    const body = element('div');
    const updated = new Date(entry.modified).toLocaleString('ru',{dateStyle:'short',timeStyle:'short'});
    body.append(element('h2',entry.settings.item), element('p',
      (statuses[entry.status] || 'Поиск') + ' · осталось ' + entry.budget + ' ед. · ' + updated));
    const button = element('button', id === activeId ? 'К поиску' : 'Открыть','button secondary small');
    button.addEventListener('click', () => id === activeId ? showPage('search') : restore(id));
    card.append(body,button);
    return card;
  }));
}

function readableError(message) {
  if (message?.startsWith('Evidence already processed')) return 'Эта подсказка уже учтена. Проверь историю поиска.';
  if (message?.includes('impossible')) return 'Этот результат невозможен при текущих настройках модели.';
  if (message?.includes('budget') || message?.includes('blocked')) return 'Действие недоступно. Проверь маршрут и оставшееся время.';
  if (message?.includes('Session expired')) return 'Подключение к поиску потеряно. Обнови страницу, чтобы восстановить его.';
  return 'Не удалось сохранить действие. Проверь данные и попробуй ещё раз.';
}

async function request(operation, payload, {dialog, caseId} = {}) {
  if (busy) return false;
  busy = true;
  const submit = dialog?.querySelector('button[type=submit]');
  const formError = dialog?.querySelector('.form-error');
  if (submit) submit.disabled = true;
  if (formError) formError.textContent = '';
  notice('error','');
  notice('message','');
  try {
    const response = await fetch('/api/session', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({operation,session:sessionToken,revision:state?.revision,...payload}),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(readableError(result.error));
    sessionToken = result.session;
    scenarioId = result.scenario_id;
    state = result.state;
    if (operation === 'start' || operation === 'restore') {
      activeId = caseId || makeId();
      editing = false;
      get('show-expansion').checked = false;
      showPage('search');
    }
    if (operation !== 'toggle') {
      const latestSearch = [...state.history].reverse().find(event => event.type === 'search');
      preview = state.actions[0]?.target || latestSearch?.target ||
        Object.entries(state.belief).sort((a,b) => b[1] - a[1])[0][0];
      branchLabel = state.chosen;
    }
    if (state.status !== 'active') editing = false;
    get('trace-range').value = 0;
    saveCurrent();
    render();
    dialog?.close();
    if (operation === 'report') notice('message','Подсказка сохранена. Вероятности обновлены.');
    return true;
  } catch (error) {
    const message = error instanceof TypeError ?
      'Не удалось связаться с приложением. Проверь, открыто ли окно запуска.' : error.message;
    if (formError) formError.textContent = message;
    else notice('error',message);
    return false;
  } finally {
    if (submit) submit.disabled = false;
    busy = false;
  }
}

function restore(id) {
  const {settings,events} = saved.cases[id];
  return request('restore',{settings,events},{caseId:id});
}

function render() {
  get('workspace').hidden = false;
  get('title').textContent = state.item;
  get('case-context').textContent = 'Учебный кампус · ' + (state.mode === 'simulation' ? 'Симуляция' : 'Поиск вещи');
  get('case-description').textContent = [state.description,
    state.last_seen ? 'Последний раз видели: ' + place(state.last_seen) : '']
    .filter(Boolean).join(' · ');
  get('case-description').hidden = !get('case-description').textContent;
  get('status').dataset.status = state.status;
  get('status').textContent = statuses[state.status];
  renderRecommendation();
  renderBelief();
  renderMap();
  renderHistory();
  renderRankings();
  renderAssumptions();
}

function meter(value) {
  const track = element('div',undefined,'meter');
  const fill = element('span');
  fill.style.width = Math.max(0,Math.min(100,100 * value)) + '%';
  track.append(fill);
  return track;
}

function renderRecommendation() {
  const best = state.actions[0];
  const panel = get('recommendation');
  panel.replaceChildren();
  get('controls').hidden = !best;
  get('add-report').hidden = state.mode !== 'manual';
  if (best) {
    const found = best.branches.find(branch => branch.observation === 'found');
    let description = 'Завершение сохраняет оставшееся время. Доступные действия не улучшают ожидаемый результат.';
    if (best.kind === 'search') {
      const steps = state.routes[best.target].steps;
      description = 'До места ' + steps + ' шагов. После осмотра совет обновится с учётом результата.';
    }
    if (best.kind === 'ask') description = 'Уточнение займёт меньше времени, чем осмотр. Ответ поможет выбрать, куда идти.';
    const tags = element('div',undefined,'rec-tags');
    if (best.duration) tags.append(element('span',best.duration + ' ед. времени'));
    if (found) tags.append(element('span',pct(found.probability) + ' шанс находки при осмотре'));
    panel.append(element('p',actName(best),'rec-title'), element('p',description,'rec-copy'),tags);
    get('run-action').textContent = state.mode === 'simulation' ? 'Выполнить действие' :
      best.kind === 'stop' ? 'Завершить поиск' : 'Записать результат';
  } else {
    panel.append(element('p',statuses[state.status],'rec-title'),
      element('p','История и расчёты доступны ниже.','rec-copy'));
  }
  const line = element('div',undefined,'budget-line');
  line.append(element('span','Осталось времени'),element('b',state.budget + ' из ' + state.initial_budget + ' ед.'));
  get('budget-view').replaceChildren(line,meter(state.budget / state.initial_budget));
}

function selectPreview(name) {
  preview = name;
  get('trace-range').value = 0;
  renderMap();
  for (const button of get('belief').querySelectorAll('button')) {
    button.setAttribute('aria-pressed', String(button.dataset.location === preview));
  }
}

function renderBelief() {
  const entries = Object.entries(state.belief).sort((a,b) => b[1] - a[1]);
  get('belief').replaceChildren(...entries.map(([name,value]) => {
    const route = state.routes[name];
    const checked = state.history.some(event => event.type === 'search' && event.target === name);
    const button = element('button',undefined,'location-row');
    button.dataset.location = name;
    button.setAttribute('aria-pressed', String(name === preview));
    const body = element('div');
    const caption = route.steps === null ? 'Нет маршрута' :
      (route.steps === 0 ? 'Ты здесь' : route.steps + ' шагов') + (checked ? ' · уже проверено' : '');
    body.append(element('span',place(name),'location-name'),
      element('span',caption,'location-sub' + (route.steps === null ? ' blocked' : '')));
    const result = element('div');
    result.append(element('b',pct(value),'location-number'),meter(value));
    button.append(element('span',symbols[name] || '·','location-icon'),body,result);
    button.addEventListener('click', () => selectPreview(name));
    return button;
  }));
}

const mapBounds = {left:.085, top:.092, width:.83, height:.79};

function cellPosition(row,col) {
  return [
    mapBounds.left + (col + .5) * mapBounds.width / state.rows[0].length,
    mapBounds.top + (row + .5) * mapBounds.height / state.rows.length,
  ];
}

function mapShape(ctx, x, y, w, h, radius, color) {
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.roundRect(x,y,w,h,radius);
  ctx.fill();
}

function drawMap() {
  if (!state || get('search').hidden) return;
  const canvas = get('map-art');
  const {width,height} = canvas.getBoundingClientRect();
  if (!width || !height) return;
  const scale = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);
  const ctx = canvas.getContext('2d');
  ctx.scale(scale,scale);
  const cols = state.rows[0].length;
  const cellWidth = mapBounds.width * width / cols;
  const cellHeight = mapBounds.height * height / state.rows.length;
  const left = mapBounds.left * width;
  const top = mapBounds.top * height;
  ctx.fillStyle = '#e4ecd6';
  ctx.fillRect(0,0,width,height);
  for (let i=0;i<36;i++) {
    const x = (i * .173 + .027) % 1;
    const y = (i * .327 + .013) % 1;
    if (x > .078 && x < .924 && y > .075 && y < .895) continue;
    const radius = 4 + (i % 4) * 1.5;
    ctx.fillStyle = '#bbd0a7';
    ctx.beginPath();
    ctx.arc(x * width, y * height, radius,0,Math.PI*2);
    ctx.fill();
    ctx.fillStyle = '#cadcba';
    ctx.beginPath();
    ctx.arc(x * width - 2,y * height - 2,radius * .65,0,Math.PI*2);
    ctx.fill();
  }
  mapShape(ctx,left-4,top-4,cellWidth*cols+8,cellHeight*state.rows.length+8,12,'#d8e4c7');
  mapShape(ctx,left,top,cellWidth*cols,cellHeight*state.rows.length,9,'#f4f2e6');
  ctx.strokeStyle = '#dfdfcf';
  ctx.lineWidth = .65;
  for (let row=1;row<state.rows.length;row++) {
    ctx.beginPath();
    ctx.moveTo(left,top+row*cellHeight);
    ctx.lineTo(left+cellWidth*cols,top+row*cellHeight);
    ctx.stroke();
  }
  for (let col=1;col<cols;col++) {
    ctx.beginPath();
    ctx.moveTo(left+col*cellWidth,top);
    ctx.lineTo(left+col*cellWidth,top+cellHeight*state.rows.length);
    ctx.stroke();
  }
  state.original_rows.forEach((line,row) => {
    for (let start=0;start<line.length;start++) {
      if (line[start] !== '#') continue;
      let end = start+1;
      while (line[end] === '#') end++;
      const x = left + start*cellWidth + 2;
      const y = top + row*cellHeight + 3;
      const w = (end-start)*cellWidth-4;
      const h = cellHeight-6;
      mapShape(ctx,x+2,y+2,w,h,5,'#a7bca8');
      mapShape(ctx,x,y,w,h,5,'#c6d7c5');
      mapShape(ctx,x+4,y+4,w-8,h-8,3,'#d7e3d2');
      ctx.fillStyle = '#bdcfbd';
      for (let vent=x+10;vent<x+w-7;vent+=15) ctx.fillRect(vent,y+h/2-1,6,3);
      start = end-1;
    }
  });
  const closed = new Set(state.closed.map(cellKey));
  for (const [r,c] of state.closed) {
    mapShape(ctx,left+c*cellWidth+2,top+r*cellHeight+2,cellWidth-4,cellHeight-4,3,'#e8b59a');
    ctx.strokeStyle = '#92563b';
    ctx.beginPath();
    ctx.moveTo(left+c*cellWidth+5,top+r*cellHeight+5);
    ctx.lineTo(left+(c+1)*cellWidth-5,top+(r+1)*cellHeight-5);
    ctx.stroke();
  }
  const route = state.routes[preview];
  if (get('show-expansion').checked) {
    const count = Number(get('trace-range').value);
    route.expanded.slice(0,count).forEach(([r,c]) => {
      if (!closed.has(cellKey([r,c]))) mapShape(ctx,left+c*cellWidth+2,top+r*cellHeight+2,cellWidth-4,cellHeight-4,3,'#d7e5bf');
    });
    if (count < route.expanded.length) return;
  }
  if (route.path.length > 1) {
    ctx.beginPath();
    route.path.forEach(([r,c],index) => {
      const [x,y] = cellPosition(r,c);
      if (index === 0) ctx.moveTo(x*width,y*height);
      else ctx.lineTo(x*width,y*height);
    });
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.lineWidth = 10;
    ctx.strokeStyle = '#fffef5';
    ctx.stroke();
    ctx.lineWidth = 5;
    ctx.strokeStyle = '#19735e';
    ctx.stroke();
  }
}

function renderMap() {
  const route = state.routes[preview];
  get('map-location').textContent = place(preview);
  get('map-caption').textContent = route.steps === null ? 'С текущей позиции сюда нет маршрута.' :
    (route.steps ? route.steps + ' шагов от твоей позиции' : 'Ты уже здесь') +
    (get('show-expansion').checked ? ' · просмотрено ' + get('trace-range').value + ' клеток' : '');
  const visit = state.actions.find(action => action.kind === 'search' && action.target === preview);
  get('record-visit').hidden = !visit || state.mode === 'simulation';
  get('edit-map').hidden = state.status !== 'active';
  get('edit-map').setAttribute('aria-pressed',String(editing));
  get('edit-map').textContent = editing ? 'Готово' : 'Настроить проходы';
  get('map-help').hidden = !editing;
  get('trace-range').max = route.expanded.length;
  get('trace-steps').hidden = !get('show-expansion').checked;
  get('trace-label').textContent = 'Клетки: ' + get('trace-range').value + ' / ' + route.expanded.length;
  const pins = get('map-pins');
  const fragment = document.createDocumentFragment();
  const current = cellKey(state.position);
  const places = new Set(Object.values(state.locations).map(cellKey));
  if (editing) {
    state.original_rows.forEach((line,row) => [...line].forEach((symbol,col) => {
      const id = cellKey([row,col]);
      if (symbol === '#' || places.has(id) || id === current || id === cellKey(state.start)) return;
      const [x,y] = cellPosition(row,col);
      const closed = state.closed.some(cell => cellKey(cell) === id);
      const tile = element('button',undefined,'corridor' + (closed ? ' closed' : ''));
      const w = mapBounds.width / line.length;
      const h = mapBounds.height / state.rows.length;
      tile.style.left = (x-w/2)*100 + '%';
      tile.style.top = (y-h/2)*100 + '%';
      tile.style.width = w*100 + '%';
      tile.style.height = h*100 + '%';
      const label = (closed ? 'Открыть проход ' : 'Закрыть проход ') + row + ', ' + col;
      tile.setAttribute('aria-label',label);
      tile.title = label;
      tile.addEventListener('click', () => request('toggle',{row,col}));
      fragment.append(tile);
    }));
  }
  function pinAt(cell, name, icon, isYou) {
    const [x,y] = cellPosition(...cell);
    const pin = element(isYou ? 'div' : 'button',undefined,'pin' +
      (isYou ? ' you-pin' : '') + (x > .8 ? ' edge-right' : '') + (y > .77 ? ' edge-bottom' : ''));
    pin.style.left = x*100 + '%';
    pin.style.top = y*100 + '%';
    const marker = element('span',undefined,'pin-marker');
    if (icon) marker.append(element('b',icon));
    pin.append(marker,element('span',name,'pin-label'));
    return pin;
  }
  for (const [name,cell] of Object.entries(state.locations)) {
    const pin = pinAt(cell,place(name),symbols[name],false);
    pin.setAttribute('aria-label','Маршрут: ' + place(name));
    pin.setAttribute('aria-pressed',String(name === preview));
    pin.addEventListener('click', () => selectPreview(name));
    fragment.append(pin);
  }
  fragment.append(pinAt(state.position,'Ты здесь','',true));
  pins.replaceChildren(fragment);
  drawMap();
}

function renderHistory() {
  const history = get('history');
  get('download').disabled = state.history.length === 0;
  if (!state.history.length) {
    history.replaceChildren(element('p','Добавь подсказку или запиши проверку места. Здесь появятся результаты.','empty'));
    return;
  }
  history.replaceChildren(...state.history.slice().reverse().map((event,index) => {
    const detail = element('details',undefined,'event');
    detail.open = index === 0;
    let title = 'Поиск завершён';
    if (event.type === 'map') title = (event.blocked ? 'Закрыт проход ' : 'Открыт проход ') + event.cell.join(', ');
    if (event.update) {
      const label = {report:'Подсказка', ask:'Уточнение', search:'Проверка'}[event.type];
      title = label + ': ' + place(event.target) + ' · ' + outcomes[event.outcome];
    }
    detail.append(element('summary',title));
    if (event.note) detail.append(element('p',event.note));
    detail.append(element('p','Осталось ' + event.budget + ' ед. времени.'));
    if (event.update) {
      const b = event.update;
      const shift = pct(b.prior[event.target]) + ' → ' + pct(b.posterior[event.target]);
      detail.append(element('p',place(event.target) + ': ' + shift));
      const calc = element('details',undefined,'event');
      calc.append(element('summary','Показать расчёт Bayes'),table(
        ['Место','До подсказки','Правдоподобие','Вес','После подсказки'],
        Object.keys(b.prior).map(name => [place(name),pct(b.prior[name]),decimal(b.likelihood[name]),
          decimal(b.weights[name]),pct(b.posterior[name])])),
        element('p','Сумма весов: ' + decimal(b.evidence_probability)));
      detail.append(calc);
    }
    return detail;
  }));
}

function renderRankings() {
  get('rankings').replaceChildren(state.actions.length ? table(['Действие','Время','Q'],state.actions.map(a => {
    const button = element('button',actName(a),'table-button');
    button.addEventListener('click',() => { branchLabel = a.label; renderBranches(); });
    return [button,String(a.duration),decimal(a.q)];
  }),0) : element('p','Поиск завершён.'));
  renderBranches();
}

function renderBranches() {
  const action = state.actions.find(a => a.label === branchLabel);
  const container = get('branches');
  container.replaceChildren();
  if (!action) return;
  if (!action.branches.length) {
    container.append(element('p','Остановка завершает поиск с оценкой 0.'));
    return;
  }
  container.append(element('p',actName(action)),table(
    ['Исход','Вероятность','Награда','Ценность продолжения','Вклад в Q'],
    action.branches.map(b => [outcomes[b.observation],pct(b.probability),decimal(b.reward),
      decimal(b.continuation),decimal(b.weighted)])),
    element('p','Сумма вкладов: ' + decimal(action.q) + '. Коэффициент γ = ' + state.costs.gamma + '.'));
}

function renderAssumptions() {
  const m = state.observation_model;
  const c = state.costs;
  get('assumptions').replaceChildren(table(['Параметр','Значение'],[
    ['Положительная подсказка, если вещь там',pct(m.sensitivity)],
    ['Положительная подсказка, если вещь в другом месте',pct(m.false_positive)],
    ['Находка при проверке правильного места',pct(m.detection)],
    ['Время шага / проверки / уточнения',[c.move,c.search,c.ask].join(' / ')],
    ['Награда за находку / штраф за время / γ',[c.reward_found,c.time_penalty,c.gamma].join(' / ')],
    ['Глубина планирования',String(state.depth)],
  ]),element('p','При выборе последнего известного места его исходный вес умножается на 3. Затем веса нормируются.'));
}

function renderExperiments() {
  const data = config.experiments;
  const results = Object.entries(data.summaries[get('experiment-scenario').value]);
  get('experiment-sample').textContent = data.trials_per_policy + ' запусков на стратегию · глубина ' + data.depth;
  get('experiment-bars').replaceChildren(...results.map(([key,m]) => {
    const bar = element('div',undefined,'experiment-bar');
    bar.append(element('b',policies[key] + ' · ' + pct(m.success_rate)),meter(m.success_rate));
    return bar;
  }));
  get('experiment-table').replaceChildren(table(['Стратегия','Найдено','95% интервал','Среднее время','Средняя награда'],
    results.map(([key,m]) => [policies[key],m.successes + '/' + m.episodes,
      m.success_ci95_wilson.map(pct).join('–'),decimal(m.mean_time_all),decimal(m.mean_discounted_return)])));
}

function showPage(id) {
  for (const button of document.querySelectorAll('[data-tab]')) {
    const chosen = button.dataset.tab === id;
    get(button.dataset.tab).hidden = !chosen;
    if (chosen) button.setAttribute('aria-current','page');
    else button.removeAttribute('aria-current');
  }
  if (id === 'search') requestAnimationFrame(drawMap);
  window.scrollTo(0,0);
}

function openDialog(id) {
  const dialog = get(id);
  dialog.querySelector('.form-error').textContent = '';
  dialog.showModal();
}

function updateSetup() {
  const preset = config.scenarios.find(s => s.id === get('scenario').value);
  const places = preset.locations.map(name => [name,place(name)]);
  selectOptions('start-at',[['','Главный вход'],...places],get('start-at').value);
  selectOptions('last-seen',[['','Не помню'],...places],get('last-seen').value);
  get('budget').value = preset.budget;
  get('scenario').title = scenarioHelp[preset.id] || preset.description;
}

function startExample(dialog) {
  return request('start',{
    scenario:'baseline', item:'Наушники', description:'Чёрный кейс · пример поиска',
    mode:'manual',budget:30,depth:3,seed:42,start_at:'',last_seen:'',
  },{dialog});
}

function updateActionForm() {
  const action = state.actions[Number(get('action-select').value)];
  get('action-title').textContent = actName(action);
  get('action-detail').textContent = action.kind === 'stop' ? 'История останется в разделе «Мои поиски».' :
    (state.mode === 'manual' ? 'Запиши итог после выполнения действия. ' : 'Результат определит симуляция. ') +
    'Будет списано ' + action.duration + ' ед. времени.';
  const useOutcome = state.mode === 'manual' && action.kind !== 'stop';
  get('outcome-field').hidden = !useOutcome;
  get('outcome').required = useOutcome;
  selectOptions('outcome',[['','Выбери результат'],...action.branches.map(b => [b.observation,outcomes[b.observation]])]);
  get('apply-action').textContent = action.kind === 'stop' ? 'Завершить поиск' :
    state.mode === 'manual' ? 'Сохранить результат' : 'Выполнить действие';
}

function openAction(action) {
  selectOptions('action-select',state.actions.map((a,i) => [String(i),actName(a)]),
    action ? String(state.actions.indexOf(action)) : '0');
  get('action-field').hidden = Boolean(action);
  updateActionForm();
  openDialog('action-dialog');
}

function applyAction(action, dialog) {
  return request('action',{kind:action.kind,target:action.target,outcome:get('outcome').value},{dialog});
}

get('open-setup').addEventListener('click', () => { if (config) openDialog('setup'); });
get('scenario').addEventListener('change',updateSetup);
get('mode').addEventListener('change',() => { get('seed-field').hidden = get('mode').value !== 'simulation'; });
get('open-example').addEventListener('click', () => startExample(get('setup')));
get('setup-form').addEventListener('submit', event => {
  event.preventDefault();
  request('start',{
    scenario:get('scenario').value,item:get('item').value,description:get('description').value,
    mode:get('mode').value,budget:Number(get('budget').value),depth:Number(get('depth').value),
    seed:Number(get('seed').value),start_at:get('start-at').value,last_seen:get('last-seen').value,
  },{dialog:get('setup')});
});
get('run-action').addEventListener('click', () => {
  const action = state.actions[0];
  if (state.mode === 'simulation' && action.kind !== 'stop') applyAction(action);
  else openAction(action);
});
get('other-action').addEventListener('click',() => openAction());
get('record-visit').addEventListener('click', () => {
  const action = state.actions.find(a => a.kind === 'search' && a.target === preview);
  if (action) openAction(action);
});
get('action-select').addEventListener('change',updateActionForm);
get('action-form').addEventListener('submit',event => {
  event.preventDefault();
  applyAction(state.actions[Number(get('action-select').value)],get('action-dialog'));
});
get('add-report').addEventListener('click',() => {
  get('report-id').value = '';
  get('report-note').value = '';
  get('report-outcome').value = 'yes';
  selectOptions('report-target',Object.keys(state.locations).map(name => [name,place(name)]),preview);
  openDialog('report-dialog');
});
get('report-form').addEventListener('submit',event => {
  event.preventDefault();
  request('report',{target:get('report-target').value,outcome:get('report-outcome').value,
    report_id:get('report-id').value.trim() || makeId(),note:get('report-note').value},{dialog:get('report-dialog')});
});
get('edit-map').addEventListener('click',() => { editing = !editing; renderMap(); });
get('show-expansion').addEventListener('change',renderMap);
get('trace-range').addEventListener('input',renderMap);
get('experiment-scenario').addEventListener('change',renderExperiments);
get('download').addEventListener('click',() => {
  const url = URL.createObjectURL(new Blob([JSON.stringify(state,null,2)],{type:'application/json'}));
  const link = element('a');
  link.href = url;
  link.download = 'findback-search.json';
  link.click();
  setTimeout(() => URL.revokeObjectURL(url),1000);
});
for (const button of document.querySelectorAll('[data-tab],[data-page]')) {
  button.addEventListener('click',() => showPage(button.dataset.tab || button.dataset.page));
}
for (const button of document.querySelectorAll('[data-close]')) {
  button.addEventListener('click',() => get(button.dataset.close).close());
}
new ResizeObserver(drawMap).observe(get('map-art'));

async function initialize() {
  const response = await fetch('/api/config');
  if (!response.ok) throw new Error('Не удалось загрузить карту кампуса.');
  config = await response.json();
  const presets = config.scenarios.map(s => [s.id,scenarioNames[s.id] || s.name]);
  selectOptions('scenario',presets);
  selectOptions('experiment-scenario',presets);
  updateSetup();
  renderExperiments();
  readSaved();
  if (!saved.cases[saved.active] || !await restore(saved.active)) await startExample();
}
initialize().catch(() => notice('error','Не удалось загрузить FindBack. Проверь окно запуска и обнови страницу.'));
