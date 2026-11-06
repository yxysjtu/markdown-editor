"""打开的文件夹里的路径。所有读写都要经过这里，不允许离开打开的文件夹。"""
from pathlib import Path

MARKDOWN_SUFFIXES = (".md", ".markdown")


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def workspace(root):
    """用户打开的文件夹，必须是绝对路径。"""
    path = Path(root) if isinstance(root, str) and root else None
    if path is None or not path.is_absolute():
        raise ApiError(400, "Enter the full path of a folder")
    if not path.is_dir():
        raise ApiError(404, f"Folder not found: {root}")
    return path.resolve()


def content_path(root, rel):
    """把相对路径转成文件路径，不允许离开打开的文件夹，也不允许碰 .git 这样的隐藏文件。"""
    base = workspace(root)
    parts = rel.split("/") if isinstance(rel, str) else []
    invalid = not parts or "\\" in rel or ":" in rel or any(
        not part or part.startswith(".") or part.endswith((" ", ".")) for part in parts
    )
    if invalid:
        raise ApiError(400, "Path not allowed")
    path = (base / rel).resolve()
    if base not in path.parents:
        raise ApiError(400, "Path not allowed")
    return path


def markdown_path(root, rel):
    path = content_path(root, rel)
    if path.suffix.lower() not in MARKDOWN_SUFFIXES:
        raise ApiError(400, "Only Markdown files can be edited")
    return path


def read_markdown(root, rel):
    """返回 (文件路径, 内容)。换行符统一成 \\n。"""
    path = markdown_path(root, rel)
    if not path.is_file():
        raise ApiError(404, "File not found")
    try:
        content = path.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError:  # 用错误的编码打开再保存会损坏文件，所以直接拒绝
        raise ApiError(415, "This file is not UTF-8. Convert its encoding before editing.")
    return path, content.replace("\r\n", "\n")
