---
extends: none
css: ./resume.css
pdf-bookmarks: false  # 一页的简历用不着书签，日期也不会混进书签里
style:
  # 这两项在 resume.css 里写成 var(--accent) 和 var(--font-size)，用这个模板的文档可以改
  accent: "#1a5fb4"
  font-size: 五号

  # 页面选项，所有模板都能用
  paper: A4
  page-margin: 15mm 18mm
  page-numbers: false
---

# 姓名

::: contact
电话 · 邮箱 · 城市
:::

## 工作经历

### 公司名称 · 职位 [2020 – 至今]{.date}

- 这个文件是简历模板，打开它就能看到效果。样式在 `resume.css` 里。
- 任何文件夹里的文件写 `template: resume` 就能用它，例子见 `examples/resume/resume.md`。
