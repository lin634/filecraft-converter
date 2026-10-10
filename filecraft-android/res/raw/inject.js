// FileCraft Android 壳注入脚本：
// 网页的导出（PDF/MD/zip/思维导图 HTML）都走 blob: URL + <a download>，
// Android WebView 的 DownloadListener 处理不了 blob，这里把 a.click() 拦下来，
// 分块经 JS 桥（AndroidSaver）交给原生侧写入系统「下载」目录。
(function () {
  if (window.__filecraftSavePatched) return;
  window.__filecraftSavePatched = true;

  function abToB64(buf) {
    var bytes = new Uint8Array(buf), bin = '', n = bytes.length;
    for (var i = 0; i < n; i += 0x8000) {
      bin += String.fromCharCode.apply(null, bytes.subarray(i, Math.min(i + 0x8000, n)));
    }
    return btoa(bin);
  }

  function dataUrlB64(dataUrl) { return dataUrl.substring(dataUrl.indexOf(',') + 1); }

  function saveBlob(blob, name) {
    var S = window.AndroidSaver;
    if (!S || typeof S.begin !== 'function') return false;
    var id = S.begin(name || 'filecraft-export');
    if (!id) return false;
    var fail = function () { try { S.abort(id); } catch (e) {} };
    var total = blob.size;
    var canSlice = typeof blob.slice === 'function' && typeof Blob.prototype.arrayBuffer === 'function';
    if (!canSlice) {
      var fr = new FileReader();
      fr.onerror = fail;
      fr.onloadend = function () { S.chunk(id, dataUrlB64(fr.result)); S.end(id); };
      fr.readAsDataURL(blob);
      return true;
    }
    var CH = 1536000; // 1.5MB，3 的倍数，保证 base64 分块边界对齐
    var i = 0;
    (function step() {
      if (i >= total) { S.end(id); return; }
      blob.slice(i, Math.min(i + CH, total)).arrayBuffer().then(function (buf) {
        S.chunk(id, abToB64(buf));
        i = Math.min(i + CH, total);
        step();
      }, fail);
    })();
    return true;
  }

  var origClick = HTMLAnchorElement.prototype.click;

  function legacySave(blob, name) {
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    origClick.call(a); // 用原始 click，避免再次被拦截
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  }

  HTMLAnchorElement.prototype.click = function () {
    try {
      var href = this.getAttribute('href') || '';
      if (href.indexOf('blob:') === 0 && this.hasAttribute('download')) {
        var name = this.getAttribute('download') || 'filecraft-export';
        fetch(href).then(function (r) { return r.blob(); }).then(function (b) {
          if (!saveBlob(b, name)) legacySave(b, name);
        });
        return;
      }
    } catch (e) {}
    return origClick.apply(this, arguments);
  };
})();
