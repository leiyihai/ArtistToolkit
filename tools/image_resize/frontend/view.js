// 图片批量缩放 TAB 页(Electron renderer)
// 与 tools/image_resize/core.py(经 backend.py stdio 服务)联调。
window.__PAGES__ = window.__PAGES__ || [];

const PRESETS = [
  ['64×64', 64, 64],
  ['128×128', 128, 128],
  ['256×256', 256, 256],
  ['512×512', 512, 512],
  ['800×600', 800, 600],
  ['1024×768', 1024, 768],
  ['1920×1080', 1920, 1080],
];

window.__PAGES__.push({
  id: 'image-resize',
  title: '批量缩放',

  mount(container) {
    let running = false;
    let cancelled = false;

    container.innerHTML = `
      <div class="page-head">
        <h1>批量缩放</h1>
        <p>递归扫描文件夹 → 精确缩放到目标尺寸 → 保持目录结构输出</p>
      </div>
      <div class="card">
        <h2>1 · 输入文件夹</h2>
        <div class="dropzone" id="in-dz">将文件夹拖到此处,或点击选择</div>
        <div class="path-line" id="in-path"></div>
        <input type="file" id="in-file" webkitdirectory multiple hidden>
      </div>
      <div class="card">
        <h2>2 · 输出文件夹</h2>
        <div class="field"><span class="field-label">输出路径</span>
          <input class="text-input" id="out" spellcheck="false" placeholder="选择或填写输出文件夹">
          <button class="btn" id="browse">浏览…</button>
        </div>
      </div>
      <div class="card">
        <h2>3 · 目标尺寸</h2>
        <div class="field"><span class="field-label">预设</span>
          <div class="chips" id="preset-chips"></div>
        </div>
        <div class="field" style="margin-top:10px;"><span class="field-label">自定义</span>
          <input class="text-input num" id="w" type="number" min="1" max="8192" value="64" style="max-width:100px;">
          <span class="muted">×</span>
          <input class="text-input num" id="h" type="number" min="1" max="8192" value="64" style="max-width:100px;">
          <span class="muted">像素,拉伸填满(不保持比例)</span>
        </div>
      </div>
      <div class="runbar">
        <div class="progress" id="progress"><div class="bar" id="bar"></div></div>
        <button class="btn" id="cancel" disabled>取消</button>
        <button class="btn btn-primary" id="run">开始缩放</button>
      </div>
      <div class="card">
        <h2>运行日志</h2>
        <div class="log" id="log">就绪。</div>
      </div>
    `;

    const inDz = container.querySelector('#in-dz');
    const inPath = container.querySelector('#in-path');
    const inFile = container.querySelector('#in-file');
    const outEl = container.querySelector('#out');
    const logEl = container.querySelector('#log');
    const runBtn = container.querySelector('#run');
    const cancelBtn = container.querySelector('#cancel');
    const bar = container.querySelector('#bar');
    const progress = container.querySelector('#progress');
    const presetChips = container.querySelector('#preset-chips');
    const wEl = container.querySelector('#w');
    const hEl = container.querySelector('#h');
    let inputDir = '';

    const log = (msg, cls) => {
      logEl.textContent += (logEl.textContent === '就绪。' ? '' : '\n') + msg;
      logEl.className = 'log' + (cls ? ' ' + cls : '');
      logEl.scrollTop = logEl.scrollHeight;
    };
    const setInput = (dir) => {
      inputDir = dir;
      inPath.textContent = dir || '未选择';
      inPath.classList.toggle('selected', !!dir);
      inDz.classList.toggle('has-value', !!dir);
    };

    // 输入:按钮 / 点击 dropzone / 拖入文件夹
    inDz.addEventListener('click', () => inFile.click());
    inFile.addEventListener('change', () => {
      const p = window.api.pathFor(inFile.files[0]);
      if (p) setInput(p);
      inFile.value = '';
    });
    inDz.addEventListener('dragover', (e) => { e.preventDefault(); inDz.classList.add('dragover'); });
    inDz.addEventListener('dragleave', () => inDz.classList.remove('dragover'));
    inDz.addEventListener('drop', (e) => {
      e.preventDefault();
      inDz.classList.remove('dragover');
      if (e.dataTransfer.files.length) setInput(window.api.pathFor(e.dataTransfer.files[0]));
    });

    // 输出
    container.querySelector('#browse').addEventListener('click', async () => {
      const d = await window.api.pickDir();
      if (d) outEl.value = d;
    });
    window.api.defaultOut().then(d => { if (!outEl.value) outEl.value = d; });

    // 预设尺寸(单选,点击填充宽高)
    const applyPreset = (w, h, chip) => {
      wEl.value = w; hEl.value = h;
      [...presetChips.children].forEach(c => c.classList.toggle('active', c === chip));
    };
    PRESETS.forEach(([label, w, h]) => {
      const b = document.createElement('button');
      b.className = 'chip';
      b.textContent = label;
      if (w === 64 && h === 64) b.classList.add('active');
      b.addEventListener('click', () => applyPreset(w, h, b));
      presetChips.appendChild(b);
    });
    // 手动改宽高则取消预设高亮
    wEl.addEventListener('input', () => [...presetChips.children].forEach(c => c.classList.remove('active')));
    hEl.addEventListener('input', () => [...presetChips.children].forEach(c => c.classList.remove('active')));

    // 后端日志 + 进度
    const offLog = window.api.onLog((msg) => {
      if (msg.event === 'log') log(msg.message || '');
      else if (msg.event === 'progress' && msg.total) {
        bar.style.width = Math.round(msg.done / msg.total * 100) + '%';
      }
    });

    runBtn.addEventListener('click', async () => {
      if (running) return;
      if (!inputDir) { log('请先选择输入文件夹。', 'err'); return; }
      const out = outEl.value.trim();
      if (!out) { log('请填写输出文件夹。', 'err'); return; }
      const w = +wEl.value, h = +hEl.value;
      if (!(w > 0 && h > 0)) { log('请输入有效的目标尺寸。', 'err'); return; }

      running = true; cancelled = false;
      runBtn.disabled = true; cancelBtn.disabled = false;
      progress.classList.remove('indeterminate');
      bar.style.width = '0%';
      log(`开始: ${inputDir} → ${out} · 目标 ${w}×${h}`);
      try {
        await window.api.call('process', { input: inputDir, output: out, width: w, height: h });
        if (!cancelled) log('✓ 全部完成', 'ok');
      } catch (e) {
        log('✗ 处理出错: ' + e.message, 'err');
      }
      running = false; cancelled = false;
      runBtn.disabled = false; cancelBtn.disabled = true;
    });

    cancelBtn.addEventListener('click', async () => {
      cancelled = true;
      log('正在取消…');
      try { await window.api.call('cancel'); } catch (e) { /* 后端已退出等,忽略 */ }
    });

    this._cleanup = () => offLog();
  },

  unmount() { if (this._cleanup) this._cleanup(); },
});
