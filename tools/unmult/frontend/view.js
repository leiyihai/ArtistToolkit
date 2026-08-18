// 特效抠图 TAB 页(Electron renderer)
// 与 tools/unmult/core.py(经 backend.py stdio 服务)联调。
window.__PAGES__ = window.__PAGES__ || [];

window.__PAGES__.push({
  id: 'unmult',
  title: '特效抠图',

  mount(container) {
    let files = []; // {path, url, name}
    let running = false;

    container.innerHTML = `
      <div class="page-head">
        <h1>特效抠图</h1>
        <p>去掉黑底 / 白底,输出带真实 Alpha 的透明 PNG(火焰、烟雾、粒子、光效素材)</p>
      </div>
      <div class="card">
        <h2>1 · 添加图片</h2>
        <div class="dropzone" id="dz">将图片拖到此处,或点击选择(PNG / JPG / TIFF / WebP,可多张)</div>
        <div class="thumbs" id="thumbs"></div>
        <div style="display:flex;gap:8px;margin-top:12px;align-items:center;">
          <input type="file" id="file" accept=".png,.jpg,.jpeg,.tif,.tiff,.webp" multiple hidden>
          <button class="btn" id="pick">选择图片…</button>
          <button class="btn" id="clear">清空</button>
          <span class="empty-hint" id="hint"></span>
        </div>
      </div>
      <div class="card">
        <h2>2 · 处理选项</h2>
        <div class="field"><span class="field-label">背景模式</span>
          <div class="seg" id="mode-seg"></div>
        </div>
        <div class="field"><span class="field-label">边缘清理(Defringe)
          <span class="muted" id="df-val">0(关闭)</span>
        </span>
          <input type="range" id="df" min="0" max="100" value="0" step="5" style="flex:1;max-width:280px;">
        </div>
        <div class="field"><span class="field-label"></span>
          <label class="chip" style="user-select:none;"><input type="checkbox" id="rebuild" style="vertical-align:-2px;"> 忽略输入自带 Alpha,重新计算</label>
          <label class="chip" style="user-select:none;"><input type="checkbox" id="no-ow" style="vertical-align:-2px;"> 输出已存在时跳过</label>
        </div>
      </div>
      <div class="card">
        <h2>3 · 输出路径</h2>
        <div class="field"><span class="field-label">输出路径</span>
          <input class="text-input" id="out" spellcheck="false">
          <button class="btn" id="browse">浏览…</button>
        </div>
      </div>
      <div class="runbar">
        <div class="progress" id="progress"><div class="bar" id="bar"></div></div>
        <button class="btn btn-primary" id="run">开始处理</button>
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
    const bar = container.querySelector('#bar');
    const modeSeg = container.querySelector('#mode-seg');

    const MODES = [
      ['auto', '自动判断'],
      ['black', '去黑底'],
      ['white', '去白底'],
    ];
    let mode = 'auto';

    const log = (msg, cls) => {
      logEl.textContent += (logEl.textContent === '就绪。' ? '' : '\n') + msg;
      logEl.className = 'log' + (cls ? ' ' + cls : '');
      logEl.scrollTop = logEl.scrollHeight;
    };

    const renderThumbs = () => {
      thumbs.innerHTML = '';
      if (!files.length) { hint.textContent = ''; return; }
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
        if (!/\.(png|jpe?g|tiff?|webp)$/i.test(f.name)) continue;
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

    // 模式单选
    MODES.forEach(([v, label]) => {
      const b = document.createElement('button');
      b.textContent = label;
      b.dataset.v = v;
      if (v === mode) b.classList.add('active');
      b.addEventListener('click', () => {
        mode = v;
        [...modeSeg.children].forEach(x => x.classList.toggle('active', x === b));
      });
      modeSeg.appendChild(b);
    });

    // Defringe 滑块
    const dfVal = container.querySelector('#df-val');
    const df = container.querySelector('#df');
    df.addEventListener('input', () => {
      const v = +df.value;
      dfVal.textContent = v === 0 ? '0(关闭)' : (v / 100).toFixed(2);
    });

    container.querySelector('#browse').addEventListener('click', async () => {
      const d = await window.api.pickDir();
      if (d) outEl.value = d;
    });
    window.api.defaultOut().then(d => { if (!outEl.value) outEl.value = d; });

    // 后端日志 + 进度
    const offLog = window.api.onLog((msg) => {
      if (msg.event === 'log') log(msg.message || '');
      else if (msg.event === 'progress' && msg.total) {
        bar.style.width = Math.round(msg.done / msg.total * 100) + '%';
      }
    });

    runBtn.addEventListener('click', async () => {
      if (running) return;
      if (!files.length) { log('请先添加图片(拖入或点击“选择图片”)。', 'err'); return; }
      const out = outEl.value.trim();
      if (!out) { log('请填写输出保存路径。', 'err'); return; }

      running = true;
      runBtn.disabled = true;
      runBtn.textContent = '处理中…';
      progress.classList.remove('indeterminate');
      bar.style.width = '0%';
      const modeName = MODES.find(m => m[0] === mode)[1];
      const defringe = +df.value / 100;
      log(`开始: ${files.length} 张图 · 模式【${modeName}】 · 输出到 ${out}`);
      try {
        await window.api.call('unmult_process', {
          paths: files.map(f => f.path),
          out,
          mode,
          defringe,
          rebuild_alpha: container.querySelector('#rebuild').checked,
          no_overwrite: container.querySelector('#no-ow').checked,
        });
        log('✓ 全部完成,结果已保存到 ' + out, 'ok');
      } catch (e) {
        log('✗ 处理出错: ' + e.message, 'err');
      }
      running = false;
      runBtn.disabled = false;
      runBtn.textContent = '开始处理';
    });

    this._cleanup = () => { offLog(); files.forEach(f => URL.revokeObjectURL(f.url)); };
  },

  unmount() { if (this._cleanup) this._cleanup(); },
});
