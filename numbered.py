"""内置的 numbered：基于它的模板（比如 report）会给标题、图、表、公式自动编号，并支持交叉引用。

语法尽量和 Pandoc 的 pandoc-crossref 一致，以后想交给 Pandoc 转换时不用重写：

    # 引言 {#sec:intro}              标题，{-} 表示不编号
    ![系统架构](arch.png){#fig:arch}  单独成段的图片，说明就是图题
    : 实验结果 {#tbl:result}          紧贴表格前后的一段，就是表题
    $$ E = mc^2 $$ {#eq:energy}      独立公式都会编号，{-} 表示不编号
    如[@fig:arch]所示                 引用，类型有 fig、tbl、eq、lst、sec

    ```python title="a.py" {#lst:a}   代码块，写了 title 或标签才编号，title 显示在代码上方

    ::: figures {#fig:compare cols=2}  图组：共用一个图号，每张图是一个子图
    ![对照组](a.png){#fig:a}            引用这张图时显示“图 2-1(a)”
    ![实验组](b.png){#fig:b}

    两组实验结果的对比                   最后这段文字是总标题
    :::
"""
import re
from html import escape
from string import ascii_lowercase, ascii_uppercase

from markdown_it.token import Token
from mdit_py_plugins.container import container_plugin

LABEL = r"[^\s{}\]]+"
HEADING_ATTR = re.compile(r"\s*\{(?:#sec:(" + LABEL + r")|-|\.unnumbered)\}\s*$")
IMAGE_ATTRS = re.compile(r"^\s*\{([^{}]*)\}\s*$")
IMAGE_WIDTH = re.compile(r"\d+(?:\.\d+)?(?:%|cm|mm)")
PAGE_BREAK = "\\newpage"
TABLE_CAPTION = re.compile(r"^(?:Table)?:\s+")
TABLE_ATTR = re.compile(r"\s*\{#tbl:(" + LABEL + r")\}\s*$")
EQUATION_ATTR = re.compile(r"(\$\$)[ \t]*\{(?:#eq:(" + LABEL + r")|(-))\}[ \t]*$")
REFERENCE = re.compile(r"\[@(fig|tbl|eq|lst|sec):(" + LABEL + r")\]")
CODE_TITLE = re.compile(r"""\btitle=(?:"([^"]*)"|'([^']*)')""")
CODE_LABEL = re.compile(r"\{#lst:(" + LABEL + r")\}")
FENCE = re.compile(r"^ {0,3}(```|~~~)")
GROUP_LABEL = re.compile(r"#fig:(" + LABEL + r")")
GROUP_COLUMNS = re.compile(r"\bcols=(\d+)")
DEFAULT_GROUP_COLUMNS = 2
MAX_GROUP_COLUMNS = 6
LONG_CODE_LINES = 30  # 超过这个行数的代码，打印时直接从当前位置开始排，不整块移到下一页，否则前一页会大片留白

TEXT = {
    "zh": {"fig": "图 {}", "tbl": "表 {}", "eq": "式 ({})", "lst": "代码 {}", "chapter": "第 {} 章", "section": "第 {} 节",
           "abstract": "摘要：", "keywords": "关键词：", "keyword_separator": "；", "caption_gap": "　",
           "page_break": "分页符", "appendix": "附录 {}", "toc": "目录"},
    "en": {"fig": "Figure {}", "tbl": "Table {}", "eq": "Eq. ({})", "lst": "Listing {}", "chapter": "Section {}", "section": "Section {}",
           "abstract": "Abstract: ", "keywords": "Keywords: ", "keyword_separator": "; ", "caption_gap": ". ",
           "page_break": "Page break", "appendix": "Appendix {}", "toc": "Contents"},
}
# 这些标题按惯例不编号，不用每次都写 {-}
UNNUMBERED_TITLES = {"摘要", "abstract", "目录", "contents", "参考文献", "references", "致谢",
                     "acknowledgements", "acknowledgments"}
# 附录按 A、B 编号。可以只写“附录”，也可以写“附录：问卷”或“Appendix A: Survey”，字母都由编号决定
APPENDIX_TITLE = re.compile(
    r"^(?:附录(?:\s*[A-Z](?![A-Za-z]))?(?:\s*[:：.\-–—]\s*|\s+|$)"
    r"|(?i:appendix)(?:\s+[A-Z](?![A-Za-z])(?:\s*[:：.\-–—]\s*|\s+|$)|\s*[:：.\-–—]\s*|\s*$))"
)


def text_for(lang):
    return TEXT["en"] if str(lang or "").lower().startswith("en") else TEXT["zh"]


def chinese_number(number):
    """1 到 99 写成一、十二、二十三，用于“第一章”。超出范围时直接用数字。"""
    digits = "零一二三四五六七八九"
    if not 1 <= number <= 99:
        return str(number)
    tens, ones = divmod(number, 10)
    return ("" if tens == 0 else "十" if tens == 1 else digits[tens] + "十") + (digits[ones] if ones else "")


def chapter_name(text, number):
    """一级标题前显示的编号。写了 chapter-format 时是“第一章”这样的格式。"""
    form = text.get("chapter_format")
    return form.replace("{cn}", chinese_number(int(number))).replace("{}", number) if form else number


def prepare_source(body):
    """公式插件只认 $$ (标签) 的写法，这里把 $$ {#eq:x} 换过去。行数不变，同步滚动不受影响；代码块里的不动。"""
    lines = body.split("\n")
    fence = None
    for index, line in enumerate(lines):
        match = FENCE.match(line)
        if match:
            fence = None if fence == match.group(1) else fence or match.group(1)
        elif fence is None:
            lines[index] = EQUATION_ATTR.sub(lambda m: f"$$ ({m.group(2) or '-'})", line)
    return "\n".join(lines)


def read_heading_attrs(state):
    """在解析行内内容之前去掉标题末尾的标记，否则它们会出现在标题和锚点里。"""
    tokens = state.tokens
    for index, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        inline = tokens[index + 1]
        match = HEADING_ATTR.search(inline.content)
        if match:
            inline.content = inline.content[:match.start()]
            token.meta = {"label": match.group(1), "numbered": match.group(1) is not None}


def html_block(content=""):
    token = Token("html_block", "", 0)
    token.content = content
    return token


def html_inline(content):
    token = Token("html_inline", "", 0)
    token.content = content
    return token


def read_image_attrs(child):
    """解析图片后面的 {#fig:x width=60%}，返回 (标签, 宽度)。不是图片属性时返回 None。写错的宽度直接忽略。"""
    match = IMAGE_ATTRS.match(child.content) if child.type == "text" else None
    if not match:
        return None
    label = width = None
    for part in match.group(1).split():
        if part.startswith("#fig:"):
            label = part[len("#fig:"):]
        elif part.startswith("width="):
            value = part[len("width="):]
            width = value if IMAGE_WIDTH.fullmatch(value) else None
        else:
            return None
    return label, width


def group_images(inline):
    """一段里全是图片（可以带属性和换行）时返回 [(图片, 标签), ...]，否则返回 None。"""
    images = []
    has_attrs = False
    for child in inline.children or []:
        if child.type == "image":
            images.append((child, None))
            has_attrs = False
        elif child.type == "softbreak" or (child.type == "text" and not child.content.strip()):
            continue
        else:
            attrs = read_image_attrs(child)
            if attrs is None or not images or has_attrs:
                return None
            has_attrs = True
            label, width = attrs
            images[-1] = (images[-1][0], label)
            if width:
                images[-1][0].attrSet("style", f"width: {width}")
    return images or None


def figure_parts(inline):
    """单独成段的一张图片返回 (图片, 标签)，否则返回 None。"""
    images = group_images(inline)
    return images[0] if images and len(images) == 1 else None


def table_caption_parts(inline):
    """表题的行内内容，去掉开头的冒号和末尾的标签。返回 (内容, 标签)。"""
    children = [child for child in inline.children]
    children[0].content = TABLE_CAPTION.sub("", children[0].content, count=1)
    label = None
    if children[-1].type == "text":
        match = TABLE_ATTR.search(children[-1].content)
        if match:
            label = match.group(1)
            children[-1].content = children[-1].content[:match.start()]
    return children, label


class Numbering:
    def __init__(self, text):
        self.text = text
        self.counts = [0] * 6
        self.chapter = 0  # 图、表、公式编号的前缀：普通章是数字，附录是字母
        self.appendices = 0
        self.in_appendix = False
        self.items = {"fig": 0, "tbl": 0, "eq": 0, "lst": 0}
        self.separator = text.get("number_separator", "-")  # 空的表示全文连续编号，不带章号
        self.references = {}  # (类型, 标签) -> (显示的文字, 锚点)

    def start_chapter(self):
        if self.separator:
            self.items = dict.fromkeys(self.items, 0)

    def next_item(self, kind, label):
        self.items[kind] += 1
        number = f"{self.chapter}{self.separator}{self.items[kind]}" if self.chapter and self.separator else str(self.items[kind])
        anchor = f"{kind}:{label}" if label else None
        if label:
            self.references[(kind, label)] = (self.text[kind].format(number), anchor)
        return number, anchor

    def next_appendix(self):
        self.appendices += 1
        self.in_appendix = True
        self.counts[1:] = [0] * 5
        self.chapter = ascii_uppercase[(self.appendices - 1) % len(ascii_uppercase)]
        self.start_chapter()
        return self.chapter

    def next_heading(self, level):
        self.counts[level - 1 if level > 1 or not self.in_appendix else 0] += 1
        self.counts[level:] = [0] * (6 - level)
        if level == 1:
            self.in_appendix = False
            self.chapter = self.counts[0]
            self.start_chapter()
        parts = [str(max(count, 1)) for count in self.counts[:level]]
        if self.in_appendix:
            parts[0] = self.chapter
        return ".".join(parts)


def replace_references(children, numbering):
    """把文字里的 [@fig:x] 换成链接。代码里的不是文字节点，不受影响。"""
    result = []
    for child in children:
        if child.type == "image" and child.children:
            child.children = replace_references(child.children, numbering)
        if child.type != "text" or "[@" not in child.content:
            result.append(child)
            continue
        position = 0
        for match in REFERENCE.finditer(child.content):
            before = Token("text", "", 0)
            before.content = child.content[position:match.start()]
            result.append(before)
            target = numbering.references.get((match.group(1), match.group(2)))
            if target:
                result.append(html_inline(f'<a class="xref" href="#{escape(target[1])}">{escape(target[0])}</a>'))
            else:  # 写错的标签要显眼，否则打印出来才发现
                result.append(html_inline(f'<span class="xref-missing" title="No such label">{escape(match.group(0))}</span>'))
            position = match.end()
        rest = Token("text", "", 0)
        rest.content = child.content[position:]
        result.append(rest)
    return result


def number_document(state):
    tokens = state.tokens
    text = state.env["numbered_text"]
    numbering = Numbering(text)
    render = state.md.renderer.render
    captions = []  # 全部编号之后才能渲染，图题里也可能有引用：(节点, 标签名, 样式, 前缀, 行内内容, 锚点)
    groups = []  # 图组，同样要等全部编号之后才能渲染

    def is_numbered_heading(position):
        token = tokens[position]
        if token.meta.get("numbered") is False:
            return False
        return tokens[position + 1].content.strip().lower() not in UNNUMBERED_TITLES

    # 文章最高一级的标题算第一级，这样从 ## 开始写也能编号成 1、1.1
    levels = [int(token.tag[1]) for index, token in enumerate(tokens)
              if token.type == "heading_open" and is_numbered_heading(index)]
    shift = min(levels) - 1 if levels else 0

    output = []
    last_table = None
    skip_numbers = False  # 不编号的章（比如“参考文献”）里面的小节也不编号
    index = 0
    while index < len(tokens):
        token = tokens[index]

        if token.type == "heading_open":
            level = max(int(token.tag[1]) - shift, 1)
            numbered = is_numbered_heading(index)
            inline = tokens[index + 1]
            tokens[index + 2].tag = token.tag = f"h{level}"
            if level == 1:
                skip_numbers = not numbered
            label = token.meta.get("label")
            if numbered and not skip_numbers:
                appendix = APPENDIX_TITLE.match(inline.content) if level == 1 else None
                if appendix:
                    number = numbering.next_appendix()
                    shown = text["appendix"].format(number)
                    first = inline.children[0]
                    if first.type == "text":  # “附录”这几个字由编号显示，不要重复
                        first.content = first.content[appendix.end():]
                else:
                    number = numbering.next_heading(level)
                    shown = chapter_name(text, number) if level == 1 else number
                inline.children.insert(0, html_inline(f'<span class="heading-number">{escape(shown)}</span> '))
                if label:
                    if numbering.in_appendix:
                        reference = text["appendix"].format(number)
                    elif level == 1 and text.get("chapter_format"):
                        reference = shown
                    else:
                        reference = (text["chapter"] if level == 1 else text["section"]).format(number)
                    numbering.references[("sec", label)] = (reference, f"sec:{label}")
            elif label:
                numbering.references[("sec", label)] = (inline.content, f"sec:{label}")
            if label:
                token.attrSet("id", f"sec:{label}")

        elif token.type == "paragraph_open" and not token.hidden:
            inline = tokens[index + 1]
            if inline.content.strip() == PAGE_BREAK:
                line = (token.map[0] if token.map else 0) + state.env.get("line_offset", 0)
                output.append(html_block(f'<div class="page-break" data-line="{line}" data-label="{escape(text["page_break"])}"></div>\n'))
                index += 3
                continue
            figure = figure_parts(inline)
            is_caption =bool(TABLE_CAPTION.match(inline.content)) and inline.children and inline.children[0].type == "text"
            next_is_table = index + 3 < len(tokens) and tokens[index + 3].type == "table_open"
            after_table = bool(output) and output[-1].type == "table_close"
            if figure:
                image, label = figure
                inline.children = [image]
                token.tag = tokens[index + 2].tag = "figure"
                token.attrSet("class", "figure")
                output += [token, inline]
                if image.children or label:  # 粘贴的图片没有说明，不编号，也不占图号
                    number, anchor = numbering.next_item("fig", label)
                    if anchor:
                        token.attrSet("id", anchor)
                    caption = html_block()
                    captions.append((caption, "figcaption", "figure-caption", text["fig"].format(number), image.children or [], None))
                    output.append(caption)
                output.append(tokens[index + 2])
                index += 3
                continue
            if is_caption and (next_is_table or after_table):
                children, label = table_caption_parts(inline)
                number, anchor = numbering.next_item("tbl", label)
                caption = html_block()
                captions.append((caption, "p", "table-caption", text["tbl"].format(number), children, anchor))
                if next_is_table:
                    output.append(caption)
                else:
                    output.insert(last_table, caption)
                index += 3
                continue

        elif token.type == "table_open":
            last_table = len(output)

        elif token.type == "fence":
            title = CODE_TITLE.search(token.info)
            label = CODE_LABEL.search(token.info)
            # 去掉属性，只留语言名给代码高亮
            token.info = CODE_LABEL.sub("", CODE_TITLE.sub("", token.info)).strip()
            if title or label:
                number, anchor = numbering.next_item("lst", label.group(1) if label else None)
                caption_text = Token("text", "", 0)  # 当作纯文字，文件名里的 _ 和 * 不是格式
                caption_text.content = (title.group(1) or title.group(2) or "") if title else ""
                caption = html_block()
                captions.append((caption, "p", "code-caption", text["lst"].format(number), [caption_text], anchor))
                output.append(caption)
            if token.content.count("\n") > LONG_CODE_LINES:
                output += [html_block('<div class="code-long">\n'), token, html_block("</div>\n")]
                index += 1
                continue

        elif token.type == "container_figures_open":
            end = index + 1
            while tokens[end].type != "container_figures_close":
                end += 1
            label = GROUP_LABEL.search(token.info)
            columns = GROUP_COLUMNS.search(token.info)
            number, anchor = numbering.next_item("fig", label.group(1) if label else None)
            group = {
                "node": html_block(),
                "prefix": text["fig"].format(number),
                "anchor": anchor,
                "columns": min(max(int(columns.group(1)), 1), MAX_GROUP_COLUMNS) if columns else DEFAULT_GROUP_COLUMNS,
                "line": (token.map[0] if token.map else 0) + state.env.get("line_offset", 0),
                "images": [],
                "caption": [],
            }
            output.append(group["node"])
            position = index + 1
            while position < end:
                inner = tokens[position]
                # 图组里不该有的内容（比如列表）放到图组后面，不能悄悄丢掉。列表项里的段落不算总标题
                if inner.type != "paragraph_open" or inner.level != token.level + 1:
                    output.append(inner)
                    position += 1
                    continue
                inline = tokens[position + 1]
                images = group_images(inline)
                if images:
                    group["images"] += images
                else:
                    group["caption"] = inline.children or []  # 有多段文字时，最后一段是总标题
                position += 3
            for order, (_, sub_label) in enumerate(group["images"]):
                if sub_label:
                    letter = ascii_lowercase[order % len(ascii_lowercase)]
                    numbering.references[("fig", sub_label)] = (f'{group["prefix"]}({letter})', f"fig:{sub_label}")
            groups.append(group)
            index = end + 1
            continue

        elif token.type in ("math_block", "math_block_label"):
            label = token.info.strip() if token.type == "math_block_label" else None
            line = (token.map[0] if token.map else 0) + state.env.get("line_offset", 0)
            math = f'<span class="math math-display">\\[{escape(token.content, quote=False)}\\]</span>'
            if label == "-":
                output.append(html_block(f'<div class="equation" data-line="{line}">{math}</div>\n'))
            else:
                if label and label.startswith("eq:"):
                    label = label[3:]
                number, anchor = numbering.next_item("eq", label)
                attribute = f' id="{escape(anchor)}"' if anchor else ""
                output.append(html_block(
                    f'<div class="equation"{attribute} data-line="{line}">{math}'
                    f'<span class="equation-number">({number})</span></div>\n'
                ))
            index += 1
            continue

        output.append(token)
        index += 1

    for token in output:
        if token.type == "inline" and token.children:
            token.children = replace_references(token.children, numbering)
    for node, tag, css_class, prefix, children, anchor in captions:
        attribute = f' id="{escape(anchor)}"' if anchor else ""
        body = render(replace_references(children, numbering), state.md.options, state.env).strip()
        gap = text["caption_gap"] if body else ""
        node.content = (f'<{tag} class="caption {css_class}"{attribute}>'
                        f'<span class="caption-label">{escape(prefix)}</span>{gap}{body}</{tag}>\n')

    def render_inline(children):
        return render(replace_references(children, numbering), state.md.options, state.env).strip()

    for group in groups:
        cells = []
        for order, (image, sub_label) in enumerate(group["images"]):
            picture = render([image], state.md.options, state.env)  # 先渲染图片，替换引用后的内容不适合放进 alt
            letter = ascii_lowercase[order % len(ascii_lowercase)]
            attribute = f' id="{escape("fig:" + sub_label)}"' if sub_label else ""
            cells.append(f'<figure class="subfigure"{attribute}>{picture}'
                         f'<figcaption class="caption subfigure-caption">{f"({letter}) {render_inline(image.children or [])}".strip()}</figcaption></figure>')
        body = render_inline(group["caption"])
        gap = text["caption_gap"] if body else ""
        attribute = f' id="{escape(group["anchor"])}"' if group["anchor"] else ""
        group["node"].content = (
            f'<figure class="figure-group"{attribute} data-line="{group["line"]}" style="--figure-columns: {group["columns"]}">'
            f'<div class="figure-grid">{"".join(cells)}</div>'
            f'<figcaption class="caption figure-caption"><span class="caption-label">{escape(group["prefix"])}</span>{gap}{body}</figcaption>'
            f'</figure>\n'
        )
    state.tokens = output


def enable(md):
    md.use(container_plugin, name="figures")
    md.core.ruler.after("block", "numbered_heading_attrs", read_heading_attrs)
    md.core.ruler.before("add_line_numbers", "number_document", number_document)
    return md


def front_matter_html(meta, text, render_inline):
    """题目、作者、摘要和关键词。"""
    parts = []
    if meta.get("title"):
        parts.append(f'<div class="doc-title">{render_inline(str(meta["title"]))}</div>')
    author = meta.get("author")
    if isinstance(author, list):
        author = "　".join(str(name) for name in author)
    for value, css_class in ((author, "doc-author"), (meta.get("affiliation"), "doc-affiliation"),
                             (str(meta["date"])[:10] if meta.get("date") else None, "doc-date")):
        if value:
            parts.append(f'<p class="{css_class}">{render_inline(str(value))}</p>')
    abstract = meta.get("abstract")
    if abstract:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", str(abstract)) if p.strip()]
        for position, paragraph in enumerate(paragraphs):
            label = f'<strong class="front-label">{text["abstract"]}</strong>' if position == 0 else ""
            parts.append(f'<p class="doc-abstract">{label}{render_inline(paragraph)}</p>')
    keywords = meta.get("keywords")
    if keywords:
        words = re.split(r"[,，;；]\s*", keywords) if isinstance(keywords, str) else [str(word) for word in keywords]
        joined = text["keyword_separator"].join(escape(word.strip()) for word in words if word.strip())
        parts.append(f'<p class="doc-keywords"><strong class="front-label">{text["keywords"]}</strong>{joined}</p>')
    return f'<header class="front-matter">{"".join(parts)}</header>\n' if parts else ""
