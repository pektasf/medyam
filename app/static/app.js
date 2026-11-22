/* ============================================================
   ESKİ USUL AI STUDIO — app.js v0.5 Master
   Gelişmiş UI / UX, 3-Kolon Sahne Editörü, Raporlar & Ayarlar
   ============================================================ */

const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);

// Global State
let currentActiveWorkflowId = null;
let currentExportScriptId = null;
let currentEditorScriptId = null;
let currentEditorScriptData = null;
let currentActiveSceneIndex = 0;
let isEditorDirty = false;
let isMockupPlaying = false;
let mockupPlayInterval = null;
let activeSSE = null;
let lastVoice = null;
let vaultScriptsCache = [];
let vaultCurrentFilter = 'all';

const agentIcons = ['✦','⌕','◉','✧','✎','▧','文','✓','⌁','↗'];

// ------------------------------------------------------------------ TOAST --
function toast(msg, type = 'info') {
  const t = $('#toast');
  if (!t) return;
  t.textContent = msg;
  t.className = 'toast show ' + type;
  setTimeout(() => t.className = 'toast', 4000);
}

function esc(s = '') {
  return String(s).replace(/[&<>"']/g, c => (
    {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]
  ));
}

// ------------------------------------------------------------------ API WRAPPER --
async function api(url, opts = {}) {
  try {
    const r = await fetch(url, opts);
    let d = {};
    try { d = await r.json(); } catch {}
    if (!r.ok) {
      throw new Error(d.detail || d.message || `Sunucu hatası (${r.status})`);
    }
    return d;
  } catch (err) {
    if (err.message && (err.message.includes('Failed to fetch') || err.message.includes('NetworkError'))) {
      throw new Error('Sunucuya ulaşılamıyor (127.0.0.1:8765). Lütfen uygulamanın açık olduğundan emin olun.');
    }
    throw err;
  }
}

// ------------------------------------------------------------------ NAVIGATION --
function showView(name) {
  $$('.view').forEach(x => x.classList.toggle('active', x.id === name));
  $$('.nav-item').forEach(x => x.classList.toggle('active', x.dataset.view === name));
  
  const titles = {
    overview:       'Kokpit & Süreç',
    ideas:          'Fikir & Senaryo Laboratuvarı',
    editor:         '3-Kolon Sahne Editörü',
    'scripts-vault':'Senaryo Arşivi & Arama Masası',
    assets:         'Medya & Kurgu Masası',
    reports:        'Stüdyo Raporları & Video Vault',
    agents:         '10 Uzman Operasyon Paneli',
    settings:       'Ayarlar & API Yönetimi',
    analytics:      'Yayın Performansı'
  };
  
  if ($('#page-title')) {
    $('#page-title').textContent = titles[name] || 'Eski Usul AI Studio';
  }
  window.scrollTo(0, 0);

  // Görünüm geçişlerinde ilgili verileri tetikle
  if (name === 'reports') {
    loadStudioReports();
  } else if (name === 'scripts-vault') {
    loadVaultScripts();
  } else if (name === 'editor') {
    ensureEditorHasScript();
  } else if (name === 'settings') {
    loadSettings();
  }
}

// Navigasyon butonlarını bağla
$$('.nav-item').forEach(b => {
  b.addEventListener('click', () => showView(b.dataset.view));
});

// ------------------------------------------------------------------ REFRESH DASHBOARD --
async function refresh() {
  try {
    const d = await api('/api/dashboard');
    if ($('#stat-ideas')) $('#stat-ideas').textContent = d.stats.ideas;
    if ($('#stat-scripts')) $('#stat-scripts').textContent = d.stats.scripts;
    if ($('#stat-assets')) $('#stat-assets').textContent = d.stats.assets;
    if ($('#stat-pending')) $('#stat-pending').textContent = d.stats.pending;

    // Aktif Proje Banner Bilgisi
    if (d.scripts && d.scripts.length > 0) {
      const latest = d.scripts[0];
      if ($('#active-project-title')) $('#active-project-title').textContent = latest.title;
      if ($('#active-project-desc')) {
        $('#active-project-desc').textContent = latest.hook || 'Son senaryo hazır. Sahneleri düzenleyin, seslendirin ve kurgulayın.';
      }
    }

    // Mini agent listesi
    if ($('#agent-mini')) {
      $('#agent-mini').innerHTML = d.tasks.slice(0, 5).map(a =>
        `<div class="agent-mini-row" style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--line);font-size:11.5px;">
          <span>${esc(a.title)}</span>
          <span class="badge ${a.status === 'completed' ? 'badge-green' : ''}">● ${esc(a.status === 'ready' ? 'Hazır' : a.status)}</span>
         </div>`
      ).join('');
    }

    // Ajan gridi
    if ($('#agent-grid')) {
      $('#agent-grid').innerHTML = d.tasks.map((a, i) =>
        `<div class="agent-card">
          <div class="agent-icon">${agentIcons[i] || '✦'}</div>
          <b>${esc(a.title)}</b>
          <p>${esc(a.detail)}</p>
          <div class="badge ${a.status === 'completed' ? 'badge-green' : a.status === 'running' ? 'badge-orange' : ''}">
            ● ${esc(
              a.status === 'ready'      ? 'Sistemde Tanımlı' :
              a.status === 'completed'  ? 'Görevi Tamamlandı' :
              a.status === 'running'    ? 'Çalışıyor (Paralel)' :
              a.status === 'failed'     ? 'Hata' : a.status
            )}
          </div>
         </div>`
      ).join('');
    }

    // Son senaryolar (Kokpit)
    if ($('#recent-scripts')) {
      $('#recent-scripts').innerHTML = d.scripts.length
        ? d.scripts.slice(0, 4).map(s =>
            `<div class="script-item" style="cursor:pointer;" onclick="openScriptInEditor('${s.id}')">
              <div>
                <b>${esc(s.title)}</b>
                <small>${esc(s.language.toUpperCase())} · Kalite puanı ${s.score}/100</small>
              </div>
              <div style="display:flex;gap:6px;align-items:center;">
                <span class="badge ${s.review === 'approved' ? 'badge-green' : s.review === 'revision' ? 'badge-orange' : ''}">
                  ${s.review === 'approved' ? '✓ Onaylandı' : s.review === 'revision' ? 'Revizyon' : 'İnceleme'}
                </span>
                <button class="btn btn-secondary" style="padding:2px 8px;font-size:11px;" onclick="event.stopPropagation();openScriptInEditor('${s.id}')">Düzenle ✍️</button>
              </div>
             </div>`
          ).join('')
        : '<div class="empty">Henüz senaryo yok. Yeni bir içerik oluşturarak başlayın.</div>';
    }

    // Fikir havuzu
    if ($('#idea-list')) {
      $('#idea-list').innerHTML = d.ideas.length
        ? d.ideas.map(i =>
            `<div class="idea-item">
              <div>
                <b>${esc(i.title)}</b>
                <small>${esc(i.angle || 'Açıklama eklenmedi')} · ${esc(i.language.toUpperCase())}</small>
              </div>
              <button class="btn btn-secondary" style="padding:3px 8px;font-size:11px;" onclick="fillBriefWithIdea('${esc(i.title)}')">Seç ↗</button>
             </div>`
          ).join('')
        : '<div class="empty">Henüz fikir eklenmedi.</div>';
    }

    // Medya arşivi
    if ($('#asset-list')) {
      $('#asset-list').innerHTML = d.assets.length
        ? '<div class="asset-grid">' + d.assets.map(a =>
            `<div class="asset-card">
              <b>${esc(a.filename)}</b>
              <small>${esc(a.kind)} · ${esc(a.license_name)}</small>
              <div style="margin-top:6px;">
                <span class="badge ${a.commercial_ok ? 'badge-green' : 'badge-orange'}">${a.commercial_ok ? '✓ Ticari Onaylı' : '! Lisans Kontrolü'}</span>
              </div>
              ${a.source_url ? `<a href="${esc(a.source_url)}" target="_blank" class="btn-text" style="display:block;margin-top:6px;font-size:10px;">Kaynağı Gör ↗</a>` : ''}
             </div>`
          ).join('') + '</div>'
        : '<div class="empty">Henüz medya eklenmedi.</div>';
    }

    // Dropdown seçenekleri güncelle
    vaultScriptsCache = d.scripts || [];
    const scriptOpts = '<option value="">Senaryo seçin...</option>' + vaultScriptsCache.map(s =>
      `<option value="${s.id}">${esc(s.title)} (${s.language.toUpperCase()})</option>`
    ).join('');
    
    if ($('#export-script')) $('#export-script').innerHTML = scriptOpts;
    if ($('#tts-script-select')) $('#tts-script-select').innerHTML = scriptOpts;
    if ($('#editor-script-select')) $('#editor-script-select').innerHTML = scriptOpts;

    // Eğer editörde açık bir senaryo yoksa ilkini seç
    if (!currentEditorScriptId && vaultScriptsCache.length > 0) {
      currentEditorScriptId = vaultScriptsCache[0].id;
      if ($('#editor-script-select')) $('#editor-script-select').value = currentEditorScriptId;
    }

  } catch (e) {
    console.error('Refresh hatası:', e);
  }
}

function fillBriefWithIdea(title) {
  showView('ideas');
  if ($('#topic')) {
    $('#topic').value = title;
    $('#topic').focus();
  }
}

// ------------------------------------------------------------------ 3-KOLON SAHNE EDİTÖRÜ -------------------
function ensureEditorHasScript() {
  if (currentEditorScriptId) {
    loadScriptToEditor(currentEditorScriptId);
  } else if (vaultScriptsCache.length > 0) {
    loadScriptToEditor(vaultScriptsCache[0].id);
  } else {
    $('#editor-scenes-list').innerHTML = '<div class="empty">Henüz senaryo yok. Fikir & Senaryo sekmesinden bir senaryo üretin.</div>';
    $('#inspector-body').innerHTML = '<div class="empty">Düzenlenecek senaryo bulunamadı.</div>';
  }
}

window.openScriptInEditor = (scriptId) => {
  currentEditorScriptId = scriptId;
  showView('editor');
  loadScriptToEditor(scriptId);
};

window.loadScriptToEditor = async (scriptId) => {
  if (!scriptId) return;
  currentEditorScriptId = scriptId;
  if ($('#editor-script-select')) $('#editor-script-select').value = scriptId;
  
  try {
    const data = await api(`/api/scripts/${scriptId}`);
    currentEditorScriptData = data;
    currentActiveSceneIndex = 0;
    isEditorDirty = false;
    updateDraftBadge(false);

    renderEditorScenesList();
    renderActiveSceneInspector();
    updateMockupPreview();
    calculateLiveStats();
  } catch (err) {
    toast(`Senaryo yüklenemedi: ${err.message}`, 'error');
  }
};

function renderEditorScenesList() {
  const container = $('#editor-scenes-list');
  if (!container || !currentEditorScriptData) return;

  const scenes = currentEditorScriptData.scenes || [];
  if (scenes.length === 0) {
    container.innerHTML = `
      <div class="empty" style="padding:20px;">
        Bu senaryoda henüz sahne bulunmuyor.<br>
        <button class="btn btn-secondary" style="margin-top:10px;" onclick="addNewScene()">+ İlk Sahneyi Ekle</button>
      </div>`;
    return;
  }

  container.innerHTML = scenes.map((sc, idx) => {
    const isActive = idx === currentActiveSceneIndex;
    const timeCode = sc.time || `${idx * 4}-${(idx + 1) * 4}s`;
    const visual = sc.visual || sc.shot || 'Görsel tanımlanmadı';
    const text = sc.on_screen_text || sc.text || sc.narration || '';

    return `
      <div class="scene-item ${isActive ? 'active' : ''}" onclick="selectScene(${idx})">
        <div class="scene-item-head">
          <span class="scene-num">SAHNE ${idx + 1}</span>
          <span class="scene-time">${esc(timeCode)}</span>
        </div>
        <div class="scene-visual-shot">${esc(visual)}</div>
        <div class="scene-text-preview">“${esc(text)}”</div>
        <div class="scene-item-actions">
          <button class="btn-text" onclick="event.stopPropagation();deleteScene(${idx})" title="Sahneyi Sil">🗑️ Sil</button>
        </div>
      </div>
    `;
  }).join('');
}

window.selectScene = (index) => {
  if (!currentEditorScriptData || !currentEditorScriptData.scenes) return;
  currentActiveSceneIndex = Math.max(0, Math.min(index, currentEditorScriptData.scenes.length - 1));
  renderEditorScenesList();
  renderActiveSceneInspector();
  updateMockupPreview();
};

function renderActiveSceneInspector() {
  const container = $('#inspector-body');
  const titleBadge = $('#inspector-scene-title');
  if (!container || !currentEditorScriptData) return;

  const scenes = currentEditorScriptData.scenes || [];
  if (scenes.length === 0 || !scenes[currentActiveSceneIndex]) {
    container.innerHTML = '<div class="empty">Lütfen sol taraftan bir sahne seçin.</div>';
    if (titleBadge) titleBadge.textContent = 'Sahne Seçin';
    return;
  }

  const sc = scenes[currentActiveSceneIndex];
  if (titleBadge) titleBadge.textContent = `Sahne ${currentActiveSceneIndex + 1}`;

  container.innerHTML = `
    <div class="field-box">
      <label class="field-label">Zaman Aralığı (Saniye)</label>
      <input id="insp-time" class="field-input font-mono" value="${esc(sc.time || '')}" placeholder="Örn: 0-3s" oninput="onInspectorInput('time', this.value)">
    </div>

    <div class="field-box">
      <label class="field-label">Ekranda Görünecek Metin (On-Screen Text)</label>
      <input id="insp-screen-text" class="field-input" value="${esc(sc.on_screen_text || sc.text || '')}" placeholder="TikTok ekranında görülecek başlık..." oninput="onInspectorInput('on_screen_text', this.value)">
    </div>

    <div class="field-box">
      <label class="field-label">Seslendirme Metni (Narration)</label>
      <textarea id="insp-narration" class="field-input" rows="3" placeholder="Bu sahnede seslendirilecek cümle..." oninput="onInspectorInput('narration', this.value)">${esc(sc.narration || '')}</textarea>
    </div>

    <div class="field-box">
      <label class="field-label">Görsel / Kamera Tanımı (Visual Prompt)</label>
      <textarea id="insp-visual" class="field-input" rows="3" placeholder="Pexels/Pixabay aramasında kullanılacak görsel tanım..." oninput="onInspectorInput('visual', this.value)">${esc(sc.visual || sc.shot || '')}</textarea>
    </div>

    <div style="display:flex;gap:8px;margin-top:10px;">
      <button class="btn btn-secondary flex-1" onclick="searchStockForCurrentScene()">🔍 Bu Sahneye Stok Video Bul</button>
    </div>
  `;
}

window.onInspectorInput = (field, val) => {
  if (!currentEditorScriptData || !currentEditorScriptData.scenes[currentActiveSceneIndex]) return;
  const sc = currentEditorScriptData.scenes[currentActiveSceneIndex];
  sc[field] = val;
  if (field === 'on_screen_text') sc['text'] = val;
  if (field === 'visual') sc['shot'] = val;

  isEditorDirty = true;
  updateDraftBadge(true);
  updateMockupPreview();
  calculateLiveStats();
};

function updateDraftBadge(dirty) {
  const badge = $('#draft-status-badge');
  if (!badge) return;
  if (dirty) {
    badge.className = 'badge badge-orange';
    badge.textContent = 'Taslak: Değişiklikler var *';
  } else {
    badge.className = 'badge badge-green';
    badge.textContent = 'Taslak: Güncel ✓';
  }
}

function calculateLiveStats() {
  if (!currentEditorScriptData) return;
  const scenes = currentEditorScriptData.scenes || [];
  
  // Tüm seslendirme metinlerini birleştir
  let fullText = currentEditorScriptData.narration || '';
  if (scenes.length > 0) {
    const sceneTexts = scenes.map(s => s.narration || s.on_screen_text || '').filter(Boolean);
    if (sceneTexts.length > 0) {
      fullText = sceneTexts.join(' ');
    }
  }

  const words = fullText.trim() ? fullText.trim().split(/\s+/).length : 0;
  // Türkçe konuşma temposu: dakikada ~135 kelime -> saniyede ~2.25 kelime
  const estSeconds = Math.round(words / 2.25);

  if ($('#live-word-count')) $('#live-word-count').textContent = `${words} kelime`;
  if ($('#live-est-duration')) $('#live-est-duration').textContent = `~${estSeconds}s`;
}

function updateMockupPreview() {
  if (!currentEditorScriptData) return;
  const scenes = currentEditorScriptData.scenes || [];
  const sc = scenes[currentActiveSceneIndex];

  if ($('#mockup-scene-badge')) {
    $('#mockup-scene-badge').textContent = sc ? `SAHNE ${currentActiveSceneIndex + 1} (${sc.time || ''})` : 'SAHNE HAZIR DEĞİL';
  }
  if ($('#mockup-visual-preview')) {
    $('#mockup-visual-preview').textContent = sc ? (sc.visual || sc.shot || 'Kamera ve görsel plan tanımlanmadı.') : '';
  }
  if ($('#mockup-subtitle-text')) {
    $('#mockup-subtitle-text').textContent = sc ? `“${sc.on_screen_text || sc.narration || currentEditorScriptData.hook || ''}”` : '';
  }
}

window.addNewScene = () => {
  if (!currentEditorScriptData) return;
  if (!currentEditorScriptData.scenes) currentEditorScriptData.scenes = [];
  
  const count = currentEditorScriptData.scenes.length;
  const startSec = count * 4;
  const endSec = startSec + 4;

  const newScene = {
    time: `${startSec}-${endSec}s`,
    shot: 'Orta çekim, sakin ve sinematik atmosfer',
    visual: 'Atmosferik kentsel detay veya doğa görüntüsü',
    on_screen_text: 'Yeni sahne başlığı',
    narration: 'Bu sahnede söylenecek yeni cümle.'
  };

  currentEditorScriptData.scenes.push(newScene);
  currentActiveSceneIndex = count;
  isEditorDirty = true;
  updateDraftBadge(true);
  
  renderEditorScenesList();
  renderActiveSceneInspector();
  updateMockupPreview();
  calculateLiveStats();
  toast('Yeni sahne eklendi.');
};

window.deleteScene = (idx) => {
  if (!currentEditorScriptData || !currentEditorScriptData.scenes) return;
  if (!confirm(`Sahne ${idx + 1}'i silmek istediğinizden emin misiniz?`)) return;

  currentEditorScriptData.scenes.splice(idx, 1);
  currentActiveSceneIndex = Math.max(0, idx - 1);
  isEditorDirty = true;
  updateDraftBadge(true);

  renderEditorScenesList();
  renderActiveSceneInspector();
  updateMockupPreview();
  calculateLiveStats();
  toast('Sahne silindi.');
};

window.saveCurrentScriptChanges = async () => {
  if (!currentEditorScriptId || !currentEditorScriptData) {
    toast('Kaydedilecek aktif senaryo bulunamadı.');
    return;
  }

  // Sahne seslendirmelerinden genel narration'ı güncelle
  const scenes = currentEditorScriptData.scenes || [];
  const fullNarration = scenes.map(s => s.narration).filter(Boolean).join(' ');

  try {
    await api(`/api/scripts/${currentEditorScriptId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: currentEditorScriptData.title,
        hook: currentEditorScriptData.hook,
        narration: fullNarration || currentEditorScriptData.narration,
        scenes: scenes,
        review: currentEditorScriptData.review
      })
    });
    isEditorDirty = false;
    updateDraftBadge(false);
    toast('Senaryo ve sahneler başarıyla kaydedildi ✓');
    refresh();
  } catch (err) {
    toast(`Kaydetme hatası: ${err.message}`, 'error');
  }
};

window.searchStockForCurrentScene = () => {
  if (!currentEditorScriptData || !currentEditorScriptData.scenes[currentActiveSceneIndex]) return;
  const sc = currentEditorScriptData.scenes[currentActiveSceneIndex];
  const query = sc.visual || sc.shot || currentEditorScriptData.title;
  showView('assets');
  if ($('#stock-query')) {
    $('#stock-query').value = query;
    searchStock();
  }
};

window.toggleMockupPlay = () => {
  if (isMockupPlaying) {
    clearInterval(mockupPlayInterval);
    isMockupPlaying = false;
    if ($('#mockup-play-btn')) $('#mockup-play-btn').textContent = '▶ Storyboard Oynat';
    return;
  }

  if (!currentEditorScriptData || !currentEditorScriptData.scenes || currentEditorScriptData.scenes.length === 0) {
    toast('Oynatılacak sahne bulunamadı.');
    return;
  }

  isMockupPlaying = true;
  if ($('#mockup-play-btn')) $('#mockup-play-btn').textContent = '⏹ Storyboard Durdur';

  mockupPlayInterval = setInterval(() => {
    currentActiveSceneIndex = (currentActiveSceneIndex + 1) % currentEditorScriptData.scenes.length;
    selectScene(currentActiveSceneIndex);
  }, 3000);
};

window.triggerEditorFullProduction = () => {
  if (!currentEditorScriptId) {
    toast('Lütfen önce bir senaryo seçin.');
    return;
  }
  triggerFullAutonomous(currentEditorScriptId, null);
};

// ------------------------------------------------------------------ SENARYO ARŞİVİ (SCRIPT VAULT) --
window.loadVaultScripts = () => {
  const container = $('#vault-scripts-grid');
  if (!container) return;

  const scripts = vaultScriptsCache || [];
  if (scripts.length === 0) {
    container.innerHTML = '<div class="empty">Henüz senaryo bulunmuyor. Fikir & Senaryo sekmesinden yeni üretim başlatın.</div>';
    return;
  }

  filterVaultScripts();
};

window.setVaultStatusFilter = (status, btn) => {
  vaultCurrentFilter = status;
  $$('.filter-pill').forEach(p => p.classList.remove('active'));
  if (btn) btn.classList.add('active');
  filterVaultScripts();
};

window.filterVaultScripts = () => {
  const query = ($('#vault-search-input')?.value || '').toLowerCase().trim();
  const container = $('#vault-scripts-grid');
  if (!container) return;

  let filtered = vaultScriptsCache.filter(s => {
    const matchStatus = 
      vaultCurrentFilter === 'all' ? true :
      vaultCurrentFilter === 'approved' ? s.review === 'approved' :
      vaultCurrentFilter === 'pending' ? (!s.review || s.review === 'pending') :
      vaultCurrentFilter === 'revision' ? s.review === 'revision' : true;

    const matchQuery = !query ? true :
      (s.title && s.title.toLowerCase().includes(query)) ||
      (s.hook && s.hook.toLowerCase().includes(query));

    return matchStatus && matchQuery;
  });

  if (filtered.length === 0) {
    container.innerHTML = '<div class="empty">Filtrelere uygun senaryo bulunamadı.</div>';
    return;
  }

  container.innerHTML = filtered.map(s => `
    <div class="vault-card">
      <div class="vault-card-head">
        <div>
          <h4>${esc(s.title)}</h4>
          <small>${esc(s.language.toUpperCase())} · Kalite: <b>${s.score}/100</b></small>
        </div>
        <span class="badge ${s.review === 'approved' ? 'badge-green' : s.review === 'revision' ? 'badge-orange' : ''}">
          ${s.review === 'approved' ? '✓ Onaylandı' : s.review === 'revision' ? 'Revizyon' : 'İnceleme Bekliyor'}
        </span>
      </div>

      <div class="vault-hook">“${esc(s.hook || 'Giriş kancası tanımlanmadı')}”</div>

      <div class="vault-actions">
        <button class="btn btn-secondary flex-1" onclick="openScriptInEditor('${s.id}')">✍️ Düzenle</button>
        <button class="btn btn-accent flex-1" onclick="triggerFullAutonomous('${s.id}', null)">⚡ Otonom Kurgula</button>
        <button class="btn btn-danger" onclick="deleteScriptVault('${s.id}')" title="Sil">🗑️</button>
      </div>
    </div>
  `).join('');
};

window.deleteScriptVault = async (id) => {
  if (!confirm('Bu senaryoyu arşivden silmek istediğinize emin misiniz?')) return;
  try {
    await api(`/api/scripts/${id}`, { method: 'DELETE' });
    toast('Senaryo arşivden silindi.');
    refresh();
    loadVaultScripts();
  } catch (err) {
    toast(`Silme hatası: ${err.message}`, 'error');
  }
};

// ------------------------------------------------------------------ YENİ RAPORLAR & ANALİZ PANELİ --
async function loadStudioReports() {
  const container = $('#reports-grid');
  if (!container) return;
  container.innerHTML = '<div class="empty">Raporlar yükleniyor...</div>';
  try {
    const reports = await api('/api/reports');
    if (!reports.length) {
      container.innerHTML = '<div class="empty">Henüz üretilmiş bir senaryo veya video raporu bulunmuyor. Fikir & Senaryo sekmesinden ilk üretimi başlatın.</div>';
      return;
    }

    container.innerHTML = reports.map(r => `
      <div class="report-card">
        <div class="report-card-head">
          <div>
            <h4>${esc(r.title)}</h4>
            <small style="color:var(--ink-muted);font-size:10.5px;">${esc(r.created_at)} · ${esc(r.provider || 'AI Engine')}</small>
          </div>
          <span class="badge ${r.score >= 70 ? 'badge-green' : 'badge-orange'}">${r.score}/100 Kalite</span>
        </div>

        ${r.hook ? `<div class="report-hook">“${esc(r.hook)}”</div>` : ''}

        <!-- VİDEO VARSA DİKEY OYNATICI MOCKUP'I -->
        ${r.video_url ? `
          <div class="phone-mockup-wrapper">
            <div class="phone-mockup-screen">
              <video src="${esc(r.video_url)}" controls playsinline></video>
            </div>
          </div>
        ` : `
          <div style="background:#f5f5f0;border-radius:var(--radius-sm);padding:24px;text-align:center;color:var(--ink-muted);font-size:11px;">
            🎬 Henüz video montajı yapılmamış.
          </div>
        `}

        <div class="report-metrics-row">
          <span>Sahneler: <b>${r.scenes_count} Sahne</b></span>
          <span>Durum: <b>${esc(r.review_status === 'approved' ? '✓ Onaylı' : 'İnceleme')}</b></span>
          <span>Dil: <b>${esc(r.language.toUpperCase())}</b></span>
        </div>

        <div class="report-actions">
          ${r.video_url ? `
            <button class="btn btn-secondary flex-1" onclick="window.open('/api/export/${r.script_id}/tiktok-package', '_blank')">📦 TikTok Paketi (.ZIP)</button>
          ` : `
            <button class="btn btn-accent flex-1" onclick="triggerFullAutonomous('${r.script_id}', '${r.workflow_id || ''}')">⚡ Otomatik Kurgula</button>
          `}
          <button class="btn btn-secondary" onclick="generateVoice('${r.script_id}')">🎙️ Seslendir</button>
        </div>
      </div>
    `).join('');

  } catch (err) {
    container.innerHTML = `<div class="agent-error" style="color:var(--accent-red);padding:20px;text-align:center;">Raporlar yüklenemedi: ${esc(err.message)}</div>`;
  }
}

// ------------------------------------------------------------------ AYARLAR (SETTINGS) YÖNETİMİ --
async function loadSettings() {
  try {
    const s = await api('/api/settings');
    
    // Status Badges
    const geminiB = $('#badge-gemini-status');
    if (geminiB) {
      geminiB.className = 'badge ' + (s.gemini_api_key_configured ? 'badge-green' : 'badge-orange');
      geminiB.textContent = s.gemini_api_key_configured ? '✓ Tanımlı' : 'Eksik';
    }

    const groqB = $('#badge-groq-status');
    if (groqB) {
      groqB.className = 'badge ' + (s.groq_api_key_configured ? 'badge-green' : 'badge-orange');
      groqB.textContent = s.groq_api_key_configured ? '✓ Tanımlı' : 'Eksik';
    }

    const pexelsB = $('#badge-pexels-status');
    if (pexelsB) {
      pexelsB.className = 'badge ' + (s.pexels_api_key_configured ? 'badge-green' : '');
      pexelsB.textContent = s.pexels_api_key_configured ? '✓ Tanımlı' : 'Opsiyonel';
    }

    const pixabayB = $('#badge-pixabay-status');
    if (pixabayB) {
      pixabayB.className = 'badge ' + (s.pixabay_api_key_configured ? 'badge-green' : '');
      pixabayB.textContent = s.pixabay_api_key_configured ? '✓ Tanımlı' : 'Opsiyonel';
    }

    const ffmpegB = $('#check-ffmpeg');
    if (ffmpegB) {
      ffmpegB.className = 'badge ' + (s.ffmpeg_installed ? 'badge-green' : 'badge-orange');
      ffmpegB.textContent = s.ffmpeg_installed ? '✓ Hazır (FFmpeg 7.x)' : 'Bulunamadı';
    }

    if ($('#cfg-gemini-model')) $('#cfg-gemini-model').value = s.gemini_model || 'gemini-2.5-flash';
    if ($('#cfg-groq-model')) $('#cfg-groq-model').value = s.groq_model || 'openai/gpt-oss-120b';

    if ($('#cfg-gemini-key') && s.gemini_api_key) $('#cfg-gemini-key').placeholder = s.gemini_api_key;
    if ($('#cfg-groq-key') && s.groq_api_key) $('#cfg-groq-key').placeholder = s.groq_api_key;
    if ($('#cfg-pexels-key') && s.pexels_api_key) $('#cfg-pexels-key').placeholder = s.pexels_api_key;
    if ($('#cfg-pixabay-key') && s.pixabay_api_key) $('#cfg-pixabay-key').placeholder = s.pixabay_api_key;

  } catch (err) {
    console.warn('Ayarlar yüklenemedi:', err);
  }
}

window.saveSettings = async (event) => {
  event.preventDefault();
  const payload = {};
  
  const gKey = $('#cfg-gemini-key')?.value.trim();
  if (gKey) payload.gemini_api_key = gKey;
  const gModel = $('#cfg-gemini-model')?.value.trim();
  if (gModel) payload.gemini_model = gModel;

  const grKey = $('#cfg-groq-key')?.value.trim();
  if (grKey) payload.groq_api_key = grKey;
  const grModel = $('#cfg-groq-model')?.value.trim();
  if (grModel) payload.groq_model = grModel;

  const pKey = $('#cfg-pexels-key')?.value.trim();
  if (pKey) payload.pexels_api_key = pKey;

  const pxKey = $('#cfg-pixabay-key')?.value.trim();
  if (pxKey) payload.pixabay_api_key = pxKey;

  try {
    const res = await api('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    toast(res.message || 'Ayarlar başarıyla kaydedildi ✓');
    loadSettings();
  } catch (err) {
    toast(`Ayarlar kaydedilemedi: ${err.message}`, 'error');
  }
};

// ------------------------------------------------------------------ WORKFLOW KONTROLLERİ (START & STOP) --
function agentStatusLabel(s) {
  return ({
    pending:'Sırada', queued:'Sırada', running:'Çalışıyor',
    completed:'Tamamlandı', failed:'Hata', skipped:'Atlandı', cancelled:'Durduruldu'
  })[s] || s;
}

function renderWorkflow(w) {
  currentActiveWorkflowId = w.id;
  const agents = w.agents || [];
  const done   = agents.filter(a => a.status === 'completed').length;
  const isRunning = ['queued', 'running'].includes(w.status);

  // STOP butonunu göster/gizle
  if ($('#stop-btn')) {
    $('#stop-btn').style.display = isRunning ? 'inline-flex' : 'none';
  }

  const list = agents.map((a, i) => {
    return `
      <div class="agent-run-row ${a.status}">
        <div class="agent-run-index">${String(i + 1).padStart(2, '0')}</div>
        <div class="agent-run-main">
          <b>${esc(a.agent_name)}</b>
          <small>${esc(a.department)}${a.provider ? ' · ' + esc(a.provider) : ''}</small>
          ${a.output?.summary ? `<p>${esc(a.output.summary)}</p>` : ''}
          ${a.error ? `<p style="color:var(--accent-red);font-size:11px;margin-top:4px;">${esc(a.error)}</p>` : ''}
        </div>
        <span class="agent-run-status ${esc(a.status)}">${agentStatusLabel(a.status)}</span>
      </div>`;
  }).join('');

  const stateText =
    w.status === 'awaiting_human_review' ? '<b style="color:var(--forest-green);">Paralel ekip tamamlandı · İnsan onayı bekleniyor</b>' :
    w.status === 'failed'    ? '<b style="color:var(--accent-red);">İş akışı durdu</b>' :
    w.status === 'cancelled' ? '<b style="color:var(--accent-gold);">İş akışı kullanıcı tarafından durduruldu (STOP)</b>' :
    w.status === 'approved'  ? '<b style="color:var(--forest-green);">Senaryo onaylandı ✓</b>' :
    `<b>Uzmanlar paralel çalışıyor · ${done}/${agents.length} tamamlandı</b>`;

  let finalReview = '';
  if (w.status === 'awaiting_human_review' && w.result?.script_id) {
    const sId = w.result.script_id;
    currentExportScriptId = sId;
    currentEditorScriptId = sId;

    const scriptAgent = agents.find(a => a.agent_key === 'scriptwriter');
    const del = scriptAgent?.output?.deliverable || {};
    const sc  = del.script || del;
    const hook      = sc.hook      || '';
    const narration = sc.narration || '';
    const scenes    = sc.scenes    || [];

    finalReview = `
      <div class="panel workflow-final">
        <div class="eyebrow">HUMAN REVIEW GATE · İNSAN ONAYI</div>
        <h3>${esc(w.topic)}</h3>
        ${hook ? `<div class="hook">“${esc(hook)}”</div>` : ''}
        ${narration ? `<div class="eyebrow" style="margin-top:14px">SESLENDİRME METNİ</div><p class="narration">${esc(narration)}</p>` : ''}
        
        <div style="margin-top:14px;">
          <div class="eyebrow">ZAMAN KODLU SAHNELER</div>
          ${scenes.map(s => `
            <div class="scene-row">
              <time>${esc(s.time || '')}</time>
              <div>
                <b>${esc(s.visual || s.shot || 'Sahne')}</b>
                <div style="color:var(--ink-muted);">${esc(s.on_screen_text || s.text || '')}</div>
              </div>
            </div>`).join('')}
        </div>

        <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:18px;">
          <button class="btn btn-primary" onclick="reviewScript('${sId}','approved')">✓ Senaryoyu Onayla</button>
          <button class="btn btn-secondary" onclick="openScriptInEditor('${sId}')">✍️ 3-Kolon Editörde Düzenle</button>
          <button class="btn btn-accent" onclick="triggerFullAutonomous('${sId}', '${w.id}')">⚡ Tek Tıkla Tam Otonom Kurgu</button>
          <button class="btn btn-secondary" onclick="generateVoice('${sId}')">🎙️ Seslendir</button>
          <button class="btn btn-danger" onclick="reviewScript('${sId}','revision')">Revizyon İste</button>
        </div>
      </div>`;
  }

  $('#generated-result').innerHTML = `
    <div class="panel workflow-panel">
      <div class="panel-header">
        <div>
          <div class="eyebrow">CANLI İŞ AKIŞI</div>
          <h3>${esc(w.topic)}</h3>
        </div>
        <div style="display:flex;align-items:center;gap:10px;">
          ${isRunning ? `<button class="btn btn-danger" onclick="cancelActiveWorkflow()">⏹ Durdur (Stop)</button>` : ''}
          <span class="badge ${done === agents.length ? 'badge-green' : 'badge-orange'}">${done}/${agents.length} Uzman</span>
        </div>
      </div>
      <p class="muted" style="margin-bottom:12px;">${stateText}${w.error ? ' · ' + esc(w.error) : ''}</p>
      <div class="agent-run-list">${list || '<div class="empty">Ajanlar başlatılıyor…</div>'}</div>
    </div>
    ${finalReview}`;
}

// ------------------------------------------------------------------ SSE STREAM --
function startWorkflowStream(workflowId) {
  if (activeSSE) { activeSSE.close(); activeSSE = null; }
  const es = new EventSource(`/api/workflows/${workflowId}/stream`);
  activeSSE = es;

  es.onmessage = (e) => {
    try {
      const w = JSON.parse(e.data);
      renderWorkflow(w);
      refresh();
      if (['awaiting_human_review','failed','cancelled','approved','revision_requested'].includes(w.status)) {
        es.close(); activeSSE = null;
        if (w.status === 'awaiting_human_review') toast('Paralel uzman ekip üretimini tamamladı! Senaryo onayınızı bekliyor.');
        if (w.status === 'cancelled') toast('İş akışı durduruldu.');
      }
    } catch {}
  };
  es.onerror = () => { es.close(); activeSSE = null; fallbackPoll(workflowId); };
}

async function fallbackPoll(id) {
  try {
    const w = await api('/api/workflows/' + id);
    renderWorkflow(w);
    await refresh();
    if (['queued','running'].includes(w.status)) setTimeout(() => fallbackPoll(id), 2000);
  } catch (e) { toast(e.message); }
}

// ------------------------------------------------------------------ STOP / CANCEL ACTION --
window.cancelActiveWorkflow = async () => {
  if (!currentActiveWorkflowId) {
    toast('Aktif çalışan bir iş akışı bulunamadı.');
    return;
  }
  toast('İş akışı durduruluyor...');
  try {
    const res = await api(`/api/workflows/${currentActiveWorkflowId}/cancel`, { method: 'POST' });
    toast(res.message || 'İş akışı durduruldu.');
    if ($('#stop-btn')) $('#stop-btn').style.display = 'none';
    refresh();
  } catch (err) {
    toast(`Durdurma hatası: ${err.message}`, 'error');
  }
};

// ------------------------------------------------------------------ GENERATE SUBMIT --
$('#generate-form')?.addEventListener('submit', async e => {
  e.preventDefault();
  const btn = $('#generate-btn');
  btn.disabled = true;
  btn.textContent = 'Paralel ekip başlatılıyor…';
  if ($('#stop-btn')) $('#stop-btn').style.display = 'inline-flex';

  try {
    const d = await api('/api/workflows/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        topic:           $('#topic')?.value,
        language:        $('#language')?.value || 'tr',
        duration:        +($('#duration')?.value || 35),
        format:          $('#format')?.value || 'tiktok_reels',
        target_audience: $('#target-audience')?.value || 'discovery',
        tone:            $('#tone')?.value || 'observant',
        hook_model:      $('#hook-model')?.value || 'intrigue',
        cta:             $('#cta')?.value || '',
        quality_mode:    $('#quality-mode')?.value || 'high',
        project_id:      'welcome',
      }),
    });
    currentActiveWorkflowId = d.workflow_id;
    toast('Uzman ekip paralel olarak çalışmaya başladı');
    startWorkflowStream(d.workflow_id);
  } catch (err) {
    toast(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '✦ Uzman Ekibi Çalıştır';
  }
});

// ------------------------------------------------------------------ VOICE GENERATE (EDGE-TTS) --
window.generateVoice = async (scriptId) => {
  if (!scriptId) {
    toast('Lütfen önce bir senaryo seçin.');
    return;
  }
  toast('Doğal seslendirme oluşturuluyor (Edge-TTS)…');
  try {
    const res = await api(`/api/scripts/${scriptId}/generate-voice`, { method: 'POST' });
    lastVoice = res.filename;
    toast(res.message || 'Seslendirme başarıyla oluşturuldu!');
    if ($('#tts-result')) $('#tts-result').textContent = `Oluşturuldu: ${res.filename}`;
    refresh();
  } catch (err) {
    toast(`Seslendirme hatası: ${err.message}`, 'error');
  }
};

$('#auto-tts-btn')?.addEventListener('click', () => {
  const sId = $('#tts-script-select')?.value;
  if (!sId) { toast('Lütfen önce bir senaryo seçin'); return; }
  generateVoice(sId);
});

// ------------------------------------------------------------------ FULL AUTONOMOUS --
window.triggerFullAutonomous = async (scriptId, workflowId) => {
  if (!scriptId) {
    toast('Lütfen önce bir senaryo seçin.');
    return;
  }
  toast('Yapay zeka otonom kurguyu başlattı: Görseller bulunuyor, seslendiriliyor ve kurgulanıyor…');
  try {
    if (workflowId) {
      toast('Sahneler için en uygun stok videolar taranıyor ve indiriliyor…');
      try { await api(`/api/workflows/${workflowId}/auto-curate`, { method: 'POST' }); } catch (e) { console.log('Curate warn:', e); }
    }
    toast('Sinematik geçişler, ses ve altyazılar birleştiriliyor…');
    const res = await api(`/api/scripts/${scriptId}/full-autonomous-production`, { method: 'POST' });
    currentExportScriptId = scriptId;
    toast(res.message || 'Tam otonom kurgu hazırlandı!');
    showView('reports');
    loadStudioReports();
    refresh();
  } catch (err) {
    toast(`Otonom üretim hatası: ${err.message}`, 'error');
  }
};

$('#full-auto-btn')?.addEventListener('click', () => {
  const sId = $('#export-script')?.value || currentExportScriptId;
  if (!sId) { toast('Lütfen önce bir senaryo seçin'); return; }
  triggerFullAutonomous(sId, null);
});

// ------------------------------------------------------------------ STOCK SEARCH --
async function searchStock() {
  const q = $('#stock-query')?.value.trim();
  if (!q) { toast('Lütfen bir arama terimi girin'); return; }
  const resDiv = $('#stock-results');
  if (!resDiv) return;
  resDiv.innerHTML = '<div class="hint-text">Pexels ve Pixabay üzerinde dikey HD videolar aranıyor…</div>';
  try {
    const items = await api(`/api/stock/search?q=${encodeURIComponent(q)}`);
    if (!items.length) {
      resDiv.innerHTML = '<div class="empty">Sonuç bulunamadı. (.env içinde PEXELS_API_KEY veya PIXABAY_API_KEY tanımlı olduğundan emin olun).</div>';
      return;
    }
    resDiv.innerHTML = '<div class="asset-grid">' + items.map(it => `
      <div class="asset-card">
        <b>${esc(it.source)} Video</b>
        <small>${esc(it.author)}</small>
        <button class="btn btn-primary full" style="margin-top:8px;font-size:10.5px;padding:6px;" onclick='downloadStockItem(${JSON.stringify(it)})'>⬇ Arşive İndir (Ticari Onaylı)</button>
      </div>
    `).join('') + '</div>';
  } catch (err) {
    resDiv.innerHTML = `<div style="color:var(--accent-red);font-size:11.5px;">Hata: ${esc(err.message)}</div>`;
  }
}
$('#stock-search-btn')?.addEventListener('click', searchStock);

window.downloadStockItem = async (it) => {
  toast(`${it.source} videosu indiriliyor…`);
  try {
    await api('/api/stock/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(it)
    });
    toast('Video başarıyla arşive indirildi ve ticari onaylandı ✓');
    refresh();
  } catch (err) {
    toast(`İndirme hatası: ${err.message}`, 'error');
  }
};

// ------------------------------------------------------------------ SMART VIDEO EXPORT --
$('#export-btn')?.addEventListener('click', async () => {
  const id = $('#export-script')?.value || currentExportScriptId;
  if (!id) { toast('Önce kurgulanacak senaryoyu seçin'); return; }
  const fd = new FormData();
  if (lastVoice) fd.append('voice_filename', lastVoice);
  fd.append('burn_subtitles', $('#export-subtitles')?.checked ? 'true' : 'false');
  
  const b = $('#export-btn');
  b.disabled = true;
  b.textContent = 'Sinematik montaj yapılıyor (FFmpeg xfade + safe-zone altyazı)…';
  try {
    const d = await api('/api/export/' + id, { method: 'POST', body: fd });
    currentExportScriptId = id;
    $('#export-result').innerHTML = `
      <div style="background:#edf5ee;border:1px solid #c2dec5;border-radius:var(--radius-sm);padding:12px;margin-top:10px;">
        <a href="${d.url}" target="_blank" style="font-weight:700;color:var(--forest-green);display:block;">${esc(d.filename)} · MP4 Videosunu Aç ↗</a>
        <small style="color:var(--ink-secondary);display:block;margin-top:4px;">${d.clips_count} sahne kilitlendi · Safe-Zone altyazı gömüldü ✓</small>
      </div>`;
    if ($('#tiktok-pkg-btn')) $('#tiktok-pkg-btn').style.display = 'block';
    toast('Sinematik video taslağı başarıyla oluşturuldu!');
    refresh();
  } catch (e) {
    $('#export-result').textContent = e.message;
    toast(e.message, 'error');
  } finally {
    b.disabled = false;
    b.textContent = '▶ Sinematik Video Taslağı Oluştur';
  }
});

$('#tiktok-pkg-btn')?.addEventListener('click', () => {
  if (currentExportScriptId) {
    window.open(`/api/export/${currentExportScriptId}/tiktok-package`, '_blank');
  }
});

window.reviewScript = async (id, status) => {
  try {
    await api(`/api/scripts/${id}/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    });
    toast(status === 'approved' ? 'Senaryo onaylandı ✓' : 'Revizyon olarak işaretlendi');
    refresh();
  } catch (e) { toast(e.message, 'error'); }
};

// ------------------------------------------------------------------ FORMS --
$('#idea-form')?.addEventListener('submit', async e => {
  e.preventDefault();
  try {
    await api('/api/ideas', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: $('#idea-title').value, language: 'tr' }),
    });
    $('#idea-title').value = '';
    toast('Fikir havuzuna eklendi');
    refresh();
  } catch (e) { toast(e.message, 'error'); }
});

$('#asset-form')?.addEventListener('submit', async e => {
  e.preventDefault();
  const f = $('#asset-file')?.files[0];
  if (!f) return;
  const fd = new FormData();
  fd.append('file', f);
  fd.append('kind', $('#asset-kind')?.value || 'video');
  fd.append('license_name', $('#asset-license')?.value || 'Own footage');
  fd.append('commercial_ok', $('#asset-commercial')?.checked ? 'true' : 'false');
  try {
    await api('/api/assets', { method: 'POST', body: fd });
    toast('Medya arşive başarıyla eklendi ✓');
    e.target.reset();
    refresh();
  } catch (e) { toast(e.message, 'error'); }
});

$('#metrics-form')?.addEventListener('submit', async e => {
  e.preventDefault();
  const payload = {
    project_id: 'welcome',
    views: +$('#m-views')?.value || 0,
    avg_watch: +$('#m-watch')?.value || 0,
    saves: +$('#m-saves')?.value || 0,
    shares: +$('#m-shares')?.value || 0,
    followers: +$('#m-followers')?.value || 0,
    notes: $('#m-notes')?.value || '',
  };
  try {
    await api('/api/metrics', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    toast('Performans verisi kaydedildi');
    refresh();
  } catch (e) { toast(e.message, 'error'); }
});

// İLK YÜKLEME
refresh();
loadSettings();
