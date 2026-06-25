async function loadTradeRecommendations() {
  try {
    const res = await fetch('data/daily_report.json?v=' + Date.now(), { cache: 'no-store' });
    const data = await res.json();
    const rec = data.trade_recommendations;
    if (!rec) return;

    let section = document.getElementById('tradeRecommendationsSection');
    if (!section) {
      section = document.createElement('section');
      section.id = 'tradeRecommendationsSection';
      const weekly = document.getElementById('weeklyBox');
      if (weekly && weekly.parentNode) weekly.parentNode.insertBefore(section, weekly.nextSibling);
      else document.querySelector('main').prepend(section);
    }

    const candidates = rec.top_candidates || [];
    const cards = candidates.length ? candidates.map(c => `
      <article class="card">
        <div class="assetHead">
          <div>
            <h3>${c.name} ${c.direction}</h3>
            <p>${c.symbol} • ${c.action}</p>
          </div>
          <span class="badge ${c.score >= 70 ? 'good' : 'neutral'}">${c.score}/100</span>
        </div>
        <div class="levels">
          <div><span>Üst filtre</span><strong>${c.higher_tf}</strong></div>
          <div><span>Setup TF</span><strong>${c.setup_tf}</strong></div>
          <div><span>Giriş TF</span><strong>${c.entry_tf}</strong></div>
          <div><span>Tip</span><strong>${c.style}</strong></div>
        </div>
        <div class="comment"><strong>Giriş planı:</strong> ${c.entry_plan}</div>
        <div class="comment small"><strong>Geçersiz olur:</strong> ${c.invalid_if}</div>
        <div class="comment small"><strong>Neden?</strong><br>${(c.reasons || []).map(r => '• ' + r).join('<br>')}</div>
      </article>
    `).join('') : '<div class="card"><h3>NO TRADE</h3><p>Temiz işlem adayı çıkmadı. Sistem pas geçmeyi öneriyor.</p></div>';

    section.innerHTML = `
      <div class="sectionTitle">
        <h2>İşlem Adayları</h2>
        <p>Coin + yön + timeframe öneri motoru</p>
      </div>
      <div class="card">
        <p class="eyebrow">Piyasa Rejimi</p>
        <h2>${rec.market_regime?.regime || '-'}</h2>
        <p>${rec.summary || ''}</p>
        <p class="muted">Eksik veri: ${(rec.market_regime?.missing_data || []).join(', ')}</p>
      </div>
      <div class="assetGrid">${cards}</div>
    `;
  } catch (err) {
    console.warn('Trade recommendation UI error:', err);
  }
}

window.addEventListener('load', loadTradeRecommendations);
setInterval(loadTradeRecommendations, 5 * 60 * 1000);
