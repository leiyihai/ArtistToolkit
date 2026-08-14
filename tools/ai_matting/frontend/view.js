// AI 抠图 TAB 页(Electron renderer)
// 与 tools/ai_matting/core.py(经 backend.py stdio 服务)联调。
window.__PAGES__ = window.__PAGES__ || [];

window.__PAGES__.push({
  id: 'ai-matting',
  title: 'AI 抠图',

  mount(container) {
    let files = []; // {path, url, name}
    let running = false;

    container.innerHTML = `
      <div class="page-head">
        <h1>AI 抠图</h1>
        <p>拖入图片 → AI 去除背景 → 输出透明背景 PNG(保留原尺寸)</p>
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
        <h2>2 · 输出设置</h2>
        <div class="field"><span class="field-label">输出路径</span>
          <input class="text-input" id="out" spellcheck="false">
          <button class="btn" id="browse">浏览…</button>
        </div>
      </div>
      <div class="runbar">
        <div class="progress" id="progress"><div class="bar"></div></div>
        <button class="btn btn-primary" id="run">开始抠图</button>
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
      const out = outEl.value.trim();
      if (!out) { log('请填写输出保存路径。', 'err'); return; }

      running = true;
      runBtn.disabled = true;
      runBtn.textContent = '抠图中…';
      progress.classList.add('indeterminate');
      log(`开始: ${files.length} 张图 · 输出到 ${out}`);
      try {
        await window.api.call('matting_process', {
          paths: files.map(f => f.path),
          out,
        });
        log('✓ 全部完成,结果已保存到 ' + out, 'ok');
      } catch (e) {
        log('✗ 处理出错: ' + e.message, 'err');
      }
      running = false;
      runBtn.disabled = false;
      runBtn.textContent = '开始抠图';
      progress.classList.remove('indeterminate');
    });

    this._cleanup = () => { offLog(); files.forEach(f => URL.revokeObjectURL(f.url)); };
  },

  unmount() { if (this._cleanup) this._cleanup(); },
});
