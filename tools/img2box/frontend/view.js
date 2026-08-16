// HDRI 转天空盒 TAB 页:选 HDRI → 指定 Blender → 烘焙/切图/输出 → 一键浏览器预览
window.__PAGES__ = window.__PAGES__ || [];

window.__PAGES__.push({
  id: 'img2box',
  title: 'HDRI 转天空盒',

  mount(container) {
    let hdriPath = '';
    let running = false;
    const LS_KEY = 'img2box.blenderPath';

    container.innerHTML = `
      <div class="page-head">
        <h1>HDRI 转天空盒</h1>
        <p>HDRI 全景图 → Blender 烘焙 → 4×3 网格切图 → 6 个天空盒面(含 bedwars 版)</p>
      </div>
      <div class="card">
        <h2>1 · 输入 HDRI</h2>
        <div class="dropzone" id="dz">将 HDRI 图片拖到此处,或点击选择(单张 PNG)</div>
        <div class="thumbs" id="hdri-thumb" style="display:none;margin-top:12px;">
          <div class="thumb">
            <img id="hdri-img" alt="">
            <div class="tname" id="hdri-name"></div>
          </div>
        </div>
        <div style="display:flex;gap:8px;margin-top:12px;align-items:center;">
          <input type="file" id="file" accept=".png" hidden>
          <button class="btn" id="pick">选择图片…</button>
          <button class="btn" id="clear">清空</button>
          <span class="empty-hint" id="hint"></span>
        </div>
      </div>
      <div class="card">
        <h2>2 · 环境</h2>
        <div class="field"><span class="field-label">Blender</span>
          <input class="text-input" id="blender" placeholder="blender.exe 的完整路径(烘焙必需)" spellcheck="false">
          <button class="btn" id="browse-blender">浏览…</button>
        </div>
        <div style="margin-top:8px;padding-left:84px;color:var(--muted);font-size:12px;">
          支持 Blender 3.x / 4.x / 5.x,自动匹配对应版本模板;其他版本可能无法打开模板
        </div>
        <div class="field"><span class="field-label">输出目录</span>
          <input class="text-input" id="out" spellcheck="false">
          <button class="btn" id="browse-out">浏览…</button>
        </div>
      </div>
      <div class="runbar">
        <div class="progress" id="progress"><div class="bar"></div></div>
        <button class="btn btn-primary" id="run">开始转换</button>
      </div>
      <div class="card" id="preview-card">
        <h2>预览天空盒</h2>
        <div class="field"><span class="field-label">面图目录</span>
          <input class="text-input" id="skybox-dir" placeholder="6 张面图(right/left/top/bottom/front/back.png)所在文件夹" spellcheck="false">
          <button class="btn" id="browse-skybox">浏览…</button>
        </div>
        <div class="field">
          <span class="field-label"></span>
          <span style="color:var(--muted)">在浏览器中打开 3D 天空盒(拖拽旋转视角),无需重新烘焙</span>
          <button class="btn btn-primary" id="open-preview">在浏览器中预览</button>
        </div>
      </div>
      <div class="card">
        <h2>运行日志</h2>
        <div class="log" id="log">就绪。</div>
      </div>
    `;

    const dz = container.querySelector('#dz');
    const fileInput = container.querySelector('#file');
    const hint = container.querySelector('#hint');
    const hdriThumb = container.querySelector('#hdri-thumb');
    const hdriImg = container.querySelector('#hdri-img');
    const hdriName = container.querySelector('#hdri-name');
    const blenderInput = container.querySelector('#blender');
    const outInput = container.querySelector('#out');
    const logEl = container.querySelector('#log');
    const runBtn = container.querySelector('#run');
    const progress = container.querySelector('#progress');
    const skyboxDirInput = container.querySelector('#skybox-dir');

    let progStart = -1; // 进度行起始位置(一行原地更新,类似抠图模型加载)
    const log = (msg, cls) => {
      let prefix = '';
      if (progStart >= 0) { prefix = '\n'; progStart = -1; }
      logEl.textContent += (logEl.textContent === '就绪。' ? '' : prefix) + msg;
      logEl.className = 'log' + (cls ? ' ' + cls : '');
      logEl.scrollTop = logEl.scrollHeight;
    };
    const progressMsg = (text) => {
      if (progStart < 0) { progStart = logEl.textContent.length; logEl.textContent += '⏳ ' + text; }
      else { logEl.textContent = logEl.textContent.slice(0, progStart) + '⏳ ' + text; }
      logEl.scrollTop = logEl.scrollHeight;
    };

    // ---------- Blender 路径:localStorage 优先,未设置则自动探测 ----------
    const saved = localStorage.getItem(LS_KEY);
    if (saved) blenderInput.value = saved;
    window.api.call('img2box_find_blender').then((r) => {
      if (r.ok && r.result && !blenderInput.value.trim()) blenderInput.value = r.result;
    }).catch(() => {});
    blenderInput.addEventListener('change', () => localStorage.setItem(LS_KEY, blenderInput.value.trim()));
    container.querySelector('#browse-blender').addEventListener('click', async () => {
      const p = await window.api.pickFile();
      if (p) { blenderInput.value = p; localStorage.setItem(LS_KEY, p); }
    });

    // ---------- 输出目录 ----------
    window.api.defaultOut().then((d) => { outInput.value = d; });
    container.querySelector('#browse-out').addEventListener('click', async () => {
      const d = await window.api.pickDir();
      if (d) outInput.value = d;
    });

    // ---------- 输入图片 ----------
    let hdriUrl = '';
    let lastFile = null;
    const setHdri = (path, name) => {
      if (hdriUrl) URL.revokeObjectURL(hdriUrl);
      hdriPath = path;
      hdriUrl = URL.createObjectURL(lastFile);
      hdriImg.src = hdriUrl;
      hdriName.textContent = name;
      hdriThumb.style.display = '';
      hint.textContent = name;
    };
    dz.addEventListener('dragover', (e) => { e.preventDefault(); dz.classList.add('dragover'); });
    dz.addEventListener('dragleave', () => dz.classList.remove('dragover'));
    dz.addEventListener('drop', (e) => {
      e.preventDefault(); dz.classList.remove('dragover');
      const f = e.dataTransfer.files[0];
      if (f) { lastFile = f; setHdri(window.api.pathFor(f), f.name); }
    });
    dz.addEventListener('click', () => fileInput.click());
    container.querySelector('#pick').addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', () => {
      const f = fileInput.files[0];
      if (f) { lastFile = f; setHdri(window.api.pathFor(f), f.name); }
      fileInput.value = '';
    });
    container.querySelector('#clear').addEventListener('click', () => {
      hdriPath = ''; lastFile = null;
      if (hdriUrl) { URL.revokeObjectURL(hdriUrl); hdriUrl = ''; }
      hdriThumb.style.display = 'none';
      hint.textContent = '';
    });

    // ---------- 运行 ----------
    runBtn.addEventListener('click', async () => {
      if (running) return;
      if (!hdriPath) { log('请先添加 HDRI 图片。', 'err'); return; }
      const blender = blenderInput.value.trim();
      if (!blender) { log('请指定 blender.exe 路径。', 'err'); return; }
      const out = outInput.value.trim();
      if (!out) { log('请填写输出目录。', 'err'); return; }

      running = true;
      runBtn.disabled = true;
      runBtn.textContent = '转换中…';
      progress.classList.add('indeterminate');
      log(`开始: ${hint.textContent} → ${out}`);
      try {
        await window.api.call('img2box_process', {
          input: hdriPath, blender_path: blender, out_dir: out,
        });
        log('✓ 全部完成,结果已保存到 ' + out, 'ok');
        // 自动填默认预览目录(标准版面图),也可手动改其他路径预览
        skyboxDirInput.value = out.replace(/[\\/]+$/, '') + '/skybox';
      } catch (e) {
        log('✗ 处理出错: ' + e.message, 'err');
      }
      running = false;
      runBtn.disabled = false;
      runBtn.textContent = '开始转换';
      progress.classList.remove('indeterminate');
    });

    // ---------- 浏览器预览(独立:填任意面图目录即可,无需烘焙) ----------
    container.querySelector('#browse-skybox').addEventListener('click', async () => {
      const d = await window.api.pickDir();
      if (d) skyboxDirInput.value = d;
    });
    container.querySelector('#open-preview').addEventListener('click', async () => {
      const dir = skyboxDirInput.value.trim();
      if (!dir) { log('请填写或选择面图目录。', 'err'); return; }
      try {
        const r = await window.api.call('img2box_preview', { skybox_dir: dir });
        if (r.ok && r.result) {
          log('已启动预览服务: ' + r.result);
          window.api.openUrl(r.result);
        } else {
          log('预览服务启动失败: ' + (r.error || '未知错误'), 'err');
        }
      } catch (e) {
        log('✗ 预览失败: ' + e.message, 'err');
      }
    });

    // ---------- 日志与阶段进度 ----------
    const offLog = window.api.onLog((msg) => {
      if (msg.event === 'progress') progressMsg(msg.message || '');
      else if (msg.event === 'log') log(msg.message || '');
    });

    // ---------- 清理 ----------
    this._cleanup = () => { offLog(); };
  },

  unmount() { if (this._cleanup) this._cleanup(); },
});
