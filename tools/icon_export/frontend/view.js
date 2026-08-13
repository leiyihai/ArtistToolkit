// 批量图标导出 TAB 页(Electron renderer)
// 与 tools/icon_export/core.py(经 backend.py stdio 服务)联调。
window.__PAGES__ = window.__PAGES__ || [];

const CROPS = [
  ['original', '无(直接缩放)'],
  ['square', '方形'],
  ['circle', '正圆'],
  ['rounded_square', '圆角方形'],
];
const SIZES = [32, 64, 128, 256];
const CORNER_MIN = 1;   // 圆角半径下限(px,以 128px 输出为基准)
const CORNER_MAX = 64;  // 上限(px):64px = 128px 边长的 50%
const CORNER_DEFAULT = 18;  // 默认 18px(≈ 14% × 128)

window.__PAGES__.push({
  id: 'icon-export',
  title: '批量图标导出',

  mount(container) {
    let files = []; // {path, url, name}
    let running = false;
    const state = { crop: 'original', normalize: false, cornerRatio: CORNER_DEFAULT };

    container.innerHTML = `
      <div class="page-head">
        <h1>批量图标导出</h1>
        <p>拖入图片 → 抠图去背景 → 拆分为独立图标 → 按形状与尺寸裁切输出</p>
      </div>
      <div class="card">
        <h2>1 · 添加图片</h2>
        <div class="dropzone" id="dz">将图片拖到此处,或点击选择(PNG / JPG / WebP,可多张)</div>
        <div class="thumbs" id="thumbs"></div>
        <div style="display:flex;gap:8px;margin-top:12px;align-items:center;">
          <input type="file" id="file" accept=".png,.jpg,.jpeg,.webp" multiple hidden>
          <button class="btn" id="pick">选择图片…</button>
          <button class="btn" id="clear">清空</button>
          <span class="empty-hint" id="hint"></span>
        </div>
      </div>
      <div class="card">
        <h2>2 · 输出选项</h2>
        <div class="field"><span class="field-label">裁切类型</span>
          <div class="seg" id="crop-seg"></div>
        </div>
        <div class="field disabled" id="corner-row"><span class="field-label">圆角半径
          <span class="q" id="corner-q">?</span>
          <span class="tooltip" id="corner-tip">圆角半径以 128px 输出为基准设置;其他输出尺寸按比例换算。</span>
        </span>
          <input type="range" id="corner" min="1" max="64" value="18" step="1">
          <span class="corner-val" id="corner-val">18px</span>
        </div>
        <div class="field"><span class="field-label">输出尺寸</span>
          <div class="chips" id="size-chips"></div>
        </div>
        <div class="field"><span class="field-label">输出路径</span>
          <input class="text-input" id="out" spellcheck="false">
          <button class="btn" id="browse">浏览…</button>
        </div>
        <div class="field"><span class="field-label"></span>
          <label class="chip" id="norm" style="user-select:none;">统一图标视觉大小</label>
        </div>
      </div>
      <div class="runbar">
        <div class="progress" id="progress"><div class="bar"></div></div>
        <button class="btn btn-primary" id="run">开始导出</button>
      </div>
      <div class="card">
        <h2>运行日志</h2>
        <div class="log" id="log">就绪。</div>
      </div>
    `;

    const dz = container.querySelector('#dz');
    const thumbs = container.querySelector('#thumbs');
    const hint = container.querySelector('#hint');
    const fileInput = container.querySelector('#file');
    const outEl = container.querySelector('#out');
    const logEl = container.querySelector('#log');
    const runBtn = container.querySelector('#run');
    const progress = container.querySelector('#progress');
    const cropSeg = container.querySelector('#crop-seg');
    const sizeChips = container.querySelector('#size-chips');

    // 裁切类型(单选)
    const cornerRow = container.querySelector('#corner-row');
    const cornerSlider = container.querySelector('#corner');
    const cornerVal = container.querySelector('#corner-val');
    CROPS.forEach(([v, label]) => {
      const b = document.createElement('button');
      b.textContent = label;
      b.dataset.v = v;
      if (v === state.crop) b.classList.add('active');
      b.addEventListener('click', () => {
        state.crop = v;
        [...cropSeg.children].forEach(x => x.classList.toggle('active', x === b));
        cornerRow.classList.toggle('disabled', v !== 'rounded_square');
      });
      cropSeg.appendChild(b);
    });
    // 圆角半径(仅圆角方形生效,单位 px,以 128px 输出为基准)
    cornerSlider.addEventListener('input', () => {
      state.cornerRatio = +cornerSlider.value;
      cornerVal.textContent = cornerSlider.value + 'px';
    });
    // 说明浮窗:点击 ? 切换
    const cornerQ = container.querySelector('#corner-q');
    const cornerTip = container.querySelector('#corner-tip');
    cornerQ.addEventListener('click', (e) => {
      e.stopPropagation();
      cornerTip.classList.toggle('show');
    });
    document.addEventListener('click', (e) => {
      if (!cornerTip.contains(e.target) && e.target !== cornerQ) cornerTip.classList.remove('show');
    });
    // 输出尺寸(多选,默认 128)
    SIZES.forEach(s => {
      const b = document.createElement('button');
      b.textContent = `${s}×${s}`;
      b.dataset.v = s;
      if (s === 128) b.classList.add('active');
      b.addEventListener('click', () => b.classList.toggle('active'));
      sizeChips.appendChild(b);
    });
    // normalize 开关
    const norm = container.querySelector('#norm');
    norm.addEventListener('click', () => {
      state.normalize = !state.normalize;
      norm.classList.toggle('active', state.normalize);
    });

    const log = (msg, cls) => {
      logEl.textContent += (logEl.textContent === '就绪。' ? '' : '\n') + msg;
      logEl.className = 'log' + (cls ? ' ' + cls : '');
      logEl.scrollTop = logEl.scrollHeight;
    };

    const renderThumbs = () => {
      thumbs.innerHTML = '';
      if (!files.length) { thumbs.innerHTML = ''; hint.textContent = ''; return; }
      hint.textContent = `已添加 ${files.length} 张`;
      files.forEach((f, i) => {
        const t = document.createElement('div');
        t.className = 'thumb';
        const img = document.createElement('img');
        img.src = f.url;
        const name = document.createElement('div');
        name.className = 'tname';
        name.textContent = f.name;
        name.title = f.name;
        const x = document.createElement('button');
        x.className = 'tremove';
        x.textContent = '×';
        x.title = '移除';
        x.addEventListener('click', () => { URL.revokeObjectURL(f.url); files.splice(i, 1); renderThumbs(); });
        t.append(img, name, x);
        thumbs.appendChild(t);
      });
    };

    const addFiles = (fileList) => {
      let added = 0;
      for (const f of fileList) {
        if (!/\.(png|jpe?g|webp)$/i.test(f.name)) continue;
        if (files.some(x => x.path === f.path)) continue;
        files.push({ path: window.api.pathFor(f), url: URL.createObjectURL(f), name: f.name });
        added++;
      }
      if (added) renderThumbs();
    };

    dz.addEventListener('dragover', (e) => { e.preventDefault(); dz.classList.add('dragover'); });
    dz.addEventListener('dragleave', () => dz.classList.remove('dragover'));
    dz.addEventListener('drop', (e) => {
      e.preventDefault();
      dz.classList.remove('dragover');
      if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
    });
    dz.addEventListener('click', () => fileInput.click());
    container.querySelector('#pick').addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', () => { addFiles(fileInput.files); fileInput.value = ''; });
    container.querySelector('#clear').addEventListener('click', () => {
      files.forEach(f => URL.revokeObjectURL(f.url));
      files = [];
      renderThumbs();
    });
    container.querySelector('#browse').addEventListener('click', async () => {
      const d = await window.api.pickDir();
      if (d) outEl.value = d;
    });

    // 默认输出路径
    window.api.defaultOut().then(d => { outEl.value = d; });

    // 后端日志(本页活动期间)
    const offLog = window.api.onLog((msg) => {
      if (msg.event === 'log') log(msg.message || '');
    });

    runBtn.addEventListener('click', async () => {
      if (running) return;
      if (!files.length) { log('请先添加图片(拖入或点击“选择图片”)。', 'err'); return; }
      const sizes = [...sizeChips.querySelectorAll('.active')].map(b => +b.dataset.v);
      if (!sizes.length) { log('请至少勾选一个输出尺寸。', 'err'); return; }
      const out = outEl.value.trim();
      if (!out) { log('请填写输出保存路径。', 'err'); return; }
      const cornerDesc = state.crop === 'rounded_square' ? ` · 圆角 ${state.cornerRatio}px` : '';

      running = true;
      runBtn.disabled = true;
      runBtn.textContent = '处理中…';
      progress.classList.add('indeterminate');
      log(`开始: ${files.length} 张图 · ${CROPS.find(c => c[0] === state.crop)[1]}${cornerDesc} · ${sizes.join('/')} · ${out}`);
      try {
        await window.api.call('process_batch', {
          paths: files.map(f => f.path),
          crop: state.crop,
          sizes,
          out,
          normalize: state.normalize,
          corner_ratio: state.crop === 'rounded_square' ? state.cornerRatio / 128 : undefined,
        });
        log('✓ 全部完成,结果已保存到 ' + out, 'ok');
      } catch (e) {
        log('✗ 处理出错: ' + e.message, 'err');
      }
      running = false;
      runBtn.disabled = false;
      runBtn.textContent = '开始导出';
      progress.classList.remove('indeterminate');
    });

    this._cleanup = () => { offLog(); files.forEach(f => URL.revokeObjectURL(f.url)); };
  },

  unmount() { if (this._cleanup) this._cleanup(); },
});
