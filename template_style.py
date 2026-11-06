"""模板的样式：检查 frontmatter 里的 style 选项和模板自带的 CSS，再生成样式文字。

选项有三种：所有模板都能用的页面选项、numbered 的编号选项、模板 CSS 里用到的变量（var(--accent) 对应 style 里的 accent）。
Markdown 文件和模板可能来自别人，所以值都要通过检查，模板 CSS 不能联网，也不能影响文档以外的内容。
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
DEFAULT_MARGIN = (1.8, 1.6, 1.8, 1.6)  # 上右下左，单位是 cm。和 document.css 里普通文档的页边距一样
NUMBER_SEPARATORS = {"2-1": "-", "2.1": ".", "1": ""}  # 空的表示全文连续编号，不带章号

BASES = {"none": "", "numbered": "numbered"}  # 内置的基础 -> 文档的 class

# 模板 CSS 放在这个选择器里面。写 h1 { } 只影响文档内容，写 body { } 也不会匹配到编辑器界面；
# 同时优先级够高，能盖过 document.css 里的规则。继承时后面的模板写在后面，优先级相同，所以子模板优先
CSS_SCOPE = ".doc" * 5
# 注释、字符串和不带引号的 url() 里的括号都不算数，要从左到右一次认出来：字符串里可以有 /*，注释里也可以有引号
CSS_TOKEN = re.compile(r'''(/\*.*?\*/)|"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|url\(\s*[^'"\s)][^)]*\)''', re.S | re.I)
CSS_ESCAPE = re.compile(r"\\([0-9a-fA-F]{1,6})\s?|\\(.)", re.S)
CSS_URL = re.compile(r"""url\(\s*['"]?([^'")\s]*)""")
CSS_NETWORK = re.compile(r"@import|@namespace|\b(?:src|image|image-set|element)\(")
CSS_FONT_FACE = re.compile(r"@font-face\s*\{[^{}]*\}", re.I)  # 嵌套在选择器里不生效，要放到外面。css_problem 已经保证它不会联网
CSS_PAGE = re.compile(r"@page\b", re.I)
CSS_VARIABLE = re.compile(r"var\(\s*--([\w-]+)")
VARIABLE_VALUE = re.compile(r"""[\w\s#%.,()+*/"'-]+""")
VARIABLE_NETWORK = re.compile(r"\b(?:url|src|image|image-set|element)\(", re.I)
BLANK_MARGIN_BOXES = ('@top-left { content: ""; } @top-center { content: ""; } @top-right { content: ""; } '
                      '@bottom-left { content: ""; } @bottom-right { content: ""; }')  # 写空内容，打印窗口才不会画自带的日期、标题和网址


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


def font_names(value):
    names = value if isinstance(value, list) else re.split(r"[,，]", value) if isinstance(value, str) else [None]
    names = [name.strip() for name in names if isinstance(name, str) and name.strip()]
    if not names or not all(FONT_NAME.fullmatch(name) for name in names):
        raise ValueError("font names separated by commas")
    return ", ".join(f'"{name}"' for name in names)


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


def variable_value(value):
    """模板 CSS 变量的值。这里不知道它的含义，只保证它跑不出自己这一条声明。"""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError("a value like #1a5fb4, 12pt or 小四")
    text = str(value).strip()
    if text in SIZE_NAMES:
        return f"{SIZE_NAMES[text]}pt"
    depth = 0
    for char in text:
        depth += (char == "(") - (char == ")")
        if depth < 0:
            break
    if (not VARIABLE_VALUE.fullmatch(text) or depth != 0 or "/*" in text or VARIABLE_NETWORK.search(text)
            or text.count('"') % 2 or text.count("'") % 2):
        raise ValueError("a value like #1a5fb4, 12pt or 小四, without ; : { } < > or links")
    return text


def variable_checker(name):
    """按名字的结尾检查变量的值，这样写错的字号和对齐方式能提示出来。别的名字只做基本的安全检查。"""
    if name == "line-height":
        return line_height
    if name == "first-line-indent":
        return indent
    if name.endswith("-size"):
        return size
    if name.endswith("-align"):
        return alignment
    if name.endswith("-font"):
        return font_names
    return variable_value


# 这些选项改变编号和称呼，只有基于 numbered 时才有。选项名 -> (检查函数, 文字表里的名字)
TEXT_OPTIONS = {
    "numbering": (numbering, "number_separator"),
    "chapter-format": (chapter_format, "chapter_format"),
    "figure-label": (label, "fig"),
    "table-label": (label, "tbl"),
    "code-label": (label, "lst"),
    "appendix-label": (label, "appendix"),
}
PAGE_OPTIONS = {"paper": paper, "page-margin": page_margin, "page-numbers": switch}  # 所有模板都能用


def decode_escape(match):
    if match.group(1):
        code = int(match.group(1), 16)
        return chr(code) if 0 < code <= 0x10FFFF else ""
    return match.group(2)


def without_comments(text):
    return CSS_TOKEN.sub(lambda match: " " if match.group(1) else match.group(0), text)


def css_problem(text):
    """模板 CSS 不能跑出 CSS_SCOPE，不能结束 <style>，也不能发网络请求。有问题时整个文件都不用。"""
    if "</style" in text.lower():
        return 'it must not contain "</style"'
    bare = CSS_TOKEN.sub(" ", text)
    if "/*" in bare:
        return "a comment is not closed"
    if '"' in bare or "'" in bare:
        return "a string is not closed"
    if "\\" in bare:  # 转义可以把关键字和括号藏起来
        return "backslashes are only allowed inside strings"
    depth = 0
    for char in bare:
        depth += (char == "{") - (char == "}")
        if depth < 0:
            return 'there is an extra "}"'
    if depth != 0:
        return 'a "{" is not closed'
    decoded = CSS_ESCAPE.sub(decode_escape, without_comments(text)).lower()
    if CSS_NETWORK.search(decoded) or any(not url.startswith("data:") for url in CSS_URL.findall(decoded)):
        return "it must not load anything from outside: @import is not allowed, and url() only works with data:"
    return ""


def read_css(text, name):
    """检查模板 CSS。返回 (放进 CSS_SCOPE 之后的样式, 它用到的变量名, 问题列表)。"""
    problem = css_problem(text)
    if problem:
        return "", set(), [f'Template CSS "{name}" was not used: {problem}.']
    code = without_comments(text)
    problems = []
    if CSS_PAGE.search(code):
        problems.append(f'Template CSS "{name}": @page does not work here. Use the paper, page-margin and page-numbers options.')
    fonts = "\n".join(CSS_FONT_FACE.findall(code))
    scoped = f"{CSS_SCOPE} {{\n{CSS_FONT_FACE.sub('', code)}\n}}"
    return f"{fonts}\n{scoped}" if fonts else scoped, set(CSS_VARIABLE.findall(code)), problems


def checker(name, base, css_variables):
    """返回 (检查函数, 是不是 CSS 变量)。不认识这个名字时检查函数是 None。"""
    if name in PAGE_OPTIONS:
        return PAGE_OPTIONS[name], False
    if base == "numbered" and name in TEXT_OPTIONS:
        return TEXT_OPTIONS[name][0], False
    if name in css_variables:
        return variable_checker(name), True
    return None, False


def read_style(layers, base, css_variables=()):
    """按顺序合并几层 style，后面的优先。返回 (选项的值, 模板 CSS 变量的值, 问题列表)。写错的项不生效，仍用前一层的值。"""
    values = {}
    variables = {}
    problems = []
    for layer in layers:
        if layer is None:
            continue
        if not isinstance(layer, dict):
            problems.append('"style" should be a list of "name: value" lines')
            continue
        for name, value in layer.items():
            check, is_variable = checker(name, base, css_variables)
            if check is None:
                problems.append(f'Unknown style option "{name}"')
                continue
            try:
                (variables if is_variable else values)[name] = check(value)
            except ValueError as err:
                problems.append(f'Invalid value for style option "{name}": {value}. Expected {err}')
    return values, variables, problems


def apply_text(text, values):
    """把编号格式和称呼合并到文字表里，返回新的文字表。"""
    result = dict(text)
    for name, (_, key) in TEXT_OPTIONS.items():
        if name in values:
            result[key] = values[name]
    return result


def is_paged(values):
    """写了纸张或边距的文档，预览和导出的 HTML 显示成一张纸，见 document.css 的 .paged。"""
    return "paper" in values or "page-margin" in values


def centimeters(length):
    return f"{length:g}cm"


def page_rules(values):
    if not (is_paged(values) or "page-numbers" in values):
        return []
    descriptors = []
    if "paper" in values:
        width, height = values["paper"]
        descriptors.append(f"size: {centimeters(width)} {centimeters(height)};")
    if "page-margin" in values:
        descriptors.append("margin: " + " ".join(centimeters(side) for side in values["page-margin"]) + ";")
    number = 'counter(page); font: 10.5pt "Times New Roman", serif' if values.get("page-numbers") else '""'
    descriptors.append(f"@bottom-center {{ content: {number}; }} {BLANK_MARGIN_BOXES}")
    rules = ["@page { " + " ".join(descriptors) + " }"]
    if is_paged(values):
        width, height = values.get("paper", DEFAULT_PAPER)
        top, right, bottom, left = values.get("page-margin", DEFAULT_MARGIN)
        sheet = f"max-width: {centimeters(width)}; min-height: {centimeters(height)};"
        rules.append(f".preview-pane .doc.paged {{ {sheet} }}")
        rules.append("@container (min-width: 620.01px) { .preview-pane .doc.paged { "
                     f"padding: {centimeters(top)} min({right / width * 100:.2f}%, {centimeters(right)}) "
                     f"{centimeters(bottom)} min({left / width * 100:.2f}%, {centimeters(left)}); }} }}")
        rules.append("@media screen { body.exported .doc.paged { "
                     f"{sheet} padding: {' '.join(centimeters(side) for side in (top, right, bottom, left))}; }} }}")
    return rules


def build_css(values, variables):
    rules = page_rules(values)
    if variables:
        rules.append(".doc { " + " ".join(f"--{name}: {value};" for name, value in variables.items()) + " }")
    return "\n".join(rules)
