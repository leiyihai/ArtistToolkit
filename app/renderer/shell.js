// 外壳:动态加载功能页脚本(tools/<name>/frontend/view.js),渲染侧边栏,切换时 mount/unmount
// 新增 TAB 页:在 features.js 的 FEATURES 里登记文件夹名(见 docs/new-tab-guide.md),无需改本文件
const FEATURES = window.__FEATURES__ || [];

const sidebar = document.getElementById('sidebar-pages');
const container = document.getElementById('page-container');
let current = null;

function loadScript(url) {
  return new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = url;
    s.onload = resolve;
    s.onerror = () => reject(new Error('功能页加载失败: ' + url));
    document.head.appendChild(s);
  });
}

(async () => {
  const toolsRoot = await window.api.toolsRoot();
  const base = 'file:///' + toolsRoot.replace(/\\/g, '/');
  await Promise.all(FEATURES.map((name) => loadScript(base + '/' + name + '/frontend/view.js')));

  const PAGES = window.__PAGES__ || [];
  // 并发加载完成顺序不定,按 features.js 定义的 FEATURES 顺序固定页签排序
  // (view.js 的 id 用连字符,FEATURES 用下划线,归一化后匹配)
  const idx = (p) => FEATURES.indexOf((p.id || '').replace(/-/g, '_'));
  PAGES.sort((a, b) => idx(a) - idx(b));
  PAGES.forEach((page, i) => {
    const btn = document.createElement('button');
    btn.className = 'nav-btn';
    btn.textContent = page.title;
    btn.addEventListener('click', () => show(i));
    sidebar.appendChild(btn);
  });

  function show(i) {
    if (current && current.unmount) current.unmount();
    current = PAGES[i];
    container.innerHTML = '';
    current.mount(container);
    [...sidebar.children].forEach((b, j) => b.classList.toggle('active', j === i));
  }

  if (PAGES.length) show(0);
  else container.innerHTML = '<div class="empty-hint" style="margin-top:80px">没有可用的功能页</div>';
})().catch((e) => {
  console.error(e);
  container.innerHTML = '<div class="empty-hint" style="margin-top:80px">功能页加载失败,请重新启动</div>';
});
