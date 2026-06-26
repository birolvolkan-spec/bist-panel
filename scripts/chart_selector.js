let comparisonChart = null;
let comparisonSeriesPayload = null;
const DEFAULT_SELECTED_SERIES = new Set(['BTCUSDT.P', 'ETHUSDT.P', 'DXY']);

function chartFmt(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '-';
  return Number(v).toLocaleString('tr-TR', { maximumFractionDigits: 2 });
}

function ensureComparisonChartBox() {
  let box = document.getElementById('comparisonChartBox');
  if (box) return box;
  const main = document.querySelector('main');
  const anchor = document.getElementById('assetDecisionBox') || document.querySelector('.decision.card');
  if (!main || !anchor) return null;
  box = document.createElement('section');
  box.className = 'card';
  box.id = 'comparisonChartBox';
  box.innerHTML = `
    <div class="sectionTitle compactTitle">
      <div>
        <p class="eyebrow">Karşılaştırmalı Grafik</p>
        <h2>Makro + dominance + futures grafiği</h2>
      </div>
      <p class="muted" id="comparisonChartStatus">Veri yükleniyor...</p>
    </div>
    <div class="chartWrap bigChart"><canvas id="comparisonChartCanvas"></canvas></div>
    <div id="comparisonChartControls" class="chips chartControls"></div>
    <p class="muted smallNote">Grafik normalize çalışır: seçilen her seri ilk değerini 100 kabul eder. Böylece DXY, TOTAL, dominance ve BTC/ETH aynı grafikte okunabilir.</p>
  `;
  anchor.parentNode.insertBefore(box, anchor.nextSibling);
  return box;
}

function seriesById(id) {
  return (comparisonSeriesPayload?.series || []).find(s => s.id === id);
}

function selectedSeriesIds() {
  return Array.from(document.querySelectorAll('#comparisonChartControls input[type="checkbox"]'))
    .filter(x => x.checked)
    .map(x => x.value);
}

function buildAlignedData(ids) {
  const dateSet = new Set();
  ids.forEach(id => {
    const s = seriesById(id);
    (s?.points || []).forEach(p => {
      if (p.normalized !== null && p.normalized !== undefined) dateSet.add(p.date);
    });
  });
  const dates = Array.from(dateSet).sort();
  return dates.map(date => {
    const row = { date };
    ids.forEach(id => {
      const s = seriesById(id);
      const p = (s?.points || []).find(x => x.date === date);
      row[id] = p && p.normalized !== null && p.normalized !== undefined ? p.normalized : null;
    });
    return row;
  });
}

function renderComparisonChart() {
  const canvas = document.getElementById('comparisonChartCanvas');
  const status = document.getElementById('comparisonChartStatus');
  if (!canvas || !comparisonSeriesPayload) return;
  const ids = selectedSeriesIds();
  if (comparisonChart) comparisonChart.destroy();
  if (!ids.length) {
    status.textContent = 'Grafiğe eklemek için alttan en az bir veri seç.';
    return;
  }
  const dataRows = buildAlignedData(ids);
  const labels = dataRows.map(x => x.date.slice(5));
  const datasets = ids.map(id => {
    const s = seriesById(id);
    return {
      label: s?.label || id,
      data: dataRows.map(r => r[id]),
      spanGaps: true,
      tension: 0.25,
      borderWidth: 2,
      pointRadius: 0,
      fill: false,
    };
  });
  comparisonChart = new Chart(canvas.getContext('2d'), {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: true, labels: { color: '#dce6ff' } },
        tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${chartFmt(ctx.parsed.y)}` } },
      },
      scales: {
        x: { ticks: { color: '#9aa8c7', maxTicksLimit: 8 }, grid: { color: 'rgba(255,255,255,.06)' } },
        y: { ticks: { color: '#9aa8c7' }, grid: { color: 'rgba(255,255,255,.08)' }, title: { display: true, text: 'Normalize endeks', color: '#9aa8c7' } },
      },
    },
  });
  status.textContent = `${ids.length} seri grafikte • ${comparisonSeriesPayload.updated_at || ''}`;
}

function renderComparisonControls() {
  const controls = document.getElementById('comparisonChartControls');
  if (!controls || !comparisonSeriesPayload) return;
  controls.innerHTML = '';
  (comparisonSeriesPayload.series || []).forEach(s => {
    const count = (s.points || []).length;
    const label = document.createElement('label');
    label.className = 'chartCheck';
    label.title = `${s.source || ''} • ${count} veri`;
    const checked = DEFAULT_SELECTED_SERIES.has(s.id) && count > 1;
    label.innerHTML = `<input type="checkbox" value="${s.id}" ${checked ? 'checked' : ''} ${count < 2 ? 'disabled' : ''}> <span>${s.label}</span> <em>${count}</em>`;
    controls.appendChild(label);
  });
  controls.querySelectorAll('input').forEach(input => input.addEventListener('change', renderComparisonChart));
}

async function loadComparisonChart() {
  ensureComparisonChartBox();
  const status = document.getElementById('comparisonChartStatus');
  try {
    const res = await fetch('data/chart_series.json?v=' + Date.now(), { cache: 'no-store' });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    comparisonSeriesPayload = await res.json();
    renderComparisonControls();
    renderComparisonChart();
  } catch (err) {
    if (status) status.textContent = 'Grafik verisi yüklenemedi: ' + err.message;
  }
}

window.addEventListener('load', () => {
  setTimeout(loadComparisonChart, 600);
});
