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

  var statusTimer = null;

  function keepStatus(text, isError) { // 一直显示到下一条消息：进行中、未保存和错误
    clearTimeout(statusTimer);
    status.textContent = text;
    status.classList.toggle('error', !!isError);
  }

  function showStatus(text, isError) { // 操作结果几秒后自动消失；错误不消失，免得没看到
    keepStatus(text, isError);
    if (!isError) statusTimer = setTimeout(function () { status.textContent = ''; }, 3000);
  }

  function isDirty() {
    return !!current && cm.getValue() !== saved;
  }

  function folderUrl(folder) {
    return '/?root=' + encodeURIComponent(folder);
  }

  // ---------- 设置 ----------
  var DEFAULT_PREFERENCES = { font_size: 14, image_folder: 'fig', image_save_base: 'current' };
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
    document.getElementById('pref-image-base').value = prefs.image_save_base;
    showImagePathHint();
  }

  function preferencesInDialog() {
    return {
      font_size: +prefSize.value,
      image_folder: document.getElementById('pref-image-folder').value,
      image_save_base: document.getElementById('pref-image-base').value
    };
  }

  function showImagePathHint() { // 让用户直接看到图片会存到哪里
    var folder = document.getElementById('pref-image-folder').value.trim().replace(/\\/g, '/').replace(/^\/+|\/+$/g, '');
    var inFileFolder = document.getElementById('pref-image-base').value === 'current';
    document.getElementById('pref-image-hint').textContent =
      'Example: ' + (inFileFolder ? 'notes/' : '') + folder + '/image.png' +
      (inFileFolder ? ' for a file in notes/' : ', wherever the Markdown file is');
  }

  function previewPreferences() { // 调节时编辑区实时变化，保存后才写入文件
    var prefs = preferencesInDialog();
    document.getElementById('pref-font-size-value').textContent = prefs.font_size + ' px';
    showImagePathHint();
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
        summary.dataset.path = item.path;
        summary.addEventListener('click', function (event) {
          if (isMultiSelectClick(event)) {
            event.preventDefault(); // 不要折叠文件夹
            toggleSelected(item.path);
          } else {
            selectOnly(item.path);
          }
        });
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
        button.addEventListener('click', function (event) {
          if (isMultiSelectClick(event)) toggleSelected(item.path);
          else openFile(item.path);
        });
        enableTreeActions(button, item);
        parent.appendChild(button);
      }
    });
  }

  // ---------- 移动和重命名 ----------
  var DRAG_TYPE = 'application/x-markdown-editor-path'; // 不用 text/plain，否则拖到编辑区会把路径插进正文
  var draggedPaths = null; // 正在拖动的文件和文件夹
  var lastMoveError = '';
  var RENAME_DOUBLE_CLICK_MS = 300; // 两次点击间隔不超过这个时间，才算双击重命名
  var clicks = { path: null, previous: -Infinity, last: -Infinity }; // 不存在行上：切回窗口时文件树会重新渲染
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
        if (status.classList.contains('error')) keepStatus(''); // 这次成功了，之前的错误不该还留着
        if (affectsCurrent) {
          current.path = data.path + current.path.slice(from.length);
          filePath.textContent = current.path;
          document.title = current.path.split('/').pop() + ' · Markdown Editor';
          history.replaceState(null, '', location.search + '#' + encodeURIComponent(current.path));
          renderPreview(); // 图片的相对路径变了
        }
        selection = new Set(Array.from(selection, function (path) {
          return isInside(path, from) ? data.path + path.slice(from.length) : path;
        }));
        return loadTree().then(function () {
          if (folderToShow !== undefined) openFolders(folderToShow);
          return data.path;
        });
      });
    }).catch(function (err) {
      lastMoveError = err.message;
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
    row.addEventListener('click', function (event) {
      var samePath = clicks.path === item.path;
      clicks = { path: item.path, previous: samePath ? clicks.last : -Infinity, last: event.timeStamp };
    });
    row.addEventListener('dblclick', function (event) {
      event.preventDefault();
      // 系统的双击判定比较宽松（Windows 默认约 500ms），连续点文件夹时容易误触发重命名
      if (clicks.last - clicks.previous > RENAME_DOUBLE_CLICK_MS || isMultiSelectClick(event)) return;
      startRename(row, item);
    });
    row.addEventListener('dragstart', function (event) {
      // 拖动选中的项时一起移动，拖动没选中的项时只移动它自己
      draggedPaths = selection.has(item.path) ? topLevelPaths(selection) : [item.path];
      event.dataTransfer.setData(DRAG_TYPE, item.path);
      event.dataTransfer.effectAllowed = 'move';
      treeRows().forEach(function (other) {
        if (draggedPaths.indexOf(other.dataset.path) !== -1) other.classList.add('tree-dragging');
      });
    });
    row.addEventListener('dragend', function () {
      draggedPaths = null;
      tree.querySelectorAll('.tree-dragging').forEach(function (other) { other.classList.remove('tree-dragging'); });
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
    if (draggedPaths === null) return false;
    var movesSomething = draggedPaths.some(function (path) { return parentOf(path) !== folder; });
    var intoItself = draggedPaths.some(function (path) { return isInside(folder, path); }); // 文件夹不能放进自己里面
    return movesSomething && !intoItself;
  }

  function moveMany(paths, folder) {
    var moving = paths.filter(function (path) { return parentOf(path) !== folder; });
    var moved = 0;
    lastMoveError = '';
    return moving.reduce(function (done, from) {
      return done.then(function () {
        return movePath(from, joinPath(folder, from.split('/').pop()), folder);
      }).then(function (path) {
        if (path !== null) moved++;
      });
    }, Promise.resolve()).then(function () {
      if (moved === moving.length) showStatus('Moved ' + moved + (moved === 1 ? ' item' : ' items'));
      else if (moving.length > 1) showStatus('Moved ' + moved + ' of ' + moving.length + ' items: ' + lastMoveError, true);
      // 只有一项且失败时，错误就是 movePath 显示的那条
    });
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
    var paths = draggedPaths;
    var allowed = canDropInto(folder);
    clearDropTarget();
    if (!allowed) return;
    event.preventDefault();
    moveMany(paths, folder);
  });

  // ---------- 选中 ----------
  // 选中的文件和文件夹。单击文件夹选中它，Ctrl+点击或框选可以选中多个。没选中时，垃圾桶删除当前打开的文件
  var selection = new Set();

  function isInside(path, folder) { // path 就是 folder，或者在 folder 里面
    return path === folder || path.indexOf(folder + '/') === 0;
  }

  function isMultiSelectClick(event) {
    return event.ctrlKey || event.metaKey;
  }

  function treeRows() {
    return tree.querySelectorAll('summary, .tree-file');
  }

  function isFolderPath(path) {
    return !!tree.querySelector('details[data-path="' + CSS.escape(path) + '"]');
  }

  // 文件夹和它里面的文件都选中时，只操作文件夹
  function topLevelPaths(paths) {
    var all = Array.from(paths);
    return all.filter(function (path) {
      return !all.some(function (other) { return other !== path && isInside(path, other); });
    });
  }

  function selectOnly(path) {
    selection = new Set([path]);
    markActive();
  }

  function toggleSelected(path) {
    if (selection.has(path)) selection.delete(path);
    else selection.add(path);
    markActive();
  }

  function clearSelection() {
    selection = new Set();
    markActive();
  }

  // 新建文件和文件夹的默认位置：选中的文件夹，否则是当前文件所在的文件夹
  function newItemParent() {
    var only = selection.size === 1 ? Array.from(selection)[0] : null;
    if (only !== null && isFolderPath(only)) return only;
    return current ? parentOf(current.path) : '';
  }

  function updateDeleteButton() {
    var label = 'Select a file or folder to delete';
    if (selection.size > 1) {
      label = 'Move ' + topLevelPaths(selection).length + ' selected items to the Recycle Bin';
    } else {
      var target = selection.size === 1 ? Array.from(selection)[0] : current && current.path;
      if (target) label = 'Move "' + target + '" to the Recycle Bin';
    }
    deleteButton.disabled = selection.size === 0 && !current;
    deleteButton.title = label;
    deleteButton.setAttribute('aria-label', label);
  }

  function markActive() {
    var exists = new Set();
    treeRows().forEach(function (row) {
      var path = row.dataset.path;
      exists.add(path);
      row.classList.toggle('tree-selected', selection.has(path));
      if (row.tagName === 'BUTTON') row.classList.toggle('active', !!current && path === current.path);
    });
    selection.forEach(function (path) { // 比如在资源管理器里被删了
      if (!exists.has(path)) selection.delete(path);
    });
    updateDeleteButton();
  }

  // ---------- 框选 ----------
  // 文件行本身可以拖动移动，所以框选要从空白处开始
  var marquee = null;
  var ignoreNextTreeClick = false;

  function rowIsShown(row) { // 折叠的文件夹里的项看不见，不参与框选
    var container = row.tagName === 'SUMMARY' ? row.parentElement.parentElement : row.parentElement;
    return !container.closest('details:not([open])');
  }

  function updateMarquee() {
    var box = tree.getBoundingClientRect();
    var currentX = marquee.clientX - box.left + tree.scrollLeft;
    var currentY = marquee.clientY - box.top + tree.scrollTop;
    var left = Math.min(marquee.startX, currentX);
    var top = Math.min(marquee.startY, currentY);
    var width = Math.abs(currentX - marquee.startX);
    var height = Math.abs(currentY - marquee.startY);
    if (!marquee.element.parentElement) tree.appendChild(marquee.element); // 文件树可能刚重新渲染过
    marquee.element.style.left = left + 'px';
    marquee.element.style.top = top + 'px';
    marquee.element.style.width = width + 'px';
    marquee.element.style.height = height + 'px';

    var next = new Set(marquee.base);
    var viewLeft = left + box.left - tree.scrollLeft;
    var viewTop = top + box.top - tree.scrollTop;
    treeRows().forEach(function (row) {
      if (!rowIsShown(row)) return;
      var rect = row.getBoundingClientRect();
      var hit = rect.left < viewLeft + width && rect.right > viewLeft && rect.top < viewTop + height && rect.bottom > viewTop;
      if (hit) next.add(row.dataset.path);
    });
    selection = next;
    markActive();
  }

  function endMarquee() {
    document.removeEventListener('mousemove', onMarqueeMove);
    document.removeEventListener('mouseup', endMarquee);
    clearInterval(marquee.scrollTimer);
    marquee.element.remove();
    ignoreNextTreeClick = marquee.moved; // 框选结束时的 click 不算“点空白处”
    marquee = null;
    setTimeout(function () { ignoreNextTreeClick = false; }, 0);
  }

  function onMarqueeMove(event) {
    marquee.clientX = event.clientX;
    marquee.clientY = event.clientY;
    if (!marquee.moved) {
      var box = tree.getBoundingClientRect();
      var distance = Math.abs(event.clientX - box.left + tree.scrollLeft - marquee.startX) +
        Math.abs(event.clientY - box.top + tree.scrollTop - marquee.startY);
      if (distance < 4) return; // 手抖不算框选
      marquee.moved = true;
    }
    updateMarquee();
  }

  tree.addEventListener('mousedown', function (event) {
    if (event.button !== 0 || event.target.closest('summary, button, input')) return;
    var box = tree.getBoundingClientRect();
    if (event.clientX >= box.left + tree.clientWidth || event.clientY >= box.top + tree.clientHeight) return; // 点的是滚动条
    event.preventDefault(); // 不要选中文字
    var element = document.createElement('div');
    element.className = 'tree-marquee';
    marquee = {
      element: element,
      startX: event.clientX - box.left + tree.scrollLeft,
      startY: event.clientY - box.top + tree.scrollTop,
      clientX: event.clientX,
      clientY: event.clientY,
      base: isMultiSelectClick(event) ? new Set(selection) : new Set(),
      moved: false,
      scrollTimer: setInterval(function () { // 拖到上下边缘时自动滚动
        if (!marquee.moved) return;
        var view = tree.getBoundingClientRect();
        if (marquee.clientY < view.top + 24) tree.scrollTop -= 12;
        else if (marquee.clientY > view.bottom - 24) tree.scrollTop += 12;
        else return;
        updateMarquee();
      }, 30)
    };
    document.addEventListener('mousemove', onMarqueeMove);
    document.addEventListener('mouseup', endMarquee);
  });

  // 点文件树的空白处取消选中
  tree.addEventListener('click', function (event) {
    if (ignoreNextTreeClick || isMultiSelectClick(event)) return;
    if (!event.target.closest('summary, .tree-file')) clearSelection();
  });

  var collapseButton = document.createElement('button'); // 文件树每次重新渲染时都放回根目录那一行
  collapseButton.type = 'button';
  collapseButton.className = 'tree-collapse';
  collapseButton.textContent = '‹';
  collapseButton.title = 'Collapse sidebar';
  collapseButton.setAttribute('aria-label', 'Collapse sidebar');
  collapseButton.setAttribute('aria-controls', 'file-tree');

  function loadTree() {
    return request('/api/tree?root=' + encodeURIComponent(root)).then(function (data) {
      var open = {};
      var hasPrevious = !!tree.firstChild;
      tree.querySelectorAll('details').forEach(function (d) { open[d.dataset.path] = d.open; });
      tree.textContent = '';
      var rootLabel = document.createElement('div');
      rootLabel.className = 'tree-root';
      var rootName = document.createElement('span');
      rootName.className = 'tree-root-name';
      rootName.textContent = data.name;
      rootName.title = data.root;
      rootLabel.appendChild(rootName);
      rootLabel.appendChild(collapseButton);
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
    updateDeleteButton();
    exportToggle.disabled = true;
    closeExportMenu();
    openFindButton.disabled = true;
    closeFind();
    document.body.classList.add('no-file');
    document.getElementById('toc').hidden = true;
    previewBody.textContent = '';
    previewError.hidden = true;
    filePath.textContent = 'Select a file on the left';
    document.title = 'Markdown Editor';
    history.replaceState(null, '', location.search);
  }

  function deleteMessage(paths, fileCounts) {
    if (paths.length === 1) {
      var path = paths[0];
      var files = fileCounts[path];
      if (files === null) return 'Move "' + path + '" to the Recycle Bin?';
      if (files === 0) return 'Move the empty folder "' + path + '" to the Recycle Bin?';
      return 'Move folder "' + path + '" and ' + files + (files === 1 ? ' file' : ' files') + ' to the Recycle Bin?';
    }
    var lines = paths.slice(0, 10).map(function (item) {
      var count = fileCounts[item];
      return '  ' + item + (count === null ? '' : ' (folder, ' + count + (count === 1 ? ' file)' : ' files)'));
    });
    if (paths.length > 10) lines.push('  ... and ' + (paths.length - 10) + ' more');
    return 'Move these ' + paths.length + ' items to the Recycle Bin?\n\n' + lines.join('\n');
  }

  function deleteTargets(paths, fileCounts) {
    var inTargets = function (path) {
      return paths.some(function (target) { return isInside(path, target); });
    };
    var affectsCurrent = !!current && inTargets(current.path);
    var message = deleteMessage(paths, fileCounts);
    if (affectsCurrent && isDirty()) message += '\n\nUnsaved changes in "' + current.path + '" will be lost.';
    if (!window.confirm(message)) return Promise.resolve();
    if (affectsCurrent) {
      clearTimeout(saveTimer); // 要删了，不用再保存，否则可能把它重新写回去
      cm.setOption('readOnly', true);
    }
    var deleted = [];
    var firstError = '';
    return paths.reduce(function (done, path) {
      return done.then(function () {
        return request('/api/delete', { root: root, path: path });
      }).then(function () {
        deleted.push(path);
      }).catch(function (err) {
        firstError = firstError || err.message;
      });
    }, saving || Promise.resolve()).then(function () {
      selection.forEach(function (path) {
        if (deleted.some(function (target) { return isInside(path, target); })) selection.delete(path);
      });
      if (affectsCurrent) {
        if (deleted.some(function (target) { return isInside(current.path, target); })) closeCurrentFile();
        else cm.setOption('readOnly', false); // 没删成，继续编辑
      }
      if (firstError) {
        showStatus(paths.length === 1 ? firstError : 'Moved ' + deleted.length + ' of ' + paths.length + ' items to the Recycle Bin: ' + firstError, true);
      } else {
        showStatus(paths.length === 1 ? 'Moved to the Recycle Bin' : 'Moved ' + paths.length + ' items to the Recycle Bin');
      }
      return loadTree();
    });
  }

  deleteButton.addEventListener('click', function () {
    opening.then(function () { // 等进行中的打开完成，才能判断删除会不会影响正在编辑的文件
      var paths = selection.size ? topLevelPaths(selection) : current ? [current.path] : [];
      if (!paths.length) return null;
      var fileCounts = {};
      return Promise.all(paths.map(function (path) {
        fileCounts[path] = null;
        if (!isFolderPath(path)) return null;
        return request('/api/folder-info?root=' + encodeURIComponent(root) + '&path=' + encodeURIComponent(path)).then(function (info) {
          fileCounts[path] = info.files;
        });
      })).then(function () {
        return deleteTargets(paths, fileCounts);
      });
    }).catch(function (err) { showStatus(err.message, true); });
  });

  // ---------- 导出 ----------
  var KATEX_CSS = 'https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css';
  var exportToggle = document.getElementById('export-toggle');
  var exportMenu = document.getElementById('export-menu');
  document.getElementById('export').hidden = false;

  function closeExportMenu() {
    exportMenu.hidden = true;
    exportToggle.setAttribute('aria-expanded', 'false');
  }

  function fileStem(path) {
    return path.split('/').pop().replace(/\.[^.]+$/, '');
  }

  function escapeHtml(text) {
    var el = document.createElement('div');
    el.textContent = text;
    return el.innerHTML;
  }

  function download(name, content, type) {
    var url = URL.createObjectURL(new Blob([content], { type: type }));
    var link = document.createElement('a');
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 10000);
  }

  function blobToDataUrl(blob) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () { resolve(reader.result); };
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  }

  // 把本地图片嵌进文件，导出的文件单独发给别人也能显示。返回没能嵌入的图片数量
  function embedImages(container) {
    var failed = 0;
    var images = Array.prototype.filter.call(container.querySelectorAll('img'), function (img) {
      return (img.getAttribute('src') || '').indexOf('/files?') === 0;
    });
    return Promise.all(images.map(function (img) {
      return fetch(img.getAttribute('src')).then(function (response) {
        if (!response.ok) throw new Error('not found');
        return response.blob();
      }).then(blobToDataUrl).then(function (dataUrl) {
        img.setAttribute('src', dataUrl);
      }).catch(function () { failed++; });
    })).then(function () { return failed; });
  }

  // 导出文件的目录，只用链接和 details，不需要脚本。标题太少时不需要目录
  function exportTocList(body) {
    var headings = Array.prototype.filter.call(body.querySelectorAll('h1, h2, h3'), function (heading) { return heading.id; });
    if (headings.length < TOC_MIN_HEADINGS) return '';
    var top = Math.min.apply(null, headings.map(function (h) { return +h.tagName.charAt(1); }));
    var list = document.createElement('ul');
    headings.forEach(function (heading) {
      var item = document.createElement('li');
      item.className = 'toc-level-' + (+heading.tagName.charAt(1) - top);
      var link = document.createElement('a');
      link.setAttribute('href', '#' + heading.id);
      copyHeadingContent(heading, link);
      item.appendChild(link);
      list.appendChild(item);
    });
    return list.outerHTML;
  }

  // 生成独立的 HTML：内容是当前编辑器里的（包括还没保存的改动），样式都写在文件里
  function buildExportHtml(path, content, forPdf) {
    return Promise.all([
      request('/api/render', { root: root, path: path, content: content }),
      fetch('/document.css').then(function (r) { return r.text(); }),
      fetch('/code.css').then(function (r) { return r.text(); })
    ]).then(function (results) {
      var data = results[0];
      var body = document.createElement('div');
      body.innerHTML = sanitizeHtml(data.html);
      body.querySelectorAll('[data-line]').forEach(function (el) { el.removeAttribute('data-line'); });
      if (window.renderMathInElement) {
        renderMathInElement(body, {
          delimiters: [
            { left: '\\(', right: '\\)', display: false },
            { left: '\\[', right: '\\]', display: true }
          ],
          throwOnError: false
        });
      }
      return embedImages(body).then(function (failedImages) {
        var title = data.title || fileStem(path);
        var tocList = exportTocList(body);
        var toc = tocList ? '<details class="export-toc" open><summary>' + escapeHtml(data.toc_title) + '</summary>' + tocList + '</details>\n' : '';
        if (forPdf) { // PDF 的书签来自标题，只保留三级
          body.querySelectorAll('h4, h5, h6').forEach(function (heading) { heading.setAttribute('role', 'paragraph'); });
        }
        var head = '';
        if (data.show_head && (data.title || data.date || data.tags.length)) {
          head = '<header class="doc-head">' + (data.title ? '<h1>' + escapeHtml(data.title) + '</h1>' : '') +
            '<div class="doc-meta">' + (data.date ? '<time>' + escapeHtml(data.date) + '</time>' : '') +
            '<div class="tags">' + data.tags.map(function (tag) { return '<span class="tag">' + escapeHtml(tag) + '</span>'; }).join('') + '</div>' +
            '</div></header>';
        }
        var html = '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n' +
          '<meta name="viewport" content="width=device-width, initial-scale=1">\n' +
          '<title>' + escapeHtml(title) + '</title>\n' +
          (body.querySelector('.katex') ? '<link rel="stylesheet" href="' + KATEX_CSS + '">\n' : '') +
          '<style>\n' + results[1] + '\n' + results[2] + '\n' + data.template_css + '\n</style>\n</head>\n' +
          '<body class="exported' + (toc ? ' has-toc' : '') + '">\n' + toc + '<article class="doc' + (data.doc_class ? ' ' + data.doc_class : '') + '">\n' + head + '<div class="prose">' + body.innerHTML + '</div>\n</article>\n</body>\n</html>\n';
        return { html: html, failedImages: failedImages };
      });
    });
  }

  // 用隐藏的 iframe 打印，只打印文档，不带编辑器界面。在打印窗口里选“另存为 PDF”
  function printHtml(html, name) {
    return new Promise(function (resolve) {
      var frame = document.createElement('iframe');
      frame.style.cssText = 'position:fixed;right:-10000px;top:0;width:800px;height:600px;border:0';
      frame.setAttribute('aria-hidden', 'true');
      // 沙箱不允许运行脚本：Markdown 里可能带 <script>，而这个 iframe 和编辑器同源，能调用写文件的接口
      frame.setAttribute('sandbox', 'allow-same-origin allow-modals');
      frame.onload = function () {
        var win = frame.contentWindow;
        var pageTitle = document.title;
        var finished = false;
        var done = function () {
          if (finished) return;
          finished = true;
          document.title = pageTitle;
          frame.remove();
          resolve();
        };
        win.document.fonts.ready.then(function () {
          document.title = name; // Chrome 用这个作为默认的 PDF 文件名
          win.focus();
          win.print(); // Chrome 会在这里等打印窗口关闭
          done();
        });
      };
      frame.srcdoc = html;
      document.body.appendChild(frame);
    });
  }

  function exportCurrent(format) {
    if (!current) return;
    var path = current.path;
    var content = cm.getValue();
    var stem = fileStem(path);
    closeExportMenu();
    if (format === 'md') {
      download(path.split('/').pop(), content, 'text/markdown;charset=utf-8');
      showStatus('Exported ' + stem + '.md');
      return;
    }
    keepStatus('Preparing export…');
    buildExportHtml(path, content, format === 'pdf').then(function (result) {
      var note = result.failedImages ? ' (' + result.failedImages + ' image(s) could not be embedded)' : '';
      if (format === 'html') {
        download(stem + '.html', result.html, 'text/html;charset=utf-8');
        showStatus('Exported ' + stem + '.html' + note, !!result.failedImages);
        return null;
      }
      return fetch('/api/pdf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ html: result.html })
      }).then(function (response) {
        if (response.ok) {
          return response.blob().then(function (pdf) {
            download(stem + '.pdf', pdf, 'application/pdf');
            showStatus('Exported ' + stem + '.pdf' + note, !!result.failedImages);
          });
        }
        if (response.status === 501) { // 没有 Chrome 或 Edge，退回打印窗口。这样生成的 PDF 没有书签
          showStatus('Choose “Save as PDF” in the print dialog' + note, !!result.failedImages);
          return printHtml(result.html, stem);
        }
        return response.json().then(function (body) { throw new Error(body.error || 'Request failed'); });
      });
    }).catch(function (err) {
      showStatus('Could not export: ' + err.message, true);
    });
  }

  exportToggle.addEventListener('click', function () {
    exportMenu.hidden = !exportMenu.hidden;
    exportToggle.setAttribute('aria-expanded', String(!exportMenu.hidden));
  });
  exportMenu.addEventListener('click', function (event) {
    var button = event.target.closest('button');
    if (button) exportCurrent(button.dataset.format);
  });
  document.addEventListener('click', function (event) {
    if (!event.target.closest('#export')) closeExportMenu();
  });
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && !exportMenu.hidden) {
      closeExportMenu();
      exportToggle.focus();
    }
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
    keepStatus('Saving image…');
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
    exportToggle.disabled = false;
    openFindButton.disabled = false;
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
    clearSelection(); // 点了文件，垃圾桶就回到删除这个文件
    if (current && current.path === path) return Promise.resolve(); // 重新加载会清空撤销记录
    opening = opening.then(function () {
      return saveNow();
    }).then(function (ok) {
      if (!ok) return; // 没保存成功就不切换，否则改动会丢
      return request(fileUrl(path)).then(function (data) {
        showFile(data);
        previewPane.scrollTop = 0;
        openFolders(parentOf(data.path)); // 只在打开文件时展开它的上级，否则用户没法折叠或展开这些文件夹
      });
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
    keepStatus('Saving…');
    return request('/api/save', { root: root, path: path, content: content, mtime: current.mtime, force: !!force })
      .then(function (data) {
        if (!current || current.path !== path) return true;
        current.mtime = data.mtime;
        saved = content;
        if (isDirty()) keepStatus('Unsaved changes');
        else showStatus('Saved');
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

  // ---------- 清理内容 ----------
  // Markdown 可以直接写 HTML，别人给的文件里可能藏着脚本，所以显示和导出之前都要清理
  var REMOVED_TAGS = 'script, object, embed, applet, base, meta, link, set, animate, animatetransform, animatemotion';
  var URL_ATTRIBUTES = ['href', 'xlink:href', 'src', 'action', 'formaction', 'data', 'poster', 'background', 'ping'];

  function isSafeUrl(tag, attribute, value) {
    var url = value.replace(/[\u0000-\u0020]+/g, '').toLowerCase(); // 浏览器会忽略这些字符，比如 java\nscript:
    if (url.indexOf('data:') === 0) return tag === 'IMG' && attribute === 'src' && url.indexOf('data:image/') === 0;
    return !/^[a-z][a-z0-9+.-]*:/.test(url) || /^(https?|mailto|tel):/.test(url);
  }

  function sanitizeHtml(html) {
    var doc = new DOMParser().parseFromString('<!DOCTYPE html><body>' + html, 'text/html'); // 这样解析不会运行脚本，也不会加载图片
    doc.body.querySelectorAll(REMOVED_TAGS).forEach(function (el) { el.remove(); });
    doc.body.querySelectorAll('*').forEach(function (el) {
      Array.prototype.slice.call(el.attributes).forEach(function (attribute) {
        var name = attribute.name.toLowerCase();
        var unsafe = name.indexOf('on') === 0 || name === 'srcdoc' ||
          (URL_ATTRIBUTES.indexOf(name) !== -1 && !isSafeUrl(el.tagName, name, attribute.value));
        if (unsafe) el.removeAttribute(attribute.name);
      });
    });
    return doc.body.innerHTML;
  }

  // ---------- 预览 ----------
  function renderPreview() {
    if (!current) return;
    var seq = ++previewSeq;
    request('/api/render', { root: root, path: current.path, content: cm.getValue() }).then(function (data) {
      if (seq !== previewSeq) return;
      previewError.hidden = !data.warning;
      previewError.textContent = data.warning;
      document.getElementById('preview-doc').className = 'doc' + (data.doc_class ? ' ' + data.doc_class : '');
      var templateStyle = document.getElementById('template-style');
      if (templateStyle.textContent !== data.template_css) templateStyle.textContent = data.template_css; // 没变时不重算样式，打字时才不卡
      document.getElementById('preview-head').hidden = !data.show_head || !(data.title || data.date || data.tags.length);
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
      previewBody.innerHTML = sanitizeHtml(data.html);
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

  function copyHeadingContent(heading, target) {
    target.innerHTML = heading.innerHTML; // 保留渲染好的公式和代码
    target.querySelectorAll('sup').forEach(function (el) { el.remove(); }); // 去掉脚注编号
    target.querySelectorAll('a').forEach(function (el) { // 目录项里不能再放链接
      var text = document.createElement('span');
      text.innerHTML = el.innerHTML;
      el.replaceWith(text);
    });
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
      copyHeadingContent(heading, item);
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
    if (document.body.classList.contains('mode-preview')) return; // 编辑区隐藏时滚动信息全是 0，会误判成滚到了底
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
      keepStatus('Unsaved changes');
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
      if (target) {
        // 不用 scrollIntoView：它会连外层页面一起滚动，把工具栏推出屏幕
        previewPane.scrollTop += target.getBoundingClientRect().top - previewPane.getBoundingClientRect().top - 16;
      }
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

  // 折叠左边的文件夹栏，状态会记住。收起按钮在侧栏右上角，侧栏收起后左边留一条窄边放展开按钮
  var expandButton = document.getElementById('expand-tree');
  function setTreeCollapsed(collapsed) {
    document.body.classList.toggle('tree-collapsed', collapsed);
    cm.refresh(); // 编辑区宽度变了，要重新计算换行
    syncScroll();
  }
  function toggleTree(collapsed) {
    localStorage.setItem('editor-tree-collapsed', collapsed ? '1' : '0');
    setTreeCollapsed(collapsed);
    (collapsed ? expandButton : collapseButton).focus(); // 刚点的按钮消失了，键盘焦点要跟过去
  }
  expandButton.addEventListener('click', function () { toggleTree(false); });
  collapseButton.addEventListener('click', function (event) {
    event.stopPropagation(); // 收起侧栏不应该取消选中文件夹
    toggleTree(true);
  });
  setTreeCollapsed(localStorage.getItem('editor-tree-collapsed') === '1');

  // ---------- 查找替换 ----------
  var findPanel = document.getElementById('find-panel');
  var findInput = document.getElementById('find-input');
  var replaceInput = document.getElementById('replace-input');
  var findCount = document.getElementById('find-count');
  var replaceRow = document.getElementById('replace-row');
  var findToggleReplace = document.getElementById('find-toggle-replace');
  var findOptions = {
    matchCase: document.getElementById('find-case'),
    wholeWord: document.getElementById('find-word'),
    regex: document.getElementById('find-regex')
  };
  var findMatches = []; // [{from, to, groups}]，from 和 to 是在整篇文字里的位置
  var findMarks = [];
  var currentFindMark = null;

  function optionOn(button) {
    return button.getAttribute('aria-pressed') === 'true';
  }

  function escapeRegExp(text) {
    return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  function buildFindRegExp() {
    var source = optionOn(findOptions.regex) ? findInput.value : escapeRegExp(findInput.value);
    if (optionOn(findOptions.wholeWord)) {
      source = '(?<![\\w\\u0080-\\uFFFF])(?:' + source + ')(?![\\w\\u0080-\\uFFFF])'; // 中文也算单词字符
    }
    return new RegExp(source, optionOn(findOptions.matchCase) ? 'gm' : 'gim');
  }

  function clearFindMarks() {
    findMarks.forEach(function (mark) { mark.clear(); });
    findMarks = [];
    if (currentFindMark) currentFindMark.clear();
    currentFindMark = null;
  }

  function selectionIndexes() {
    return { from: cm.indexFromPos(cm.getCursor('from')), to: cm.indexFromPos(cm.getCursor('to')) };
  }

  function selectedMatchIndex() {
    var selection = selectionIndexes();
    for (var i = 0; i < findMatches.length; i++) {
      if (findMatches[i].from === selection.from && findMatches[i].to === selection.to) return i;
    }
    return -1;
  }

  function updateFindCurrent() { // 根据选区更新“第几个”和当前匹配的高亮
    if (currentFindMark) currentFindMark.clear();
    currentFindMark = null;
    var index = selectedMatchIndex();
    if (index !== -1) {
      currentFindMark = cm.markText(cm.posFromIndex(findMatches[index].from), cm.posFromIndex(findMatches[index].to), { className: 'cm-find-current' });
    }
    if (!findMatches.length) {
      findCount.textContent = findInput.value ? 'No results' : '';
    } else {
      findCount.textContent = index !== -1 ? (index + 1) + ' of ' + findMatches.length : findMatches.length + (findMatches.length === 1 ? ' result' : ' results');
    }
  }

  function refreshFind() { // 重新查找并高亮，不移动选区
    var pattern = null;
    var invalid = false;
    if (findInput.value) {
      try {
        pattern = buildFindRegExp();
      } catch (err) {
        invalid = true;
      }
    }
    findMatches = [];
    if (pattern) {
      var text = cm.getValue();
      var match;
      while ((match = pattern.exec(text))) {
        if (match[0]) findMatches.push({ from: match.index, to: match.index + match[0].length, groups: match });
        else pattern.lastIndex++; // 跳过空匹配（比如 ^ 或 x*），否则会死循环
      }
    }
    cm.operation(function () {
      clearFindMarks();
      findMarks = findMatches.map(function (item) {
        return cm.markText(cm.posFromIndex(item.from), cm.posFromIndex(item.to), { className: 'cm-find-match' });
      });
      updateFindCurrent();
    });
    findInput.parentElement.classList.toggle('invalid', invalid);
    findCount.classList.toggle('error', invalid);
    if (invalid) findCount.textContent = 'Invalid regex';
    var none = !findMatches.length;
    ['find-prev', 'find-next', 'replace-one', 'replace-all'].forEach(function (id) {
      document.getElementById(id).disabled = none;
    });
  }

  function selectFindMatch(item) {
    var from = cm.posFromIndex(item.from);
    var to = cm.posFromIndex(item.to);
    cm.setSelection(from, to, { scroll: false });
    cm.scrollIntoView({ from: from, to: to }, 90); // 留出空间，不要被小窗挡住
  }

  function goToMatch(forward) {
    if (!findMatches.length) return;
    var selection = selectionIndexes();
    var target = null;
    if (forward) {
      target = findMatches.find(function (item) { return item.from >= selection.to; }) || findMatches[0];
    } else {
      for (var i = findMatches.length - 1; i >= 0 && !target; i--) {
        if (findMatches[i].to <= selection.from) target = findMatches[i];
      }
      target = target || findMatches[findMatches.length - 1];
    }
    selectFindMatch(target);
  }

  function revealFirstMatch() { // 输入查找内容时，跳到光标之后最近的匹配
    var from = selectionIndexes().from;
    var target = findMatches.find(function (item) { return item.from >= from; }) || findMatches[0];
    if (target) selectFindMatch(target);
  }

  function replacementFor(item) {
    var replacement = replaceInput.value;
    if (!optionOn(findOptions.regex)) return replacement; // 普通查找时 $ 和 \ 就是普通字符
    return replacement.replace(/\$(\$|&|\d{1,2}|<[^>]*>)|\\([nt\\])/g, function (whole, ref, escaped) {
      if (escaped) return { n: '\n', t: '\t', '\\': '\\' }[escaped];
      if (ref === '$') return '$';
      if (ref === '&') return item.groups[0];
      if (ref[0] === '<') {
        var named = item.groups.groups;
        return named && ref.slice(1, -1) in named ? named[ref.slice(1, -1)] || '' : whole;
      }
      return +ref > 0 && +ref < item.groups.length ? item.groups[+ref] || '' : whole;
    });
  }

  function canEditDocument() {
    return !!current && !cm.getOption('readOnly');
  }

  function replaceCurrent() {
    if (!canEditDocument() || !findMatches.length) return;
    var index = selectedMatchIndex();
    if (index === -1) { // 还没选中匹配时，先跳过去看一眼，再按一次才替换
      goToMatch(true);
      return;
    }
    var item = findMatches[index];
    var text = replacementFor(item);
    cm.replaceRange(text, cm.posFromIndex(item.from), cm.posFromIndex(item.to), 'replace');
    cm.setCursor(cm.posFromIndex(item.from + text.length)); // 替换后的文字不再参与这次查找
    goToMatch(true);
  }

  function replaceAll() {
    if (!canEditDocument() || !findMatches.length) return;
    var items = findMatches.slice();
    cm.operation(function () { // 放在一次操作里，撤销时一步还原
      for (var i = items.length - 1; i >= 0; i--) { // 从后往前，前面的位置不会变
        cm.replaceRange(replacementFor(items[i]), cm.posFromIndex(items[i].from), cm.posFromIndex(items[i].to), 'replace');
      }
    });
    findCount.textContent = 'Replaced ' + items.length;
    replaceInput.focus(); // 按钮可能刚变成不可用，焦点不能丢，否则 Esc 关不掉小窗
  }

  function reserveFindSpace() { // 小窗开着时内容往下让，否则开头几行被挡住，也滚不出来
    var open = !findPanel.hidden;
    var lines = cm.getWrapperElement();
    lines.classList.toggle('find-open', open);
    if (open) lines.style.setProperty('--find-space', (findPanel.offsetHeight + 12) + 'px');
    cm.refresh();
  }

  function setReplaceVisible(visible) {
    replaceRow.hidden = !visible;
    findToggleReplace.setAttribute('aria-expanded', String(visible));
    reserveFindSpace();
  }

  function openFind(showReplace) {
    if (!current) return;
    if (document.body.classList.contains('mode-preview')) {
      document.querySelector('.mode-switch [data-mode="split"]').click(); // 预览模式看不到编辑区
    }
    var wasHidden = findPanel.hidden;
    findPanel.hidden = false;
    if (showReplace || wasHidden) setReplaceVisible(!!showReplace);
    openFindButton.setAttribute('aria-expanded', 'true');
    var selected = cm.getSelection();
    if (selected && selected.indexOf('\n') === -1) {
      findInput.value = optionOn(findOptions.regex) ? escapeRegExp(selected) : selected;
    }
    refreshFind();
    findInput.focus();
    findInput.select();
  }

  function closeFind() {
    findPanel.hidden = true;
    openFindButton.setAttribute('aria-expanded', 'false');
    findMatches = [];
    clearFindMarks();
    reserveFindSpace();
  }

  var openFindButton = document.getElementById('open-find');
  openFindButton.hidden = false;
  openFindButton.addEventListener('click', function () {
    if (findPanel.hidden || document.body.classList.contains('mode-preview')) {
      openFind(true);
    } else {
      closeFind();
      cm.focus();
    }
  });
  document.getElementById('find-close').addEventListener('click', function () {
    closeFind();
    cm.focus();
  });
  findToggleReplace.addEventListener('click', function () {
    setReplaceVisible(replaceRow.hidden);
  });
  document.getElementById('find-prev').addEventListener('click', function () { goToMatch(false); });
  document.getElementById('find-next').addEventListener('click', function () { goToMatch(true); });
  document.getElementById('replace-one').addEventListener('click', replaceCurrent);
  document.getElementById('replace-all').addEventListener('click', replaceAll);
  Object.keys(findOptions).forEach(function (name) {
    findOptions[name].addEventListener('click', function () {
      findOptions[name].setAttribute('aria-pressed', String(!optionOn(findOptions[name])));
      refreshFind();
      revealFirstMatch();
    });
  });
  findInput.addEventListener('input', function () {
    refreshFind();
    revealFirstMatch();
  });
  findInput.addEventListener('keydown', function (event) {
    if (event.key === 'Enter') {
      event.preventDefault();
      goToMatch(!event.shiftKey);
    }
  });
  replaceInput.addEventListener('keydown', function (event) {
    if (event.key === 'Enter') {
      event.preventDefault();
      replaceCurrent();
    }
  });
  // 文字变了（打字、撤销）或者换了文件，都要重新查找
  ['changes', 'swapDoc'].forEach(function (name) {
    cm.on(name, function () {
      if (!findPanel.hidden) refreshFind();
    });
  });
  cm.on('cursorActivity', function () {
    if (!findPanel.hidden) cm.operation(updateFindCurrent);
  });
  document.addEventListener('keydown', function (event) {
    if (document.querySelector('dialog[open]')) return;
    if (event.key === 'Escape' && !findPanel.hidden && event.target.closest('#editor-pane')) {
      closeFind();
      cm.focus();
      return;
    }
    if (!event.ctrlKey && !event.metaKey || event.altKey || event.shiftKey || !current) return;
    if (document.body.classList.contains('mode-preview')) return; // 预览时留给浏览器自带的查找，不跳视图
    var key = event.key.toLowerCase();
    if (key === 'f' || (key === 'h' && event.ctrlKey)) {
      event.preventDefault();
      openFind(key === 'h');
    }
  });

  var newFileButton = document.getElementById('new-file');
  newFileButton.hidden = false;
  // 新建文件和新建文件夹共用一个小窗
  var newItemDialog = document.getElementById('new-item-dialog');
  var newItemFolder = document.getElementById('new-item-folder');
  var newItemName = document.getElementById('new-item-name');
  var newItemError = document.getElementById('new-item-error');
  var newItemCreate = document.getElementById('new-item-create');
  var newItemKind = null;

  var NEW_ITEM_KINDS = {
    file: {
      title: 'New File',
      nameLabel: 'File name',
      defaultName: 'untitled.md',
      create: function (path) {
        return saveNow().then(function (ok) {
          if (!ok) throw new Error('Could not save the current file.');
          return request('/api/new', { root: root, path: path });
        }).then(function (data) {
          newItemDialog.close();
          return loadTree().then(function () { return openFile(data.path); });
        });
      }
    },
    folder: {
      title: 'New Folder',
      nameLabel: 'Folder name',
      defaultName: 'untitled',
      create: function (path) {
        return request('/api/new-folder', { root: root, path: path }).then(function (data) {
          newItemDialog.close();
          return loadTree().then(function () {
            openFolders(data.path);
            showStatus('Created ' + data.path);
          });
        });
      }
    }
  };

  function showNewItemError(message) {
    newItemError.textContent = message;
    newItemError.hidden = false;
  }

  function openNewItemDialog(kind) {
    var settings = NEW_ITEM_KINDS[kind];
    newItemKind = kind;
    document.getElementById('new-item-title').textContent = settings.title;
    document.getElementById('new-item-name-label').textContent = settings.nameLabel;
    newItemFolder.value = newItemParent();
    newItemName.value = settings.defaultName;
    newItemError.hidden = true;
    newItemDialog.showModal();
    newItemName.focus();
    var suffix = newItemName.value.lastIndexOf('.');
    newItemName.setSelectionRange(0, suffix === -1 ? newItemName.value.length : suffix); // 后缀不用改，不选中
  }

  newFileButton.addEventListener('click', function () { openNewItemDialog('file'); });
  document.getElementById('new-item-cancel').addEventListener('click', function () {
    newItemDialog.close();
  });
  document.getElementById('new-item-form').addEventListener('submit', function (event) {
    event.preventDefault();
    if (newItemCreate.disabled) return; // 上一次还没创建完
    var settings = NEW_ITEM_KINDS[newItemKind];
    var name = newItemName.value.trim().replace(/\\/g, '/');
    if (!name) {
      showNewItemError('Enter a ' + settings.nameLabel.toLowerCase() + '.');
      newItemName.focus();
      return;
    }
    var folder = newItemFolder.value.trim().replace(/\\/g, '/').replace(/^\/+|\/+$/g, '');
    newItemCreate.disabled = true;
    settings.create(joinPath(folder, name)).catch(function (err) {
      showNewItemError(err.message);
    }).then(function () {
      newItemCreate.disabled = false;
    });
  });

  var newFolderButton = document.getElementById('new-folder');
  newFolderButton.hidden = false;
  newFolderButton.addEventListener('click', function () { openNewItemDialog('folder'); });

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
