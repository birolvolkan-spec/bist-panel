const LIVE_SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'OPUSDT', 'XRPUSDT', 'ADAUSDT', 'AVAXUSDT', 'LINKUSDT', 'DOGEUSDT'];
const BINANCE_FAPI = 'https://fapi.binance.com';

function liveFmt(n, suffix = '') {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return '-';
  return Number(n).toLocaleString('tr-TR', { maximumFractionDigits: 5 }) + suffix;
}

function livePct(n) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return '-';
  const v = Number(n);
  const sign = v > 0 ? '+' : '';
  return sign + v.toLocaleString('tr-TR', { maximumFractionDigits: 2 }) + '%';
}

function liveBadgeClass(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return 'neutral';
  if (Number(v) > 0) return 'good';
  if (Number(v) < 0) return 'bad';
  return 'neutral';
}

async function fetchJson(url) {
  const res = await fetch(url, { cache: 'no-store' });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return await res.json();
}

async function loadLiveCrypto() {
  const box = document.getElementById('liveCryptoBox');
  const status = document.getElementById('liveCryptoStatus');
  if (!box || !status) return;

  try {
    status.textContent = 'Canlı Binance Futures verisi alınıyor...';
    const tickerRaw = await fetchJson(`${BINANCE_FAPI}/fapi/v1/ticker/24hr`);
    const premiumRaw = await fetchJson(`${BINANCE_FAPI}/fapi/v1/premiumIndex`);

    const tickerMap = new Map((Array.isArray(tickerRaw) ? tickerRaw : []).map(x => [x.symbol, x]));
    const premiumMap = new Map((Array.isArray(premiumRaw) ? premiumRaw : []).map(x => [x.symbol, x]));

    const rows = LIVE_SYMBOLS.map(symbol => {
      const t = tickerMap.get(symbol) || {};
      const p = premiumMap.get(symbol) || {};
      const ch = Number(t.priceChangePercent);
      return `
        <div class="dataRow">
          <strong><span class="miniCategory">CANLI KRİPTO</span>${symbol}</strong>
          <span>${liveFmt(t.lastPrice, ' $')}</span>
          <span class="badge ${liveBadgeClass(ch)}">${livePct(ch)}</span>
          <span>${liveFmt(t.quoteVolume, ' $')}</span>
          <span>${liveFmt(Number(p.lastFundingRate) * 100, '%')}</span>
          <span>${liveFmt(p.markPrice, ' $')}</span>
        </div>`;
    }).join('');

    box.innerHTML = `
      <div class="dataHead">
        <strong>Coin</strong><strong>Fiyat</strong><strong>24s</strong><strong>Hacim</strong><strong>Funding</strong><strong>Mark</strong>
      </div>
      ${rows}`;
    const now = new Date();
    status.textContent = `Canlı görünüm: tarayıcıdan Binance Futures okundu • ${now.toLocaleTimeString('tr-TR')}`;
  } catch (err) {
    status.textContent = 'Canlı akış alınamadı. Panel son GitHub raporunu göstermeye devam eder. Sebep: ' + err.message;
  }
}

function makeCategoryTag(text) {
  const tag = document.createElement('span');
  tag.className = 'categoryTag';
  tag.textContent = text;
  tag.style.display = 'inline-flex';
  tag.style.alignItems = 'center';
  tag.style.justifyContent = 'center';
  tag.style.padding = '4px 7px';
  tag.style.borderRadius = '999px';
  tag.style.fontSize = '10px';
  tag.style.fontWeight = '800';
  tag.style.letterSpacing = '.08em';
  tag.style.background = 'rgba(255,255,255,.08)';
  tag.style.color = '#9aa8c7';
  tag.style.marginBottom = '6px';
  return tag;
}

function addTagsToCards(containerId, label) {
  const root = document.getElementById(containerId);
  if (!root) return;
  root.querySelectorAll('.asset.card').forEach(card => {
    if (card.querySelector('.categoryTag')) return;
    const head = card.querySelector('.assetHead > div');
    if (!head) return;
    head.prepend(makeCategoryTag(label));
  });
}

function addTagsToRows(containerId, label) {
  const root = document.getElementById(containerId);
  if (!root) return;
  root.querySelectorAll('.row').forEach(row => {
    if (row.querySelector('.categoryTag')) return;
    const left = row.querySelector('div');
    if (!left) return;
    left.prepend(makeCategoryTag(label));
  });
}

function ensureColorLegend() {
  if (document.getElementById('colorLegendBox')) return;
  const decision = document.querySelector('.decision.card');
  if (!decision || !decision.parentNode) return;
  const box = document.createElement('section');
  box.className = 'card';
  box.id = 'colorLegendBox';
  box.innerHTML = `
    <p class="eyebrow">Renk ve Grup Açıklaması</p>
    <div class="chips">
      <span>🟢 Yeşil: pozitif / güçlenme</span>
      <span>🔴 Kırmızı: negatif / zayıflama</span>
      <span>🟠 Turuncu: nötr / kararsız / veri sınırlı</span>
      <span>Etiket: KRİPTO / BIST / EMTİA / FON / MAKRO</span>
    </div>
  `;
  decision.parentNode.insertBefore(box, decision.nextSibling);
}

function applyCategoryLabels() {
  ensureColorLegend();
  addTagsToCards('cryptoCards', 'KRİPTO');
  addTagsToCards('commodityCards', 'EMTİA');
  addTagsToCards('bistCards', 'BIST');
  addTagsToRows('macroList', 'MAKRO');
  addTagsToRows('compareList', 'GENEL');
  addTagsToRows('opportunities', 'FIRSAT');
  addTagsToRows('funds', 'FON');
}

window.addEventListener('load', () => {
  loadLiveCrypto();
  applyCategoryLabels();
  setTimeout(applyCategoryLabels, 800);
});
setInterval(loadLiveCrypto, 30 * 1000);
setInterval(applyCategoryLabels, 2000);
