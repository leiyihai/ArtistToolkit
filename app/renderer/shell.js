// 外壳:渲染侧边栏页签,切换时 mount/unmount 功能页(功能页经 registerPage 注册)
const PAGES = window.__PAGES__ || [];
const sidebar = document.getElementById('sidebar-pages');
const container = document.getElementById('page-container');
let current = null;

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
