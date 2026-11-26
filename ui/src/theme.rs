//! 还原 Electron 版的 Claude 配色与排版。
//!
//! 取值来自 `app/renderer/styles.css` 的 `:root`:
//! 暖米白底 + 白卡片 + 珊瑚橙强调色,13px 基准字号、10px 圆角。

use gpui_kit::component::Theme;
use gpui_kit::*;

/// 侧边栏宽度(`#sidebar { width: 208px }`)。
pub const SIDEBAR_WIDTH: f32 = 208.0;
/// 页面内容区内边距(`#page-container { padding: 22px 26px }`)。
pub const CONTENT_PAD_X: f32 = 26.0;
pub const CONTENT_PAD_Y: f32 = 22.0;
/// 卡片圆角(`--radius: 10px`)。
pub const RADIUS: f32 = 10.0;

pub fn bg() -> Hsla {
    rgb(0xf5f4ef).into()
}
pub fn panel() -> Hsla {
    rgb(0xffffff).into()
}
pub fn panel_2() -> Hsla {
    rgb(0xf0eee8).into()
}
pub fn panel_log() -> Hsla {
    rgb(0xfaf9f6).into()
}
pub fn border() -> Hsla {
    rgb(0xe5e3dc).into()
}
pub fn border_strong() -> Hsla {
    rgb(0xc9c5bb).into()
}
pub fn text() -> Hsla {
    rgb(0x1f1e1d).into()
}
pub fn muted() -> Hsla {
    rgb(0x6f6c66).into()
}
pub fn accent() -> Hsla {
    rgb(0xd97757).into()
}
pub fn accent_hover() -> Hsla {
    rgb(0xc9603f).into()
}
/// `rgba(217, 119, 87, 0.12)`,gpui 的 rgba 把透明度放在低 8 位。
pub fn accent_dim() -> Hsla {
    rgba(0xd3771f1f).into()
}
pub fn ok() -> Hsla {
    rgb(0x2f9e6e).into()
}
pub fn danger() -> Hsla {
    rgb(0xd6453d).into()
}
pub fn white() -> Hsla {
    rgb(0xffffff).into()
}

/// 把 gpui-kit 的全局主题调成 Electron 版的观感,让组件(按钮/输入/复选框/进度条)
/// 与自绘控件用同一套色板。
pub fn install(cx: &mut App) {
    let theme: &mut Theme = Theme::global_mut(cx);
    theme.radius = px(RADIUS);
    theme.font_family = "Microsoft YaHei UI".into();
    theme.font_size = px(13.);
    theme.mono_font_family = "Cascadia Mono".into();
    theme.mono_font_size = px(12.);

    let colors = &mut theme.colors;
    colors.background = bg();
    colors.foreground = text();
    colors.border = border();
    colors.muted = panel_2();
    colors.muted_foreground = muted();
    colors.popover = panel();
    colors.popover_foreground = text();
    colors.input = panel();
    colors.ring = accent();
    colors.selection = accent_dim();
    colors.danger = danger();
    colors.danger_foreground = white();
    colors.success = ok();
    colors.progress_bar = accent();
    colors.slider_bar = accent();
    colors.slider_thumb = accent();
    colors.caret = accent();
    colors.title_bar = bg();
    colors.title_bar_border = border();
    colors.overlay = rgba(0x1e1d1d99).into();

    colors.primary = accent();
    colors.primary_hover = accent_hover();
    colors.primary_active = accent_hover();
    colors.primary_foreground = white();

    colors.secondary = panel();
    colors.secondary_hover = panel_2();
    colors.secondary_active = panel_2();
    colors.secondary_foreground = text();

    colors.button = panel();
    colors.button_hover = panel_2();
    colors.button_active = panel_2();
    colors.button_foreground = text();
    colors.button_primary = accent();
    colors.button_primary_hover = accent_hover();
    colors.button_primary_active = accent_hover();
    colors.button_primary_foreground = white();
    colors.button_secondary = panel();
    colors.button_secondary_hover = panel_2();
    colors.button_secondary_active = panel_2();
    colors.button_secondary_foreground = text();

    colors.sidebar = panel();
    colors.sidebar_foreground = muted();
    colors.sidebar_border = border();
    colors.sidebar_accent = panel_2();
    colors.sidebar_accent_foreground = text();
    colors.sidebar_primary = accent();
    colors.sidebar_primary_foreground = white();

    colors.list = panel();
    colors.list_hover = panel_2();
    colors.list_active = accent_dim();
    colors.list_active_border = accent();
}
