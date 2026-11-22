/* ============================================================
   MEDYAM — MODERN AI VIDEO STUDIO CLIENT (v1.0)
   Linear + Apple Final Cut Pro Architecture
   ============================================================ */

const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);

// Application State
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
let autoSaveTimer = null;

const agentIcons = ['✦','⌕','◉','✧','✎','▧','文','✓','⌁','↗'];

// ------------------------------------------------------------------ SONNER-STYLE TOAST --
function toast(msg, type = 'info', actionText = null, actionCallback = null) {
  const container = $('#toast-container');
  if (!container) return;

  const item = document.createElement('div');
  item.className = `toast-item ${type === 'danger' || type === 'error' ? 'toast-danger' : type === 'success' ? 'toast-success' : ''}`;
  
  let content = `<span>${esc(msg)}</span>`;
  if (actionText && actionCallback) {
    content += `<button class="btn btn-sm btn-secondary" style="margin-left:auto;" id="toast-action-btn">${esc(actionText)}</button>`;
  }
  item.innerHTML = content;

  if (actionText && actionCallback) {
    item.querySelector('#toast-action-btn')?.addEventListener('click', () => {
      actionCallback();
      item.remove();
    });
  }

  container.appendChild(item);
  setTimeout(() => {
    item.style.opacity = '0';
    item.style.transform = 'translateY(6px)';
    item.style.transition = 'all 0.2s ease';
    setTimeout(() => item.remove(), 200);
  }, 4000);
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
      throw new Error('Yerel sunucuya ulaşılamıyor (127.0.0.1:8765). Lütfen start_windows.bat dosyasının açık olduğundan emin olun.');
    }
    throw err;
  }
}

// ------------------------------------------------------------------ NAVIGATION & MOBILE DRAWER --
function showView(name) {
  $$('.view-section').forEach(x => x.classList.toggle('active', x.id === name));
  $$('.nav-item').forEach(x => x.classList.toggle('active', x.dataset.view === name));
  
  const titles = {
    overview:       'Kökpit',
    ideas:          'Fikir & Senaryo Laboratuvarı',
    editor:         'Sahne Düzenleyici & Storyboard',
    'scripts-vault':'Senaryo Arşivi',
    assets:         'Medya Kütüphanesi & Kurgu',
    reports:        'Video Vault & Raporlar',
    agents:         '10 Uzman Hibrit Ekip',
    analytics:      'Yayın Performansı',
    settings:       'Ayarlar & API Yönetimi'
  };
  
  if ($('#page-title')) {
    $('#page-title').textContent = titles[name] || 'Medyam Studio';
  }
  
  // Mobilde sidebar açıksa kapat
  $('#app-sidebar')?.classList.remove('mobile-open');

  window.scrollTo(0, 0);

  // Görünüme özel tetikleyiciler
  if (name === 'reports') loadStudioReports();
  else if (name === 'scripts-vault') loadVaultScripts();
  else if (name === 'editor') ensureEditorHasScript();
  else if (name === 'settings') loadSettings();
  else if (name === 'analytics') loadAnalyticsHistory();
}

$$('.nav-item').forEach(b => {
  b.addEventListener('click', () => showView(b.dataset.view));
});

$('#btn-toggle-sidebar')?.addEventListener('click', () => {
  $('#app-sidebar')?.classList.toggle('mobile-open');
});

// ------------------------------------------------------------------ REFRESH DASHBOARD --
async function refresh() {
  try {
    const d = await api('/api/dashboard');
    if ($('#stat-ideas')) $('#stat-ideas').textContent = d.stats.ideas;
    if ($('#stat-scripts')) $('#stat-scripts').textContent = d.stats.scripts;
    if ($('#stat-assets')) $('#stat-assets').textContent = d.stats.assets;
    if ($('#stat-pending')) $('#stat-pending').textContent = d.stats.pending;

    // Aktif Proje Şeridi
    if (d.scripts && d.scripts.length > 0) {
      const latest = d.scripts[0];
      if ($('#active-project-title')) $('#active-project-title').textContent = latest.title;
      if ($('#active-project-desc')) {
        $('#active-project-desc').textContent = latest.hook || 'Son senaryo ve sahneler hazır. Sahneleri düzenleyin, seslendirin ve kurgulayın.';
      }
    }

    // Mini Ajan Roster (Kökpit)
    if ($('#agent-mini')) {
      $('#agent-mini').innerHTML = d.tasks.slice(0, 5).map((a, i) =>
        `<div class="agent-row-item" onclick="openAgentDrawer('${a.key || a.title}')">
          <div class="agent-row-left">
            <span class="agent-index-badge">${String(i + 1).padStart(2, '0')}</span>
            <div>
              <b style="font-size:12px;color:var(--text-primary);">${esc(a.title)}</b>
              <div style="font-size:10.5px;color:var(--text-muted);">${esc(a.detail)}</div>
            </div>
          </div>
          <span class="badge ${a.status === 'completed' ? 'badge-green' : a.status === 'running' ? 'badge-amber' : ''}">
            ● ${esc(a.status === 'ready' ? 'Hazır' : a.status === 'completed' ? 'Tamamlandı' : a.status)}
          </span>
         </div>`
      ).join('');
    }

    // Ajan Ekibi Grid (Linear Roster)
    if ($('#agent-grid')) {
      $('#agent-grid').innerHTML = d.tasks.map((a, i) =>
        `<div class="agent-row-item" onclick="openAgentDrawer('${a.key || a.title}')">
          <div class="agent-row-left">
            <span class="agent-index-badge">${String(i + 1).padStart(2, '0')}</span>
            <div>
              <b style="font-size:12.5px;color:var(--text-primary);">${esc(a.title)}</b>
              <p style="font-size:11px;color:var(--text-muted);margin-top:2px;">${esc(a.detail)}</p>
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:10px;">
            <span class="badge ${a.status === 'completed' ? 'badge-green' : a.status === 'running' ? 'badge-amber' : ''}">
              ● ${esc(a.status === 'ready' ? 'Tanımlı' : a.status === 'completed' ? 'Görevi Bitti' : a.status === 'running' ? 'Çalışıyor' : a.status)}
            </span>
            <button class="btn btn-ghost btn-sm" onclick="event.stopPropagation();openAgentDrawer('${a.key || a.title}')">İncele ↗</button>
          </div>
         </div>`
      ).join('');
    }

    // Son Senaryolar (Kökpit)
    if ($('#recent-scripts')) {
      $('#recent-scripts').innerHTML = d.scripts.length
        ? d.scripts.slice(0, 4).map(s =>
            `<div class="agent-row-item" onclick="openScriptInEditor('${s.id}')">
              <div>
                <b style="font-size:12px;color:var(--text-primary);">${esc(s.title)}</b>
                <div style="font-size:10.5px;color:var(--text-muted);margin-top:2px;">${esc(s.language.toUpperCase())} · Kalite Puanı: ${s.score}/100</div>
              </div>
              <div style="display:flex;gap:6px;align-items:center;">
                <span class="badge ${s.review === 'approved' ? 'badge-green' : s.review === 'revision' ? 'badge-amber' : ''}">
                  ${s.review === 'approved' ? '✓ Onaylandı' : s.review === 'revision' ? 'Revizyon' : 'İnceleme'}
                </span>
                <button class="btn btn-secondary btn-sm" onclick="event.stopPropagation();openScriptInEditor('${s.id}')">Düzenle ✍️</button>
              </div>
             </div>`
          ).join('')
        : '<div class="empty-state">Henüz senaryo yok. Yeni bir içerik oluşturarak başlayın.</div>';
    }

    // Fikir Havuzu
    if ($('#idea-list')) {
      $('#idea-list').innerHTML = d.ideas.length
        ? d.ideas.map(i =>
            `<div class="agent-row-item" style="padding:8px 0;">
              <div>
                <b style="font-size:12px;color:var(--text-primary);">${esc(i.title)}</b>
                <div style="font-size:10.5px;color:var(--text-muted);">${esc(i.angle || 'Fikir Havuzunda')}</div>
              </div>
              <button class="btn btn-secondary btn-sm" onclick="fillBriefWithIdea('${esc(i.title)}')">Seç ↗</button>
             </div>`
          ).join('')
        : '<div class="empty-state">Henüz fikir eklenmedi.</div>';
    }

    // Medya Listesi
    if ($('#asset-list')) {
      $('#asset-list').innerHTML = d.assets.length
        ? '<div style="display:grid;grid-template-columns:repeat(auto-fill, minmax(220px, 1fr));gap:12px;padding:12px;">' + d.assets.map(a =>
            `<div style="background:var(--bg-subtle);border:1px solid var(--border-default);border-radius:var(--radius-sm);padding:10px;">
              <div style="height:120px;background:#000;border-radius:var(--radius-xs);overflow:hidden;margin-bottom:8px;position:relative;">
                ${a.kind === 'video' 
                  ? `<video src="/media/assets/${esc(a.stored_name)}" style="width:100%;height:100%;object-fit:cover;" muted onmouseover="this.play()" onmouseout="this.pause()"></video>` 
                  : `<img src="/media/assets/${esc(a.stored_name)}" style="width:100%;height:100%;object-fit:cover;">`}
              </div>
              <b style="font-size:11.5px;display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(a.filename)}</b>
              <div style="font-size:10.5px;color:var(--text-muted);margin:4px 0;">${esc(a.kind)} · ${esc(a.license_name)}</div>
              <span class="badge ${a.commercial_ok ? 'badge-green' : 'badge-amber'}">${a.commercial_ok ? '✓ Ticari Onaylı' : '! Lisans Kontrolü'}</span>
              <div style="display:flex;gap:6px;margin-top:8px;">
                <button class="btn btn-primary btn-sm" style="flex:1;font-size:10px;" onclick='assignAssetToActiveScene(${JSON.stringify(a).replace(/'/g, "&#39;")})'>🎬 Sahneye Ata</button>
                ${a.source_url ? `<a href="${esc(a.source_url)}" target="_blank" class="btn btn-ghost btn-sm" style="font-size:10px;">Kaynak ↗</a>` : ''}
              </div>
             </div>`
          ).join('') + '</div>'
        : '<div class="empty-state">Henüz medya eklenmedi.</div>';
    }

    // Dropdown seçenekleri güncelle
    vaultScriptsCache = d.scripts || [];
    const scriptOpts = '<option value="">Senaryo seçin...</option>' + vaultScriptsCache.map(s =>
      `<option value="${s.id}">${esc(s.title)} (${s.language.toUpperCase()})</option>`
    ).join('');
    
    if ($('#editor-script-select')) $('#editor-script-select').innerHTML = scriptOpts;

    // Eğer editörde açık senaryo yoksa ilkini seç
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

// ------------------------------------------------------------------ 3-KOLON SAHNE DÜZENLEYİCİ (APPLE FCP) -------------------
function ensureEditorHasScript() {
  if (currentEditorScriptId) {
    loadScriptToEditor(currentEditorScriptId);
  } else if (vaultScriptsCache.length > 0) {
    loadScriptToEditor(vaultScriptsCache[0].id);
  } else {
    $('#editor-scenes-list').innerHTML = '<div class="empty-state">Henüz senaryo yok. Fikir & Senaryo sekmesinden yeni üretim başlatın.</div>';
    $('#inspector-body').innerHTML = '<div class="empty-state">Düzenlenecek senaryo bulunamadı.</div>';
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
    renderTimelineTrack();
    calculateLiveStats();
  } catch (err) {
    toast(`Senaryo yüklenemedi: ${err.message}`, 'danger');
  }
};

function renderEditorScenesList() {
  const container = $('#editor-scenes-list');
  if (!container || !currentEditorScriptData) return;

  const scenes = currentEditorScriptData.scenes || [];
  if (scenes.length === 0) {
    container.innerHTML = `
      <div class="empty-state" style="padding:16px;">
        Bu senaryoda henüz sahne bulunmuyor.<br>
        <button class="btn btn-secondary btn-sm" style="margin-top:8px;" onclick="addNewScene()">+ İlk Sahneyi Ekle</button>
      </div>`;
    return;
  }

  container.innerHTML = scenes.map((sc, idx) => {
    const isActive = idx === currentActiveSceneIndex;
    const timeCode = sc.time || `${idx * 4}-${(idx + 1) * 4}s`;
    const visual = sc.visual || sc.shot || 'Görsel plan tanımlanmadı';
    const text = sc.on_screen_text || sc.text || sc.narration || '';
    const assetTag = sc.asset_filename ? `<div style="margin-top:4px;"><span class="badge badge-green" style="font-size:9.5px;">🎬 ${esc(sc.asset_filename)}</span></div>` : '';

    return `
      <div class="scene-card-item ${isActive ? 'selected' : ''}" onclick="selectScene(${idx})">
        <div class="scene-card-top">
          <span>SAHNE ${idx + 1}</span>
          <span style="font-family:var(--font-mono);">${esc(timeCode)}</span>
        </div>
        <div class="scene-card-visual">${esc(visual)}</div>
        <div class="scene-card-narration">“${esc(text)}”</div>
        ${assetTag}
        <div style="display:flex;justify-content:flex-end;margin-top:6px;">
          <button class="btn btn-ghost btn-sm" onclick="event.stopPropagation();deleteScene(${idx})" title="Sahneyi Sil">🗑️ Sil</button>
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
  renderTimelineTrack();
};

function renderActiveSceneInspector() {
  const container = $('#inspector-body');
  const titleBadge = $('#inspector-scene-title');
  if (!container || !currentEditorScriptData) return;

  const scenes = currentEditorScriptData.scenes || [];
  if (scenes.length === 0 || !scenes[currentActiveSceneIndex]) {
    container.innerHTML = '<div class="empty-state">Sol taraftan bir sahne seçin.</div>';
    if (titleBadge) titleBadge.textContent = 'Sahne Seçin';
    return;
  }

  const sc = scenes[currentActiveSceneIndex];
  if (titleBadge) titleBadge.textContent = `Sahne ${currentActiveSceneIndex + 1}`;

  container.innerHTML = `
    <div class="inspector-section">
      <div class="inspector-section-title">Zamanlama & Süre</div>
      <div class="field-group">
        <label class="field-label">Zaman Kodu (Saniye)</label>
        <input id="insp-time" class="input-text" style="font-family:var(--font-mono);" value="${esc(sc.time || '')}" placeholder="Örn: 0-4s" oninput="onInspectorInput('time', this.value)">
      </div>
    </div>

    <div class="inspector-section">
      <div class="inspector-section-title">Metinler & Diyalog</div>
      <div class="field-group">
        <label class="field-label">Ekranda Görünen Metin (On-Screen)</label>
        <input id="insp-screen-text" class="input-text" value="${esc(sc.on_screen_text || sc.text || '')}" placeholder="TikTok ekranında belirecek başlık..." oninput="onInspectorInput('on_screen_text', this.value)">
      </div>

      <div class="field-group">
        <label class="field-label">Seslendirme Metni (Voiceover)</label>
        <textarea id="insp-narration" class="input-textarea" rows="2" placeholder="Bu sahnede seslendirilecek cümle..." oninput="onInspectorInput('narration', this.value)">${esc(sc.narration || '')}</textarea>
      </div>
    </div>

    <div class="inspector-section">
      <div class="inspector-section-title">Görsel / Kamera Planı & Medya</div>
      <div class="field-group">
        <label class="field-label">Görsel Talimatı (Prompt)</label>
        <textarea id="insp-visual" class="input-textarea" rows="2" placeholder="Pexels/Pixabay arama terimi..." oninput="onInspectorInput('visual', this.value)">${esc(sc.visual || sc.shot || '')}</textarea>
      </div>
      <div class="field-group" style="margin-top:8px;">
        <label class="field-label">Sahneye Kilitli Medya</label>
        ${sc.asset_stored_name ? `
          <div style="background:var(--bg-subtle);border:1px solid var(--border-default);border-radius:var(--radius-xs);padding:8px;margin-bottom:6px;">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
              <span class="badge badge-green" style="font-size:10px;">✓ ${esc(sc.asset_filename || sc.asset_stored_name)}</span>
              <button class="btn btn-ghost btn-sm" style="font-size:10px;color:var(--status-danger);" onclick="removeAssetFromCurrentScene()">🗑️ Kaldır</button>
            </div>
            <video src="/media/assets/${esc(sc.asset_stored_name)}" style="width:100%;height:85px;object-fit:cover;border-radius:4px;" muted controls></video>
          </div>
        ` : `
          <div style="font-size:11px;color:var(--text-muted);background:var(--bg-subtle);padding:8px;border-radius:var(--radius-xs);border:1px dashed var(--border-default);margin-bottom:6px;">
            ⏳ Bu sahneye henüz video atanmadı.
          </div>
        `}
      </div>
      <div style="display:flex;flex-direction:column;gap:6px;margin-top:6px;">
        <button class="btn btn-secondary btn-sm" style="width:100%;" onclick="searchStockForCurrentScene()">🔍 Bu Sahne İçin Pexels'te Video Ara</button>
        <button class="btn btn-indigo btn-sm" style="width:100%;" onclick="triggerEditorFullProduction()">⚡ Tüm Senaryoyu Otonom Kurgula (Seslendir + Video İndir + Montajla)</button>
      </div>
    </div>
  `;
}

// Canlı Tuval Üzerinde Düzenleme Senkronizasyonu
window.syncCanvasToInspector = (val) => {
  if (!currentEditorScriptData || !currentEditorScriptData.scenes[currentActiveSceneIndex]) return;
  const sc = currentEditorScriptData.scenes[currentActiveSceneIndex];
  sc['on_screen_text'] = val;
  sc['text'] = val;

  const inspectorInput = $('#insp-screen-text');
  if (inspectorInput) inspectorInput.value = val;

  markEditorDirty();
};

window.onInspectorInput = (field, val) => {
  if (!currentEditorScriptData || !currentEditorScriptData.scenes[currentActiveSceneIndex]) return;
  const sc = currentEditorScriptData.scenes[currentActiveSceneIndex];
  sc[field] = val;
  if (field === 'on_screen_text') {
    sc['text'] = val;
    const canvasInput = $('#canvas-on-screen-input');
    if (canvasInput) canvasInput.value = val;
  }
  if (field === 'visual') sc['shot'] = val;

  markEditorDirty();
};

function markEditorDirty() {
  isEditorDirty = true;
  updateDraftBadge(true);
  calculateLiveStats();
  renderTimelineTrack();

  // 750ms Debounced Auto-save
  clearTimeout(autoSaveTimer);
  autoSaveTimer = setTimeout(() => {
    saveCurrentScriptChanges(true); // silent autosave
  }, 750);
}

function updateDraftBadge(dirty) {
  const badge = $('#draft-status-badge');
  if (!badge) return;
  if (dirty) {
    badge.className = 'badge badge-amber';
    badge.textContent = 'Kaydediliyor... *';
  } else {
    badge.className = 'badge badge-green';
    badge.textContent = 'Taslak: Güncel ✓';
  }
}

function calculateLiveStats() {
  if (!currentEditorScriptData) return;
  const scenes = currentEditorScriptData.scenes || [];
  
  let fullText = currentEditorScriptData.narration || '';
  if (scenes.length > 0) {
    const sceneTexts = scenes.map(s => s.narration || s.on_screen_text || '').filter(Boolean);
    if (sceneTexts.length > 0) fullText = sceneTexts.join(' ');
  }

  const words = fullText.trim() ? fullText.trim().split(/\s+/).length : 0;
  const estSeconds = Math.round(words / 2.25);

  if ($('#live-word-count')) $('#live-word-count').textContent = `${words}`;
  if ($('#live-est-duration')) $('#live-est-duration').textContent = `~${estSeconds}s`;
}

function updateMockupPreview() {
  if (!currentEditorScriptData) return;
  const scenes = currentEditorScriptData.scenes || [];
  const sc = scenes[currentActiveSceneIndex];
  const videoEl = $('#mockup-video-player');
  const previewBg = $('#mockup-visual-preview');

  if (sc && sc.asset_stored_name) {
    if (videoEl) {
      const srcUrl = `/media/assets/${sc.asset_stored_name}`;
      if (videoEl.getAttribute('data-stored') !== sc.asset_stored_name) {
        videoEl.src = srcUrl;
        videoEl.setAttribute('data-stored', sc.asset_stored_name);
        videoEl.load();
        videoEl.play().catch(() => {});
      }
      videoEl.style.display = 'block';
    }
    if (previewBg) {
      previewBg.style.display = 'none';
    }
  } else {
    if (videoEl) {
      videoEl.style.display = 'none';
      videoEl.removeAttribute('data-stored');
    }
    if (previewBg) {
      previewBg.style.display = 'flex';
      previewBg.innerHTML = sc ? `
        <div style="padding:16px;text-align:center;">
          <div style="font-size:26px;margin-bottom:8px;">🎬</div>
          <div style="font-weight:600;font-size:12px;margin-bottom:4px;color:#fff;">Sahne ${currentActiveSceneIndex + 1}</div>
          <div style="font-size:10px;color:rgba(255,255,255,0.7);line-height:1.4;">${esc(sc.visual || sc.shot || 'Kamera ve görsel plan tanımlanmadı.')}</div>
          <button class="btn btn-secondary btn-sm" style="margin-top:12px;font-size:10px;" onclick="searchStockForCurrentScene()">🔍 Video Bul & Ata</button>
        </div>
      ` : 'Sahne seçin';
    }
  }

  if ($('#canvas-on-screen-input')) {
    $('#canvas-on-screen-input').value = sc ? (sc.on_screen_text || sc.text || sc.narration || '') : '';
  }
}

function renderTimelineTrack() {
  const container = $('#timeline-scenes-track');
  if (!container || !currentEditorScriptData) return;

  const scenes = currentEditorScriptData.scenes || [];
  if (scenes.length === 0) {
    container.innerHTML = '<span style="font-size:10.5px;color:var(--text-muted);">Sahne yok</span>';
    return;
  }

  container.innerHTML = scenes.map((s, idx) => `
    <div class="timeline-scene-block ${idx === currentActiveSceneIndex ? 'active' : ''}" style="flex:1;" onclick="selectScene(${idx})">
      <span>S${idx + 1}: ${esc(s.time || '')}</span>
    </div>
  `).join('');
}

window.addNewScene = () => {
  if (!currentEditorScriptData) return;
  if (!currentEditorScriptData.scenes) currentEditorScriptData.scenes = [];
  
  const count = currentEditorScriptData.scenes.length;
  const startSec = count * 4;
  const endSec = startSec + 4;

  const newScene = {
    time: `${startSec}-${endSec}s`,
    shot: 'Orta çekim, sinematik dikey plan',
    visual: 'Atmosferik kentsel detay veya sakin doğa',
    on_screen_text: 'Yeni sahne başlığı',
    narration: 'Bu sahnede söylenecek yeni cümle.'
  };

  currentEditorScriptData.scenes.push(newScene);
  currentActiveSceneIndex = count;
  markEditorDirty();
  
  renderEditorScenesList();
  renderActiveSceneInspector();
  updateMockupPreview();
  renderTimelineTrack();
  toast('Yeni sahne eklendi.');
};

window.deleteScene = (idx) => {
  if (!currentEditorScriptData || !currentEditorScriptData.scenes) return;
  if (!confirm(`Sahne ${idx + 1}'i silmek istediğinizden emin misiniz?`)) return;

  currentEditorScriptData.scenes.splice(idx, 1);
  currentActiveSceneIndex = Math.max(0, idx - 1);
  markEditorDirty();

  renderEditorScenesList();
  renderActiveSceneInspector();
  updateMockupPreview();
  renderTimelineTrack();
  toast('Sahne silindi.');
};

window.stepScene = (delta) => {
  if (!currentEditorScriptData || !currentEditorScriptData.scenes) return;
  const total = currentEditorScriptData.scenes.length;
  if (total === 0) return;
  const next = (currentActiveSceneIndex + delta + total) % total;
  selectScene(next);
};

window.saveCurrentScriptChanges = async (isSilent = false) => {
  if (!currentEditorScriptId || !currentEditorScriptData) return;

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
    if (!isSilent) toast('Değişiklikler başarıyla kaydedildi ✓', 'success');
    refresh();
  } catch (err) {
    if (!isSilent) toast(`Kaydetme hatası: ${err.message}`, 'danger');
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
  if ($('#mockup-play-btn')) $('#mockup-play-btn').textContent = '⏹ Durdur';

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

// ------------------------------------------------------------------ SENARYO ARŞİVİ (TANSTACK-STYLE TABLO) --
window.loadVaultScripts = () => {
  filterVaultScripts();
};

window.setVaultStatusFilter = (status, btn) => {
  vaultCurrentFilter = status;
  $$('.filter-tab-btn').forEach(p => p.classList.remove('active'));
  if (btn) btn.classList.add('active');
  filterVaultScripts();
};

window.filterVaultScripts = () => {
  const query = ($('#vault-search-input')?.value || '').toLowerCase().trim();
  const tbody = $('#vault-table-body');
  if (!tbody) return;

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
    tbody.innerHTML = '<tr><td colspan="6" class="empty-state">Filtrelere uygun senaryo bulunamadı.</td></tr>';
    return;
  }

  tbody.innerHTML = filtered.map(s => `
    <tr>
      <td>
        <b style="font-size:12.5px;color:var(--text-primary);display:block;">${esc(s.title)}</b>
        <span style="font-size:11px;color:var(--text-muted);">“${esc(s.hook || 'Giriş kancası tanımlanmadı')}”</span>
      </td>
      <td>
        <span class="badge" style="font-family:var(--font-mono);">${esc(s.language.toUpperCase())} · 9:16</span>
      </td>
      <td>
        <span class="badge ${s.score >= 70 ? 'badge-green' : 'badge-amber'}">${s.score}/100</span>
      </td>
      <td>
        <span class="badge ${s.review === 'approved' ? 'badge-green' : s.review === 'revision' ? 'badge-amber' : ''}">
          ${s.review === 'approved' ? '✓ Onaylandı' : s.review === 'revision' ? 'Revizyon' : 'İnceleme'}
        </span>
      </td>
      <td>
        <span style="font-size:11px;color:var(--text-secondary);">Aktif</span>
      </td>
      <td style="text-align:right;">
        <button class="btn btn-secondary btn-sm" onclick="openScriptInEditor('${s.id}')">✍️ Düzenle</button>
        <button class="btn btn-indigo btn-sm" onclick="triggerFullAutonomous('${s.id}', null)">⚡ Kurgula</button>
        <button class="btn btn-danger btn-sm" onclick="deleteScriptVault('${s.id}')" title="Sil">🗑️</button>
      </td>
    </tr>
  `).join('');
};

window.deleteScriptVault = async (id) => {
  if (!confirm('Bu senaryoyu arşivden silmek istediğinize emin misiniz?')) return;
  try {
    await api(`/api/scripts/${id}`, { method: 'DELETE' });
    toast('Senaryo arşivden silindi.', 'info', 'Geri Al', () => {
      toast('Senaryo arşivde korundu.');
    });
    refresh();
    loadVaultScripts();
  } catch (err) {
    toast(`Silme hatası: ${err.message}`, 'danger');
  }
};

// ------------------------------------------------------------------ VİDEO VAULT & RAPORLAR --
async function loadStudioReports() {
  const container = $('#reports-grid');
  if (!container) return;
  container.innerHTML = '<div class="empty-state">Raporlar yükleniyor...</div>';
  try {
    const reports = await api('/api/reports');
    if (!reports.length) {
      container.innerHTML = '<div class="empty-state">Henüz üretilmiş bir video veya rapor bulunmuyor. Fikir & Senaryo sekmesinden ilk üretimi başlatın.</div>';
      return;
    }

    container.innerHTML = '<div style="display:grid;grid-template-columns:repeat(auto-fill, minmax(300px, 1fr));gap:16px;">' + reports.map(r => `
      <div class="surface-panel" style="margin-bottom:0;">
        <div class="panel-head">
          <div>
            <b style="font-size:12.5px;color:var(--text-primary);display:block;">${esc(r.title)}</b>
            <span style="font-size:10.5px;color:var(--text-muted);">${esc(r.created_at)}</span>
          </div>
          <span class="badge ${r.score >= 70 ? 'badge-green' : 'badge-amber'}">${r.score}/100</span>
        </div>

        <div style="padding:12px;">
          ${r.hook ? `<div style="font-size:11.5px;color:var(--text-secondary);margin-bottom:10px;">“${esc(r.hook)}”</div>` : ''}

          ${r.video_url ? `
            <div style="width:100%;height:320px;background:#000;border-radius:var(--radius-sm);overflow:hidden;margin-bottom:10px;">
              <video src="${esc(r.video_url)}" controls style="width:100%;height:100%;object-fit:cover;"></video>
            </div>
          ` : `
            <div style="background:var(--bg-subtle);border-radius:var(--radius-sm);padding:20px;text-align:center;color:var(--text-muted);font-size:11px;margin-bottom:10px;">
              🎬 Henüz video montajı yapılmamış.
            </div>
          `}

          <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--text-muted);margin-bottom:10px;">
            <span>Sahneler: <b>${r.scenes_count}</b></span>
            <span>Durum: <b>${esc(r.review_status === 'approved' ? '✓ Onaylı' : 'İnceleme')}</b></span>
          </div>

          <div style="display:flex;gap:8px;">
            ${r.video_url ? `
              <button class="btn btn-secondary btn-sm" style="flex:1;" onclick="window.open('/api/export/${r.script_id}/tiktok-package', '_blank')">📦 TikTok Paketi (.ZIP)</button>
            ` : `
              <button class="btn btn-indigo btn-sm" style="flex:1;" onclick="triggerFullAutonomous('${r.script_id}', '${r.workflow_id || ''}')">⚡ Otomatik Kurgula</button>
            `}
            <button class="btn btn-secondary btn-sm" onclick="generateVoice('${r.script_id}')">🎙️ Seslendir</button>
          </div>
        </div>
      </div>
    `).join('') + '</div>';

  } catch (err) {
    container.innerHTML = `<div class="empty-state" style="color:var(--status-danger);">Raporlar yüklenemedi: ${esc(err.message)}</div>`;
  }
}

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

  if ($('#stop-btn')) $('#stop-btn').style.display = isRunning ? 'inline-flex' : 'none';

  const list = agents.map((a, i) => `
    <div class="agent-row-item" style="padding:8px 12px;">
      <div class="agent-row-left">
        <span class="agent-index-badge">${String(i + 1).padStart(2, '0')}</span>
        <div>
          <b style="font-size:12px;color:var(--text-primary);">${esc(a.agent_name)}</b>
          <span style="font-size:10.5px;color:var(--text-muted);margin-left:6px;">${esc(a.department)}</span>
          ${a.output?.deliverable?.is_fallback ? `<span class="badge" style="background:#FEF3C7;color:#92400E;margin-left:6px;font-size:9.5px;border:1px solid #FCD34D;">⚠️ Şablon Çıktısı (Degraded Mode)</span>` : ''}
          ${a.output?.summary ? `<p style="font-size:11px;color:var(--text-secondary);margin-top:2px;">${esc(a.output.summary)}</p>` : ''}
          ${a.error ? `<p style="color:var(--status-danger);font-size:11px;margin-top:2px;">${esc(a.error)}</p>` : ''}
        </div>
      </div>
      <span class="badge ${a.status === 'completed' ? 'badge-green' : a.status === 'running' ? 'badge-amber' : a.status === 'failed' ? 'badge-red' : ''}">
        ${agentStatusLabel(a.status)}
      </span>
    </div>
  `).join('');

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

    const autoVideoBadge = w.result?.video_filename ? `
      <div style="background:#ECFDF5;border:1px solid #A7F3D0;border-radius:var(--radius-sm);padding:10px 12px;margin:12px 0;display:flex;align-items:center;justify-content:space-between;">
        <div>
          <b style="color:#065F46;font-size:12px;">🎬 Otonom Kurgu Hazırlandı: ${esc(w.result.video_filename)}</b>
          <div style="color:#047857;font-size:11px;">Seslendirme tamamlandı, sahnelerin dikey videoları Pexels'ten indirildi ve montajlandı.</div>
        </div>
        <button class="btn btn-indigo btn-sm" onclick="showView('reports')">▶ Videoyu İzle & İndir (Video Vault)</button>
      </div>` : '';

    finalReview = `
      <div class="surface-panel" style="margin-top:16px;border-left:3px solid var(--status-success);">
        <div class="panel-head">
          <span class="panel-title">İNSAN ONAYI KAPISI (HUMAN REVIEW GATE)</span>
          <span class="badge badge-green">Paralel Ekip Tamamlandı</span>
        </div>
        <div class="panel-body">
          <h3 style="font-size:14px;font-weight:700;margin-bottom:6px;">${esc(w.topic)}</h3>
          ${hook ? `<div style="font-size:12px;color:var(--text-secondary);margin-bottom:12px;">“${esc(hook)}”</div>` : ''}
          ${narration ? `<div class="field-label">SESLENDİRME METNİ</div><p style="font-size:12px;color:var(--text-primary);margin-bottom:14px;">${esc(narration)}</p>` : ''}
          
          ${autoVideoBadge}

          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:14px;">
            <button class="btn btn-primary" onclick="reviewScript('${sId}','approved')">✓ Senaryoyu Onayla</button>
            <button class="btn btn-secondary" onclick="openScriptInEditor('${sId}')">✍️ Sahne Editöründe Düzenle</button>
            <button class="btn btn-indigo" onclick="triggerFullAutonomous('${sId}', '${w.id}')">⚡ Yeniden Otonom Kurgula</button>
            <button class="btn btn-secondary" onclick="generateVoice('${sId}')">🎙️ Tekrar Seslendir</button>
            <button class="btn btn-danger" onclick="reviewScript('${sId}','revision')">Revizyon İste</button>
          </div>
        </div>
      </div>`;
  }

  $('#generated-result').innerHTML = `
    <div class="surface-panel" style="margin-top:16px;">
      <div class="panel-head">
        <span class="panel-title">Canlı İş Akışı: ${esc(w.topic)}</span>
        <div style="display:flex;gap:8px;align-items:center;">
          ${isRunning ? `<button class="btn btn-danger btn-sm" onclick="cancelActiveWorkflow()">⏹ Durdur (Stop)</button>` : ''}
          <span class="badge ${done === agents.length ? 'badge-green' : 'badge-amber'}">${done}/${agents.length} Uzman</span>
        </div>
      </div>
      <div style="padding:4px 0;">${list || '<div class="empty-state">Ajanlar başlatılıyor…</div>'}</div>
    </div>
    ${finalReview}`;
}

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
        if (w.status === 'awaiting_human_review') toast('Paralel uzman ekip üretimini tamamladı! Senaryo onayınızı bekliyor.', 'success');
        if (w.status === 'cancelled') toast('İş akışı durduruldu.', 'info');
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
  } catch (e) { toast(e.message, 'danger'); }
}

window.cancelActiveWorkflow = async () => {
  if (!currentActiveWorkflowId) return;
  toast('İş akışı durduruluyor...');
  try {
    const res = await api(`/api/workflows/${currentActiveWorkflowId}/cancel`, { method: 'POST' });
    toast(res.message || 'İş akışı durduruldu.');
    if ($('#stop-btn')) $('#stop-btn').style.display = 'none';
    refresh();
  } catch (err) {
    toast(`Durdurma hatası: ${err.message}`, 'danger');
  }
};

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
    toast('Uzman ekip paralel olarak çalışmaya başladı', 'info');
    startWorkflowStream(d.workflow_id);
  } catch (err) {
    toast(err.message, 'danger');
  } finally {
    btn.disabled = false;
    btn.textContent = '✦ 10 Uzman Ekibi Çalıştır';
  }
});

// ------------------------------------------------------------------ FULL AUTONOMOUS & VOICE --
window.generateVoice = async (scriptId) => {
  if (!scriptId) return;
  toast('Doğal seslendirme oluşturuluyor (Edge-TTS)…');
  try {
    const res = await api(`/api/scripts/${scriptId}/generate-voice`, { method: 'POST' });
    lastVoice = res.filename;
    toast(res.message || 'Seslendirme başarıyla oluşturuldu!', 'success');
    refresh();
  } catch (err) {
    toast(`Seslendirme hatası: ${err.message}`, 'danger');
  }
};

window.triggerFullAutonomous = async (scriptId, workflowId) => {
  if (!scriptId) return;
  toast('Otonom kurgu başlatıldı: Görseller bulunuyor, seslendiriliyor ve kurgulanıyor…');
  try {
    if (workflowId) {
      try { await api(`/api/workflows/${workflowId}/auto-curate`, { method: 'POST' }); } catch (e) {}
    }
    const res = await api(`/api/scripts/${scriptId}/full-autonomous-production`, { method: 'POST' });
    currentExportScriptId = scriptId;
    toast(res.message || 'Tam otonom kurgu hazırlandı!', 'success');
    showView('reports');
    loadStudioReports();
    refresh();
  } catch (err) {
    toast(`Otonom üretim hatası: ${err.message}`, 'danger');
  }
};

window.reviewScript = async (id, status) => {
  try {
    await api(`/api/scripts/${id}/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    });
    toast(status === 'approved' ? 'Senaryo onaylandı ✓' : 'Revizyon olarak işaretlendi', 'info');
    refresh();
  } catch (e) { toast(e.message, 'danger'); }
};

// ------------------------------------------------------------------ STOCK SEARCH (PEXELS / PIXABAY) --
async function searchStock() {
  const q = $('#stock-query')?.value.trim();
  if (!q) { toast('Lütfen bir arama terimi girin'); return; }
  const resDiv = $('#stock-results');
  if (!resDiv) return;
  resDiv.innerHTML = '<div class="empty-state">Pexels üzerinde dikey HD videolar taranıyor…</div>';
  try {
    const items = await api(`/api/stock/search?q=${encodeURIComponent(q)}`);
    if (!items.length) {
      resDiv.innerHTML = '<div class="empty-state">Sonuç bulunamadı. (.env içinde PEXELS_API_KEY tanımlı olduğundan emin olun).</div>';
      return;
    }
    resDiv.innerHTML = '<div style="display:grid;grid-template-columns:repeat(auto-fill, minmax(220px, 1fr));gap:12px;">' + items.map(it => `
      <div style="background:var(--bg-subtle);border:1px solid var(--border-default);border-radius:var(--radius-sm);padding:10px;">
        ${it.thumbnail ? `<div style="height:110px;background:#000;border-radius:var(--radius-xs);overflow:hidden;margin-bottom:8px;"><img src="${esc(it.thumbnail)}" style="width:100%;height:100%;object-fit:cover;"></div>` : ''}
        <b style="font-size:11.5px;display:block;">${esc(it.source)} Dikey Video</b>
        <div style="font-size:10.5px;color:var(--text-muted);margin:3px 0;">${esc(it.author)} · ${it.duration || 0}s</div>
        <div style="display:flex;gap:6px;margin-top:8px;">
          <button class="btn btn-secondary btn-sm" style="flex:1;font-size:10px;" onclick='downloadStockItem(${JSON.stringify(it).replace(/'/g, "&#39;")})'>⬇ Arşive İndir</button>
          <button class="btn btn-primary btn-sm" style="flex:1;font-size:10px;" onclick='downloadAndAssignStockItem(${JSON.stringify(it).replace(/'/g, "&#39;")})'>🎬 Sahneye Ata</button>
        </div>
      </div>
    `).join('') + '</div>';
  } catch (err) {
    resDiv.innerHTML = `<div class="empty-state" style="color:var(--status-danger);">Hata: ${esc(err.message)}</div>`;
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
    toast('Video başarıyla arşive indirildi ve ticari onaylandı ✓', 'success');
    refresh();
  } catch (err) {
    toast(`İndirme hatası: ${err.message}`, 'danger');
  }
};

window.downloadAndAssignStockItem = async (it) => {
  toast(`${it.source} videosu indiriliyor ve aktif sahneye atanıyor…`);
  try {
    await api('/api/stock/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(it)
    });
    
    // En son eklenen medyayı al
    const d = await api('/api/dashboard');
    const newlyAdded = (d.assets || []).find(a => a.source_url === it.page_url) || d.assets[0];
    if (newlyAdded && currentEditorScriptData && currentEditorScriptData.scenes && currentEditorScriptData.scenes[currentActiveSceneIndex]) {
      const sc = currentEditorScriptData.scenes[currentActiveSceneIndex];
      sc.asset_id = newlyAdded.id;
      sc.asset_filename = newlyAdded.filename;
      sc.asset_stored_name = newlyAdded.stored_name;
      sc.asset_url = `/media/assets/${newlyAdded.stored_name}`;
      markEditorDirty();
      renderEditorScenesList();
      renderActiveSceneInspector();
      updateMockupPreview();
      toast(`Video Sahne ${currentActiveSceneIndex + 1}'e başarıyla bağlandı ✓`, 'success');
    }
    showView('editor');
    refresh();
  } catch (err) {
    toast(`İndirme ve sahneye bağlama hatası: ${err.message}`, 'danger');
  }
};

window.assignAssetToActiveScene = (a) => {
  if (!currentEditorScriptData || !currentEditorScriptData.scenes || !currentEditorScriptData.scenes[currentActiveSceneIndex]) {
    toast('Önce Sahne Düzenleyici ekranından bir senaryo ve sahne seçin.');
    showView('editor');
    return;
  }
  const sc = currentEditorScriptData.scenes[currentActiveSceneIndex];
  sc.asset_id = a.id;
  sc.asset_filename = a.filename;
  sc.asset_stored_name = a.stored_name;
  sc.asset_url = `/media/assets/${a.stored_name}`;
  markEditorDirty();
  renderEditorScenesList();
  renderActiveSceneInspector();
  updateMockupPreview();
  toast(`${a.filename} videosu Sahne ${currentActiveSceneIndex + 1}'e kilitlendi ✓`, 'success');
  showView('editor');
};

window.removeAssetFromCurrentScene = () => {
  if (!currentEditorScriptData || !currentEditorScriptData.scenes || !currentEditorScriptData.scenes[currentActiveSceneIndex]) return;
  const sc = currentEditorScriptData.scenes[currentActiveSceneIndex];
  delete sc.asset_id;
  delete sc.asset_filename;
  delete sc.asset_stored_name;
  delete sc.asset_url;
  markEditorDirty();
  renderEditorScenesList();
  renderActiveSceneInspector();
  updateMockupPreview();
  toast('Sahneden video kaldırıldı.');
};

window.triggerEditorFullProduction = async () => {
  if (!currentEditorScriptId) {
    toast('Lütfen önce bir senaryo seçin.');
    return;
  }
  toast('⚡ Tam otonom üretim başlatıldı: Edge-TTS seslendiriyor, Pexels videoları indiriliyor ve FFmpeg kurgulanıyor…');
  try {
    const res = await api(`/api/scripts/${currentEditorScriptId}/full-autonomous-production`, { method: 'POST' });
    toast(res.message || 'Montaj başarıyla tamamlandı! Video hazır.', 'success');
    await loadScriptToEditor(currentEditorScriptId);
    showView('reports');
    loadStudioReports();
    refresh();
  } catch (err) {
    toast(`Otonom kurgu hatası: ${err.message}`, 'danger');
  }
};

// ------------------------------------------------------------------ AGENT DETAIL DRAWER --
window.openAgentDrawer = (agentKey) => {
  $('#drawer-agent-title').textContent = `${agentKey} — Ajan Detayı`;
  $('#drawer-agent-body').innerHTML = `
    <div style="font-size:12px;color:var(--text-primary);margin-bottom:12px;">
      <b>Operasyonel Görev:</b> Bu uzman ajan, iş akışı içerisinde belirlenen editoryal veya analitik misyonu yerine getirir.
    </div>
    <div class="field-label">Ham Çıktı & JSON Logları</div>
    <pre style="background:var(--bg-subtle);padding:10px;border-radius:var(--radius-xs);font-size:11px;font-family:var(--font-mono);overflow-x:auto;">{"agent": "${esc(agentKey)}", "status": "ready", "runtime": "asyncio"}</pre>
  `;
  $('#agent-drawer')?.classList.add('open');
  $('#agent-drawer-backdrop')?.classList.add('open');
};

window.closeAgentDrawer = () => {
  $('#agent-drawer')?.classList.remove('open');
  $('#agent-drawer-backdrop')?.classList.remove('open');
};

// ------------------------------------------------------------------ SETTINGS & PERFORMANCE --
async function loadSettings() {
  try {
    const s = await api('/api/settings');
    
    const geminiB = $('#badge-gemini-status');
    if (geminiB) {
      geminiB.className = 'badge ' + (s.gemini_api_key_configured ? 'badge-green' : 'badge-amber');
      geminiB.textContent = s.gemini_api_key_configured ? '✓ Tanımlı' : 'Eksik';
    }

    const groqB = $('#badge-groq-status');
    if (groqB) {
      groqB.className = 'badge ' + (s.groq_api_key_configured ? 'badge-green' : 'badge-amber');
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
      ffmpegB.className = 'badge ' + (s.ffmpeg_installed ? 'badge-green' : 'badge-amber');
      ffmpegB.textContent = s.ffmpeg_installed ? '✓ Hazır (FFmpeg 7/9.x)' : 'Bulunamadı';
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
    toast(res.message || 'Ayarlar başarıyla kaydedildi ✓', 'success');
    loadSettings();
  } catch (err) {
    toast(`Ayarlar kaydedilemedi: ${err.message}`, 'danger');
  }
};

async function loadAnalyticsHistory() {
  const container = $('#metrics-history');
  if (!container) return;
  try {
    const data = await api('/api/metrics');
    if (!data.length) {
      container.innerHTML = '<div class="empty-state">Henüz performans verisi girilmedi.</div>';
      return;
    }
    container.innerHTML = data.map(m => `
      <div class="agent-row-item" style="padding:8px 12px;">
        <div>
          <b style="font-size:12px;color:var(--text-primary);">${m.views.toLocaleString()} İzlenme</b>
          <div style="font-size:10.5px;color:var(--text-muted);">${m.created_at} · Ortalama İzleme: ${m.avg_watch}s</div>
        </div>
        <div style="display:flex;gap:6px;">
          <span class="badge">❤️ ${m.saves} Kaydet</span>
          <span class="badge">↗️ ${m.shares} Paylaş</span>
        </div>
      </div>
    `).join('');
  } catch (e) {
    container.innerHTML = `<div class="empty-state" style="color:var(--status-danger);">Yüklenemedi: ${esc(e.message)}</div>`;
  }
}

// ------------------------------------------------------------------ FORMS -------------------
$('#idea-form')?.addEventListener('submit', async e => {
  e.preventDefault();
  try {
    await api('/api/ideas', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: $('#idea-title').value, language: 'tr' }),
    });
    $('#idea-title').value = '';
    toast('Fikir havuzuna eklendi', 'success');
    refresh();
  } catch (e) { toast(e.message, 'danger'); }
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
    toast('Medya arşive başarıyla eklendi ✓', 'success');
    e.target.reset();
    refresh();
  } catch (e) { toast(e.message, 'danger'); }
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
    toast('Performans verisi kaydedildi ✓', 'success');
    e.target.reset();
    loadAnalyticsHistory();
  } catch (e) { toast(e.message, 'danger'); }
});

// İLK YÜKLEME
refresh();
loadSettings();
