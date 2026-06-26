const LIVE_SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'OPUSDT', 'XRPUSDT', 'ADAUSDT', 'AVAXUSDT', 'LINKUSDT', 'DOGEUSDT'];
const BINANCE_FAPI = 'https://fapi.binance.com';
const BINANCE_DATA = 'https://fapi.binance.com/futures/data';

function liveFmt(n, suffix = '') {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return '-';
  const abs = Math.abs(Number(n));
  const maxDigits = abs >= 1000000 ? 0 : abs >= 1000 ? 2 : 5;
  return Number(n).toLocaleString('tr-TR', { maximumFractionDigits: maxDigits }) + suffix;
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

async function fetchMaybe(url) {
  try { return await fetchJson(url); } catch (err) { return null; }
}

function calcDeltaFromKline(kline) {
  if (!Array.isArray(kline)) return { delta: null, deltaRatioPct: null };
  const volume = Number(kline[5]);
  const takerBuy = Number(kline[9]);
  if (!Number.isFinite(volume) || !Number.isFinite(takerBuy) || volume <= 0) return { delta: null, deltaRatioPct: null };
  const takerSell = volume - takerBuy;
  const delta = takerBuy - takerSell;
  return { delta, deltaRatioPct: (delta / volume) * 100 };
}

async function fetchLiveDetail(symbol) {
  const [oiNow, oiHist, takerRows, klines] = await Promise.all([
    fetchMaybe(`${BINANCE_FAPI}/fapi/v1/openInterest?symbol=${symbol}`),
    fetchMaybe(`${BINANCE_DATA}/openInterestHist?symbol=${symbol}&period=15m&limit=8`),
    fetchMaybe(`${BINANCE_DATA}/takerlongshortRatio?symbol=${symbol}&period=15m&limit=1`),
    fetchMaybe(`${BINANCE_FAPI}/fapi/v1/klines?symbol=${symbol}&interval=15m&limit=1`),
  ]);

  let oiChangePct = null;
  if (Array.isArray(oiHist) && oiHist.length >= 2) {
    const first = Number(oiHist[0].sumOpenInterest);
    const last = Number(oiHist[oiHist.length - 1].sumOpenInterest);
    if (Number.isFinite(first) && Number.isFinite(last) && first !== 0) oiChangePct = ((last - first) / first) * 100;
  }

  const taker = Array.isArray(takerRows) && takerRows.length ? takerRows[takerRows.length - 1] : {};
  const latestKline = Array.isArray(klines) && klines.length ? klines[klines.length - 1] : null;
  const d = calcDeltaFromKline(latestKline);

  return {
    openInterest: oiNow && oiNow.openInterest !== undefined ? Number(oiNow.openInterest) : null,
    oiChangePct,
    takerRatio: taker && taker.buySellRatio !== undefined ? Number(taker.buySellRatio) : null,
    takerBuyVol: taker && taker.buyVol !== undefined ? Number(taker.buyVol) : null,
    takerSellVol: taker && taker.sellVol !== undefined ? Number(taker.sellVol) : null,
    deltaRatioPct: d.deltaRatioPct,
  };
}

async function loadLiveCrypto() {
  const box = document.getElementById('liveCryptoBox');
  const status = document.getElementById('liveCryptoStatus');
  if (!box || !status) return;

  try {
    status.textContent = 'Canlı Binance Futures verisi alınıyor: fiyat + funding + OI + taker + delta...';
    const [tickerRaw, premiumRaw, details] = await Promise.all([
      fetchJson(`${BINANCE_FAPI}/fapi/v1/ticker/24hr`),
      fetchJson(`${BINANCE_FAPI}/fapi/v1/premiumIndex`),
      Promise.all(LIVE_SYMBOLS.map(s => fetchLiveDetail(s))),
    ]);

    const tickerMap = new Map((Array.isArray(tickerRaw) ? tickerRaw : []).map(x => [x.symbol, x]));
    const premiumMap = new Map((Array.isArray(premiumRaw) ? premiumRaw : []).map(x => [x.symbol, x]));
    const detailMap = new Map(LIVE_SYMBOLS.map((s, i) => [s, details[i] || {}]));

    const rows = LIVE_SYMBOLS.map(symbol => {
      const t = tickerMap.get(symbol) || {};
      const p = premiumMap.get(symbol) || {};
      const d = detailMap.get(symbol) || {};
      const ch = Number(t.priceChangePercent);
      return `
        <div class="dataRow futuresRow">
          <strong><span class="miniCategory">CANLI KRİPTO</span>${symbol}</strong>
          <span>${liveFmt(t.lastPrice, ' $')}</span>
          <span class="badge ${liveBadgeClass(ch)}">${livePct(ch)}</span>
          <span>${liveFmt(Number(p.lastFundingRate) * 100, '%')}</span>
          <span>${liveFmt(d.openInterest)}</span>
          <span class="badge ${liveBadgeClass(d.oiChangePct)}">${livePct(d.oiChangePct)}</span>
          <span>${liveFmt(d.takerRatio)}</span>
          <span class="badge ${liveBadgeClass((d.takerRatio || 1) - 1)}">${d.takerRatio === null || d.takerRatio === undefined ? '-' : (d.takerRatio > 1 ? 'Alıcı' : d.takerRatio < 1 ? 'Satıcı' : 'Denge')}</span>
          <span class="badge ${liveBadgeClass(d.deltaRatioPct)}">${livePct(d.deltaRatioPct)}</span>
          <span>${liveFmt(p.markPrice, ' $')}</span>
        </div>`;
    }).join('');

    box.innerHTML = `
      <div class="dataHead futuresRow">
        <strong>Coin</strong><strong>Fiyat</strong><strong>24s</strong><strong>Funding</strong><strong>OI</strong><strong>OI 2s</strong><strong>Taker A/S</strong><strong>Taker Yön</strong><strong>Delta 15m</strong><strong>Mark</strong>
      </div>
      ${rows}`;
    const now = new Date();
    status.textContent = `Canlı futures görünüm: OI / taker / delta dahil • ${now.toLocaleTimeString('tr-TR')}`;
  } catch (err) {
    status.textContent = 'Canlı futures akış alınamadı. Panel son GitHub raporunu göstermeye devam eder. Sebep: ' + err.message;
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
