---
extends: numbered
css: ./article.css
lang: en
title: Academic Article Template
author: Open this file to see how the template looks
date: 2026-11-12
abstract: |
  This file is the template behind `template: article`. It follows the default LaTeX article class at 12pt: Computer Modern type, a centered title, no paragraph indent with a little space between paragraphs, justified and hyphenated text, and bold numbered section headings.
style:
  # 页面：A4，四边 1 英寸。想要和美国的 LaTeX 默认一样就写 paper: Letter
  paper: A4
  page-margin: 2.54cm
  page-numbers: true
  page-number-font: Article Roman
  page-number-size: 12pt

  # 正文。字体是 fonts 文件夹里的 Latin Modern，中文用宋体
  body-font: Article Roman, SimSun, Songti SC, Noto Serif CJK SC
  title-font: Article Title
  code-font: Article Mono
  font-size: 12pt
  small-size: 10.95pt  # 摘要、图题、表格、脚注，等于 LaTeX 的 \small
  line-height: 1.21
  first-line-indent: 0
  paragraph-spacing: .5em
  link-color: inherit

  # 题目和标题，等于 LaTeX 12pt 时的 \LARGE、\large、\Large
  title-size: 20.74pt
  author-size: 14.4pt
  heading-1-size: 17.28pt
  heading-2-size: 14.4pt
  heading-3-size: 12pt

  numbering: "1"  # 图、表、公式全文连续编号（Figure 1、Figure 2），和 LaTeX 一样；章节标题照样是 1、1.1
---

This file is the `article` template. Its look lives in `article.css`; numbering and cross references come from the built-in `numbered`. To make your own version, create a file with `extends: article` and write only the options you want to change. A full example is in `examples/academic-article/`.

# Introduction {#sec:intro}

Paragraphs are justified and long words such as electroencephalography are hyphenated, so the spacing stays even. **Bold** and *italic* use the matching Latin Modern faces. See [@sec:method], [@fig:sample], [@tbl:sample] and [@eq:sample].

## Background

A second-level heading is numbered 1.1.

# Method {#sec:method}

$$
\hat{x} = \arg\min_x \lVert y - Ax \rVert_2^2 + \lambda \lVert x \rVert_1
$$ {#eq:sample}

![A sample figure](../examples/academic-article/fig/framework.svg){#fig:sample width=60%}

: A sample table {#tbl:sample}

| Method | Error |
| --- | --- |
| A | 1.2 |
| B | 0.8 |

# References

References are not numbered.
