// === util ===
function esc(s) {
  if (s === null || s === undefined) return '';
  return String(s).replace(/[&<>"']/g, c => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[c]));
}

function showError(msg) {
  alert("Ошибка: " + msg);
}

async function apiFetch(url, opts) {
  let resp;
  try {
    resp = await fetch(url, opts);
  } catch (e) {
    throw new Error("Сетевая ошибка: " + e.message);
  }
  if (resp.status === 401 || resp.redirected) {
    window.location = "/login";
    throw new Error("Требуется авторизация");
  }
  let data = null;
  try { data = await resp.json(); } catch (_) {}
  if (!resp.ok) {
    const msg = (data && data.error) || `HTTP ${resp.status}`;
    throw new Error(msg);
  }
  return data;
}

// === logs table ===
async function fetchLogs() {
  const params = new URLSearchParams();
  const from = document.getElementById('dateFrom').value;
  const to = document.getElementById('dateTo').value;
  const ip = document.getElementById('ipFilter').value;
  const kw = document.getElementById('keyword').value;
  const fileId = document.getElementById('fileFilter').value;
  const url = document.getElementById('urlFilter').value;
  const groupIp = document.getElementById('groupByIp').checked;
  const groupDate = document.getElementById('groupByDate').checked;

  if (from) params.set('from', new Date(from).toISOString());
  if (to) params.set('to', new Date(to).toISOString());
  if (ip) params.set('ip', ip);
  if (kw) params.set('keyword', kw);
  if (fileId) params.set('file_id', fileId);
  if (url) params.set('url', url);
  if (groupIp) params.set('group_by', 'ip');
  else if (groupDate) params.set('group_by', 'date');
  params.set('limit', '200');

  try {
    const data = await apiFetch('/api/logs?' + params);
    renderLogs(data);
  } catch (e) {
    showError(e.message);
  }
}

function renderLogs(data) {
  const tbody = document.querySelector('#logTable tbody');
  tbody.innerHTML = '';
  const totalInfo = document.getElementById('totalInfo');

  if (data.group_by === 'ip') {
    totalInfo.textContent = `(группировка по IP, ${data.items.length})`;
    for (const it of data.items) {
      tbody.insertAdjacentHTML('beforeend',
        `<tr><td colspan="7"><b>${esc(it.ip)}</b> — ${it.count} запросов</td></tr>`);
    }
    return;
  }
  if (data.group_by === 'date') {
    totalInfo.textContent = `(группировка по дате, ${data.items.length})`;
    for (const it of data.items) {
      tbody.insertAdjacentHTML('beforeend',
        `<tr><td colspan="7"><b>${esc(it.date)}</b> — ${it.count} записей</td></tr>`);
    }
    return;
  }
  totalInfo.textContent = `(всего: ${data.total}, показано: ${data.items.length})`;
  if (!data.items.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted">Нет данных</td></tr>`;
    return;
  }
  for (const e of data.items) {
    tbody.insertAdjacentHTML('beforeend', `
      <tr>
        <td><small>${esc(e.timestamp)}</small></td>
        <td><small>${esc(e.ip)}</small></td>
        <td><small>${esc(e.method)}</small></td>
        <td><small title="${esc(e.url)}">${esc((e.url||'').substring(0,80))}</small></td>
        <td><small>${esc(e.status_code)}</small></td>
        <td><small>${esc(e.size)}</small></td>
        <td><small title="${esc(e.user_agent)}">${esc((e.user_agent||'').substring(0,30))}</small></td>
      </tr>
    `);
  }
}

// === urls ===
async function loadUrls() {
  try {
    const data = await apiFetch('/api/urls?limit=100');
    const sel = document.getElementById('urlFilter');
    const cur = sel.value;
    sel.innerHTML = '<option value="">-- все URL --</option>';
    for (const it of data.items) {
      const opt = document.createElement('option');
      opt.value = it.url;
      opt.textContent = `${it.url} (${it.count})`;
      sel.appendChild(opt);
    }
    sel.value = cur;
  } catch (e) { showError(e.message); }
}

// === files ===
async function loadFiles() {
  try {
    const data = await apiFetch('/api/files');
    const ul = document.getElementById('filesList');
    const sel = document.getElementById('fileFilter');
    const curSel = sel.value;
    ul.innerHTML = '';
    sel.innerHTML = '<option value="">-- все файлы --</option>';
    for (const f of data.items) {
      const li = document.createElement('li');
      li.className = 'list-group-item d-flex justify-content-between align-items-center';
      li.style.cursor = 'pointer';
      li.innerHTML = `
        <div>
          <b>${esc(f.filename)}</b><br>
          <small class="text-muted">
            ${f.entries_count} записей • ${f.file_size} байт •
            ${esc(f.status)}
            ${f.error_message ? '<span class="text-danger">' + esc(f.error_message) + '</span>' : ''}
          </small>
        </div>
        <span class="badge bg-secondary">${esc(f.status)}</span>
      `;
      li.onclick = () => viewFile(f.id);
      ul.appendChild(li);

      const opt = document.createElement('option');
      opt.value = f.id;
      opt.textContent = f.filename;
      sel.appendChild(opt);
    }
    sel.value = curSel;
  } catch (e) { showError(e.message); }
}

async function viewFile(fileId) {
  try {
    const data = await apiFetch(`/api/files/${fileId}/entries?limit=100`);
    const tbody = document.querySelector('#logTable tbody');
    tbody.innerHTML = '';
    document.getElementById('totalInfo').textContent = `файл: ${data.file.filename}`;
    if (!data.items.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted">Файл пуст</td></tr>`;
      return;
    }
    for (const e of data.items) {
      tbody.insertAdjacentHTML('beforeend', `
        <tr>
          <td><small>${esc(e.timestamp)}</small></td>
          <td><small>${esc(e.ip)}</small></td>
          <td><small>${esc(e.method)}</small></td>
          <td><small>${esc(e.url)}</small></td>
          <td><small>${esc(e.status_code)}</small></td>
          <td><small>${esc(e.size)}</small></td>
          <td></td>
        </tr>
      `);
    }
  } catch (e) { showError(e.message); }
}

// === import with progress ===
async function triggerImport() {
  try {
    const { task_id } = await apiFetch('/api/import', { method: 'POST' });
    pollImport(task_id);
  } catch (e) { showError(e.message); }
}

async function pollImport(taskId) {
  const bar = document.getElementById('progressBar');
  const info = document.getElementById('progressInfo');
  try {
    const t = await apiFetch('/api/import/status/' + taskId);
    const pct = t.percent || 0;
    bar.style.width = pct + '%';
    bar.textContent = pct + '%';
    bar.className = 'progress-bar ' + (t.status === 'failed' ? 'bg-danger' : (t.status === 'done' ? 'bg-success' : ''));
    info.textContent =
      `${t.processed_files}/${t.total_files} файлов, ` +
      `${t.processed_bytes}/${t.total_bytes} байт, ` +
      `записей: ${t.entries_inserted}, ошибок: ${t.errors}`;
    if (t.status === 'running') {
      setTimeout(() => pollImport(taskId), 700);
    } else if (t.status === 'done') {
      info.textContent += ' — Готово';
      loadFiles();
      loadUrls();
      loadStats();
      fetchLogs();
    } else {
      info.textContent += ' — Ошибка: ' + (t.error_message || 'unknown');
      showError(t.error_message || 'Импорт завершился ошибкой');
    }
  } catch (e) {
    setTimeout(() => pollImport(taskId), 1500);
  }
}

// === stats ===
async function loadStats() {
  try {
    const s = await apiFetch('/api/stats');
    document.getElementById('stats').innerHTML =
      `Записей: <b>${s.total_entries}</b><br>` +
      `Файлов: <b>${s.total_files}</b><br>` +
      `Уникальных IP: <b>${s.unique_ips}</b><br>` +
      `Уникальных URL: <b>${s.unique_urls}</b>`;
  } catch (e) { /* silent */ }
}

// === init ===
document.addEventListener('DOMContentLoaded', () => {
  loadFiles();
  loadUrls();
  loadStats();
  fetchLogs();
  // автообновление статистики
  setInterval(loadStats, 30000);
});
