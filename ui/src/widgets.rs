//! 与 Electron 版对齐的界面构件(卡片、按钮、分段选择、chip、字段行、拖放区、日志)。
//!
//! 尺寸/颜色都取自 `app/renderer/styles.css`,便于逐像素对照。

use gpui_kit::component::*;
use gpui_kit::prelude::FluentBuilder as _;
use gpui_kit::*;

use std::path::PathBuf;

use crate::theme;
use crate::thumbs::ThumbCache;

/// 白底卡片(`.card`):1px 边框、10px 圆角、16px 内边距。
pub fn card() -> Div {
    div()
        .w_full()
        .p(px(16.))
        .rounded(px(theme::RADIUS))
        .border_1()
        .border_color(theme::border())
        .bg(theme::panel())
}

/// 卡片标题(`.card h2`):12px、600、muted。
pub fn card_title(text: &'static str) -> Div {
    div()
        .mb(px(12.))
        .text_size(px(12.))
        .font_weight(FontWeight::SEMIBOLD)
        .text_color(theme::muted())
        .child(text)
}

/// 默认按钮(`.btn`):白底、1px 边框、圆角 10、8×16 内边距。
pub fn button(
    id: impl Into<ElementId>,
    label: impl Into<SharedString>,
    primary: bool,
    on_click: impl Fn(&ClickEvent, &mut Window, &mut App) + 'static,
) -> Stateful<Div> {
    let label: SharedString = label.into();
    div()
        .id(id)
        .flex()
        .items_center()
        .justify_center()
        .gap(px(6.))
        .px(px(16.))
        .py(px(8.))
        .rounded(px(theme::RADIUS))
        .border_1()
        .border_color(if primary { theme::accent() } else { theme::border() })
        .bg(if primary { theme::accent() } else { theme::panel() })
        .text_color(if primary { theme::white() } else { theme::text() })
        .text_size(px(13.))
        .cursor_pointer()
        .when(primary, |this| this.font_weight(FontWeight::SEMIBOLD))
        .when(!primary, |this| {
            this.hover(|this| this.bg(theme::panel_2()).border_color(theme::border_strong()))
        })
        .when(primary, |this| this.hover(|this| this.bg(theme::accent_hover())))
        .child(label)
        .on_click(on_click)
}

/// 分段选择的容器(`.seg`):浅底、1px 边框、3px 内边距。
pub fn seg_container() -> Div {
    div()
        .flex()
        .items_center()
        .gap(px(2.))
        .p(px(3.))
        .rounded(px(theme::RADIUS))
        .border_1()
        .border_color(theme::border())
        .bg(theme::panel_2())
}

/// 分段选择里的一项(`.seg button`,选中时珊瑚橙填充)。
pub fn seg_item(
    id: impl Into<ElementId>,
    label: impl Into<SharedString>,
    active: bool,
    enabled: bool,
    on_click: impl Fn(&ClickEvent, &mut Window, &mut App) + 'static,
) -> Stateful<Div> {
    let label: SharedString = label.into();
    div()
        .id(id)
        .px(px(14.))
        .py(px(6.))
        .rounded(px(7.))
        .text_size(px(13.))
        .when(active, |this| {
            this.bg(theme::accent())
                .text_color(theme::white())
                .font_weight(FontWeight::SEMIBOLD)
        })
        .when(!active, |this| {
            this.text_color(theme::muted()).hover(|this| this.text_color(theme::text()))
        })
        .when(!enabled, |this| this.opacity(0.45))
        .when(enabled, |this| this.cursor_pointer())
        .child(label)
        .when(enabled, |this| this.on_click(on_click))
}

/// 多选 chip(`.chip`):胶囊形,选中珊瑚橙。
pub fn chip(
    id: impl Into<ElementId>,
    label: impl Into<SharedString>,
    active: bool,
    enabled: bool,
    on_click: impl Fn(&ClickEvent, &mut Window, &mut App) + 'static,
) -> Stateful<Div> {
    let label: SharedString = label.into();
    div()
        .id(id)
        .px(px(14.))
        .py(px(6.))
        .rounded(px(999.))
        .border_1()
        .border_color(if active { theme::accent() } else { theme::border() })
        .bg(if active { theme::accent() } else { theme::panel() })
        .text_color(if active { theme::white() } else { theme::muted() })
        .text_size(px(13.))
        .when(active, |this| this.font_weight(FontWeight::SEMIBOLD))
        .when(!active && enabled, |this| {
            this.hover(|this| this.border_color(theme::border_strong()).text_color(theme::text()))
        })
        .when(!enabled, |this| this.opacity(0.45))
        .when(enabled, |this| this.cursor_pointer())
        .child(label)
        .when(enabled, |this| this.on_click(on_click))
}

/// 复选 chip(Electron 版把 checkbox 做成胶囊按钮):方框 + 文案。
pub fn check_chip(
    id: impl Into<ElementId>,
    label: impl Into<SharedString>,
    checked: bool,
    enabled: bool,
    on_click: impl Fn(&ClickEvent, &mut Window, &mut App) + 'static,
) -> Stateful<Div> {
    let label: SharedString = label.into();
    div()
        .id(id)
        .flex()
        .items_center()
        .gap(px(6.))
        .px(px(13.))
        .py(px(5.))
        .rounded(px(999.))
        .border_1()
        .border_color(if checked {
            theme::accent()
        } else {
            theme::border()
        })
        .bg(theme::panel())
        .text_size(px(12.))
        .text_color(if checked { theme::text() } else { theme::muted() })
        .when(!enabled, |this| this.opacity(0.45))
        .when(enabled, |this| this.cursor_pointer())
        .child(
            div()
                .size(px(12.))
                .flex_none()
                .rounded(px(3.))
                .border_1()
                .border_color(if checked {
                    theme::accent()
                } else {
                    theme::border_strong()
                })
                .when(checked, |this| this.bg(theme::accent())),
        )
        .child(label)
        .when(enabled, |this| this.on_click(on_click))
}

/// 字段行的标签(`.field-label`):74px 宽、muted。
pub fn field_label(text: &'static str) -> Div {
    div()
        .w(px(74.))
        .flex_none()
        .text_size(px(13.))
        .text_color(theme::muted())
        .child(text)
}

/// 字段行(`.field`):标签 + 控件。
pub fn field(label: &'static str) -> Div {
    h_flex().items_center().gap(px(10.)).child(field_label(label))
}

/// 拖放区(`.dropzone`):1.5px 虚线、居中 muted 文案。
pub fn dropzone(id: impl Into<ElementId>, text: &'static str, active: bool) -> Stateful<Div> {
    div()
        .id(id)
        .w_full()
        .flex()
        .items_center()
        .justify_center()
        .px(px(16.))
        .py(px(18.))
        .rounded(px(theme::RADIUS))
        .border(px(1.5))
        .border_color(if active {
            theme::accent()
        } else {
            theme::border_strong()
        })
        .when(active, |this| {
            this.bg(theme::accent_dim()).text_color(theme::text())
        })
        .text_size(px(13.))
        .text_color(theme::muted())
        .cursor_pointer()
        .child(text)
}

/// 只读路径框(Electron 版 `.text-input` 的展示形态)。
pub fn path_box(text: impl Into<SharedString>, dim: bool) -> Div {
    div()
        .flex_1()
        .min_w_0()
        .px(px(10.))
        .py(px(8.))
        .rounded(px(theme::RADIUS))
        .border_1()
        .border_color(theme::border())
        .bg(theme::panel())
        .text_size(px(12.))
        .text_color(if dim { theme::muted() } else { theme::text() })
        .overflow_hidden()
        .child(text.into())
}

/// 日志面板(`.log`):等宽 12px、90px 高、浅底。
pub fn log_panel(lines: Vec<String>) -> Div {
    let mut body = v_flex()
        .w_full()
        .h(px(90.))
        .justify_end()
        .overflow_hidden()
        .p(px(10.))
        .gap(px(2.))
        .rounded(px(theme::RADIUS))
        .border_1()
        .border_color(theme::border())
        .bg(theme::panel_log())
        .overflow_hidden()
        .font_family("Cascadia Mono");
    for line in lines {
        body = body.child(div().text_size(px(12.)).child(line));
    }
    body
}

/// 缩略图网格(`.thumbs`):92px 宽的卡片,图片 64px 高,下面 11px 文件名。
pub fn thumb_grid(
    cache: &ThumbCache,
    paths: &[PathBuf],
    on_remove: impl Fn(usize, &ClickEvent, &mut Window, &mut App) + 'static,
) -> impl IntoElement {
    let on_remove = std::rc::Rc::new(on_remove);
    let mut grid = h_flex().w_full().flex_wrap().gap(px(10.));
    for (index, path) in paths.iter().enumerate() {
        let name = path
            .file_name()
            .map(|name| name.to_string_lossy().to_string())
            .unwrap_or_default();
        let preview: AnyElement = match cache.get(path) {
            Some(image) => img(ImageSource::Render(image))
                .h(px(64.))
                .object_fit(ObjectFit::Contain)
                .into_any_element(),
            None => div()
                .text_size(px(10.))
                .text_color(theme::muted())
                .child("无法预览")
                .into_any_element(),
        };
        let remove = on_remove.clone();
        grid = grid.child(
            v_flex()
                .relative()
                .w(px(92.))
                .p(px(6.))
                .gap(px(5.))
                .rounded(px(theme::RADIUS))
                .border_1()
                .border_color(theme::border())
                .bg(theme::panel_log())
                .child(
                    div()
                        .h(px(64.))
                        .w_full()
                        .flex()
                        .items_center()
                        .justify_center()
                        .overflow_hidden()
                        .child(preview),
                )
                .child(
                    div()
                        .text_size(px(11.))
                        .text_color(theme::muted())
                        .overflow_hidden()
                        .child(name),
                )
                .child(
                    div()
                        .id(("thumb-remove", index))
                        .absolute()
                        .top(px(3.))
                        .right(px(3.))
                        .size(px(18.))
                        .flex()
                        .items_center()
                        .justify_center()
                        .rounded_full()
                        .bg(Hsla::from(rgba(0x1e1d1d8c)))
                        .text_size(px(12.))
                        .text_color(theme::white())
                        .cursor_pointer()
                        .hover(|this| this.bg(theme::danger()))
                        .child("×")
                        .on_click(move |event, window, cx| remove(index, event, window, cx)),
                ),
        );
    }
    grid
}

/// 运行条(`.runbar`):主按钮靠右。
pub fn runbar() -> Div {
    h_flex().w_full().items_center().justify_end().gap(px(14.))
}
