"""Markdown 渲染规则：编辑器预览和博客共用同一份，两边显示一致。

这个文件只管“Markdown 怎么变成 HTML”，不读写文件、不关心页面。博客仓库里有一份副本，
博客本机构建时会从编辑器文件夹自动同步过去，所以只改编辑器这一份就行。

    md = make_markdown()
    html = md.render(text)                     # 博客：不加行号
    html = md.render(text, {"line_offset": 0}) # 编辑器：加 data-line，用于同步滚动

模板用的 ::: 块和 [文字]{.类名} 要另外调用 enable_custom_markup(md)。
依赖：markdown-it-py、mdit-py-plugins、Pygments。
"""
import re
from urllib.parse import parse_qs

from markdown_it import MarkdownIt
from mdit_py_plugins.anchors import anchors_plugin
from mdit_py_plugins.container import container_plugin
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.tasklists import tasklists_plugin
from pygments import highlight as pygments_highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

CLASS_NAME = r"[^\W\d][\w-]*"
BLOCK_CLASSES = re.compile(rf"{CLASS_NAME}(?: {CLASS_NAME})*")
SPAN_CLASSES = re.compile(rf"\{{\s*(\.{CLASS_NAME}(?:\s+\.{CLASS_NAME})*)\s*\}}")


def highlight_code(code, lang, _attrs):
    try:
        lexer = get_lexer_by_name(lang)
    except ClassNotFound:
        return ""  # 交给 markdown-it 按普通代码块输出
    return pygments_highlight(code, lexer, HtmlFormatter(nowrap=True))


def escape_html(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def render_math(content, opts):
    if opts.get("display_mode"):
        return f'<span class="math math-display">\\[{escape_html(content)}\\]</span>'
    return f'<span class="math">\\({escape_html(content)}\\)</span>'


def strip_quote_markers(state):
    """公式插件不会去掉引用里每行开头的 >，这里按引用层数去掉。"""
    depth = 0
    for token in state.tokens:
        if token.type == "blockquote_open":
            depth += 1
        elif token.type == "blockquote_close":
            depth -= 1
        elif token.type == "math_block" and depth:
            token.content = re.sub(rf"^[ \t]*(?:>[ \t]?){{1,{depth}}}", "", token.content, flags=re.M)


def is_image_line(children):
    """这一行只有图片（可以带链接，比如 [![](a.png)](url)，或者编号模板的 {#fig:a width=60%}），没有文字。"""
    return any(child.type == "image" for child in children) and all(
        child.type in ("image", "link_open", "link_close")
        or (child.type == "text" and re.fullmatch(r"\s*(?:\{[^{}]*\}\s*)?", child.content))
        for child in children)


def split_lines(state):
    """一行就是一段：换行直接换段，不用空一行。图片单独占一行时也自成一段。
    行尾写两个空格或反斜杠（硬换行）时只换行、不换段，用来写诗、地址这类要分行的内容，
    不过单独占一行的图片仍然自成一段。加粗、链接等没有结束的地方不拆开，否则格式会断掉。
    紧凑列表里的段落不显示 <p>，拆开会让各行粘在一起，所以那里换行变成 <br>。"""
    tokens = []
    index = 0
    while index < len(state.tokens):
        opening = state.tokens[index]
        inline = state.tokens[index + 1] if index + 1 < len(state.tokens) else None
        if opening.type != "paragraph_open" or not inline or inline.type != "inline" or not opening.map:
            tokens.append(opening)
            index += 1
            continue
        closing = state.tokens[index + 2]
        lines = [{"number": 0, "before": None, "free": True, "children": []}]
        depth = 0  # 还没结束的加粗、链接等有几层
        for child in inline.children or []:
            if child.type in ("softbreak", "hardbreak"):
                # 跨行的行内公式里自己带着换行，也要算进行号
                skipped = sum(c.content.count("\n") for c in lines[-1]["children"] if c.type != "text")
                lines.append({"number": lines[-1]["number"] + 1 + skipped, "before": child, "free": depth == 0, "children": []})
            else:
                depth += child.nesting
                lines[-1]["children"].append(child)
        if opening.hidden:
            for line in lines[1:]:
                if line["free"] and line["before"].type == "softbreak":
                    line["before"].type, line["before"].tag = "hardbreak", "br"
            tokens += [opening, inline, closing]
            index += 3
            continue
        pieces = []  # [起始行, 行数, 内容]
        for position, line in enumerate(lines):
            image = is_image_line(line["children"])
            split = position > 0 and line["free"] and (
                line["before"].type == "softbreak" or image or is_image_line(lines[position - 1]["children"]))
            if position == 0 or split:
                pieces.append([line["number"], 1, line["children"]])
            else:
                pieces[-1][1] += 1
                pieces[-1][2] = pieces[-1][2] + [line["before"]] + line["children"]
        if len(pieces) == 1:
            tokens += [opening, inline, closing]
            index += 3
            continue
        source = inline.content.split("\n")
        for number, count, children in pieces:
            first = opening.map[0] + number
            tokens += [
                opening.copy(attrs=dict(opening.attrs), map=[first, first + count]),
                inline.copy(children=children, content="\n".join(source[number:number + count]), map=[first, first + count]),
                closing.copy(attrs=dict(closing.attrs)),
            ]
        index += 3
    state.tokens = tokens


def add_line_numbers(state):
    """给顶层内容标上源文件行号，用于编辑器的同步滚动。没给 line_offset 时（比如博客）不加。"""
    offset = state.env.get("line_offset") if isinstance(state.env, dict) else None
    if offset is None:
        return
    for token in state.tokens:
        if token.map and token.level == 0 and token.nesting >= 0:
            token.attrSet("data-line", str(token.map[0] + offset))


# ---------- 视频 ----------
# 单独一行写 @[youtube](视频ID或链接) 或 @[bilibili](BV号或链接)，可以在后面加 "标题"
VIDEO_LINE = re.compile(r'@\[(youtube|bilibili)\]\(\s*(\S+?)(?:\s+"([^"]*)")?\s*\)\s*$', re.I)
VIDEO_TITLES = {"youtube": "YouTube 视频", "bilibili": "哔哩哔哩视频"}


def start_seconds(query):
    """链接里的开始时间：t=90、t=1m30s、start=90，都换成秒。"""
    params = parse_qs(query)
    value = (params.get("t") or params.get("start") or [""])[0]
    match = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s?)?", value)
    if not match or not value:
        return 0
    hours, minutes, seconds = (int(x or 0) for x in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def video_url(provider, target):
    """把视频 ID 或网页链接换成嵌入播放器的地址，认不出时返回空字符串。"""
    if provider == "youtube":
        match = re.match(r"(?:https?://)?(?:www\.|m\.)?(?:youtube(?:-nocookie)?\.com/(?:watch\?(?:[^#]*&)?v=|embed/|shorts/|live/)|youtu\.be/)?"
                         r"([A-Za-z0-9_-]{11})(?:[?&#](.*))?$", target)
        if not match:
            return ""
        start = start_seconds((match.group(2) or "").replace("#", "&"))
        # youtube-nocookie：不点播放就不设置跟踪 cookie
        return f"https://www.youtube-nocookie.com/embed/{match.group(1)}" + (f"?start={start}" if start else "")
    match = re.match(r"(?:https?://)?(?:www\.|m\.)?(?:bilibili\.com/video/)?(BV[A-Za-z0-9]{10})/?(?:\?(.*))?$", target)
    if not match:
        return ""
    params = parse_qs(match.group(2) or "")
    url = f"https://player.bilibili.com/player.html?bvid={match.group(1)}&autoplay=0"
    page = (params.get("p") or ["1"])[0]
    if page.isdigit() and page != "1":
        url += f"&p={page}"
    start = start_seconds(match.group(2) or "")
    return url + (f"&t={start}" if start else "")


def video_block(state, start, end, silent):
    if state.sCount[start] - state.blkIndent >= 4:  # 缩进四格是代码块
        return False
    line = state.src[state.bMarks[start] + state.tShift[start]:state.eMarks[start]]
    match = VIDEO_LINE.match(line)
    if not match:
        return False
    provider = match.group(1).lower()
    url = video_url(provider, match.group(2))
    if not url:
        return False  # 认不出的 ID 原样显示成文字，作者能看出写错了
    if silent:
        return True
    token = state.push("video", "", 0)
    token.map = [start, start + 1]
    token.meta = {"url": url, "title": match.group(3) or VIDEO_TITLES[provider]}
    state.line = start + 1
    return True


def watch_url(embed):
    """播放器地址换回视频网页地址，打印和 PDF 里放不了视频，显示这个链接。"""
    youtube = re.match(r"https://www\.youtube-nocookie\.com/embed/([\w-]{11})(?:\?start=(\d+))?", embed)
    if youtube:
        return f"https://www.youtube.com/watch?v={youtube.group(1)}" + (f"&t={youtube.group(2)}s" if youtube.group(2) else "")
    bilibili = re.search(r"bvid=(BV\w+)", embed)
    return f"https://www.bilibili.com/video/{bilibili.group(1)}" if bilibili else embed


def render_video(self, tokens, idx, options, env):
    token = tokens[idx]
    meta = token.meta
    line = token.attrGet("data-line")
    line = f' data-line="{line}"' if line is not None else ""
    return (f'<div class="video" data-link="{escape_html(watch_url(meta["url"]))}"{line}>'
            f'<iframe src="{escape_html(meta["url"])}" title="{escape_html(meta["title"])}" loading="lazy" '
            'allow="accelerometer; encrypted-media; gyroscope; picture-in-picture; fullscreen" allowfullscreen '
            'referrerpolicy="strict-origin-when-cross-origin"></iframe></div>\n')


def make_markdown():
    md = (
        MarkdownIt("commonmark", {"html": True, "highlight": highlight_code})
        .enable(["table", "strikethrough"])
        .use(dollarmath_plugin, allow_digits=False, double_inline=True, renderer=render_math)
        .use(footnote_plugin)
        .use(tasklists_plugin)
        .use(anchors_plugin, max_level=4)
    )
    md.core.ruler.push("strip_quote_markers", strip_quote_markers)
    md.core.ruler.after("inline", "split_lines", split_lines)
    md.block.ruler.before("paragraph", "video", video_block, {"alt": ["paragraph"]})
    md.add_render_rule("video", render_video)
    md.core.ruler.push("add_line_numbers", add_line_numbers)
    return md


def render_block(renderer, tokens, index, options, env):
    token = tokens[index]
    if token.nesting == 1:
        token.attrSet("class", token.info.strip())
    return renderer.renderToken(tokens, index, options, env)


def class_span(state, silent):
    """[文字]{.date} 生成 <span class="date">。只认 class：style 这些属性会绕开模板 CSS 的检查，
    所以不用 mdit-py-plugins 的 attrs 插件，它的 allowed 参数管不到这种写法。"""
    if state.src[state.pos] != "[" or state.src.startswith("@", state.pos + 1):  # [@fig:a] 是引用，不能变成文字
        return False
    label_end = state.md.helpers.parseLinkLabel(state, state.pos)
    match = SPAN_CLASSES.match(state.src, label_end + 1) if label_end >= 0 else None
    if not match:
        return False
    if not silent:
        end = state.posMax
        state.pos += 1
        state.posMax = label_end
        token = state.push("span_open", "span", 1)
        token.attrSet("class", " ".join(name[1:] for name in match.group(1).split()))
        state.md.inline.tokenize(state)
        state.push("span_close", "span", -1)
        state.posMax = end
    state.pos = match.end()
    return True


def enable_custom_markup(md):
    """模板可以写 ::: job 和 [文字]{.date}，生成带 class 的块和文字，由模板的 CSS 决定样式。
    要在 numbered.enable 之后调用，这样 ::: figures 先被认成图组。"""
    md.use(container_plugin, name="block", render=render_block,
           validate=lambda params, *_: bool(BLOCK_CLASSES.fullmatch(params.strip())))
    md.inline.ruler.after("link", "class_span", class_span)  # 排在链接后面，真正的链接不受影响
    return md
