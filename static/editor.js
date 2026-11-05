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
        var error = new Error(body.error || '请求失败');
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
    showStatus('编辑器组件加载失败，请检查网络（CodeMirror 从 CDN 加载）', true);
    return;
  }

  cm = CodeMirror(document.getElementById('editor-pane'), {
    mode: 'markdown',
    lineNumbers: true,
    lineWrapping: true,
    indentUnit: 2,
    tabSize: 2,
    indentWithTabs: false,
    readOnly: true,
    extraKeys: {
      Enter: 'newlineAndIndentContinueMarkdownList',
      Tab: function (editor) {
        if (editor.somethingSelected()) editor.indentSelection('add');
        else editor.replaceSelection('  ');
      },
      'Shift-Tab': function (editor) { editor.indentSelection('subtract'); },
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
        details.appendChild(summary);
        var children = document.createElement('div');
        children.className = 'tree-children';
        renderTree(item.children, children);
        if (!item.children.length) {
          var empty = document.createElement('div');
          empty.className = 'tree-empty';
          empty.textContent = '（空）';
          children.appendChild(empty);
        }
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
        parent.appendChild(button);
      }
    });
  }

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
        note.textContent = '这个文件夹的内容太多，只显示了一部分。';
        tree.appendChild(note);
      }
      if (!data.tree.length) {
        var empty = document.createElement('div');
        empty.className = 'tree-empty';
        empty.textContent = '没有 Markdown 文件，可以点上面的“新建文件”。';
        tree.appendChild(empty);
      }
      renderTree(data.tree, tree);
      tree.querySelectorAll('details').forEach(function (d) {
        d.open = hasPrevious ? !!open[d.dataset.path] : d.parentElement === tree;
      });
      markActive();
      return data;
    });
  }

  // ---------- 打开和保存 ----------
  function showFile(data) {
    current = { path: data.path, mtime: data.mtime };
    saved = data.content;
    document.body.classList.remove('no-file');
    cm.setOption('readOnly', false);
    cm.swapDoc(CodeMirror.Doc(data.content, 'markdown')); // 换一个文档，撤销不会跨文件
    filePath.textContent = data.path;
    document.title = data.path.split('/').pop() + ' · Markdown 编辑器';
    showStatus('已保存');
    if (location.hash.slice(1) !== encodeURIComponent(data.path)) {
      history.replaceState(null, '', location.search + '#' + encodeURIComponent(data.path));
    }
    markActive();
    renderPreview();
    cm.focus();
  }

  function openFile(path) {
    return saveNow().then(function (ok) {
      if (!ok) return; // 没保存成功就不切换，否则改动会丢
      return request(fileUrl(path)).then(showFile);
    }).catch(function (err) { showStatus(err.message, true); });
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
    showStatus('保存中…');
    return request('/api/save', { root: root, path: path, content: content, mtime: current.mtime, force: !!force })
      .then(function (data) {
        if (!current || current.path !== path) return true;
        current.mtime = data.mtime;
        saved = content;
        showStatus(isDirty() ? '有未保存的改动' : '已保存');
        return true;
      })
      .catch(function (err) {
        if (err.status !== 409) {
          showStatus('保存失败：' + err.message, true);
          return false;
        }
        var overwrite = window.confirm(
          '这个文件已在别处被修改或删除。\n\n确定：用编辑器里的内容覆盖它\n取消：放弃编辑器里的改动，重新读取文件'
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
      showStatus('保存失败', true);
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
      syncScroll();
    }).catch(function (err) {
      if (seq !== previewSeq) return;
      previewError.hidden = false;
      previewError.textContent = '预览失败：' + err.message;
    });
  }

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
      showStatus('有未保存的改动');
      saveTimer = setTimeout(saveNow, AUTOSAVE_DELAY);
    } else {
      showStatus('已保存');
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

  var newFileButton = document.getElementById('new-file');
  newFileButton.hidden = false;
  newFileButton.addEventListener('click', function () {
    var folder = current ? current.path.split('/').slice(0, -1).join('/') : '';
    var path = window.prompt('文件路径（相对于打开的文件夹，文件夹不存在时会自动创建）：', (folder ? folder + '/' : '') + 'new-file.md');
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
    loadTree().catch(function () {});
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
  filePath.textContent = '从左侧选择一个文件';
  loadTree().then(function (data) {
    filePath.textContent = '从左侧选择一个文件';
    root = data.root; // 用服务端规范化后的路径
    var path = decodeURIComponent(location.hash.slice(1));
    if (path) openFile(path);
  }).catch(function (err) {
    document.getElementById('workspace').hidden = true;
    showWelcome(err.message);
  });
})();
