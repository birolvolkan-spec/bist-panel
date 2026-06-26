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
  setTimeout(applyCategoryLabels, 800);
  setInterval(applyCategoryLabels, 2000);
});
