"""找到 frontmatter 选的模板，顺着 extends 一路读上去，整理出渲染需要的东西。

只有 none 和 numbered 是内置的，其他模板都是普通文件：先找路径，再按名字找 templates 文件夹。
"""
import posixpath
import re
from pathlib import Path

import yaml

import template_style
from paths import ApiError, content_path, markdown_path, read_markdown

APP_DIR = Path(__file__).resolve().parent
NUMBERED_CSS = APP_DIR / "templates" / "numbered.css"
TEMPLATE_NAME = re.compile(r"[\w-]+(?: [\w-]+)*")
# 打开的文件夹里放自己模板的文件夹。博客改成 _templates，开头的下划线让它不会变成导航栏的栏目
LIBRARY = "templates"


def split_frontmatter(source):
    """返回 (信息, 正文, 警告)。开头两条 --- 之间不是“名称: 值”时，它只是普通的分隔线，不算 frontmatter。"""
    match = re.match(r"---[ \t]*\n(.*?)\n---[ \t]*(?:\n|$)", source, re.S)
    if not match:
        return {}, source, ""
    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError as err:
        return {}, source[match.end():], f"Invalid frontmatter at the top of the file:\n{err}"
    if not isinstance(meta, dict):
        return {}, source, ""
    return meta, source[match.end():], ""


def is_template_file(template):
    return isinstance(template, str) and (template.startswith(("./", "../")) or template.lower().endswith(".md"))


def template_target(rel, path):
    return posixpath.normpath(posixpath.join(posixpath.dirname(rel), path))


def find_library_template(root, name, seen):
    """按名字找模板：先找打开的文件夹下的 templates，再找编辑器自带的 templates。返回 (所在的文件夹, 相对路径)。
    已经用过的文件要跳过，这样打开的文件夹里的 report.md 可以写 extends: report，继承编辑器自带的那个。"""
    if isinstance(name, str) and TEMPLATE_NAME.fullmatch(name):
        for folder, library in ((root, LIBRARY), (str(APP_DIR), "templates")):
            target = f"{library}/{name}.md"
            if (folder, target) not in seen and markdown_path(folder, target).is_file():
                return folder, target
    return None, None


def template_names(root):
    names = {"numbered"}
    for folder in (Path(root) / LIBRARY, APP_DIR / "templates"):
        names.update(path.stem for path in folder.glob("*.md") if TEMPLATE_NAME.fullmatch(path.stem))
    return ", ".join(sorted(names))


def read_template_file(root, target, template):
    """读模板文件，template 是文档里写的内容，用在提示里。返回 (它的 frontmatter, 问题)。"""
    try:
        _, content = read_markdown(root, target)
    except ApiError as err:  # 打开的文件夹以外的路径也会到这里
        return {}, f'Cannot read template file "{template}": {err.message}. It must be a UTF-8 Markdown file.'
    meta, _, problem = split_frontmatter(content)
    if problem:
        return {}, f'Template file "{template}": {problem}'
    if not meta.get("extends"):
        return {}, f'Template file "{template}" must have "extends" at the top: numbered, none or another template.'
    return meta, ""


def find_template(meta, root, rel):
    """frontmatter 选的模板，顺着 extends 一直找到内置的基础。
    返回 (基础, 模板列表, 问题)。基础是 numbered 或 none，有问题或没有模板时是 None。模板从最上层排到最下层，后面的优先。"""
    spec = meta.get("template")
    folder, path = root, rel
    chain = []
    if not spec:  # 模板文件自己写 extends，打开它时看到的就是这个模板的效果。它的 style 就是文档的 style
        spec = meta.get("extends")
        if not spec:
            return None, [], []
        chain.append({"settings": {"css": meta.get("css")}, "folder": root, "path": rel})
    seen = {(root, rel)}
    while not (isinstance(spec, str) and spec in template_style.BASES):
        if is_template_file(spec):
            target = template_target(path, spec)
        else:
            folder, target = find_library_template(root, spec, seen)
            if target is None:
                return None, [], [f'Unknown template "{spec}". Available templates: {template_names(root)}. '
                                  'Or use the path of a template file like ./my-template.md']
        if (folder, target) in seen:
            return None, [], [f'Template "{spec}" extends itself.']
        seen.add((folder, target))
        settings, problem = read_template_file(folder, target, spec)
        if problem:
            return None, [], [problem]
        chain.insert(0, {"settings": settings, "folder": folder, "path": target})
        path = target
        spec = settings["extends"]
    return spec, chain, []


def read_template_css(root, template_path, css):
    """模板写的 css: ./x.css，路径相对于模板文件。返回 (样式, 用到的变量名, 问题)。"""
    if not css:
        return "", set(), []
    try:
        if not isinstance(css, str) or not css.lower().endswith(".css"):
            raise ApiError(400, "Only .css files can be used")
        path = content_path(root, template_target(template_path, css))
        if not path.is_file():
            raise ApiError(404, "File not found")
        text = path.read_bytes().decode("utf-8-sig")
    except (ApiError, UnicodeDecodeError) as err:
        reason = err.message if isinstance(err, ApiError) else "The file is not UTF-8"
        return "", set(), [f'Cannot read template CSS "{css}": {reason}.']
    return template_style.read_css(text, css)


def read_pdf_bookmarks(sources, problems):
    """导出 PDF 时要不要书签。sources 从模板到文档排列，后面的优先，写错的不生效。"""
    result = True
    for source in sources:
        value = source.get("pdf-bookmarks", result)
        if isinstance(value, bool):
            result = value
        else:
            problems.append(f'Invalid value for "pdf-bookmarks": {value}. Expected true or false')
    return result


def load_template(meta, root, rel):
    """返回 {base, doc_class, css, values, lang, pdf_bookmarks, problems}。基础是 numbered 或 none，没有模板或出错时是 None。"""
    base, chain, problems = find_template(meta, root, rel)
    layers = [template["settings"] for template in chain]
    result = {"base": base, "doc_class": "", "css": "", "values": {}, "lang": None,
              "pdf_bookmarks": read_pdf_bookmarks(layers + [meta], problems), "problems": problems}
    if base is None:
        return result
    css_parts = []
    css_variables = set()
    if base == "numbered":
        css_parts.append(template_style.read_css(NUMBERED_CSS.read_text(encoding="utf-8"), NUMBERED_CSS.name)[0])
    for template in chain:
        css, names, css_problems = read_template_css(template["folder"], template["path"], template["settings"].get("css"))
        css_parts.append(css)
        css_variables |= names
        problems += css_problems
    values, variables, style_problems = template_style.read_style([layer.get("style") for layer in layers] + [meta.get("style")], base, css_variables)
    problems += style_problems
    classes = [template_style.BASES[base]] + (["paged"] if template_style.is_paged(values) else [])
    result.update(
        doc_class=" ".join(name for name in classes if name),
        css="\n".join([template_style.build_css(values, variables)] + css_parts),
        values=values,
        lang=meta.get("lang") or next((layer["lang"] for layer in reversed(layers) if layer.get("lang")), None),
    )
    return result
