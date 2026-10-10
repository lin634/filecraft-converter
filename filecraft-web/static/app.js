/* FileCraft Web 前端逻辑（无框架，原生 JS） */
"use strict";

// ---------- 全局状态 ----------
const state = {
  files: [],            // [{id,name,ext,size,uploaded,converted,md_size}]
  checked: new Set(),   // 勾选的文件 id
  chat: [],             // [{role:'user'|'assistant', content}]
  qaSessionId: null,    // 当前问答会话 id（12位hex），null 表示下一个问题开新会话
  summaryHtml: "",      // 最近一次总结的渲染结果
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

// ---------- 小工具 ----------
function fmtSize(n) {
  if (n == null) return "";
  if (n < 1024) return n + " B";
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
  return (n / 1024 / 1024).toFixed(1) + " MB";
}

function escText(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}

let toastTimer = null;
function toast(msg, isErr = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.toggle("err", isErr);
  el.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), isErr ? 4200 : 2600);
}

async function api(url, options = {}) {
  const res = await fetch(url, options);
  if (res.status === 401) { location.href = "/login"; throw new Error("请先登录"); }
  if (!res.ok) {
    let detail = `请求失败（HTTP ${res.status}）`;
    try {
      const data = await res.json();
      if (data.detail) detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch (_) { /* 忽略非 JSON 响应 */ }
    throw new Error(detail);
  }
  return res;
}

async function apiJson(url, options = {}) {
  return (await api(url, options)).json();
}

function downloadBlob(blob, filename) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}

function setBusy(btn, busy, busyText) {
  if (busy) {
    btn.dataset.origText = btn.textContent;
    btn.textContent = busyText || "处理中…";
    btn.disabled = true;
  } else {
    btn.textContent = btn.dataset.origText || btn.textContent;
    btn.disabled = false;
  }
}

function checkedIds() {
  return [...state.checked];
}

// ---------- 文件列表 ----------
async function loadFiles() {
  const data = await apiJson("/api/files");
  state.files = data.files || [];
  const valid = new Set(state.files.map(f => f.id));
  for (const id of [...state.checked]) if (!valid.has(id)) state.checked.delete(id);
  renderFileList();
  updateButtonStates();
}

function renderFileList() {
  const ul = $("#file-list");
  ul.innerHTML = "";
  if (!state.files.length) {
    const li = document.createElement("li");
    li.className = "empty-hint";
    li.textContent = "还没有文件。点击上方按钮选择，或把文件拖进来。";
    ul.appendChild(li);
    $("#check-all").checked = false;
    return;
  }
  for (const f of state.files) {
    const li = document.createElement("li");

    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = state.checked.has(f.id);
    cb.addEventListener("change", () => {
      if (cb.checked) state.checked.add(f.id); else state.checked.delete(f.id);
      $("#check-all").checked = state.checked.size === state.files.length;
      updateButtonStates();
    });

    const nameBox = document.createElement("div");
    nameBox.className = "file-name";
    const nm = document.createElement("span");
    nm.className = "fname";
    nm.textContent = f.name;
    nm.title = f.name;
    const meta = document.createElement("span");
    meta.className = "fmeta";
    meta.textContent = `${fmtSize(f.size)} · ${f.uploaded}`;
    nameBox.append(nm, meta);

    const badge = document.createElement("span");
    if (f.converted) {
      badge.className = "badge ok";
      badge.textContent = "已转换";
    } else {
      badge.className = "badge no";
      badge.textContent = "未转换";
    }

    const ops = document.createElement("div");
    ops.className = "file-ops";
    if (f.converted) {
      const prev = document.createElement("button");
      prev.className = "btn-link";
      prev.textContent = "预览";
      prev.addEventListener("click", () => previewMarkdown(f));
      const dl = document.createElement("button");
      dl.className = "btn-link";
      dl.textContent = "MD";
      dl.title = "下载 Markdown";
      dl.addEventListener("click", () => downloadMd(f));
      ops.append(prev, dl);
    }
    const raw = document.createElement("button");
    raw.className = "btn-link";
    raw.textContent = "原文件";
    raw.title = "下载原始文件";
    raw.addEventListener("click", () => { window.location.href = `/api/files/${f.id}/raw`; });
    const del = document.createElement("button");
    del.className = "btn-link danger";
    del.textContent = "删除";
    del.addEventListener("click", async () => {
      if (!confirm(`删除「${f.name}」？（转换结果一并删除）`)) return;
      try {
        await api(`/api/files/${f.id}`, { method: "DELETE" });
        state.checked.delete(f.id);
        await loadFiles();
      } catch (e) { toast(e.message, true); }
    });
    ops.append(raw, del);

    li.append(cb, nameBox, badge, ops);
    ul.appendChild(li);
  }
  $("#check-all").checked = state.checked.size === state.files.length;
}

function updateButtonStates() {
  const n = state.checked.size;
  const convertedN = state.files.filter(f => state.checked.has(f.id) && f.converted).length;
  $("#btn-zip").disabled = convertedN === 0;
  $("#convert-summary").textContent =
    n ? `已勾选 ${n} 个文件${convertedN < n ? `（其中 ${convertedN} 个已转换）` : ""}` : "";
}

async function uploadFiles(fileList) {
  const files = [...fileList].filter(f => /\.(docx|pptx|xlsx|pdf)$/i.test(f.name));
  const skipped = fileList.length - files.length;
  if (!files.length) { toast("没有可上传的文件（仅支持 docx/pptx/xlsx/pdf）", true); return; }
  const fd = new FormData();
  for (const f of files.slice(0, 30)) fd.append("files", f, f.name);
  try {
    const data = await apiJson("/api/upload", { method: "POST", body: fd });
    await loadFiles();
    const msgs = [];
    if (data.files.length) msgs.push(`成功上传 ${data.files.length} 个文件`);
    if (data.errors.length) msgs.push(data.errors.map(e => `${e.name}：${e.error}`).join("；"));
    if (skipped > 0) msgs.push(`${skipped} 个非支持格式已跳过`);
    const hasErr = data.errors.length || skipped > 0;
    toast(msgs.join("；"), hasErr);
  } catch (e) { toast(e.message, true); }
}

// ---------- 转 Markdown ----------
async function convertChecked() {
  const ids = checkedIds();
  if (!ids.length) { toast("请先在左侧勾选文件", true); return; }
  const btn = $("#btn-convert");
  setBusy(btn, true, "转换中…");
  $("#convert-results").innerHTML = "";
  try {
    const data = await apiJson("/api/convert", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids }),
    });
    await loadFiles();
    renderConvertResults(data.results || []);
  } catch (e) {
    toast(e.message, true);
  } finally {
    setBusy(btn, false);
  }
}

function renderConvertResults(results) {
  const box = $("#convert-results");
  box.innerHTML = "";
  let ok = 0;
  for (const r of results) {
    const item = document.createElement("div");
    if (r.ok) {
      ok++;
      item.className = "convert-item ok";
      const name = document.createElement("span");
      name.className = "cname";
      name.textContent = r.name;
      const stat = document.createElement("span");
      stat.className = "cstat";
      stat.textContent = `✓ ${fmtSize(r.md_size)}`;
      const prev = document.createElement("button");
      prev.className = "btn small";
      prev.textContent = "预览";
      const f = state.files.find(x => x.id === r.id);
      prev.addEventListener("click", () => f && previewMarkdown(f));
      const dl = document.createElement("button");
      dl.className = "btn small";
      dl.textContent = "下载 MD";
      dl.addEventListener("click", () => f && downloadMd(f));
      item.append(name, stat, prev, dl);
    } else {
      item.className = "convert-item err";
      const name = document.createElement("span");
      name.className = "cname";
      name.textContent = r.name;
      const err = document.createElement("span");
      err.className = "cerr";
      err.textContent = r.error || "转换失败";
      item.append(name, err);
    }
    box.appendChild(item);
  }
  const fail = results.length - ok;
  $("#convert-summary").textContent =
    `完成：成功 ${ok} 个${fail ? `，失败 ${fail} 个` : ""}`;
}

async function previewMarkdown(f) {
  try {
    const data = await apiJson(`/api/files/${f.id}/markdown`);
    openModal(f.name, data.html, async () => {
      downloadBlob(new Blob([data.md], { type: "text/markdown;charset=utf-8" }),
        f.name.replace(/\.[^.]+$/, "") + ".md");
    });
  } catch (e) { toast(e.message, true); }
}

async function downloadMd(f) {
  try {
    const data = await apiJson(`/api/files/${f.id}/markdown`);
    downloadBlob(new Blob([data.md], { type: "text/markdown;charset=utf-8" }),
      f.name.replace(/\.[^.]+$/, "") + ".md");
  } catch (e) { toast(e.message, true); }
}

async function downloadZip() {
  const ids = checkedIds();
  if (!ids.length) { toast("请先在左侧勾选文件", true); return; }
  const btn = $("#btn-zip");
  setBusy(btn, true, "打包中…");
  try {
    const res = await api("/api/download/zip", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids }),
    });
    downloadBlob(await res.blob(), "filecraft-markdown.zip");
  } catch (e) { toast(e.message, true); }
  finally { setBusy(btn, false); }
}

// ---------- AI 总结（SSE）----------
async function summarize() {
  const ids = checkedIds();
  if (!ids.length) { toast("请先在左侧勾选文件", true); return; }
  const notConverted = state.files.filter(f => state.checked.has(f.id) && !f.converted);
  if (notConverted.length) {
    toast(`「${notConverted[0].name}」还没有转换，请先在「转 Markdown」页转换`, true);
    return;
  }
  const btn = $("#btn-summarize");
  setBusy(btn, true, "生成中…");
  $("#summary-progress").classList.remove("hidden");
  $("#summary-editor").classList.add("hidden");
  $("#summary-empty").classList.add("hidden");
  $("#summary-progress-text").textContent = "正在准备…";
  try {
    const res = await api("/api/summarize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids, extra: $("#extra-req").value.trim() }),
    });
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    outer:
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const raw = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        const line = raw.split("\n").find(l => l.startsWith("data:"));
        if (!line) continue;
        const evt = JSON.parse(line.slice(5).trim());
        if (evt.type === "progress") {
          $("#summary-progress-text").textContent = evt.message;
        } else if (evt.type === "done") {
          showSummary(evt.summary_md, evt.html);
          loadSummaryHistory();
          break outer;
        } else if (evt.type === "error") {
          throw new Error(evt.message);
        }
      }
    }
  } catch (e) {
    toast("总结失败：" + e.message, true);
  } finally {
    $("#summary-progress").classList.add("hidden");
    setBusy(btn, false);
  }
}

function showSummary(mdText, html) {
  state.summaryHtml = html || "";
  $("#summary-text").value = mdText;
  $("#summary-editor").classList.remove("hidden");
  setSummaryView("edit");
}

function setSummaryView(view) {
  const isPreview = view === "preview";
  $$("#tab-summary .seg").forEach(b => b.classList.toggle("active", b.dataset.view === view));
  if (isPreview) {
    const md = $("#summary-text").value;
    $("#summary-preview").innerHTML = "<p class='muted'>渲染中…</p>";
    // 本地渲染即可，不必每次请求服务器
    $("#summary-preview").innerHTML = state.summaryHtml || "<p class='muted'>（空内容）</p>";
    $("#summary-text").classList.add("hidden");
    $("#summary-preview").classList.remove("hidden");
  } else {
    $("#summary-text").classList.remove("hidden");
    $("#summary-preview").classList.add("hidden");
  }
}

async function renderEditedSummary() {
  const md = $("#summary-text").value;
  try {
    const data = await apiJson("/api/render", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ markdown: md }),
    });
    state.summaryHtml = data.html;
  } catch (_) { /* 渲染失败不影响导出 */ }
}

async function exportSummaryPdf() {
  const md = $("#summary-text").value.trim();
  if (!md) { toast("总结内容为空", true); return; }
  const btn = $("#btn-export-pdf");
  setBusy(btn, true, "生成 PDF…");
  try {
    const res = await api("/api/export/pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ markdown: md, title: "文档总结" }),
    });
    downloadBlob(await res.blob(), "文档总结.pdf");
  } catch (e) { toast(e.message, true); }
  finally { setBusy(btn, false); }
}

function exportSummaryMd() {
  const md = $("#summary-text").value;
  if (!md.trim()) { toast("总结内容为空", true); return; }
  downloadBlob(new Blob([md], { type: "text/markdown;charset=utf-8" }), "文档总结.md");
}

async function exportMindmap() {
  const md = $("#summary-text").value.trim();
  if (!md) { toast("总结内容为空", true); return; }
  const btn = $("#btn-mindmap");
  setBusy(btn, true, "生成中…");
  try {
    const res = await api("/api/export/mindmap", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ markdown: md, title: "思维导图" }),
    });
    downloadBlob(await res.blob(), "思维导图.html");
    toast("思维导图已下载，用浏览器打开即可查看");
  } catch (e) { toast(e.message, true); }
  finally { setBusy(btn, false); }
}

async function copySummary() {
  try {
    await navigator.clipboard.writeText($("#summary-text").value);
    toast("已复制到剪贴板");
  } catch (_) { toast("复制失败，请手动选择文本复制", true); }
}

// ---------- 文档问答 ----------
async function qaSend(e) {
  e.preventDefault();
  const input = $("#chat-input");
  const question = input.value.trim();
  if (!question) return;
  const ids = checkedIds();
  if (!ids.length) { toast("请先在左侧勾选文件", true); return; }
  const notConverted = state.files.filter(f => state.checked.has(f.id) && !f.converted);
  if (notConverted.length) {
    toast(`「${notConverted[0].name}」还没有转换，请先转换`, true);
    return;
  }

  input.value = "";
  appendChat("user", question);
  state.chat.push({ role: "user", content: question });
  const pending = appendChat("assistant", "正在思考…", true);

  try {
    const data = await apiJson("/api/qa", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids, question, history: state.chat.slice(-12),
                             session_id: state.qaSessionId }),
    });
    pending.remove();
    appendChat("assistant", data.answer, false, data.html);
    state.chat.push({ role: "assistant", content: data.answer });
    if (data.session_id) state.qaSessionId = data.session_id;
    loadQaHistory();
  } catch (err) {
    pending.remove();
    appendChat("assistant", "❌ " + err.message);
  }
}

function appendChatSystem(text) {
  const box = $("#chat-box");
  const div = document.createElement("div");
  div.className = "chat-system";
  div.textContent = text;
  box.prepend(div);
}

function appendChat(role, text, pending = false, html = "") {
  const box = $("#chat-box");
  const bubble = document.createElement("div");
  bubble.className = `bubble ${role}` + (role === "assistant" && html ? " md" : "");
  if (role === "assistant" && html) {
    bubble.innerHTML = html;
  } else {
    bubble.textContent = text;
  }
  if (pending) bubble.classList.add("pending");
  box.appendChild(bubble);
  box.scrollTop = box.scrollHeight;
  return bubble;
}

// ---------- 弹窗 ----------
function openModal(title, html, onDownload) {
  $("#modal-title").textContent = title;
  $("#modal-body").innerHTML = html;
  const dlBtn = $("#modal-download");
  dlBtn.classList.toggle("hidden", !onDownload);
  dlBtn.onclick = onDownload || null;
  $("#modal").classList.remove("hidden");
}

function closeModal() { $("#modal").classList.add("hidden"); }

// ---------- 问答会话历史 ----------
async function loadQaHistory() {
  try {
    const data = await apiJson("/api/history/qa");
    renderQaHistory(data.items || []);
  } catch (_) { /* 静默 */ }
}

function renderQaHistory(items) {
  $("#qa-history-count").textContent = items.length ? `(${items.length})` : "";
  const ul = $("#qa-history-list");
  ul.innerHTML = "";
  if (!items.length) {
    ul.innerHTML = "<li class='history-empty'>还没有问答会话。提问后会自动保存到这里。</li>";
    return;
  }
  for (const s of items) {
    const li = document.createElement("li");
    li.className = "history-item";
    li.innerHTML = `
      <div class="history-main">
        <div class="history-title">${escText(s.title)}</div>
        <div class="history-meta">${escText(s.time)} · ${s.turns_count} 轮 · ${escText((s.files || []).join("、") || "无文件")}</div>
      </div>`;
    const open = document.createElement("button");
    open.className = "btn small";
    open.textContent = "打开";
    open.addEventListener("click", () => openQaSession(s.id));
    const del = document.createElement("button");
    del.className = "btn-link danger";
    del.textContent = "删除";
    del.addEventListener("click", async () => {
      if (!confirm("删除这个问答会话？")) return;
      try {
        await api(`/api/history/qa/${s.id}`, { method: "DELETE" });
        if (state.qaSessionId === s.id) newQaSession(false);
        loadQaHistory();
      } catch (e) { toast(e.message, true); }
    });
    li.append(open, del);
    ul.appendChild(li);
  }
}

async function openQaSession(sessionId) {
  try {
    const s = await apiJson(`/api/history/qa/${sessionId}`);
    const box = $("#chat-box");
    box.innerHTML = "";
    appendChatSystem("已打开历史会话，可继续追问（回答基于当前勾选的文件）。");
    state.chat = [];
    for (const t of s.turns || []) {
      if (t.role === "user") {
        appendChat("user", t.content);
      } else {
        appendChat("assistant", t.content, false, t.html || "");
      }
      state.chat.push({ role: t.role, content: t.content });
    }
    state.qaSessionId = s.id;
    // 恢复该会话涉及的文件勾选（仍存在的才勾）
    const existIds = new Set(state.files.map(f => f.id));
    const want = new Set((s.file_ids || []).filter(id => existIds.has(id)));
    state.checked = want;
    renderFileList();
    updateButtonStates();
    const missing = (s.file_ids || []).filter(id => !existIds.has(id)).length;
    if (missing) toast(`会话涉及的文件中有 ${missing} 个已被删除，追问前请重新勾选`, true);
    switchTab("qa");
    toast("已打开历史会话");
  } catch (e) { toast(e.message, true); }
}

function newQaSession(notice = true) {
  state.qaSessionId = null;
  state.chat = [];
  const box = $("#chat-box");
  box.innerHTML = "";
  appendChatSystem("已开始新对话。勾选文件后即可提问，回答只依据文档内容。");
  if (notice) toast("已开始新对话");
}

// ---------- 总结历史 ----------
async function loadSummaryHistory() {
  try {
    const data = await apiJson("/api/history/summaries");
    renderSummaryHistory(data.items || []);
  } catch (_) { /* 静默 */ }
}

function renderSummaryHistory(items) {
  $("#summary-history-count").textContent = items.length ? `(${items.length})` : "";
  const ul = $("#summary-history-list");
  ul.innerHTML = "";
  if (!items.length) {
    ul.innerHTML = "<li class='history-empty'>还没有历史总结。生成或「存入历史」后会出现在这里。</li>";
    return;
  }
  for (const it of items) {
    const li = document.createElement("li");
    li.className = "history-item";
    const srcBadge = it.source === "manual" ? "手动保存" : "AI 生成";
    li.innerHTML = `
      <div class="history-main">
        <div class="history-title">${escText(it.title)}</div>
        <div class="history-meta">${escText(it.time)} · ${escText((it.files || []).join("、") || "未关联文件")}${it.extra ? " · " + escText(it.extra) : ""}</div>
      </div>
      <span class="history-src ${escText(it.source)}">${srcBadge}</span>`;
    const load = document.createElement("button");
    load.className = "btn small";
    load.textContent = "载入";
    load.title = "载入到编辑器";
    load.addEventListener("click", () => loadSummaryItem(it.id));
    const del = document.createElement("button");
    del.className = "btn-link danger";
    del.textContent = "删除";
    del.addEventListener("click", async () => {
      if (!confirm("删除这条历史总结？（正文一并删除）")) return;
      try {
        await api(`/api/history/summaries/${it.id}`, { method: "DELETE" });
        loadSummaryHistory();
      } catch (e) { toast(e.message, true); }
    });
    li.append(load, del);
    ul.appendChild(li);
  }
}

async function loadSummaryItem(summaryId) {
  try {
    const data = await apiJson(`/api/history/summaries/${summaryId}`);
    showSummary(data.md, data.html);
    switchTab("summary");
    toast("已载入历史总结");
  } catch (e) { toast(e.message, true); }
}

async function saveSummaryToHistory() {
  const md = $("#summary-text").value.trim();
  if (!md) { toast("总结内容为空", true); return; }
  const names = state.files.filter(f => state.checked.has(f.id)).map(f => f.name);
  try {
    await apiJson("/api/summaries/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ markdown: md, title: "手动保存的总结", files: names }),
    });
    await loadSummaryHistory();
    $("#btn-summary-history-toggle").classList.add("open");
    $("#summary-history-list").classList.add("open");
    toast("已存入历史记录");
  } catch (e) { toast(e.message, true); }
}

// ---------- 用户区 ----------
async function loadUser() {
  try {
    const me = await apiJson("/api/me");
    const el = $("#user-name");
    el.textContent = me.display || me.username;
    el.title = `${me.username}（${me.display}）`;
  } catch (_) { /* 401 已由 api() 处理 */ }
}

async function logout() {
  try { await api("/api/logout", { method: "POST" }); } catch (_) { /* 忽略 */ }
  location.href = "/login";
}

// ---------- 事件绑定 ----------
function switchTab(name) {
  $$(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === name));
  $$(".tab-page").forEach(p => p.classList.toggle("active", p.id === "tab-" + name));
}

function bindEvents() {
  $$(".tab").forEach(t => t.addEventListener("click", () => switchTab(t.dataset.tab)));

  $("#btn-logout").addEventListener("click", logout);
  $("#btn-summary-save").addEventListener("click", saveSummaryToHistory);

  // 历史面板折叠
  $("#btn-summary-history-toggle").addEventListener("click", () => {
    $("#btn-summary-history-toggle").classList.toggle("open");
    $("#summary-history-list").classList.toggle("open");
  });
  $("#btn-qa-history-toggle").addEventListener("click", () => {
    $("#btn-qa-history-toggle").classList.toggle("open");
    $("#qa-history-list").classList.toggle("open");
  });
  $("#btn-qa-new").addEventListener("click", () => newQaSession());

  $("#btn-select-files").addEventListener("click", () => $("#input-files").click());
  $("#btn-select-folder").addEventListener("click", () => $("#input-folder").click());
  $("#input-files").addEventListener("change", (e) => {
    if (e.target.files.length) uploadFiles(e.target.files);
    e.target.value = "";
  });
  $("#input-folder").addEventListener("change", (e) => {
    if (e.target.files.length) uploadFiles(e.target.files);
    e.target.value = "";
  });

  const dz = $("#drop-zone"), ov = $("#drop-overlay");
  let dragDepth = 0;
  dz.addEventListener("dragenter", (e) => { e.preventDefault(); dragDepth++; ov.classList.remove("hidden"); });
  dz.addEventListener("dragover", (e) => e.preventDefault());
  dz.addEventListener("dragleave", () => { if (--dragDepth <= 0) { dragDepth = 0; ov.classList.add("hidden"); } });
  dz.addEventListener("drop", (e) => {
    e.preventDefault();
    dragDepth = 0;
    ov.classList.add("hidden");
    if (e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files);
  });

  $("#check-all").addEventListener("change", (e) => {
    state.checked = e.target.checked ? new Set(state.files.map(f => f.id)) : new Set();
    renderFileList();
    updateButtonStates();
  });
  $("#btn-delete-checked").addEventListener("click", async () => {
    const ids = checkedIds();
    if (!ids.length) { toast("请先勾选文件", true); return; }
    if (!confirm(`删除勾选的 ${ids.length} 个文件？（转换结果一并删除）`)) return;
    for (const id of ids) {
      try { await api(`/api/files/${id}`, { method: "DELETE" }); } catch (_) { /* 继续删其余 */ }
    }
    state.checked.clear();
    await loadFiles();
    toast("已删除");
  });

  $("#btn-convert").addEventListener("click", convertChecked);
  $("#btn-zip").addEventListener("click", downloadZip);

  $("#btn-summarize").addEventListener("click", summarize);
  $$("#tab-summary .seg").forEach(b => b.addEventListener("click", async () => {
    if (b.classList.contains("active")) return;
    if (b.dataset.view === "preview") await renderEditedSummary();  // 进入预览前重新渲染编辑后的内容
    setSummaryView(b.dataset.view);
  }));
  $("#btn-export-pdf").addEventListener("click", exportSummaryPdf);
  $("#btn-export-md").addEventListener("click", exportSummaryMd);
  $("#btn-mindmap").addEventListener("click", exportMindmap);
  $("#btn-copy").addEventListener("click", copySummary);

  $("#chat-form").addEventListener("submit", qaSend);

  $("#modal-close").addEventListener("click", closeModal);
  $("#modal").addEventListener("click", (e) => { if (e.target === $("#modal")) closeModal(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });
}

// ---------- 启动 ----------
bindEvents();
loadUser();
loadFiles().catch(e => toast("加载文件列表失败：" + e.message, true));
loadSummaryHistory();
loadQaHistory();
