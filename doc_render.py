"""按 frontmatter 选的模板渲染一篇文档：编辑器预览和博客共用。

    meta, body, warning = template_loader.split_frontmatter(text)
    html, info, problems = render_body(meta, body, env, root, rel)

root 是打开的文件夹（博客就是博客根目录），rel 是文档相对它的路径，用来找模板文件。
info 里有 doc_class、template_css、show_head 等，告诉页面怎么显示；problems 是写错的设置，给作者看。
博客仓库里有这个文件和它用到的几个文件的副本，本机构建博客时自动同步，只改编辑器这一份就行。
"""
import numbered
import template_loader
import template_style
from md_render import enable_custom_markup, make_markdown

MD = make_markdown()
MD_NUMBERED = enable_custom_markup(numbered.enable(make_markdown()))  # 基于 numbered 的模板用这个
MD_CUSTOM = enable_custom_markup(make_markdown())  # 基于 none 的模板用这个


def render_body(meta, body, env, root, rel):
    """按 frontmatter 选的模板渲染正文，返回 (HTML, 给前端的模板信息, 问题)。前端只看模板信息，不需要知道是哪个模板。"""
    template = template_loader.load_template(meta, root, rel)
    info = {
        "doc_class": template["doc_class"],
        "show_head": template["base"] != "numbered",  # numbered 的题目、作者和摘要在正文的开头
        "template_css": template["css"],
        "toc_title": "Table of Contents",
        "pdf_bookmarks": template["pdf_bookmarks"],
        "base": template["base"],
    }
    if template["base"] is None:
        return MD.render(body, env), info, template["problems"]
    if template["base"] == "none":
        return MD_CUSTOM.render(body, env), info, template["problems"]
    text = template_style.apply_text(numbered.text_for(template["lang"]), template["values"])
    env["numbered_text"] = text
    info["toc_title"] = text["toc"]
    render_inline = lambda value: MD_CUSTOM.renderInline(value, {"line_offset": 0})  # noqa: E731
    html = numbered.front_matter_html(meta, text, render_inline) + MD_NUMBERED.render(numbered.prepare_source(body), env)
    return html, info, template["problems"]
