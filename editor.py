#!/usr/bin/env python3
"""本地 Markdown 编辑器，可以打开任意文件夹。

用法：bash start.sh [文件夹]，或 python editor.py [端口]，然后打开 http://localhost:8001

只监听本机，并拒绝来自其他网页的请求，否则你打开的任意网站都可能改写你的文件。
要打开哪个文件夹由每个请求的 root 参数决定，服务端不保存“当前文件夹”，所以多个窗口可以各开一个文件夹。
"""
import json
import mimetypes
import os
import posixpath
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

import yaml
from markdown_it import MarkdownIt
from mdit_py_plugins.anchors import anchors_plugin
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.tasklists import tasklists_plugin
from pygments import highlight as pygments_highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

DEFAULT_PORT = 8001
APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
RECENT_FILE = APP_DIR / "recent.json"
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/editor.js": ("editor.js", "text/javascript; charset=utf-8"),
    "/editor.css": ("editor.css", "text/css; charset=utf-8"),
}
MARKDOWN_SUFFIXES = (".md", ".markdown")
SKIP_DIRS = {"node_modules", "__pycache__", "venv"}  # 依赖和缓存，里面的 Markdown 不是你写的
MAX_TREE_ENTRIES = 50000  # 不小心打开整个硬盘时，不至于一直卡住
MAX_RECENT = 8
CODE_CSS = HtmlFormatter(style="default").get_style_defs("pre")

recent_lock = threading.Lock()


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


# ---------- 路径 ----------
def workspace(root):
    """用户打开的文件夹，必须是绝对路径。"""
    path = Path(root) if isinstance(root, str) and root else None
    if path is None or not path.is_absolute():
        raise ApiError(400, "请提供文件夹的完整路径")
    if not path.is_dir():
        raise ApiError(404, f"找不到文件夹：{root}")
    return path.resolve()


def content_path(root, rel):
    """把相对路径转成文件路径，不允许离开打开的文件夹，也不允许碰 .git 这样的隐藏文件。"""
    base = workspace(root)
    parts = rel.split("/") if isinstance(rel, str) else []
    invalid = not parts or "\\" in rel or ":" in rel or any(
        not part or part.startswith(".") or part.endswith((" ", ".")) for part in parts
    )
    if invalid:
        raise ApiError(400, "路径不允许")
    path = (base / rel).resolve()
    if base not in path.parents:
        raise ApiError(400, "路径不允许")
    return path


def markdown_path(root, rel):
    path = content_path(root, rel)
    if path.suffix.lower() not in MARKDOWN_SUFFIXES:
        raise ApiError(400, "只能编辑 Markdown 文件")
    return path


# ---------- 文件树 ----------
def natural_key(name):
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", name.lower())]


def scan_folder(folder, base, budget):
    """文件夹里的 Markdown 文件。不显示没有 Markdown 的文件夹，但保留空文件夹，方便在里面新建文件。"""
    children = []
    try:
        entries = sorted(os.scandir(folder), key=lambda e: (not e.is_dir(), natural_key(e.name)))
    except OSError:  # 没有权限的文件夹直接跳过
        return children
    for entry in entries:
        budget["left"] -= 1
        if budget["left"] <= 0:
            budget["truncated"] = True
            break
        if entry.name.startswith(".") or entry.name in SKIP_DIRS:
            continue
        rel = Path(entry.path).relative_to(base).as_posix()
        if entry.is_dir():
            sub = scan_folder(entry.path, base, budget)
            if sub or is_empty_dir(entry.path):
                children.append({"name": entry.name, "path": rel, "children": sub})
        elif entry.name.lower().endswith(MARKDOWN_SUFFIXES):
            children.append({"name": entry.name, "path": rel})
    return children


def is_empty_dir(path):
    try:
        with os.scandir(path) as entries:
            return next(entries, None) is None
    except OSError:
        return False


def api_tree(root):
    base = workspace(root)
    budget = {"left": MAX_TREE_ENTRIES, "truncated": False}
    tree = scan_folder(base, base, budget)
    remember_folder(str(base))
    return {"root": str(base), "name": base.name or str(base), "tree": tree, "truncated": budget["truncated"]}


# ---------- 最近打开 ----------
def read_recent():
    try:
        folders = json.loads(RECENT_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [f for f in folders if isinstance(f, str)] if isinstance(folders, list) else []


def remember_folder(path):
    with recent_lock:
        folders = read_recent()
        updated = ([path] + [f for f in folders if f != path])[:MAX_RECENT]
        if updated != folders:
            try:
                RECENT_FILE.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError:
                pass  # 记不住最近打开的文件夹不影响编辑


def api_recent():
    with recent_lock:
        return {"folders": [f for f in read_recent() if os.path.isdir(f)]}


PICK_FOLDER_SCRIPT = """
import tkinter, tkinter.filedialog
root = tkinter.Tk()
root.withdraw()
root.attributes("-topmost", True)
print(tkinter.filedialog.askdirectory(title="选择要打开的文件夹"), end="")
"""


def api_pick_folder():
    """弹出系统的选择文件夹对话框。放到单独的进程里，因为 tkinter 不能在服务的线程中运行。"""
    try:
        result = subprocess.run([sys.executable, "-c", PICK_FOLDER_SCRIPT], capture_output=True,
                                encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})
    except OSError as err:
        raise ApiError(500, f"无法打开选择窗口：{err}")
    if result.returncode != 0:
        raise ApiError(500, "无法打开选择窗口，请直接输入文件夹路径")
    return {"path": str(Path(result.stdout)) if result.stdout else ""}


# ---------- 读写 ----------
def mtime_of(path):
    return str(path.stat().st_mtime_ns)  # 用字符串，纳秒数超出 JavaScript 的整数精度


def api_read(root, rel):
    path = markdown_path(root, rel)
    if not path.is_file():
        raise ApiError(404, "文件不存在")
    try:
        content = path.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError:  # 用错误的编码打开再保存会损坏文件，所以直接拒绝
        raise ApiError(415, "这个文件不是 UTF-8 编码，请先转换编码再编辑")
    return {"path": rel, "content": content.replace("\r\n", "\n"), "mtime": mtime_of(path)}


def write_file(path, content):
    temp = path.with_name(f".{path.name}.tmp")  # 先写临时文件再替换，写到一半出错也不会损坏原文件
    temp.write_bytes(content.encode("utf-8"))
    os.replace(temp, path)


def api_save(data):
    path = markdown_path(data.get("root"), data.get("path"))
    content = data.get("content")
    if not isinstance(content, str):
        raise ApiError(400, "缺少内容")
    exists = path.is_file()
    if not data.get("force") and (not exists or mtime_of(path) != data.get("mtime")):
        raise ApiError(409, "文件已在别处被修改或删除")
    if exists and b"\r\n" in path.read_bytes():  # 保持文件原有的换行符，不让 git 显示整个文件都改了
        content = content.replace("\n", "\r\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    write_file(path, content)
    return {"mtime": mtime_of(path)}


def api_new(data):
    rel = (data.get("path") or "").strip().strip("/")
    if not rel.lower().endswith(MARKDOWN_SUFFIXES):
        rel += ".md"
    path = markdown_path(data.get("root"), rel)
    if path.exists():
        raise ApiError(409, "这个文件已经存在")
    path.parent.mkdir(parents=True, exist_ok=True)
    write_file(path, f"# {path.stem}\n\n")
    return {"path": rel}


# ---------- 渲染 ----------
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


def add_line_numbers(state):
    """给顶层内容标上源文件行号，用于同步滚动。"""
    offset = state.env["line_offset"]
    for token in state.tokens:
        if token.map and token.level == 0 and token.nesting >= 0:
            token.attrSet("data-line", str(token.map[0] + offset))


MD = (
    MarkdownIt("commonmark", {"html": True, "highlight": highlight_code})
    .enable(["table", "strikethrough"])
    .use(dollarmath_plugin, allow_digits=False, double_inline=True, renderer=render_math)
    .use(footnote_plugin)
    .use(tasklists_plugin)
    .use(anchors_plugin, max_level=4)
)
MD.core.ruler.push("strip_quote_markers", strip_quote_markers)
MD.core.ruler.push("add_line_numbers", add_line_numbers)


def parse_tags(value):
    if not value:
        return []
    if isinstance(value, str):
        value = re.split(r"[,，]", value)
    if not isinstance(value, list):
        value = [value]
    return [str(t).strip() for t in value if str(t).strip()]


def split_frontmatter(source):
    """返回 (信息, 正文, 警告)。开头两条 --- 之间不是“名称: 值”时，它只是普通的分隔线，不算 frontmatter。"""
    match = re.match(r"---[ \t]*\n(.*?)\n---[ \t]*(?:\n|$)", source, re.S)
    if not match:
        return {}, source, ""
    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError as err:
        return {}, source[match.end():], f"文件开头的 frontmatter 格式有误：\n{err}"
    if not isinstance(meta, dict):
        return {}, source, ""
    return meta, source[match.end():], ""


def rewrite_images(html, root, rel):
    """正文里图片的相对路径指向 /files，这样预览能显示和文章放在一起的图片。"""
    folder = posixpath.dirname(rel)
    root_param = quote(root, safe="")

    def replace(match):
        target = posixpath.normpath(posixpath.join(folder, unquote(match.group(2))))
        return f'{match.group(1)}/files?root={root_param}&amp;path={quote(target, safe="")}"'

    return re.sub(r'(<img\b[^>]*?\bsrc=")(?![a-zA-Z][a-zA-Z0-9+.-]*:|/|#)([^"]+)"', replace, html)


def api_render(data):
    root = data.get("root")
    rel = data.get("path")
    markdown_path(root, rel)
    source = data.get("content") or ""
    meta, body, warning = split_frontmatter(source)
    html = MD.render(body, {"line_offset": source.count("\n") - body.count("\n")})
    date = meta.get("date")
    return {
        "title": str(meta.get("title") or ""),
        "date": str(date)[:10] if date else "",
        "tags": parse_tags(meta.get("tags")),
        "html": rewrite_images(html, root, rel),
        "warning": warning,
    }


# ---------- 服务 ----------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_body(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, data):
        self.send_body(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def request_allowed(self):
        """拒绝伪装成本机的域名，以及其他网站页面发来的写入请求。"""
        port = self.server.server_address[1]
        origins = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host") not in origins:
            return False
        if self.command == "POST":
            origin = self.headers.get("Origin")
            if origin and urlsplit(origin).netloc not in origins:
                return False
            if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
                return False
        return True

    def respond(self, handler):
        if not self.request_allowed():
            self.send_json(403, {"error": "请求被拒绝"})
            return
        try:
            handler()
        except ApiError as err:
            self.send_json(err.status, {"error": err.message})
        except OSError as err:
            self.send_json(500, {"error": f"读写文件失败：{err}"})

    def do_GET(self):
        self.respond(self.handle_get)

    def do_POST(self):
        self.respond(self.handle_post)

    def handle_get(self):
        url = urlsplit(self.path)
        query = {key: values[0] for key, values in parse_qs(url.query).items()}
        if url.path in STATIC_FILES:
            name, content_type = STATIC_FILES[url.path]
            self.send_body(200, (STATIC_DIR / name).read_bytes(), content_type)
        elif url.path == "/code.css":
            self.send_body(200, CODE_CSS.encode("utf-8"), "text/css; charset=utf-8")
        elif url.path == "/api/recent":
            self.send_json(200, api_recent())
        elif url.path == "/api/tree":
            self.send_json(200, api_tree(query.get("root")))
        elif url.path == "/api/file":
            self.send_json(200, api_read(query.get("root"), query.get("path")))
        elif url.path == "/files":
            path = content_path(query.get("root"), query.get("path"))
            content_type = mimetypes.guess_type(path.name)[0] or ""
            if not content_type.startswith("image/"):  # 预览只需要图片，其他文件不对外提供
                raise ApiError(403, "只能读取图片")
            if not path.is_file():
                raise ApiError(404, "文件不存在")
            self.send_body(200, path.read_bytes(), content_type)
        else:
            raise ApiError(404, "找不到页面")

    def handle_post(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError
        except ValueError:
            raise ApiError(400, "请求格式错误")
        path = urlsplit(self.path).path
        if path == "/api/pick-folder":
            self.send_json(200, api_pick_folder())
            return
        routes = {"/api/save": api_save, "/api/new": api_new, "/api/render": api_render}
        if path not in routes:
            raise ApiError(404, "找不到页面")
        self.send_json(200, routes[path](data))


class Server(ThreadingHTTPServer):
    allow_reuse_address = False  # Windows 上允许重复绑定时，第二个服务不会报错，请求也不知道会到哪个服务


def serve(port=DEFAULT_PORT):
    server = Server(("127.0.0.1", port), Handler)
    print(f"编辑器地址：http://localhost:{port} （按 Ctrl+C 停止）", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    serve(int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT)
