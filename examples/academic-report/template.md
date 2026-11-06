---
extends: report
title: 这是一个自定义模板
author: 打开这个文件就能看到模板的效果
style:
  # 页面
  paper: A4
  page-margin: 3cm 2.5cm 2.5cm 3cm  # 上 右 下 左
  page-numbers: true

  # 正文。英文字体写在前面，中文才会用后面的字体
  body-font: Times New Roman, KaiTi
  font-size: 小四
  line-height: 20pt
  first-line-indent: 2em

  # 题目和标题
  title-font: Times New Roman, SimHei
  title-size: 小二
  title-align: center
  heading-1-size: 三号
  heading-1-align: left
  heading-2-size: 四号
  heading-3-size: 小四
  heading-3-font: Times New Roman, FangSong

  # 图题和表题
  caption-size: 五号
  caption-align: center
  three-line-table: false

  # 编号和称呼
  numbering: "2.1"
  chapter-format: "第{cn}章"
  figure-label: Fig.
  table-label: "表{}"
  code-label: 程序
  appendix-label: 附件
---

这个文件是一个模板，别的文件写 `template: ./template.md` 就能用它的样式，例子见 `report_using_template.md`。模板的正文不会进入那些文件，这里的内容只用来预览效果。

# 绪论 {#sec:intro}

正文是楷体小四，固定行距 20 磅，一级标题靠左，并且写成“第一章”。如[@fig:sample]所示，结果见[@tbl:sample]，公式见[@eq:sample]，代码见[@lst:sample]，这一章是[@sec:intro]。

![示例图片](fig/framework.svg){#fig:sample width=60%}

## 二级标题

: 不是三线表，每个格子都有边框 {#tbl:sample}

| 方法 | 误差 |
| --- | --- |
| A | 1.2 |
| B | 0.8 |

$$
E = mc^2
$$ {#eq:sample}

### 三级标题

三级标题用了另一种字体。

```python title="hello.py" {#lst:sample}
print("hello")
```

# 第二部分

第二章的编号也要跟着变：

![另一张图](fig/error.svg){width=50%}

# 附录：补充材料

称呼换成了“附件”：

![附录里的图](fig/panel-a.svg){width=30%}
