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
          <strong>${symbol}</strong>
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

window.addEventListener('load', loadLiveCrypto);
setInterval(loadLiveCrypto, 30 * 1000);
