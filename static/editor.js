(function () {
  var AUTOSAVE_DELAY = 1200;
  var PREVIEW_DELAY = 150;

  var root = new URLSearchParams(location.search).get('root') || ''; // 打开的文件夹，每个窗口可以不同
  var tree = document.getElementById('file-tree');
  var filePath = document.getElementById('file-path');
  var status = document.getElementById('save-status');
  var previewPane = document.getElementById('preview-pane');
  var previewBody = document.getElementById('preview-body');
  var previewError = document.getElementById('preview-error');

  var cm = null;
  var current = null; // { path, mtime }，正在编辑的文件
  var saved = ''; // 磁盘上的内容，用来判断有没有未保存的改动
  var saveTimer = null;
  var previewTimer = null;
  var saving = null; // 进行中的保存，避免同时写两次
  var previewSeq = 0; // 只显示最新一次预览的结果

  // ---------- 请求 ----------
  function request(url, data) {
    var options = data && {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    };
    return fetch(url, options).then(function (response) {
      return response.json().then(function (body) {
        if (response.ok) return body;
        var error = new Error(body.error || 'Request failed');
        error.status = response.status;
        throw error;
      });
    });
  }

  function fileUrl(path) {
    return '/api/file?root=' + encodeURIComponent(root) + '&path=' + encodeURIComponent(path);
  }

  function showStatus(text, isError) {
    status.textContent = text;
    status.classList.toggle('error', !!isError);
  }

  function isDirty() {
    return !!current && cm.getValue() !== saved;
  }

  function folderUrl(folder) {
    return '/?root=' + encodeURIComponent(folder);
  }

  // ---------- 设置 ----------
  var DEFAULT_PREFERENCES = { font_size: 14, image_folder: 'fig' };
  var preferences = DEFAULT_PREFERENCES; // 已保存的设置
  var prefDialog = document.getElementById('preferences');
  var prefSize = document.getElementById('pref-font-size');
  var prefError = document.getElementById('pref-error');

  function applyPreferences(prefs) {
    document.documentElement.style.setProperty('--editor-font-size', prefs.font_size + 'px');
    if (cm) cm.refresh(); // 字号变了，编辑器要重新计算行高和光标位置
  }

  function showPreferencesInDialog(prefs) {
    prefSize.value = prefs.font_size;
    document.getElementById('pref-font-size-value').textContent = prefs.font_size + ' px';
    document.getElementById('pref-image-folder').value = prefs.image_folder;
  }

  function preferencesInDialog() {
    return { font_size: +prefSize.value, image_folder: document.getElementById('pref-image-folder').value };
  }

  function previewPreferences() { // 调节时编辑区实时变化，保存后才写入文件
    var prefs = preferencesInDialog();
    document.getElementById('pref-font-size-value').textContent = prefs.font_size + ' px';
    applyPreferences(prefs);
  }

  document.getElementById('open-preferences').addEventListener('click', function () {
    showPreferencesInDialog(preferences);
    prefError.hidden = true;
    prefDialog.showModal();
  });
  document.getElementById('preferences-form').addEventListener('input', previewPreferences);
  document.getElementById('pref-reset').addEventListener('click', function () {
    showPreferencesInDialog(DEFAULT_PREFERENCES);
    applyPreferences(DEFAULT_PREFERENCES);
  });
  // 放弃预览时立刻恢复已保存的设置。close 事件是异步的，到达时间不可靠，不能靠它恢复
  document.getElementById('pref-cancel').addEventListener('click', function () {
    applyPreferences(preferences);
    prefDialog.close();
  });
  prefDialog.addEventListener('cancel', function () { applyPreferences(preferences); }); // 按 Esc
  prefDialog.addEventListener('close', function () {
    if (cm) cm.focus();
  });
  document.getElementById('preferences-form').addEventListener('submit', function (event) {
    event.preventDefault(); // 先保存，成功后才关窗口；失败时留在窗口里显示原因
    request('/api/preferences', preferencesInDialog()).then(function (saved) {
      preferences = saved;
      prefDialog.close();
    }).catch(function (err) {
      prefError.textContent = 'Could not save: ' + err.message;
      prefError.hidden = false;
    });
  });
  request('/api/preferences').then(function (saved) {
    preferences = saved;
    applyPreferences(saved);
  }).catch(function () {}); // 读不到设置就用默认值

  // ---------- 欢迎页 ----------
  function showWelcome(message) {
    document.getElementById('welcome').hidden = false;
    document.getElementById('workspace').hidden = true;
    document.getElementById('new-file').hidden = true;
    document.getElementById('open-folder').hidden = true;
    document.querySelector('.mode-switch').hidden = true;
    showWelcomeError(message);
    request('/api/recent').then(function (data) {
      var list = document.getElementById('recent-list');
      list.textContent = '';
      data.folders.forEach(function (folder) {
        var link = document.createElement('a');
        link.href = folderUrl(folder);
        var name = document.createElement('span');
        name.className = 'recent-name';
        name.textContent = folder.split(/[\\/]/).filter(Boolean).pop() || folder;
        var path = document.createElement('span');
        path.className = 'recent-path';
        path.textContent = folder;
        link.appendChild(name);
        link.appendChild(path);
        list.appendChild(link);
      });
      document.getElementById('recent').hidden = !data.folders.length;
    }).catch(function () {});
  }

  function showWelcomeError(message) {
    var el = document.getElementById('welcome-error');
    el.textContent = message || '';
    el.hidden = !message;
  }

  document.getElementById('pick-folder').addEventListener('click', function () {
    var button = this;
    button.disabled = true;
    showWelcomeError('');
    request('/api/pick-folder', {}).then(function (data) {
      if (data.path) location.href = folderUrl(data.path);
    }).catch(function (err) {
      showWelcomeError(err.message);
    }).then(function () { button.disabled = false; });
  });

  document.getElementById('path-form').addEventListener('submit', function (event) {
    event.preventDefault();
    var path = document.getElementById('path-input').value.trim().replace(/^"(.*)"$/, '$1'); // 允许粘贴带引号的路径
    if (path) location.href = folderUrl(path);
  });

  // 打开别的文件夹时回到欢迎页，新窗口打开，当前的编辑不受影响
  document.getElementById('open-folder').addEventListener('click', function () {
    window.open('/', '_blank');
  });

  if (!root) {
    showWelcome();
    return;
  }

  // ---------- 编辑器 ----------
  document.getElementById('workspace').hidden = false;
  if (!window.CodeMirror) {
    showStatus('Could not load the editor. Check your network connection (CodeMirror loads from a CDN).', true);
    return;
  }

  // 表格行：以 | 开头的行，或 ---|--- 这样的分隔行。高亮只能看当前行，所以不带首尾 | 的表格只有分隔行会上色
  var TABLE_LINE = /^\s*\||^\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$/;

  // 在 Markdown 高亮上叠加公式和表格：$$...$$ 可以跨行；$...$ 的判断和预览一致，所以“$5 和 $6”不算公式
  CodeMirror.defineMode('markdown-editor', function (config) {
    var base = CodeMirror.getMode(config, {
      name: 'yaml-frontmatter',
      base: { name: 'markdown', highlightFormatting: true, strikethrough: true, taskLists: true }
    });
    return CodeMirror.overlayMode(base, {
      startState: function () { return { inDisplayMath: false }; },
      copyState: function (state) { return { inDisplayMath: state.inDisplayMath }; },
      token: function (stream, state) {
        if (state.inDisplayMath) {
          if (stream.match(/^.*?\$\$/)) state.inDisplayMath = false;
          else stream.skipToEnd();
          return 'math';
        }
        if (stream.match('$$')) {
          state.inDisplayMath = true;
          return 'math';
        }
        var plain = TABLE_LINE.test(stream.string) ? 'table' : null;
        if (stream.match(/^\\./)) return plain;
        var afterDigit = /\d/.test(stream.string.charAt(stream.pos - 1));
        if (stream.peek() === '$' && !afterDigit && stream.match(/^\$(?:[^$\\]|\\.)+?\$(?!\d)/)) return 'math';
        stream.next();
        stream.eatWhile(/[^$\\]/);
        return plain;
      }
    }, true);
  });

  // ---------- 表格 ----------
  var TABLE_ROW = /^(\s{0,3})\|/; // 缩进 4 格以上是代码块，不是表格
  var TABLE_DELIMITER_CELL = /^:?-+:?$/;

  // 按未转义的 | 拆分单元格。只调整空格，不改内容，所以重新拼回去不会改变表格的含义
  function splitTableRow(text) {
    var body = text.trim().replace(/^\|/, '');
    var cells = [];
    var cell = '';
    for (var i = 0; i < body.length; i++) {
      if (body.charAt(i) === '\\' && i + 1 < body.length) {
        cell += body.charAt(i) + body.charAt(i + 1);
        i++;
      } else if (body.charAt(i) === '|') {
        cells.push(cell.trim());
        cell = '';
      } else {
        cell += body.charAt(i);
      }
    }
    if (cell.trim()) cells.push(cell.trim()); // 没写行尾 | 时，最后一格也算
    return cells;
  }

  // 中日韩文字和全角符号在等宽字体里约占两个英文字符
  function displayWidth(text) {
    var width = 0;
    Array.from(text).forEach(function (ch) {
      var code = ch.codePointAt(0);
      var wide = (code >= 0x1100 && code <= 0x115F) || (code >= 0x2E80 && code <= 0xA4CF) ||
        (code >= 0xAC00 && code <= 0xD7A3) || (code >= 0xF900 && code <= 0xFAFF) ||
        (code >= 0xFE30 && code <= 0xFE4F) || (code >= 0xFF00 && code <= 0xFF60) ||
        (code >= 0xFFE0 && code <= 0xFFE6) || (code >= 0x1F300 && code <= 0x1FAFF) ||
        (code >= 0x20000 && code <= 0x3FFFD);
      width += wide ? 2 : 1;
    });
    return width;
  }

  function padCell(text, width) {
    return text + new Array(Math.max(0, width - displayWidth(text)) + 1).join(' ');
  }

  function delimiterCell(cell, width) {
    var left = cell.charAt(0) === ':';
    var right = cell.charAt(cell.length - 1) === ':';
    var dashes = width - (left ? 1 : 0) - (right ? 1 : 0);
    return (left ? ':' : '') + new Array(dashes + 1).join('-') + (right ? ':' : '');
  }

  // 光标所在的表格：连续的 | 开头的行，第二行必须是分隔行。代码块和公式里的不算
  function findTable(editor, lineNo) {
    var match = TABLE_ROW.exec(editor.getLine(lineNo));
    if (!match) return null;
    var type = editor.getTokenTypeAt({ line: lineNo, ch: match[0].length }) || '';
    if (/comment|math/.test(type)) return null;
    var first = lineNo;
    var last = lineNo;
    while (first > 0 && TABLE_ROW.test(editor.getLine(first - 1))) first--;
    while (last < editor.lastLine() && TABLE_ROW.test(editor.getLine(last + 1))) last++;
    if (first === last) return null;
    var delimiter = splitTableRow(editor.getLine(first + 1));
    if (!delimiter.length || !delimiter.every(function (cell) { return TABLE_DELIMITER_CELL.test(cell); })) return null;
    return { first: first, last: last, indent: match[1] };
  }

  function formatTable(rows, indent) {
    var columns = Math.max.apply(null, rows.map(function (row) { return row.length; }));
    var widths = [];
    for (var col = 0; col < columns; col++) {
      widths[col] = 3; // 分隔行至少要 ---
      rows.forEach(function (row, index) {
        if (index !== 1 && row[col]) widths[col] = Math.max(widths[col], displayWidth(row[col]));
      });
      if (rows[1][col] && /^:.*:$/.test(rows[1][col])) widths[col] = Math.max(widths[col], 5); // :---: 至少 5 格
    }
    return rows.map(function (row, index) {
      var cells = [];
      for (var col = 0; col < columns; col++) {
        var cell = row[col] || '';
        cells.push(index === 1 ? delimiterCell(cell || '---', widths[col]) : padCell(cell, widths[col]));
      }
      return indent + '| ' + cells.join(' | ') + ' |';
    });
  }

  // 表格里按 Enter：整理表格并新增一行。返回 false 表示光标不在表格里
  function handleTableEnter(editor) {
    if (editor.somethingSelected() || editor.listSelections().length > 1) return false;
    var lineNo = editor.getCursor().line;
    var table = findTable(editor, lineNo);
    if (!table) return false;
    var rows = [];
    for (var i = table.first; i <= table.last; i++) rows.push(splitTableRow(editor.getLine(i)));
    var rowIndex = lineNo - table.first;
    var isEmptyLastRow = rowIndex > 1 && lineNo === table.last && rows[rowIndex].every(function (cell) { return !cell; });
    if (isEmptyLastRow) rows.pop();
    var lines = formatTable(rows, table.indent);
    var cursor;
    if (isEmptyLastRow) {
      // 最后的空行再按 Enter：退出表格。多空一行，否则接着写的文字会被当成表格的一行
      lines.push('', '');
      cursor = { line: table.first + lines.length - 1, ch: 0 };
    } else {
      var insertAt = Math.max(rowIndex + 1, 2); // 表头和分隔行之间不能加行
      var widths = lines[1].trim().replace(/^\||\|$/g, '').split('|').map(function (cell) { return cell.trim().length; });
      var blank = table.indent + '| ' + widths.map(function (width) { return padCell('', width); }).join(' | ') + ' |';
      lines.splice(insertAt, 0, blank);
      cursor = { line: table.first + insertAt, ch: table.indent.length + 2 };
    }
    editor.operation(function () {
      editor.replaceRange(lines.join('\n'), { line: table.first, ch: 0 }, { line: table.last, ch: editor.getLine(table.last).length });
      editor.setCursor(cursor);
    });
    return true;
  }

  // ---------- 列表缩进 ----------
  var LIST_ITEM = /^(\s*)([-*+]|\d+[.)])(\s+)/;

  function indentOf(text) {
    return text.match(/^\s*/)[0].length;
  }

  // 按 Tab 后的缩进：和上一个同级项的文字对齐才算子项，所以 “1. ” 要缩进 3 格，“- ” 只要 2 格
  function nestedIndent(editor, lineNo, indent) {
    for (var i = lineNo - 1; i >= 0; i--) {
      var text = editor.getLine(i);
      if (!text.trim()) continue;
      var item = LIST_ITEM.exec(text);
      if (!item) {
        if (indentOf(text) === 0) break;
        continue;
      }
      if (item[1].length === indent) return indent + item[2].length + item[3].length;
      if (item[1].length < indent) break;
    }
    return indent + 2;
  }

  // 按 Shift+Tab 后的缩进：回到上一级列表项的位置
  function outerIndent(editor, lineNo, indent) {
    for (var i = lineNo - 1; i >= 0; i--) {
      var text = editor.getLine(i);
      if (!text.trim()) continue;
      var item = LIST_ITEM.exec(text);
      if (item && item[1].length < indent) return item[1].length;
      if (!item && indentOf(text) === 0) break;
    }
    return Math.max(0, indent - 2);
  }

  function setIndent(editor, lineNo, indent) {
    var current = indentOf(editor.getLine(lineNo));
    editor.replaceRange(new Array(indent + 1).join(' '), { line: lineNo, ch: 0 }, { line: lineNo, ch: current });
  }

  // 列表项和它的子项一起移动，不然子项会变成别的项的子项
  function moveListItem(editor, lineNo, direction) {
    var indent = LIST_ITEM.exec(editor.getLine(lineNo))[1].length;
    var target = direction > 0 ? nestedIndent(editor, lineNo, indent) : outerIndent(editor, lineNo, indent);
    var end = lineNo;
    while (end + 1 <= editor.lastLine()) {
      var next = editor.getLine(end + 1);
      if (!next.trim() || indentOf(next) <= indent) break;
      end++;
    }
    for (var i = lineNo; i <= end; i++) {
      setIndent(editor, i, Math.max(0, indentOf(editor.getLine(i)) + target - indent));
    }
    var marker = LIST_ITEM.exec(editor.getLine(lineNo));
    if (direction > 0 && /\d/.test(marker[2])) { // 新的子列表从 1 开始编号，否则预览会从原来的序号开始
      var from = { line: lineNo, ch: marker[1].length };
      var to = { line: lineNo, ch: marker[1].length + marker[2].length };
      editor.replaceRange('1' + marker[2].slice(-1), from, to);
    }
  }

  function indentLines(editor, direction) {
    editor.operation(function () {
      if (!editor.somethingSelected()) {
        var line = editor.getCursor().line;
        if (LIST_ITEM.test(editor.getLine(line))) moveListItem(editor, line, direction);
        else if (direction > 0) editor.replaceSelection('  ');
        else editor.indentLine(line, 'subtract');
        return;
      }
      // 选中多行时，所有行移动相同的距离，保持它们之间的层级
      editor.listSelections().forEach(function (range) {
        var first = Math.min(range.anchor.line, range.head.line);
        var last = Math.max(range.anchor.line, range.head.line);
        var delta = null;
        for (var i = first; i <= last; i++) {
          var text = editor.getLine(i);
          if (!text.trim()) continue;
          var indent = indentOf(text);
          if (delta === null) { // 距离由选区第一行决定
            var isItem = LIST_ITEM.test(text);
            var target = direction > 0
              ? (isItem ? nestedIndent(editor, i, indent) : indent + 2)
              : (isItem ? outerIndent(editor, i, indent) : Math.max(0, indent - 2));
            delta = target - indent;
          }
          setIndent(editor, i, Math.max(0, indent + delta));
        }
      });
    });
  }

  cm = CodeMirror(document.getElementById('editor-pane'), {
    mode: 'markdown-editor',
    lineNumbers: true,
    lineWrapping: true,
    indentUnit: 2,
    tabSize: 2,
    indentWithTabs: false,
    readOnly: true,
    extraKeys: {
      Enter: function (editor) {
        if (!handleTableEnter(editor)) editor.execCommand('newlineAndIndentContinueMarkdownList');
      },
      Tab: function (editor) { indentLines(editor, 1); },
      'Shift-Tab': function (editor) { indentLines(editor, -1); },
      'Ctrl-S': function () { saveNow(); },
      'Cmd-S': function () { saveNow(); }
    }
  });

  // ---------- 文件树 ----------
  function renderTree(items, parent) {
    items.forEach(function (item) {
      if (item.children) {
        var details = document.createElement('details');
        details.dataset.path = item.path;
        var summary = document.createElement('summary');
        summary.textContent = item.name;
        summary.title = item.path;
        enableTreeActions(summary, item);
        details.appendChild(summary);
        var children = document.createElement('div');
        children.className = 'tree-children';
        renderTree(item.children, children);
        details.appendChild(children);
        parent.appendChild(details);
      } else {
        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'tree-file';
        button.textContent = item.name;
        button.title = item.path;
        button.dataset.path = item.path;
        button.addEventListener('click', function () { openFile(item.path); });
        enableTreeActions(button, item);
        parent.appendChild(button);
      }
    });
  }

  // ---------- 移动和重命名 ----------
  var DRAG_TYPE = 'application/x-markdown-editor-path'; // 不用 text/plain，否则拖到编辑区会把路径插进正文
  var draggedPath = null;
  var renaming = false;
  var opening = Promise.resolve(); // 进行中的打开文件。双击的第一下会打开文件，移动前要等它完成

  function parentOf(path) {
    return path.split('/').slice(0, -1).join('/');
  }

  function joinPath(folder, name) {
    return folder ? folder + '/' + name : name;
  }

  function openFolders(path) { // 展开这个文件夹和它的上级
    var parts = path.split('/');
    for (var i = 1; i <= parts.length; i++) {
      var details = tree.querySelector('details[data-path="' + CSS.escape(parts.slice(0, i).join('/')) + '"]');
      if (details) details.open = true;
    }
  }

  function movePath(from, to, folderToShow) {
    var affectsCurrent = false;
    return opening.then(function () {
      affectsCurrent = !!current && (current.path === from || current.path.indexOf(from + '/') === 0);
      if (affectsCurrent) cm.setOption('readOnly', true); // 移动期间不能写入，否则会写到旧路径
      return saveNow(); // 先保存，保存失败就不移动
    }).then(function (ok) {
      if (!ok) return null;
      return request('/api/move', { root: root, from: from, to: to }).then(function (data) {
        if (affectsCurrent) {
          current.path = data.path + current.path.slice(from.length);
          filePath.textContent = current.path;
          document.title = current.path.split('/').pop() + ' · Markdown Editor';
          history.replaceState(null, '', location.search + '#' + encodeURIComponent(current.path));
          renderPreview(); // 图片的相对路径变了
        }
        return loadTree().then(function () {
          if (folderToShow !== undefined) openFolders(folderToShow);
          return data.path;
        });
      });
    }).catch(function (err) {
      showStatus(err.message, true);
      return null;
    }).then(function (result) {
      if (affectsCurrent) cm.setOption('readOnly', false);
      return result;
    });
  }

  function startRename(row, item) {
    if (renaming) return;
    renaming = true;
    var name = item.name;
    var input = document.createElement('input');
    input.type = 'text';
    input.className = 'tree-rename';
    input.value = name;
    input.setAttribute('aria-label', 'New name for ' + name);
    row.draggable = false; // 否则拖动选择文字时会变成拖动整行
    row.textContent = '';
    row.appendChild(input);
    input.focus();
    var dot = item.children ? -1 : name.lastIndexOf('.');
    input.setSelectionRange(0, dot > 0 ? dot : name.length); // 默认只选中文件名，不选扩展名

    var finished = false;
    var finish = function (commit) {
      if (finished) return;
      finished = true;
      renaming = false;
      var newName = input.value.trim();
      if (!commit || !newName || newName === name) {
        row.textContent = name;
        row.draggable = true;
        return;
      }
      var wasOpen = item.children && row.parentElement.open;
      movePath(item.path, joinPath(parentOf(item.path), newName)).then(function (path) {
        if (path === null) {
          row.textContent = name;
          row.draggable = true;
        } else if (wasOpen) {
          openFolders(path);
        }
      });
    };
    input.addEventListener('keydown', function (event) {
      event.stopPropagation();
      if (event.key === 'Enter') { event.preventDefault(); finish(true); }
      else if (event.key === 'Escape') { event.preventDefault(); finish(false); }
    });
    input.addEventListener('blur', function () { finish(true); });
    // 在输入框里点击，不要触发打开文件或折叠文件夹
    input.addEventListener('click', function (event) { event.preventDefault(); event.stopPropagation(); });
    input.addEventListener('dblclick', function (event) { event.stopPropagation(); });
  }

  function enableTreeActions(row, item) {
    row.draggable = true;
    row.addEventListener('dblclick', function (event) {
      event.preventDefault();
      startRename(row, item);
    });
    row.addEventListener('dragstart', function (event) {
      draggedPath = item.path;
      event.dataTransfer.setData(DRAG_TYPE, item.path);
      event.dataTransfer.effectAllowed = 'move';
      row.classList.add('tree-dragging');
    });
    row.addEventListener('dragend', function () {
      draggedPath = null;
      row.classList.remove('tree-dragging');
      clearDropTarget();
    });
  }

  function clearDropTarget() {
    tree.classList.remove('tree-drop-root');
    tree.querySelectorAll('.tree-drop-target').forEach(function (el) { el.classList.remove('tree-drop-target'); });
  }

  // 放下的位置：鼠标所在的文件夹，放在文件上算它所在的文件夹，其他地方算根目录
  function dropFolderAt(target) {
    var details = target.closest('details');
    return details ? details.dataset.path : '';
  }

  function canDropInto(folder) {
    if (draggedPath === null || parentOf(draggedPath) === folder) return false;
    return folder !== draggedPath && folder.indexOf(draggedPath + '/') !== 0; // 文件夹不能放进自己里面
  }

  tree.addEventListener('dragover', function (event) {
    var folder = dropFolderAt(event.target);
    clearDropTarget();
    if (!canDropInto(folder)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
    if (folder) event.target.closest('details').classList.add('tree-drop-target');
    else tree.classList.add('tree-drop-root');
  });
  tree.addEventListener('dragleave', function (event) {
    if (!tree.contains(event.relatedTarget)) clearDropTarget();
  });
  tree.addEventListener('drop', function (event) {
    var folder = dropFolderAt(event.target);
    var from = draggedPath;
    clearDropTarget();
    if (!canDropInto(folder)) return;
    event.preventDefault();
    movePath(from, joinPath(folder, from.split('/').pop()), folder);
  });

  function markActive() {
    tree.querySelectorAll('.tree-file').forEach(function (button) {
      var active = !!current && button.dataset.path === current.path;
      button.classList.toggle('active', active);
      if (active) {
        for (var el = button.parentElement; el && el !== tree; el = el.parentElement) {
          if (el.tagName === 'DETAILS') el.open = true;
        }
      }
    });
  }

  function loadTree() {
    return request('/api/tree?root=' + encodeURIComponent(root)).then(function (data) {
      var open = {};
      var hasPrevious = !!tree.firstChild;
      tree.querySelectorAll('details').forEach(function (d) { open[d.dataset.path] = d.open; });
      tree.textContent = '';
      var rootLabel = document.createElement('div');
      rootLabel.className = 'tree-root';
      rootLabel.textContent = data.name;
      rootLabel.title = data.root;
      tree.appendChild(rootLabel);
      if (data.truncated) {
        var note = document.createElement('div');
        note.className = 'tree-note';
        note.textContent = 'This folder has too many items, so only some are shown.';
        tree.appendChild(note);
      }
      if (!data.tree.length) {
        var empty = document.createElement('div');
        empty.className = 'tree-empty';
        empty.textContent = 'No Markdown files yet. Use New File above to create one.';
        tree.appendChild(empty);
      }
      renderTree(data.tree, tree);
      tree.querySelectorAll('details').forEach(function (d) {
        d.open = hasPrevious ? !!open[d.dataset.path] : true; // 刚打开文件夹时全部展开
      });
      markActive();
      return data;
    });
  }

  // ---------- 删除文件 ----------
  var deleteButton = document.getElementById('delete-file');
  deleteButton.hidden = false;

  function closeCurrentFile() {
    current = null;
    saved = '';
    previewSeq++; // 丢弃还没回来的预览结果
    clearTimeout(saveTimer);
    clearTimeout(previewTimer);
    cm.swapDoc(CodeMirror.Doc('', 'markdown-editor'));
    cm.setOption('readOnly', true);
    deleteButton.disabled = true;
    document.body.classList.add('no-file');
    document.getElementById('toc').hidden = true;
    previewBody.textContent = '';
    previewError.hidden = true;
    filePath.textContent = 'Select a file on the left';
    document.title = 'Markdown Editor';
    history.replaceState(null, '', location.search);
  }

  deleteButton.addEventListener('click', function () {
    if (!current) return;
    var path = current.path;
    if (!window.confirm('Move "' + path + '" to the Recycle Bin?')) return;
    clearTimeout(saveTimer); // 文件要删了，不用再保存，否则可能把它重新写回去
    (saving || Promise.resolve()).then(function () {
      return request('/api/delete', { root: root, path: path });
    }).then(function () {
      if (current && current.path === path) closeCurrentFile();
      showStatus('Moved to the Recycle Bin');
      return loadTree();
    }).catch(function (err) { showStatus(err.message, true); });
  });

  // ---------- 粘贴图片 ----------
  function readBase64(file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () { resolve(reader.result.split(',')[1]); };
      reader.onerror = function () { reject(new Error('Could not read the image')); };
      reader.readAsDataURL(file);
    });
  }

  function pasteImage(file) {
    var path = current.path;
    var doc = cm.getDoc();
    doc.replaceSelection('');
    var place = doc.setBookmark(doc.getCursor(), { insertLeft: true }); // 上传期间继续打字，图片也插在粘贴的位置
    showStatus('Saving image…');
    return readBase64(file).then(function (data) {
      return request('/api/image', { root: root, path: path, type: file.type, data: data });
    }).then(function (saved) {
      var position = place.find();
      place.clear();
      if (!position) throw new Error('Image saved as ' + saved.path + ', but its position is gone');
      doc.replaceRange('![](' + saved.link + ')', position);
      if (current && current.path === path) showStatus('Image saved to ' + saved.path);
    }).catch(function (err) {
      place.clear();
      showStatus('Could not save the image: ' + err.message, true);
    });
  }

  cm.on('paste', function (editor, event) {
    var clipboard = event.clipboardData;
    if (!clipboard || !current) return;
    // 同时有文字时按文字粘贴：从 Excel、Word 复制的内容也带一份图片
    if (Array.prototype.indexOf.call(clipboard.types, 'text/plain') !== -1) return;
    var images = Array.prototype.filter.call(clipboard.files, function (file) {
      return file.type.indexOf('image/') === 0;
    });
    if (!images.length) return;
    event.preventDefault();
    images.reduce(function (done, file) {
      return done.then(function () { return pasteImage(file); });
    }, Promise.resolve());
  });

  // ---------- 打开和保存 ----------
  function showFile(data) {
    current = { path: data.path, mtime: data.mtime };
    saved = data.content;
    document.body.classList.remove('no-file');
    cm.setOption('readOnly', false);
    deleteButton.disabled = false;
    cm.swapDoc(CodeMirror.Doc(data.content, 'markdown-editor')); // 换一个文档，撤销不会跨文件
    filePath.textContent = data.path;
    document.title = data.path.split('/').pop() + ' · Markdown Editor';
    showStatus('Saved');
    if (location.hash.slice(1) !== encodeURIComponent(data.path)) {
      history.replaceState(null, '', location.search + '#' + encodeURIComponent(data.path));
    }
    markActive();
    renderPreview();
    if (!renaming) cm.focus(); // 双击重命名时，不要把焦点从输入框抢走
  }

  function openFile(path) {
    if (current && current.path === path) return Promise.resolve(); // 重新加载会清空撤销记录
    opening = opening.then(function () {
      return saveNow();
    }).then(function (ok) {
      if (!ok) return; // 没保存成功就不切换，否则改动会丢
      return request(fileUrl(path)).then(showFile);
    }).catch(function (err) { showStatus(err.message, true); });
    return opening;
  }

  function reloadFromDisk() {
    return request(fileUrl(current.path)).then(function (data) {
      var position = cm.getCursor();
      var scroll = cm.getScrollInfo();
      showFile(data);
      cm.setCursor(position);
      cm.scrollTo(scroll.left, scroll.top);
    });
  }

  function writeFile(force) {
    var content = cm.getValue();
    var path = current.path;
    showStatus('Saving…');
    return request('/api/save', { root: root, path: path, content: content, mtime: current.mtime, force: !!force })
      .then(function (data) {
        if (!current || current.path !== path) return true;
        current.mtime = data.mtime;
        saved = content;
        showStatus(isDirty() ? 'Unsaved changes' : 'Saved');
        return true;
      })
      .catch(function (err) {
        if (err.status !== 409) {
          showStatus('Could not save: ' + err.message, true);
          return false;
        }
        var overwrite = window.confirm(
          'This file was changed or deleted outside the editor.\n\nOK: overwrite it with what is in the editor\nCancel: discard your edits and reload the file'
        );
        if (overwrite) return writeFile(true);
        return reloadFromDisk().then(function () { return true; }, function (reloadError) {
          showStatus(reloadError.message, true);
          return false;
        });
      });
  }

  // 返回的 Promise 结果表示内容是否已经安全落盘
  function saveNow() {
    clearTimeout(saveTimer);
    if (saving) {
      return saving.then(function () { return saveNow(); });
    }
    if (!isDirty()) return Promise.resolve(true);
    saving = writeFile(false).then(function (ok) {
      saving = null;
      return ok;
    }, function () {
      saving = null;
      showStatus('Could not save', true);
      return false;
    });
    return saving;
  }

  // ---------- 预览 ----------
  function renderPreview() {
    if (!current) return;
    var seq = ++previewSeq;
    request('/api/render', { root: root, path: current.path, content: cm.getValue() }).then(function (data) {
      if (seq !== previewSeq) return;
      previewError.hidden = !data.warning;
      previewError.textContent = data.warning;
      document.getElementById('preview-head').hidden = !(data.title || data.date || data.tags.length);
      document.getElementById('preview-title').hidden = !data.title;
      document.getElementById('preview-title').textContent = data.title;
      document.getElementById('preview-date').textContent = data.date;
      var tags = document.getElementById('preview-tags');
      tags.textContent = '';
      data.tags.forEach(function (tag) {
        var el = document.createElement('span');
        el.className = 'tag';
        el.textContent = tag;
        tags.appendChild(el);
      });
      previewBody.innerHTML = data.html;
      if (window.renderMathInElement) {
        renderMathInElement(previewBody, {
          delimiters: [
            { left: '\\(', right: '\\)', display: false },
            { left: '\\[', right: '\\]', display: true }
          ],
          throwOnError: false
        });
      }
      buildToc();
      syncScroll();
      updateTocActive();
    }).catch(function (err) {
      if (seq !== previewSeq) return;
      previewError.hidden = false;
      previewError.textContent = 'Could not render the preview: ' + err.message;
    });
  }

  // ---------- 预览目录 ----------
  var TOC_MIN_HEADINGS = 2; // 标题太少时不需要目录
  var toc = document.getElementById('toc');
  var tocRail = document.getElementById('toc-rail');
  var tocList = document.getElementById('toc-list');
  var tocPin = document.getElementById('toc-pin');
  var tocHeadings = [];
  var tocClicked = null; // 刚点击的章节

  function setTocPinned(pinned) {
    toc.classList.toggle('pinned', pinned);
    toc.parentElement.classList.toggle('toc-pinned', pinned);
    tocPin.setAttribute('aria-pressed', String(pinned));
    tocPin.title = pinned ? 'Unpin table of contents' : 'Pin table of contents';
    tocPin.setAttribute('aria-label', tocPin.title);
  }

  function toggleTocPinned() {
    var pinned = !toc.classList.contains('pinned');
    localStorage.setItem('editor-toc-pinned', pinned ? '1' : '0');
    setTocPinned(pinned);
    syncScroll(); // 固定后正文宽度可能变化
    updateTocActive();
  }

  // 让列表里的当前项保持可见，只滚动列表自身，不影响页面
  function keepInView(list, item) {
    var listBox = list.getBoundingClientRect();
    var itemBox = item.getBoundingClientRect();
    if (itemBox.top < listBox.top) list.scrollTop -= listBox.top - itemBox.top;
    else if (itemBox.bottom > listBox.bottom) list.scrollTop += itemBox.bottom - listBox.bottom;
  }

  function jumpToHeading(heading) {
    // 编辑区也一起跳过去，否则下次滚动编辑区时，预览又会被拉回原来的位置
    var line = heading.dataset.line;
    if (line !== undefined && !document.body.classList.contains('mode-preview')) {
      cm.scrollTo(null, cm.heightAtLine(+line, 'local'));
    }
    previewPane.scrollTop += heading.getBoundingClientRect().top - previewPane.getBoundingClientRect().top;
    // 靠后的标题滚不到顶部，所以点击后直接高亮所点的章节，直到再次滚动
    tocClicked = { heading: heading, scrollTop: previewPane.scrollTop };
    updateTocActive();
  }

  function buildToc() {
    var scrollTop = tocList.scrollTop; // 打字时目录会重建，不要让它跳回顶部
    tocHeadings = Array.prototype.slice.call(previewBody.querySelectorAll('h1, h2, h3'));
    var top = Math.min.apply(null, tocHeadings.map(function (h) { return +h.tagName.charAt(1); }));
    tocList.textContent = '';
    tocRail.textContent = '';
    tocHeadings.forEach(function (heading) {
      var level = +heading.tagName.charAt(1) - top;
      var dash = document.createElement('span');
      dash.className = 'toc-dash toc-level-' + level;
      tocRail.appendChild(dash);
      var item = document.createElement('button');
      item.type = 'button';
      item.className = 'toc-item toc-level-' + level;
      item.innerHTML = heading.innerHTML; // 保留渲染好的公式和代码
      item.querySelectorAll('sup').forEach(function (el) { el.remove(); }); // 去掉脚注编号
      item.querySelectorAll('a').forEach(function (el) { // 按钮里不能再放链接
        var text = document.createElement('span');
        text.innerHTML = el.innerHTML;
        el.replaceWith(text);
      });
      item.addEventListener('click', function () { jumpToHeading(heading); });
      tocList.appendChild(item);
    });
    tocList.scrollTop = scrollTop;
    toc.hidden = tocHeadings.length < TOC_MIN_HEADINGS;
  }

  function updateTocActive() {
    if (toc.hidden) return;
    var limit = previewPane.getBoundingClientRect().top + 40;
    var current = 0; // 还没读到第一个标题时，也高亮第一个
    tocHeadings.forEach(function (heading, i) {
      if (heading.getBoundingClientRect().top <= limit) current = i;
    });
    // 滚到底时，靠后的标题到不了顶部，这时高亮最后一个
    if (previewPane.scrollTop > 0 && previewPane.scrollTop + previewPane.clientHeight >= previewPane.scrollHeight - 2) {
      current = tocHeadings.length - 1;
    }
    if (tocClicked) {
      var index = tocHeadings.indexOf(tocClicked.heading);
      if (index !== -1 && Math.abs(previewPane.scrollTop - tocClicked.scrollTop) < 2) current = index;
      else tocClicked = null; // 已经滚动过，或者预览重新渲染了
    }
    [tocList, tocRail].forEach(function (list) {
      Array.prototype.forEach.call(list.children, function (item, i) {
        item.classList.toggle('active', i === current);
      });
      if (list.children[current]) keepInView(list, list.children[current]);
    });
  }

  tocPin.addEventListener('click', toggleTocPinned);
  tocRail.addEventListener('click', toggleTocPinned); // 点缩略条也能固定，触屏没有悬浮时靠它展开
  previewPane.addEventListener('scroll', updateTocActive, { passive: true });
  setTocPinned(localStorage.getItem('editor-toc-pinned') === '1');

  // 让预览跟随编辑区：找到编辑区顶部所在的内容块，按比例滚到预览里对应的位置
  function syncScroll() {
    if (!current) return;
    var info = cm.getScrollInfo();
    if (info.top + info.clientHeight >= info.height - 2) {
      previewPane.scrollTop = previewPane.scrollHeight;
      return;
    }
    var line = cm.lineAtHeight(info.top, 'local');
    var blocks = previewBody.querySelectorAll('[data-line]');
    var before = null;
    var after = null;
    for (var i = 0; i < blocks.length; i++) {
      if (+blocks[i].dataset.line <= line) before = blocks[i];
      else { after = blocks[i]; break; }
    }
    var offsetOf = function (el) {
      return el.getBoundingClientRect().top - previewPane.getBoundingClientRect().top + previewPane.scrollTop;
    };
    if (!before) {
      previewPane.scrollTop = 0;
      return;
    }
    var start = cm.heightAtLine(+before.dataset.line, 'local');
    var end = after ? cm.heightAtLine(+after.dataset.line, 'local') : info.height;
    var targetEnd = after ? offsetOf(after) : previewPane.scrollHeight;
    var ratio = end > start ? (info.top - start) / (end - start) : 0;
    previewPane.scrollTop = offsetOf(before) + ratio * (targetEnd - offsetOf(before));
  }

  // ---------- 事件 ----------
  cm.on('change', function () {
    if (!current) return;
    clearTimeout(previewTimer);
    previewTimer = setTimeout(renderPreview, PREVIEW_DELAY);
    clearTimeout(saveTimer);
    if (isDirty()) {
      showStatus('Unsaved changes');
      saveTimer = setTimeout(saveNow, AUTOSAVE_DELAY);
    } else {
      showStatus('Saved');
    }
  });
  cm.on('scroll', syncScroll);

  // 把预览里的相对链接解析成打开文件夹内的路径
  function resolveLink(href) {
    var parts = current.path.split('/').slice(0, -1);
    var clean = decodeURIComponent(href.split('#')[0]);
    var ok = true;
    clean.split('/').forEach(function (part) {
      if (part === '..') {
        if (!parts.length) ok = false;
        parts.pop();
      } else if (part && part !== '.') {
        parts.push(part);
      }
    });
    return ok ? parts.join('/') : null;
  }

  previewBody.addEventListener('click', function (event) {
    var link = event.target.closest('a');
    if (!link) return;
    event.preventDefault(); // 预览里的链接不能把编辑器页面跳走
    var href = link.getAttribute('href') || '';
    if (href.charAt(0) === '#') {
      var target = document.getElementById(decodeURIComponent(href.slice(1)));
      if (target) target.scrollIntoView();
    } else if (/^https?:/i.test(href)) {
      window.open(href, '_blank', 'noopener');
    } else if (/\.(md|markdown)(#.*)?$/i.test(href)) {
      var path = resolveLink(href);
      if (path) openFile(path); // 点笔记之间的链接，直接打开那个文件
    }
  });

  document.querySelectorAll('.mode-switch button').forEach(function (button) {
    button.addEventListener('click', function () {
      document.body.className = document.body.className.replace(/mode-\w+/, 'mode-' + button.dataset.mode);
      localStorage.setItem('editor-mode', button.dataset.mode);
      cm.refresh();
      syncScroll();
    });
  });
  var savedMode = localStorage.getItem('editor-mode');
  if (savedMode) document.body.className = document.body.className.replace(/mode-\w+/, 'mode-' + savedMode);

  // 折叠左边的文件夹栏，状态会记住
  var treeToggle = document.getElementById('toggle-tree');
  function setTreeCollapsed(collapsed) {
    document.body.classList.toggle('tree-collapsed', collapsed);
    treeToggle.textContent = collapsed ? '›' : '‹';
    treeToggle.title = collapsed ? 'Expand sidebar' : 'Collapse sidebar';
    treeToggle.setAttribute('aria-label', treeToggle.title);
    treeToggle.setAttribute('aria-expanded', String(!collapsed));
    cm.refresh(); // 编辑区宽度变了，要重新计算换行
    syncScroll();
  }
  treeToggle.hidden = false;
  treeToggle.addEventListener('click', function () {
    var collapsed = !document.body.classList.contains('tree-collapsed');
    localStorage.setItem('editor-tree-collapsed', collapsed ? '1' : '0');
    setTreeCollapsed(collapsed);
  });
  setTreeCollapsed(localStorage.getItem('editor-tree-collapsed') === '1');

  var newFileButton = document.getElementById('new-file');
  newFileButton.hidden = false;
  newFileButton.addEventListener('click', function () {
    var folder = current ? current.path.split('/').slice(0, -1).join('/') : '';
    var path = window.prompt('File path, relative to the open folder (missing folders are created):', (folder ? folder + '/' : '') + 'new-file.md');
    if (!path) return;
    saveNow().then(function (ok) {
      if (!ok) return;
      return request('/api/new', { root: root, path: path }).then(function (data) {
        return loadTree().then(function () { return openFile(data.path); });
      });
    }).catch(function (err) { showStatus(err.message, true); });
  });

  // 切回这个窗口时，看看文件有没有被别的程序（比如 git 或 VS Code）改过
  window.addEventListener('focus', function () {
    if (!renaming) loadTree().catch(function () {}); // 重建文件树会打断正在进行的重命名
    if (!current || isDirty() || saving) return;
    request(fileUrl(current.path)).then(function (data) {
      if (data.mtime !== current.mtime && !isDirty()) reloadFromDisk();
    }).catch(function () {});
  });

  window.addEventListener('beforeunload', function (event) {
    if (isDirty()) {
      saveNow();
      event.preventDefault();
      event.returnValue = '';
    }
  });

  // ---------- 启动 ----------
  filePath.textContent = 'Select a file on the left';
  loadTree().then(function (data) {
    filePath.textContent = 'Select a file on the left';
    root = data.root; // 用服务端规范化后的路径
    var path = decodeURIComponent(location.hash.slice(1));
    if (path) openFile(path);
  }).catch(function (err) {
    document.getElementById('workspace').hidden = true;
    showWelcome(err.message);
  });
})();
