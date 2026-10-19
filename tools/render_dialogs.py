"""Draw the setup and Configure dialogs for the README (docs/images/*.png).

The pictures are illustrations, not screenshots: Home Assistant's own dialogs
look slightly different. The texts come straight from strings.json, so a
picture never shows wording the integration no longer uses. Run again after
changing a dialog:

    pip install playwright markdown
    python tools/render_dialogs.py

Needs a Chromium for Playwright (``playwright install chromium``, or
PLAYWRIGHT_BROWSERS_PATH pointing at one) and, for the intended look, the
Inter font.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
STRINGS = json.loads(
    (ROOT / "custom_components" / "lg_therma_v_r290" / "strings.json").read_text()
)
OUT = ROOT / "docs" / "images"

# A 12 kW unit that answers on all three groups, energy registers on.
TABLE = {
    "energy_registers": ("✓", "✓", "✓"),
    "compressor_modulation_limit": ("–", "✓ ➕", "–"),
    "power_limit": ("–", "✓ ➕", "–"),
    "emergency_operation_button": ("–", "–", "–"),
    "experimental_registers": ("–", "–", "–"),
    "compressor_statistics": ("–", "–", "–"),
    "poll_statistics": ("–", "–", "–"),
}
CHECKED = "2026-10-19 16:40"

CSS = """
* { box-sizing: border-box; }
.wrap { padding: 16px; background: #f0f1f5; }
body { margin: 0; background: #f0f1f5;
       font-family: Inter, Roboto, sans-serif; color: #212121; }
.card { background: #fff; border-radius: 16px; padding: 24px 24px 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,.08); }
h1 { font-size: 20px; font-weight: 500; margin: 0 0 12px; }
h1.center { text-align: center; }
.text { font-size: 14px; line-height: 1.55; color: #6b6b6b; }
.text p { margin: 0 0 10px; }
.text strong { color: #212121; font-weight: 500; }
table { width: 100%; border-collapse: collapse; margin: 4px 0 12px;
        color: #212121; font-size: 14px; }
th { font-weight: 500; text-align: left; padding: 6px 8px;
     border-bottom: 1px solid #bdbdbd; }
td { padding: 6px 8px; border-bottom: 1px solid #e0e0e0; }
th[style*=center], td[style*=center] { text-align: center; }
.last { color: #212121; }
.menu { border-top: 1px solid #e0e0e0; margin-top: 8px; }
.item { display: flex; align-items: center; padding: 12px 0;
        border-bottom: 1px solid #e0e0e0; }
.item:last-child { border-bottom: none; }
.item .label { flex: 1; font-size: 16px; }
.item .desc { font-size: 13px; color: #6b6b6b; margin-top: 2px; line-height: 1.45; }
.item .chev { color: #9e9e9e; font-size: 20px; padding-left: 12px; }
.section { border: 1px solid #d6d6d6; border-radius: 10px; padding: 12px 16px;
           margin: 8px 0; }
.section .head { display: flex; font-size: 16px; }
.section .head span:first-child { flex: 1; }
.section .head span:last-child { color: #757575; font-size: 11px; padding-top: 4px; }
.section .body { margin-top: 8px; }
.toggle { display: flex; gap: 12px; margin: 10px 0 4px; }
.switch { width: 34px; height: 14px; border-radius: 7px; background: #9fd4f5;
          position: relative; margin-top: 4px; flex: none; }
.switch::after { content: ""; position: absolute; right: -4px; top: -3px;
                 width: 20px; height: 20px; border-radius: 50%; background: #03a9f4; }
.toggle .t { font-size: 15px; }
.toggle .text ul { padding-left: 18px; margin: 4px 0; }
.field { font-size: 13px; color: #6b6b6b; margin: 12px 0 4px; }
.input { border: 1px solid #bdbdbd; border-radius: 6px; padding: 9px 10px;
         font-size: 15px; margin-bottom: 12px; }
.submit { text-align: right; color: #03a9f4; font-weight: 500;
          letter-spacing: .5px; margin-top: 12px; }
.spinner { width: 40px; height: 40px; border-radius: 50%; margin: 6px auto 14px;
           border: 4px solid #cfe9fb; border-top-color: #03a9f4; }
.center { text-align: center; }
.error { background: #fdecea; color: #b71c1c; border-radius: 6px;
         padding: 10px 12px; font-size: 14px; margin-bottom: 12px; }
"""


def md(text: str, placeholders: dict[str, str] | None = None) -> str:
    for key, value in (placeholders or {}).items():
        text = text.replace("{" + key + "}", value)
    return markdown.markdown(text, extensions=["tables"])


def table_placeholders() -> dict[str, str]:
    values = {"checked": CHECKED}
    for group, (on, last, now) in TABLE.items():
        values[f"{group}_on"] = on
        values[group] = last
        values[f"{group}_now"] = now
    return values


def page(body: str) -> str:
    return (
        f"<html><head><style>{CSS}</style></head>"
        f'<body><div class="wrap">{body}</div></body></html>'
    )


def menu(items: list[tuple[str, str]]) -> str:
    rows = "".join(
        f'<div class="item"><div style="flex:1"><div class="label">'
        f'{html.escape(label)}</div><div class="desc">{html.escape(desc)}</div>'
        f'</div><div class="chev">›</div></div>'
        for label, desc in items
    )
    return f'<div class="menu">{rows}</div>'


def sections(step: dict, expanded: set[str], on: set[str]) -> str:
    out = []
    for key, section in step["sections"].items():
        if key not in expanded:
            out.append(
                f'<div class="section"><div class="head"><span>'
                f"{html.escape(section['name'])}</span><span>▼</span></div></div>"
            )
            continue
        (field,) = section["data"]
        toggle = (
            f'<div class="toggle"><div class="switch"></div><div>'
            f'<div class="t">{html.escape(section["data"][field])}</div>'
            f'<div class="text">{md(section["data_description"][field])}</div>'
            f"</div></div>"
            if field in on
            else ""
        )
        out.append(
            f'<div class="section"><div class="head"><span>'
            f"{html.escape(section['name'])}</span><span>▲</span></div>"
            f'<div class="body"><div class="text">{md(section["description"])}'
            f"</div>{toggle}</div></div>"
        )
    return "".join(out)


def check_menu() -> str:
    step = STRINGS["config"]["step"]["check"]
    items = [
        (step["menu_options"][k], step["menu_option_descriptions"][k])
        for k in ("detect", "features")
    ]
    return page(
        f'<div class="card"><h1>{step["title"]}</h1>'
        f'<div class="text">{md(step["description"])}</div>{menu(items)}</div>'
    )


def progress() -> str:
    text = STRINGS["config"]["progress"]["detect"]
    return page(
        '<div class="card center"><h1 class="center">LG Therma V R290</h1>'
        f'<div class="spinner"></div><div class="text">{html.escape(text)}</div></div>'
    )


def features() -> str:
    step = STRINGS["config"]["step"]["features"]
    marks = {
        "energy_registers": "✓",
        "compressor_modulation_limit": "✓",
        "power_limit": "✓",
    }
    on = {"energy_registers", "compressor_modulation_limit"}
    return page(
        f'<div class="card"><h1>{step["title"]}</h1>'
        f'<div class="text">{md(step["description"], marks)}</div>'
        f"{sections(step, on, on)}<div class=submit>SUBMIT</div></div>"
    )


def configure_menu() -> str:
    step = STRINGS["options"]["step"]["init"]
    items = [
        (step["menu_options"][k], step["menu_option_descriptions"][k])
        for k in ("options", "detect")
    ]
    return page(
        f'<div class="card"><h1>{step["title"]}</h1>'
        f'<div class="text">{md(step["description"], table_placeholders())}</div>'
        f"{menu(items)}</div>"
    )


def options() -> str:
    step = STRINGS["options"]["step"]["options"]
    on = {"energy_registers"}
    return page(
        f'<div class="card"><h1>{step["title"]}</h1>'
        f'<div class="text">{md(step["description"], table_placeholders())}</div>'
        f'<div class="field">{step["data"]["scan_interval"]}</div>'
        f'<div class="input">10</div>{sections(step, on, on)}'
        f"<div class=submit>SUBMIT</div></div>"
    )


def repairs() -> str:
    issue = STRINGS["issues"]["energy_registers_never_answered"]
    confirm = issue["fix_flow"]["step"]["confirm"]
    text = md(confirm["description"], {"entry": "LG Therma V /dev/ttyUSB0"})
    return page(
        f'<div class="card"><h1>{confirm["title"]}</h1>'
        f'<div class="text">{text}</div><div class=submit>SUBMIT</div></div>'
    )


PICTURES = {
    "setup-check.png": check_menu,
    "setup-progress.png": progress,
    "setup-features.png": features,
    "setup-menu.png": configure_menu,
    "setup-options.png": options,
    "repairs-never-answered.png": repairs,
}


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": 560, "height": 400}, device_scale_factor=2
        )
        tab = context.new_page()
        for name, build in PICTURES.items():
            tab.set_content(build())
            tab.wait_for_load_state()
            # The wrapper, so the grey margin around the card is in the picture.
            tab.locator(".wrap").screenshot(path=str(OUT / name))
            print("wrote", name)
        browser.close()


if __name__ == "__main__":
    main()
