---
template: ./template.md
title: 使用自定义模板的报告
author: 张三
affiliation: 某某大学
date: 2026-11-06
abstract: 这份报告的样式来自 template.md，并在自己的 style 里改了一项：一级标题改成居中。
keywords: 模板, 样式
style:
  heading-1-align: center
---

# 引言 {#sec:intro}

这里写的 `style` 比模板文件优先，所以这份报告的一级标题是居中的，其他样式和模板一样。如[@fig:arch]所示，详见[@sec:method]。

![系统架构](fig/framework.svg){#fig:arch width=60%}

# 方法 {#sec:method}

## 数据

: 实验结果 {#tbl:result}

| 方法 | 误差 |
| --- | --- |
| A | 1.2 |
| B | 0.8 |

结果见[@tbl:result]。
