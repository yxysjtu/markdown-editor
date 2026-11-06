"""学术报告的自定义样式：把 frontmatter 里的 style 选项检查一遍，再生成样式文字。

只有这里列出的选项可以用，值也都要通过检查。Markdown 文件可能来自别人，
不能让 style 里的内容变成任意 CSS。默认样式在 static/document.css，这里生成的规则放在它后面，只覆盖写了的项。
"""
import re

# 国内论文要求常写的字号，单位是 pt
SIZE_NAMES = {"初号": 42, "小初": 36, "一号": 26, "小一": 24, "二号": 22, "小二": 18, "三号": 16, "小三": 15,
              "四号": 14, "小四": 12, "五号": 10.5, "小五": 9, "六号": 7.5}
SIZE = re.compile(r"\d+(?:\.\d+)?(?:pt|px|mm|cm|em)")
PAGE_LENGTH = re.compile(r"(\d+(?:\.\d+)?)(cm|mm|in|pt)")
CM_PER_UNIT = {"cm": 1, "mm": 0.1, "in": 2.54, "pt": 2.54 / 72}
FONT_NAME = re.compile(r"[\w .\-]+")
LABEL = re.compile(r"[^{}]*(?:\{\}[^{}]*)?")
CHAPTER_FORMAT = re.compile(r"[^{}]*\{(?:cn)?\}[^{}]*")
MAX_LABEL_LENGTH = 30
PAPERS = {"A3": (29.7, 42), "A4": (21, 29.7), "A5": (14.8, 21), "B5": (17.6, 25), "LETTER": (21.59, 27.94)}
DEFAULT_PAPER = PAPERS["A4"]
DEFAULT_MARGIN = (2.54, 3.17, 2.54, 3.17)  # 上右下左，单位是 cm
NUMBER_SEPARATORS = {"2-1": "-", "2.1": ".", "1": ""}  # 空的表示全文连续编号，不带章号


def size(value):
    text = str(value).strip()
    if text in SIZE_NAMES:
        return f"{SIZE_NAMES[text]}pt"
    if SIZE.fullmatch(text):
        return text
    raise ValueError("a size like 12pt or 小四")


def line_height(value):
    text = str(value).strip()
    if isinstance(value, bool) or not re.fullmatch(r"\d+(?:\.\d+)?", text) and not SIZE.fullmatch(text):
        raise ValueError("a multiple like 1.5 or a fixed height like 20pt")
    return text


def indent(value):
    return "0" if str(value).strip() == "0" else size(value)


def alignment(value):
    if value not in ("left", "center", "right", "justify"):
        raise ValueError("left, center, right or justify")
    return value


def font(fallback):
    def read(value):
        names = value if isinstance(value, list) else re.split(r"[,，]", value) if isinstance(value, str) else [None]
        names = [name.strip() for name in names if isinstance(name, str) and name.strip()]
        if not names or not all(FONT_NAME.fullmatch(name) for name in names):
            raise ValueError("font names separated by commas")
        return ", ".join([f'"{name}"' for name in names] + [f"var({fallback})"])
    return read


def switch(value):
    if not isinstance(value, bool):
        raise ValueError("true or false")
    return value


def paper(value):
    found = PAPERS.get(str(value).strip().upper())
    if not found:
        raise ValueError("A3, A4, A5, B5 or Letter")
    return found


def page_margin(value):
    """和 CSS 一样可以写 1 到 4 个长度，返回上右下左，单位是 cm。"""
    parts = str(value).split()
    lengths = []
    for part in parts:
        match = PAGE_LENGTH.fullmatch(part)
        if part != "0" and not match:
            raise ValueError("lengths in cm, mm, in or pt, like 2.54cm 3.17cm")
        lengths.append(float(match.group(1)) * CM_PER_UNIT[match.group(2)] if match else 0)
    if not 1 <= len(lengths) <= 4:
        raise ValueError("lengths in cm, mm, in or pt, like 2.54cm 3.17cm")
    top = lengths[0]
    right = lengths[1] if len(lengths) > 1 else top
    bottom = lengths[2] if len(lengths) > 2 else top
    left = lengths[3] if len(lengths) > 3 else right
    return top, right, bottom, left


def numbering(value):
    found = NUMBER_SEPARATORS.get(str(value).strip())
    if found is None:
        raise ValueError('"2-1", "2.1" or "1"')
    return found


def label(value):
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_LABEL_LENGTH or not LABEL.fullmatch(value):
        raise ValueError('a short name like 图, or a format like "图{}"')
    return value if "{}" in value else value + " {}"


def chapter_format(value):
    if not isinstance(value, str) or len(value) > MAX_LABEL_LENGTH or not CHAPTER_FORMAT.fullmatch(value):
        raise ValueError('a format like "第{}章" or "第{cn}章"')
    return value


# 选项名 -> (检查函数, 选择器, 属性)。这些选项对应一条样式规则
CSS_OPTIONS = {
    "body-font": (font("--report-serif"), ".doc.academic", "font-family"),
    "font-size": (size, ".doc.academic", "font-size"),
    "line-height": (line_height, ".doc.academic", "line-height"),
    "first-line-indent": (indent, ".academic .prose p", "text-indent"),
    "title-font": (font("--report-sans"), ".academic .prose .report-title", "font-family"),
    "title-size": (size, ".academic .prose .report-title", "font-size"),
    "title-align": (alignment, ".academic .prose .report-title", "text-align"),
    "caption-size": (size, ".academic .prose .report-caption", "font-size"),
    "caption-align": (alignment, ".academic .prose .report-caption", "text-align"),
}
for level in (1, 2, 3):
    CSS_OPTIONS[f"heading-{level}-font"] = (font("--report-sans"), f".academic .prose h{level}", "font-family")
    CSS_OPTIONS[f"heading-{level}-size"] = (size, f".academic .prose h{level}", "font-size")
    CSS_OPTIONS[f"heading-{level}-align"] = (alignment, f".academic .prose h{level}", "text-align")

# 这些选项改变编号和称呼。选项名 -> (检查函数, 文字表里的名字)
TEXT_OPTIONS = {
    "numbering": (numbering, "number_separator"),
    "chapter-format": (chapter_format, "chapter_format"),
    "figure-label": (label, "fig"),
    "table-label": (label, "tbl"),
    "code-label": (label, "lst"),
    "appendix-label": (label, "appendix"),
}
PAGE_OPTIONS = {"paper": paper, "page-margin": page_margin, "page-numbers": switch, "three-line-table": switch}


def checker(name):
    if name in CSS_OPTIONS:
        return CSS_OPTIONS[name][0]
    if name in TEXT_OPTIONS:
        return TEXT_OPTIONS[name][0]
    return PAGE_OPTIONS.get(name)


def read_style(*layers):
    """按顺序合并几层 style，后面的优先。返回 (检查过的值, 问题列表)。写错的项不生效，仍用前一层的值。"""
    values = {}
    problems = []
    for layer in layers:
        if layer is None:
            continue
        if not isinstance(layer, dict):
            problems.append('"style" should be a list of "name: value" lines')
            continue
        for name, value in layer.items():
            check = checker(name)
            if check is None:
                problems.append(f'Unknown style option "{name}"')
                continue
            try:
                values[name] = check(value)
            except ValueError as err:
                problems.append(f'Invalid value for style option "{name}": {value}. Expected {err}')
    return values, problems


def apply_text(text, values):
    """把编号格式和称呼合并到文字表里，返回新的文字表。"""
    result = dict(text)
    for name, (_, key) in TEXT_OPTIONS.items():
        if name in values:
            result[key] = values[name]
    return result


def centimeters(length):
    return f"{length:g}cm"


def page_rules(values):
    rules = []
    descriptors = []
    if "paper" in values:
        width, height = values["paper"]
        descriptors.append(f"size: {centimeters(width)} {centimeters(height)};")
    if "page-margin" in values:
        descriptors.append("margin: " + " ".join(centimeters(side) for side in values["page-margin"]) + ";")
    if values.get("page-numbers") is False:
        descriptors.append('@bottom-center { content: ""; }')
    if descriptors:
        rules.append("@page report { " + " ".join(descriptors) + " }")
    if "paper" in values or "page-margin" in values:  # 预览和导出的 HTML 也要显示一样大的纸
        width, height = values.get("paper", DEFAULT_PAPER)
        top, right, bottom, left = values.get("page-margin", DEFAULT_MARGIN)
        sheet = f"max-width: {centimeters(width)}; min-height: {centimeters(height)};"
        rules.append("@container (min-width: 620.01px) { .preview-pane .doc.academic { "
                     f"{sheet} padding: {centimeters(top)} min({right / width * 100:.2f}%, {centimeters(right)}) "
                     f"{centimeters(bottom)} min({left / width * 100:.2f}%, {centimeters(left)}); }} }}")
        rules.append("@media screen { body.exported .doc.academic { "
                     f"{sheet} padding: {' '.join(centimeters(side) for side in (top, right, bottom, left))}; }} }}")
    return rules


def build_css(values):
    rules = page_rules(values)
    for name, (_, selector, prop) in CSS_OPTIONS.items():
        if name in values:
            rules.append(f"{selector} {{ {prop}: {values[name]}; }}")
    if values.get("three-line-table") is False:
        rules.append(".academic .prose table, .academic .prose th, .academic .prose td { border: .75pt solid #000; }")
    return "\n".join(rules)
