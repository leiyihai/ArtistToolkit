// 页签配置:功能目录名 + 侧边栏顺序(数组顺序 = 显示顺序)。
// 调整页签排序/增删,只改这里;渲染与打包校验均读取本文件。
// 对应显示名在各 tools/<name>/frontend/view.js 的 title 中定义。
window.__FEATURES__ = [
  'ai_matting',     // 智能抠图
  'unmult',         // 特效抠图
  'icon_export',    // 图集拆分
  'image_resize',   // 快捷尺寸
  'img2box',        // 天空盒烘焙
];
