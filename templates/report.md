---
extends: numbered
css: ./report.css
title: 学术报告模板
author: 打开这个文件就能看到模板的效果
style:
  # 页面
  paper: A4
  page-margin: 2.54cm 3.17cm  # 上下、左右
  page-numbers: true

  # 正文
  body-font: Times New Roman, SimSun, Songti SC, Noto Serif CJK SC
  font-size: 小四
  line-height: 1.5
  first-line-indent: 2em

  # 题目和标题。还可以单独写 title-font 和 heading-1-font 到 heading-3-font，以及 heading-2-align、heading-3-align
  heading-font: Report Heading Latin, SimHei, Heiti SC, Noto Sans CJK SC
  title-size: 二号
  title-align: center
  heading-1-size: 三号
  heading-1-align: center
  heading-2-size: 四号
  heading-3-size: 小四

  # 图题、表题和代码标题
  caption-size: 五号
  caption-align: center

  # 表格，默认是三线表。两项都写成 .75pt solid #000 时，每个格子都有边框
  table-rule: 1.5pt solid #000
  cell-border: 0
---

这个文件就是 `template: report` 用的模板，样式在 `report.css` 里，编号和交叉引用来自内置的 `numbered`。想做自己的版本，新建一个文件写 `extends: report`，只写要改的项。

# 第一章 {#sec:first}

如[@fig:sample]所示，结果见[@tbl:sample]，公式见[@eq:sample]，代码见[@lst:sample]，这一章是[@sec:first]。

![示例图片](../examples/academic-report/fig/framework.svg){#fig:sample width=60%}

## 第一节

: 示例表格 {#tbl:sample}

| 方法 | 误差 |
| --- | --- |
| A | 1.2 |
| B | 0.8 |

$$
E = mc^2
$$ {#eq:sample}

### 第一小节

```python title="hello.py" {#lst:sample}
print("hello")
```

# 附录：补充材料

附录按字母编号。

![附录里的图](../examples/academic-report/fig/panel-a.svg){width=30%}
