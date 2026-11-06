---
template: report
---

这份文件用来检查边界情况：没有题目，没有一级标题之前的内容也不应该出错。这张图在第一个标题之前，没有章号：

![标题之前的图](fig/framework.svg){#fig:before}

# 第一章

## 跳过的情况

#### 跳过第三级，直接写第四级

下面是粘贴图片的常见写法，没有说明，所以不编号，也不占图号：

![](fig/error.svg)

有说明但没有标签的图片，也会编号：

![只有说明，没有标签](fig/error.svg)

和文字写在同一段里的图片不算独立的图 ![行内图片](fig/error.svg) 这里还有文字。

写错的引用会标红：[@fig:not-exist]，[@tbl:not-exist]。

代码里的引用和标记不处理：`[@fig:before]`，以及下面的代码块：

```markdown
$$ x = 1 $$ {#eq:in-code}
![不是图](a.png){#fig:in-code}
[@fig:before]
```

引用前面的图：[@fig:before]。引用后面的图：[@fig:later]。引用下一章：[@sec:second]。

没有表题的表格也用三线表，不编号：

| A | B |
| --- | --- |
| 1 | 2 |

这段以冒号开头，但是旁边没有表格，所以只是普通文字：

: 普通文字，不是表题

# 第二章 {#sec:second}

换了一章，图号重新开始：

![第二章的第一张图](fig/framework.svg){#fig:later}

一行写完的公式：

$$ a^2 + b^2 = c^2 $$ {#eq:one-line}

没有标签的公式：

$$ E = mc^2 $$

不编号的公式：

$$ 1 + 1 = 2 $$ {-}

引用：[@eq:one-line]。

图组的边界情况。没写 cols 时默认两列，没有总标题时只显示图号：

::: figures
![第一张](fig/panel-a.svg)
![第二张](fig/panel-b.svg)
![第三张，这一行只有一张](fig/panel-d.svg)
:::

子图没写说明时，只显示字母。引用写错的子图会标红：[@fig:no-such-panel]

::: figures {cols=2}
![](fig/panel-a.svg)
![](fig/panel-b.svg)

只有总标题
:::

cols 超出范围时按最多 6 列处理：

::: figures {cols=99}
![1](fig/panel-a.svg)
![2](fig/panel-b.svg)
![3](fig/panel-c.svg)
![4](fig/panel-d.svg)
![5](fig/panel-a.svg)
![6](fig/panel-b.svg)
![7](fig/panel-c.svg)

七张图
:::

图组里不该有的内容不会丢，会放在图组后面：

::: figures
![图](fig/panel-a.svg)

- 这个列表不是图

总标题
:::

图片大小的边界情况，下面依次是 30%、5cm、写错的宽度（按原大小）、写在标签前面：

![宽度 30%](fig/panel-a.svg){#fig:w-percent width=30%}

![宽度 5cm](fig/panel-a.svg){width=5cm}

![写错的宽度](fig/panel-a.svg){width=abc}

![属性写在前面](fig/panel-a.svg){width=40% #fig:w-order}

引用：[@fig:w-percent]、[@fig:w-order]。没有说明的图也能调大小，并且不编号：

![](fig/panel-a.svg){width=25%}

不认识的属性不算图片属性，会原样显示：

![不认识的属性](fig/panel-a.svg){height=3cm}

下面是分页符。行内的 \newpage 不分页，代码里的也不分页：`\newpage`

\newpage

```
\newpage
```

代码块的边界情况。只写语言不编号：

```python
print("没有编号")
```

只有 title，文件名里的符号不当格式，HTML 也不会生效：

```python title="a_b_c*d*<b>e</b>.py"
print("代码 2-1")
```

title 可以有空格，也可以用单引号，没写语言也行：

``` title='注意力 计算'
没有语言
```

只有标签没有 title，也会编号，这样才能被引用：[@lst:only-label]。写错的引用会标红：[@lst:no-such]

```python {#lst:only-label}
print("只有标签")
```

属性顺序可以调换，不认识的语言也不报错：

```no-such-language {#lst:reorder} title="顺序调换.txt"
some text
```

列表里的代码块：

- 第一项

  ```python title="in-list.py"
  print("在列表里")
  ```

下面这个代码块里的内容不是真的标题，要原样显示：

````markdown
```python title="a.py" {#lst:in-code}
print("这是示例")
```
````

下面的代码比一页还长，只能跨页，每一页的框都应该闭合：

```python title="long.py"
def long_function():
    value_01 = compute(1)  # 第 1 行
    value_02 = compute(2)  # 第 2 行
    value_03 = compute(3)  # 第 3 行
    value_04 = compute(4)  # 第 4 行
    value_05 = compute(5)  # 第 5 行
    value_06 = compute(6)  # 第 6 行
    value_07 = compute(7)  # 第 7 行
    value_08 = compute(8)  # 第 8 行
    value_09 = compute(9)  # 第 9 行
    value_10 = compute(10)  # 第 10 行
    value_11 = compute(11)  # 第 11 行
    value_12 = compute(12)  # 第 12 行
    value_13 = compute(13)  # 第 13 行
    value_14 = compute(14)  # 第 14 行
    value_15 = compute(15)  # 第 15 行
    value_16 = compute(16)  # 第 16 行
    value_17 = compute(17)  # 第 17 行
    value_18 = compute(18)  # 第 18 行
    value_19 = compute(19)  # 第 19 行
    value_20 = compute(20)  # 第 20 行
    value_21 = compute(21)  # 第 21 行
    value_22 = compute(22)  # 第 22 行
    value_23 = compute(23)  # 第 23 行
    value_24 = compute(24)  # 第 24 行
    value_25 = compute(25)  # 第 25 行
    value_26 = compute(26)  # 第 26 行
    value_27 = compute(27)  # 第 27 行
    value_28 = compute(28)  # 第 28 行
    value_29 = compute(29)  # 第 29 行
    value_30 = compute(30)  # 第 30 行
    value_31 = compute(31)  # 第 31 行
    value_32 = compute(32)  # 第 32 行
    value_33 = compute(33)  # 第 33 行
    value_34 = compute(34)  # 第 34 行
    value_35 = compute(35)  # 第 35 行
    value_36 = compute(36)  # 第 36 行
    value_37 = compute(37)  # 第 37 行
    value_38 = compute(38)  # 第 38 行
    value_39 = compute(39)  # 第 39 行
    value_40 = compute(40)  # 第 40 行
    value_41 = compute(41)  # 第 41 行
    value_42 = compute(42)  # 第 42 行
    value_43 = compute(43)  # 第 43 行
    value_44 = compute(44)  # 第 44 行
    value_45 = compute(45)  # 第 45 行
    value_46 = compute(46)  # 第 46 行
    value_47 = compute(47)  # 第 47 行
    value_48 = compute(48)  # 第 48 行
    value_49 = compute(49)  # 第 49 行
    value_50 = compute(50)  # 第 50 行
    value_51 = compute(51)  # 第 51 行
    value_52 = compute(52)  # 第 52 行
    value_53 = compute(53)  # 第 53 行
    value_54 = compute(54)  # 第 54 行
    value_55 = compute(55)  # 第 55 行
    value_56 = compute(56)  # 第 56 行
    value_57 = compute(57)  # 第 57 行
    value_58 = compute(58)  # 第 58 行
    value_59 = compute(59)  # 第 59 行
    value_60 = compute(60)  # 第 60 行
    value_61 = compute(61)  # 第 61 行
    value_62 = compute(62)  # 第 62 行
    value_63 = compute(63)  # 第 63 行
    value_64 = compute(64)  # 第 64 行
    value_65 = compute(65)  # 第 65 行
    value_66 = compute(66)  # 第 66 行
    value_67 = compute(67)  # 第 67 行
    value_68 = compute(68)  # 第 68 行
    value_69 = compute(69)  # 第 69 行
    value_70 = compute(70)  # 第 70 行
    return value_70
```

# 不编号的章 {-}

## 这一节也不编号

不编号的章里的图继续用上一章的图号：

![不编号章里的图](fig/error.svg)

# Appendix Notes

名字以 Appendix 开头但不是附录，比如这个标题，按普通章节编号。

# 附录

## 附录里的小节

# 附录 C：写了字母也按实际顺序编号

字母由顺序决定，这一个是第二个附录，所以是 B。

# 第三章

回到普通章节后，章号接着前面的普通章节，不受附录影响。

![普通章节里的图](fig/panel-a.svg){width=30%}

这一章的编号应该是 3，因为上面那章不占编号。

- 列表第一项[^n]
- 列表第二项

[^n]: 列表里的脚注。
