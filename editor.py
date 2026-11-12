#!/usr/bin/env python3
"""本地 Markdown 编辑器，可以打开任意文件夹。

用法：bash start.sh [文件夹]，或 python editor.py [端口]，然后打开 http://localhost:8001

只监听本机，并拒绝来自其他网页的请求，否则你打开的任意网站都可能改写你的文件。
要打开哪个文件夹由每个请求的 root 参数决定，服务端不保存“当前文件夹”，所以多个窗口可以各开一个文件夹。
"""
import base64
import json
import mimetypes
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

from pygments.formatters import HtmlFormatter

import numbered
from md_render import enable_custom_markup, make_markdown
import template_loader
import template_style
from paths import MARKDOWN_SUFFIXES, ApiError, content_path, markdown_path, read_markdown, workspace

try:
    from send2trash import TrashPermissionError, send2trash
except ImportError:  # 只有删除文件需要它，没装时其他功能照常可用
    send2trash = None
    TrashPermissionError = OSError

DEFAULT_PORT = 8001
APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
RECENT_FILE = APP_DIR / "recent.json"
PREFERENCES_FILE = APP_DIR / "preferences.json"
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/editor.js": ("editor.js", "text/javascript; charset=utf-8"),
    "/editor.css": ("editor.css", "text/css; charset=utf-8"),
    "/document.css": ("document.css", "text/css; charset=utf-8"),
}
SKIP_DIRS = {"node_modules", "__pycache__", "venv"}  # 依赖和缓存，里面的 Markdown 不是你写的
MAX_TREE_ENTRIES = 50000  # 不小心打开整个硬盘时，不至于一直卡住
MAX_RECENT = 8
IMAGE_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}
MAX_IMAGE_BYTES = 50 * 1024 * 1024
CODE_CSS = HtmlFormatter(style="default").get_style_defs("pre")
CDN_CODEMIRROR = "https://cdn.jsdelivr.net/npm/codemirror@5.65.16/"
CDN_KATEX = "https://cdn.jsdelivr.net/npm/katex@0.16.11/"
# 第二道防线：就算清理漏了，也不能运行内联脚本，脚本只能来自这些地址，也不能向其他网站发请求
PAGE_SECURITY_POLICY = (
    "default-src 'none'; "
    f"script-src 'self' {CDN_CODEMIRROR} {CDN_KATEX}; "
    f"style-src 'self' 'unsafe-inline' {CDN_CODEMIRROR} {CDN_KATEX}; "
    f"font-src {CDN_KATEX} data:; "
    "img-src * data: blob:; connect-src 'self'; frame-src https:; "
    "base-uri 'none'; form-action 'none'; object-src 'none'"
)
FILE_SECURITY_POLICY = "default-src 'none'; style-src 'unsafe-inline'; sandbox"  # 直接打开 SVG 时，里面的脚本不能运行

recent_lock = threading.Lock()


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
            # if sub or is_empty_dir(entry.path):
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


# ---------- 设置 ----------
DEFAULT_PREFERENCES = {"font_size": 14, "image_folder": "fig", "image_save_base": "current"}
FONT_SIZE_RANGE = (10, 28)


def clean_image_folder(folder):
    """图片文件夹是相对于打开的文件夹的路径，不能离开它，也不能放进 .git 这样的隐藏文件夹。返回 None 表示不合法。"""
    if not isinstance(folder, str):
        return None
    folder = folder.strip().replace("\\", "/").strip("/")
    parts = folder.split("/")
    invalid = not folder or ":" in folder or any(
        not part or part.startswith(".") or part.endswith((" ", ".")) for part in parts
    )
    return None if invalid else folder


def clean_preferences(data):
    """只保留认识的设置，不合法的值用默认值，手动改坏配置文件也不影响启动。"""
    size = data.get("font_size") if isinstance(data, dict) else None
    valid_size = isinstance(size, int) and not isinstance(size, bool) and FONT_SIZE_RANGE[0] <= size <= FONT_SIZE_RANGE[1]
    folder = clean_image_folder(data.get("image_folder")) if isinstance(data, dict) else None
    
    # 新增：解析并校验保存路径基准
    save_base = data.get("image_save_base") if isinstance(data, dict) else None
    valid_save_base = save_base in ("root", "current")

    return {
        "font_size": size if valid_size else DEFAULT_PREFERENCES["font_size"],
        "image_folder": folder or DEFAULT_PREFERENCES["image_folder"],
        # 新增：返回合法的路径模式
        "image_save_base": save_base if valid_save_base else DEFAULT_PREFERENCES["image_save_base"],
    }


def api_read_preferences():
    try:
        return clean_preferences(json.loads(PREFERENCES_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return dict(DEFAULT_PREFERENCES)


def api_save_preferences(data):
    if clean_image_folder(data.get("image_folder")) is None:  # 用户正在填写，直接告诉他，而不是悄悄换成默认值
        raise ApiError(400, "Enter a folder inside the open folder, such as fig or assets/images")
    preferences = clean_preferences(data)
    write_file(PREFERENCES_FILE, json.dumps(preferences, ensure_ascii=False, indent=2) + "\n")
    return preferences


PICK_FOLDER_SCRIPT = """
import tkinter, tkinter.filedialog
root = tkinter.Tk()
root.withdraw()
root.attributes("-topmost", True)
print(tkinter.filedialog.askdirectory(title="Choose a folder to open"), end="")
"""


def api_pick_folder():
    """弹出系统的选择文件夹对话框。放到单独的进程里，因为 tkinter 不能在服务的线程中运行。"""
    try:
        result = subprocess.run([sys.executable, "-c", PICK_FOLDER_SCRIPT], capture_output=True,
                                encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})
    except OSError as err:
        raise ApiError(500, f"Could not open the folder picker: {err}")
    if result.returncode != 0:
        raise ApiError(500, "Could not open the folder picker. Enter the folder path instead.")
    return {"path": str(Path(result.stdout)) if result.stdout else ""}


# ---------- 读写 ----------
def mtime_of(path):
    return str(path.stat().st_mtime_ns)  # 用字符串，纳秒数超出 JavaScript 的整数精度


def api_read(root, rel):
    path, content = read_markdown(root, rel)
    return {"path": rel, "content": content, "mtime": mtime_of(path)}


def write_file(path, content):
    temp = path.with_name(f".{path.name}.tmp")  # 先写临时文件再替换，写到一半出错也不会损坏原文件
    temp.write_bytes(content.encode("utf-8"))
    os.replace(temp, path)


def api_save(data):
    path = markdown_path(data.get("root"), data.get("path"))
    content = data.get("content")
    if not isinstance(content, str):
        raise ApiError(400, "Missing content")
    exists = path.is_file()
    if not data.get("force") and (not exists or mtime_of(path) != data.get("mtime")):
        raise ApiError(409, "The file was changed or deleted outside the editor")
    if exists and b"\r\n" in path.read_bytes():  # 保持文件原有的换行符，不让 git 显示整个文件都改了
        content = content.replace("\n", "\r\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    write_file(path, content)
    return {"mtime": mtime_of(path)}


def unused_name(path, stem, suffix):
    """重名时在后面加编号：a.md 和 a (1).md 都有了，就用 a (2).md。"""
    if not path.exists():
        return path.name
    base = re.sub(r" \(\d+\)$", "", stem)  # 输入 a (1) 且已存在时，接着 a 的编号往下排
    pattern = re.compile(re.escape(base) + r"(?: \((\d+)\))?" + re.escape(suffix), re.I)  # Windows 不分大小写
    matches = (pattern.fullmatch(child.name) for child in path.parent.iterdir())
    largest = max((int(match.group(1) or 0) for match in matches if match), default=0)
    return f"{base} ({largest + 1}){suffix}"


def with_name(rel, name):
    return "/".join(rel.split("/")[:-1] + [name])


def api_new(data):
    root = data.get("root")
    rel = (data.get("path") or "").strip().strip("/")
    if not rel.lower().endswith(MARKDOWN_SUFFIXES):
        rel += ".md"
    path = markdown_path(root, rel)
    rel = with_name(rel, unused_name(path, path.stem, path.suffix))
    path = markdown_path(root, rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    # 写上创建日期：博客按它排序，搬运旧日记时直接改成当天的日期
    write_file(path, f"---\ndate: {datetime.now():%Y-%m-%d}\n---\n\n# {path.stem}\n\n")
    return {"path": rel}


def api_new_folder(data):
    root = data.get("root")
    rel = (data.get("path") or "").strip().strip("/")
    path = content_path(root, rel)
    rel = with_name(rel, unused_name(path, path.name, ""))  # 文件夹名里的点不是后缀，比如 v1.2
    content_path(root, rel).mkdir(parents=True)
    return {"path": rel}


def api_move(data):
    """移动或重命名文件、文件夹。目标已存在时拒绝，绝不覆盖。"""
    root = data.get("root")
    source = content_path(root, data.get("from"))
    target_rel = (data.get("to") or "").strip().strip("/")
    if source.is_file():
        markdown_path(root, data.get("from"))  # 只允许动 Markdown 文件
        if not target_rel.lower().endswith(MARKDOWN_SUFFIXES):
            target_rel += ".md"
    elif not source.is_dir():
        raise ApiError(404, "File not found")
    target = content_path(root, target_rel)
    if source in target.parents:
        raise ApiError(400, "A folder cannot be moved into itself")
    # 只改大小写时（a.md → A.md），Windows 上目标看起来已存在，其实是同一个文件
    if target.exists() and not os.path.samefile(source, target):
        raise ApiError(409, "An item with that name already exists")
    if not target.parent.is_dir():
        raise ApiError(404, "Destination folder not found")
    # 不用上面规范化后的 target：Windows 上它会变回磁盘上的旧大小写，只改大小写时就改不动了
    final = workspace(root) / target_rel
    moving_file = source.is_file()
    images = image_references(source) if moving_file and source.parent.resolve() != final.parent.resolve() else []
    os.rename(source, final)
    result = {"path": target_rel}
    if images:
        result["images"] = move_images(root, source, final, images)
    return result


# ---------- 移动文件时带上图片 ----------
IMAGE_REFERENCE = re.compile(
    # ![说明](路径 "标题")；路径有空格时写成 <路径>；路径里可以有成对的括号，比如 a(1).png
    r"!\[[^\]]*\]\(\s*(?:<([^>\n]+)>|((?:[^()\s]|\([^()\s]*\))+))(?:\s+[\"'(][^)]*)?\)"
    r"|<(?:img|audio|video|source)\b[^>]*?\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.I)  # <img src="路径">，录音和视频也算


def image_references(path):
    """文件里引用的、和它放在同一个文件夹（或子文件夹）里的图片，返回 [(写在文件里的路径, 相对文件夹的路径)]。
    网址、绝对路径和指向上级文件夹的不算：它们不跟着文件走。"""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    found = []
    for match in IMAGE_REFERENCE.finditer(text):
        written = match.group(1) or match.group(2) or match.group(3)
        if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:|/|#|\\", written):
            continue
        relative = posixpath.normpath(unquote(re.split(r"[?#]", written, maxsplit=1)[0]))
        if relative.startswith("..") or relative == "." or relative.lower().endswith(MARKDOWN_SUFFIXES):
            continue
        if (path.parent / relative).is_file() and (written, relative) not in found:
            found.append((written, relative))
    return found


def referenced_elsewhere(root, moved_to, image):
    """打开的文件夹里，除了刚移动的文件，还有没有别的 Markdown 用到这张图片。"""
    base = workspace(root)
    for folder, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS]
        for name in files:
            other = Path(folder) / name
            if not name.lower().endswith(MARKDOWN_SUFFIXES) or other == moved_to:
                continue
            for _, relative in image_references(other):
                if os.path.normcase((other.parent / relative).resolve()) == os.path.normcase(image.resolve()):
                    return True
    return False


def same_bytes(a, b):
    return a.stat().st_size == b.stat().st_size and a.read_bytes() == b.read_bytes()


def move_images(root, old_file, new_file, images):
    """把文件引用的图片按原来的相对位置放到新文件夹：_images/a.png 还是放进新位置的 _images。
    别的文件也在用的图片复制一份，不搬走；新位置已有同名但不同的图片时，不覆盖，换个名字并改文件里的引用。"""
    old_folder, new_folder = old_file.parent, new_file.parent
    report = {"moved": 0, "copied": 0, "renamed": 0}
    replacements = {}
    emptied = set()
    for written, relative in images:
        source = old_folder / relative
        if not source.is_file():  # 同一张图写了两种路径，前面已经搬走了
            continue
        target = new_folder / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shared = referenced_elsewhere(root, new_file, source)
        if target.exists():
            if same_bytes(source, target):  # 新位置已经有一模一样的，直接用它
                if not shared:
                    source.unlink()
                    emptied.add(source.parent)
                report["moved" if not shared else "copied"] += 1
                continue
            stem, suffix = target.stem, target.suffix
            number = 1
            while target.exists():  # a-1.png：不用空格和括号，引用里不用转义
                target = target.with_name(f"{stem}-{number}{suffix}")
                number += 1
            folder_part = posixpath.dirname(relative)
            new_relative = posixpath.join(folder_part, target.name) if folder_part else target.name
            # 只转义空格和括号，中文文件名保持原样，方便阅读
            replacements[written] = new_relative.replace(" ", "%20").replace("(", "%28").replace(")", "%29")
            report["renamed"] += 1
        if shared:
            shutil.copy2(source, target)
            report["copied"] += 1
        else:
            shutil.move(str(source), target)
            emptied.add(source.parent)
            report["moved"] += 1
    for folder in sorted(emptied, key=lambda p: len(p.parts), reverse=True):  # 搬空的图片文件夹删掉，不留空壳
        while folder != old_folder and old_folder in folder.parents and folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
            folder = folder.parent
    if replacements:
        text = new_file.read_bytes().decode("utf-8")  # 不用 read_text：它会把 \r\n 换成 \n，改掉文件原来的换行
        for written, new in replacements.items():
            text = re.sub(r"(\]\(\s*<?|src\s*=\s*[\"'])" + re.escape(written), lambda m: m.group(1) + new, text)
        write_file(new_file, text)
        report["rewritten"] = True
    return report


def api_delete(data):
    """把文件或文件夹移到系统回收站，不永久删除，点错了还能恢复。"""
    root = data.get("root")
    path = content_path(root, data.get("path"))  # 路径至少有一层，所以不可能删到打开的文件夹本身
    if path.is_file():
        markdown_path(root, data.get("path"))  # 文件只允许删 Markdown
    elif not path.is_dir():
        raise ApiError(404, "File not found")
    if send2trash is None:
        raise ApiError(500, "Deleting needs the send2trash package. Run: pip install -r requirements.txt")
    try:
        send2trash(str(path))
    except TrashPermissionError as err:
        raise ApiError(500, f"Could not move it to the Recycle Bin: {err}")
    return {"path": data.get("path")}


# ---------- 清理未使用的图片 ----------
MEDIA_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".avif", ".heic", ".tif", ".tiff",
                  ".mp3", ".m4a", ".wav", ".ogg", ".aac", ".flac", ".mp4", ".mov", ".webm", ".m4v")
REFERENCE = re.compile(
    r"\]\(\s*(?:<([^>\n]+)>|((?:[^()\s]|\([^()\s]*\))+))"  # ![](路径) 和 [](路径)
    r"|\b(?:src|href|poster|data)\s*=\s*[\"']([^\"']+)[\"']"  # <img src> <a href> <video poster> <object data>
    r"|^\s*\[[^\]]+\]:\s*<?([^\s>]+)", re.I | re.M)  # [名字]: 路径（引用式链接）


def walk_files(base):
    for folder, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS]
        for name in files:
            if not name.startswith("."):
                yield Path(folder) / name


def referenced_files(root):
    """打开的文件夹里，所有 Markdown 和 HTML 文件引用到的本地文件（规范化后的绝对路径）。
    包括 ../ 指向别的文件夹的，所以别处在用的图片不会被当成没用。"""
    used = set()
    for document in walk_files(workspace(root)):
        if not document.name.lower().endswith(MARKDOWN_SUFFIXES + (".html", ".htm")):
            continue
        try:
            text = document.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for match in REFERENCE.finditer(text):
            target = next(group for group in match.groups() if group)
            if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:|#|//", target):
                continue
            path = unquote(re.split(r"[?#]", target, maxsplit=1)[0])
            base = workspace(root) if path.startswith("/") else document.parent
            used.add(os.path.normcase(os.path.normpath(base / path.lstrip("/"))))
    return used


def unused_media(root, folder):
    used = referenced_files(root)
    found = []
    for path in walk_files(folder):
        if path.suffix.lower() in MEDIA_SUFFIXES and os.path.normcase(os.path.normpath(path)) not in used:
            found.append(path)
    return found


def api_unused_images(root, rel):
    """选中的文件夹（没选就是整个打开的文件夹）里，没有被任何 Markdown 或 HTML 引用的图片、录音和视频。"""
    folder = content_path(root, rel) if rel else workspace(root)
    if not folder.is_dir():
        raise ApiError(404, "Folder not found")
    base = workspace(root)
    images = [{"path": path.relative_to(base).as_posix(), "size": path.stat().st_size} for path in unused_media(root, folder)]
    return {"folder": rel or "", "images": sorted(images, key=lambda item: natural_key(item["path"]))}


def api_trash_images(data):
    """把选中的未使用图片移到回收站。动手前再查一遍，这期间被引用了的就不删。"""
    root = data.get("root")
    paths = data.get("paths")
    if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
        raise ApiError(400, "Expected a list of paths")
    if send2trash is None:
        raise ApiError(500, "Deleting needs the send2trash package. Run: pip install -r requirements.txt")
    used = referenced_files(root)
    trashed, kept = [], []
    folders = set()
    for rel in paths:
        path = content_path(root, rel)
        if not path.is_file() or path.suffix.lower() not in MEDIA_SUFFIXES:
            raise ApiError(400, f"Not an image: {rel}")
        if os.path.normcase(os.path.normpath(path)) in used:
            kept.append(rel)
            continue
        try:
            send2trash(str(path))
        except TrashPermissionError as err:
            raise ApiError(500, f"Could not move it to the Recycle Bin: {err}")
        trashed.append(rel)
        folders.add(path.parent)
    base = workspace(root)
    for folder in folders:  # 清空了的图片文件夹也删掉，不留空壳
        if folder != base and folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
    return {"trashed": trashed, "kept": kept}


def api_folder_info(root, rel):
    """文件夹里有多少个文件，包括子文件夹和非 Markdown 文件。删除前告诉用户。"""
    path = content_path(root, rel)
    if not path.is_dir():
        raise ApiError(404, "Folder not found")
    return {"files": sum(len(files) for _, _, files in os.walk(path))}


def api_save_image(data):
    """保存粘贴的图片，返回可以直接写进 Markdown 的相对路径。"""
    root = data.get("root")
    document = data.get("path")
    markdown_path(root, document)
    extension = IMAGE_TYPES.get(data.get("type"))
    if extension is None:
        raise ApiError(415, "Only PNG, JPEG, GIF and WebP images can be pasted")
    try:
        image = base64.b64decode(data.get("data") or "", validate=True)
    except ValueError:
        raise ApiError(400, "Invalid image data")
    if not image or len(image) > MAX_IMAGE_BYTES:
        raise ApiError(413, "The image is empty or larger than 50 MB")
    
    # ======== 修改开始 ========
    prefs = api_read_preferences()
    folder = prefs["image_folder"]
    save_base = prefs["image_save_base"]

    # 判断是保存在根目录还是当前文件所在目录
    if save_base == "current":
        # 获取当前 Markdown 文件所在的目录，并与图片文件夹名拼接
        doc_dir = posixpath.dirname(document)
        effective_folder = posixpath.join(doc_dir, folder) if doc_dir else folder
    else:
        effective_folder = folder

    # 后续操作全部使用 effective_folder 替换原本的 folder
    content_path(root, f"{effective_folder}/x{extension}")  # 校验文件夹没有离开打开的文件夹
    (workspace(root) / effective_folder).mkdir(parents=True, exist_ok=True)
    stem = datetime.now().strftime("image-%Y%m%d-%H%M%S")
    for attempt in range(1000):
        name = f"{stem}{'-' + str(attempt) if attempt else ''}{extension}"
        try:
            with open(workspace(root) / effective_folder / name, "xb") as file:  # x：文件已存在就失败，绝不覆盖
                file.write(image)
            break
        except FileExistsError:
            continue
    else:
        raise ApiError(409, "Could not find a free file name for the image")
    
    saved = f"{effective_folder}/{name}"
    # ======== 修改结束 ========
    
    return {"path": saved, "link": quote(posixpath.relpath(saved, posixpath.dirname(document) or "."))}

# ---------- 渲染 ----------
MD = make_markdown()
MD_NUMBERED = enable_custom_markup(numbered.enable(make_markdown()))  # 基于 numbered 的模板用这个
MD_CUSTOM = enable_custom_markup(make_markdown())  # 基于 none 的模板用这个


def parse_tags(value):
    if not value:
        return []
    if isinstance(value, str):
        value = re.split(r"[,，]", value)
    if not isinstance(value, list):
        value = [value]
    return [str(t).strip() for t in value if str(t).strip()]


def rewrite_images(html, root, rel):
    """正文里图片的相对路径指向 /files，这样预览能显示和文章放在一起的图片。"""
    folder = posixpath.dirname(rel)
    root_param = quote(root, safe="")

    def replace(match):
        target = posixpath.normpath(posixpath.join(folder, unquote(match.group(2))))
        return f'{match.group(1)}/files?root={root_param}&amp;path={quote(target, safe="")}"'

    return re.sub(r'(<img\b[^>]*?\bsrc=")(?![a-zA-Z][a-zA-Z0-9+.-]*:|/|#)([^"]+)"', replace, html)


def render_body(meta, body, env, root, rel):
    """按 frontmatter 选的模板渲染正文，返回 (HTML, 给前端的模板信息, 问题)。前端只看模板信息，不需要知道是哪个模板。"""
    template = template_loader.load_template(meta, root, rel)
    info = {
        "doc_class": template["doc_class"],
        "show_head": template["base"] != "numbered",  # numbered 的题目、作者和摘要在正文的开头
        "template_css": template["css"],
        "toc_title": "Table of Contents",
        "pdf_bookmarks": template["pdf_bookmarks"],
    }
    if template["base"] is None:
        return MD.render(body, env), info, template["problems"]
    if template["base"] == "none":
        return MD_CUSTOM.render(body, env), info, template["problems"]
    text = template_style.apply_text(numbered.text_for(template["lang"]), template["values"])
    env["numbered_text"] = text
    info["toc_title"] = text["toc"]
    render_inline = lambda value: MD_CUSTOM.renderInline(value, {"line_offset": 0})
    html = numbered.front_matter_html(meta, text, render_inline) + MD_NUMBERED.render(numbered.prepare_source(body), env)
    return html, info, template["problems"]


def api_render(data):
    root = data.get("root")
    rel = data.get("path")
    markdown_path(root, rel)
    source = data.get("content") or ""
    meta, body, warning = template_loader.split_frontmatter(source)
    env = {"line_offset": source.count("\n") - body.count("\n")}
    html, template_info, problems = render_body(meta, body, env, root, rel)
    if warning:
        problems.insert(0, warning)
    date = meta.get("date")
    return {
        "title": str(meta.get("title") or ""),
        "date": str(date)[:10] if date else "",
        "tags": parse_tags(meta.get("tags")),
        "html": rewrite_images(html, root, rel),
        "warning": "\n".join(problems),
        **template_info,
    }


# ---------- 导出 PDF ----------
BROWSER_PATHS = [
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
    r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]
BROWSER_COMMANDS = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"]
PDF_TIMEOUT_SECONDS = 120
# Markdown 里可能带脚本，这个文件又是在本机直接打开的，所以不允许运行脚本，也不允许发请求
PDF_SECURITY_POLICY = ("<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; "
                       "style-src 'unsafe-inline' https:; font-src https: data:; img-src https: http: data:\">")


def find_browser():
    for candidate in BROWSER_PATHS:
        path = os.path.expandvars(candidate)
        if os.path.isfile(path):
            return path
    for command in BROWSER_COMMANDS:
        path = shutil.which(command)
        if path:
            return path
    return None


def api_pdf(data):
    """用本机的 Chrome 或 Edge 把导出的 HTML 转成 PDF。打印窗口生成不了书签，所以不走打印窗口。"""
    html = data.get("html")
    if not isinstance(html, str) or "<head>" not in html:
        raise ApiError(400, "Missing content")
    browser = find_browser()
    if browser is None:
        raise ApiError(501, "Chrome or Edge was not found")
    html = html.replace("<head>", "<head>\n" + PDF_SECURITY_POLICY, 1)
    outline = [] if data.get("bookmarks") is False else ["--generate-pdf-document-outline"]
    with tempfile.TemporaryDirectory(prefix="markdown-editor-pdf-", ignore_cleanup_errors=True) as folder:
        folder = Path(folder)
        source = folder / "document.html"
        output = folder / "document.pdf"
        source.write_text(html, encoding="utf-8")
        try:
            subprocess.run(
                [browser, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                 "--disable-extensions", f"--user-data-dir={folder / 'profile'}",
                 "--no-pdf-header-footer", *outline, "--virtual-time-budget=10000",
                 f"--print-to-pdf={output}", source.as_uri()],
                capture_output=True, timeout=PDF_TIMEOUT_SECONDS,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except subprocess.TimeoutExpired:
            raise ApiError(504, "Creating the PDF took too long")
        if not output.is_file():
            raise ApiError(500, "The browser could not create the PDF")
        return output.read_bytes()


# ---------- 服务 ----------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_body(self, status, body, content_type, security_policy=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("X-Content-Type-Options", "nosniff")
        if security_policy:
            self.send_header("Content-Security-Policy", security_policy)
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
            self.send_json(403, {"error": "Request refused"})
            return
        try:
            handler()
        except ApiError as err:
            self.send_json(err.status, {"error": err.message})
        except OSError as err:
            self.send_json(500, {"error": f"Could not read or write the file: {err}"})

    def do_GET(self):
        self.respond(self.handle_get)

    def do_POST(self):
        self.respond(self.handle_post)

    def handle_get(self):
        url = urlsplit(self.path)
        query = {key: values[0] for key, values in parse_qs(url.query).items()}
        if url.path in STATIC_FILES:
            name, content_type = STATIC_FILES[url.path]
            self.send_body(200, (STATIC_DIR / name).read_bytes(), content_type, PAGE_SECURITY_POLICY)
        elif url.path == "/code.css":
            self.send_body(200, CODE_CSS.encode("utf-8"), "text/css; charset=utf-8")
        elif url.path == "/api/recent":
            self.send_json(200, api_recent())
        elif url.path == "/api/preferences":
            self.send_json(200, api_read_preferences())
        elif url.path == "/api/tree":
            self.send_json(200, api_tree(query.get("root")))
        elif url.path == "/api/folder-info":
            self.send_json(200, api_folder_info(query.get("root"), query.get("path")))
        elif url.path == "/api/unused-images":
            self.send_json(200, api_unused_images(query.get("root"), query.get("path")))
        elif url.path == "/api/file":
            self.send_json(200, api_read(query.get("root"), query.get("path")))
        elif url.path == "/files":
            path = content_path(query.get("root"), query.get("path"))
            content_type = mimetypes.guess_type(path.name)[0] or ""
            if not content_type.startswith("image/"):  # 预览只需要图片，其他文件不对外提供
                raise ApiError(403, "Only images can be read")
            if not path.is_file():
                raise ApiError(404, "File not found")
            self.send_body(200, path.read_bytes(), content_type, FILE_SECURITY_POLICY)
        else:
            raise ApiError(404, "Page not found")

    def handle_post(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError
        except ValueError:
            raise ApiError(400, "Invalid request")
        path = urlsplit(self.path).path
        if path == "/api/pick-folder":
            self.send_json(200, api_pick_folder())
            return
        if path == "/api/pdf":
            self.send_body(200, api_pdf(data), "application/pdf")
            return
        routes = {
            "/api/save": api_save,
            "/api/new": api_new,
            "/api/new-folder": api_new_folder,
            "/api/move": api_move,
            "/api/delete": api_delete,
            "/api/trash-images": api_trash_images,
            "/api/image": api_save_image,
            "/api/render": api_render,
            "/api/preferences": api_save_preferences,
        }
        if path not in routes:
            raise ApiError(404, "Page not found")
        self.send_json(200, routes[path](data))


class Server(ThreadingHTTPServer):
    allow_reuse_address = False  # Windows 上允许重复绑定时，第二个服务不会报错，请求也不知道会到哪个服务


def serve(port=DEFAULT_PORT):
    server = Server(("127.0.0.1", port), Handler)
    print(f"Markdown Editor: http://localhost:{port} (press Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    serve(int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT)
