"""filecraft-web 服务器：FastAPI + 复用桌面版 core/ 模块。

启动：
    python server.py            # 监听 127.0.0.1:3100（可用环境变量覆盖）

功能：
    - 浏览器上传 docx/pptx/xlsx/pdf -> 转 Markdown -> 下载
    - 勾选多个文件 AI 总结（SSE 进度）-> 可编辑 -> 导出 PDF / MD / 思维导图
    - 基于所选文档的多轮问答
    - 每个浏览器会话一个独立工作区，超期自动清理
"""
from __future__ import annotations

import io
import json
import logging
import os
import queue
import re
import threading
import time
import urllib.parse
import uuid
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

import markdown as md_lib
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               RedirectResponse, Response, StreamingResponse)
from fastapi.staticfiles import StaticFiles

import auth
import config
import store
from core import registry
from core.md_to_pdf import markdown_to_pdf
from core.mindmap import markdown_to_mindmap_html
from core.qa import QAEngine, QAError
from core.summarizer import FileInfo, Summarizer

APP_VERSION = "1.1.0"
AUTH_COOKIE = "fc_auth"

try:
    import nh3
except ImportError:  # 本地应急可用；生产环境必须安装（见 requirements.txt）
    nh3 = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("filecraft-web")


def _cleanup_loop() -> None:
    """后台线程：每 6 小时清理一次过期工作区。"""
    while True:
        time.sleep(6 * 3600)
        try:
            n = store.cleanup_expired()
            if n:
                log.info("定时清理：删除 %d 个过期工作区", n)
        except Exception:  # noqa: BLE001
            log.exception("定时清理失败")


def _seed_demo_workspace() -> None:
    """演示账号首次使用时预置样例文档（已转换），方便直接体验。"""
    import uuid
    wid = auth.workspace_id_for("demo")
    ws = store.get_workspace(wid)
    if ws is None or ws.list_files():
        return
    seed_dir = Path(config.BASE_DIR) / "seed"
    if not seed_dir.is_dir():
        return
    n = 0
    for p in sorted(seed_dir.iterdir()):
        if not p.is_file() or not registry.is_supported(p.name):
            continue
        try:
            info = ws.add_file(p.name, p.read_bytes())
            md_text = registry.convert_file(ws.file_path(info["id"]))
            ws.save_md(info["id"], md_text)
            n += 1
        except Exception:  # noqa: BLE001 - 单个样例失败不影响其余
            log.exception("预置样例失败: %s", p.name)
    if n:
        log.info("演示账号预置 %d 份样例文档", n)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    os.makedirs(config.DATA_DIR, exist_ok=True)
    auth.init()
    threading.Thread(target=_seed_demo_workspace, daemon=True).start()
    removed = store.cleanup_expired()
    if removed:
        log.info("启动清理：删除 %d 个过期工作区", removed)
    threading.Thread(target=_cleanup_loop, daemon=True).start()
    log.info("FileCraft Web v%s 启动于 http://%s:%d", APP_VERSION, config.HOST, config.PORT)
    yield


app = FastAPI(title="FileCraft Web", version=APP_VERSION, docs_url=None, redoc_url=None,
              lifespan=lifespan)

STATIC_DIR = Path(config.BASE_DIR) / "static"

#: 无需登录即可访问的路径
PUBLIC_PATHS = {"/login", "/api/login", "/api/health"}


# ---- 会话鉴权 ---------------------------------------------------------------
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path in PUBLIC_PATHS or path.startswith("/static"):
        return await call_next(request)

    sid = request.cookies.get(AUTH_COOKIE, "")
    if sid not in auth.valid_workspace_ids():
        if path.startswith("/api/"):
            return JSONResponse({"detail": "请先登录"}, status_code=401)
        return RedirectResponse("/login", status_code=302)
    request.state.sid = sid
    return await call_next(request)


def _workspace(request: Request) -> store.Workspace:
    ws = store.get_workspace(request.state.sid)
    if ws is None:  # 理论上不会发生（中间件保证 sid 合法）
        raise HTTPException(400, "会话无效，请刷新页面")
    return ws


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimiter:
    """内存限流：每 key 每小时 N 次（进程重启即清零，够用即可）。"""

    def __init__(self, limit: int):
        self.limit = limit
        self.hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.time()
        with self._lock:
            window = [t for t in self.hits.get(key, []) if now - t < 3600]
            if len(window) >= self.limit:
                raise HTTPException(429, f"调用太频繁了，每小时最多 {self.limit} 次，请稍后再试")
            window.append(now)
            self.hits[key] = window
            # 顺手清理别的 key 的过期记录
            if len(self.hits) > 500:
                self.hits = {k: v for k, v in self.hits.items()
                             if v and now - v[-1] < 3600}


ai_limiter = RateLimiter(config.AI_RATE_LIMIT_PER_HOUR)
login_limiter = RateLimiter(10)  # 登录尝试：每 IP 每小时 10 次


# ---- 登录 / 登出 ------------------------------------------------------------
@app.get("/login")
async def login_page():
    return FileResponse(STATIC_DIR / "login.html")


@app.post("/api/login")
async def login(request: Request, body: dict):
    login_limiter.check(_client_ip(request))
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    if not auth.verify(username, password):
        raise HTTPException(401, "用户名或密码错误")
    resp = JSONResponse({"ok": True, "username": username,
                         "display": auth.display_name(username)})
    resp.set_cookie(
        AUTH_COOKIE, auth.workspace_id_for(username),
        max_age=30 * 86400, httponly=True, samesite="lax",
    )
    log.info("login: %s (%s)", username, _client_ip(request))
    return resp


@app.post("/api/logout")
async def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(AUTH_COOKIE)
    return resp


@app.get("/api/me")
async def me(request: Request):
    username = auth.username_by_workspace_id(request.state.sid) or ""
    return {"username": username, "display": auth.display_name(username)}


# ---- 基础接口 ---------------------------------------------------------------
@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health():
    return {"ok": True, "version": APP_VERSION}


@app.get("/api/files")
async def list_files(request: Request):
    return {"files": _workspace(request).list_files()}


@app.post("/api/upload")
async def upload(request: Request, files: list[UploadFile] = File(...)):
    ws = _workspace(request)
    saved, errors = [], []
    for uf in files:
        name = os.path.basename(uf.filename or "")
        ext = os.path.splitext(name)[1].lower()
        if ext not in store.ALLOWED_EXTS:
            errors.append({"name": name, "error": f"不支持的格式 {ext or '(无扩展名)'}，"
                           f"仅支持 {' / '.join(store.ALLOWED_EXTS)}"})
            continue
        content = await uf.read()
        if len(content) > config.MAX_FILE_MB * 1024 * 1024:
            errors.append({"name": name, "error": f"超过单文件 {config.MAX_FILE_MB}MB 上限"})
            continue
        if not content:
            errors.append({"name": name, "error": "空文件"})
            continue
        try:
            saved.append(ws.add_file(name, content))
        except ValueError as e:
            errors.append({"name": name, "error": str(e)})
    return {"files": saved, "errors": errors}


@app.delete("/api/files/{fid}")
async def delete_file(request: Request, fid: str):
    if not _workspace(request).remove_file(fid):
        raise HTTPException(404, "文件不存在")
    return {"ok": True}


@app.get("/api/files/{fid}/raw")
async def download_raw(request: Request, fid: str):
    ws = _workspace(request)
    info = ws.get_file(fid)
    path = ws.file_path(fid)
    if not info or not path:
        raise HTTPException(404, "文件不存在")
    return _file_download(path, info["name"])


@app.get("/api/files/{fid}/markdown")
async def get_markdown(request: Request, fid: str):
    ws = _workspace(request)
    info = ws.get_file(fid)
    md_text = ws.load_md(fid)
    if not info or md_text is None:
        raise HTTPException(404, "还没有转换结果，请先转换")
    return {"id": fid, "name": info["name"], "md": md_text,
            "html": _render_html(md_text)}


@app.post("/api/convert")
async def convert_batch(request: Request, body: dict):
    ids = body.get("ids") or []
    if not isinstance(ids, list) or not ids:
        raise HTTPException(400, "请先勾选要转换的文件")
    return await _convert(request, ids)


async def _convert(request: Request, ids: list) -> dict:
    import anyio
    ws = _workspace(request)
    results = []
    for fid in ids[:20]:  # 一批最多 20 个，防止请求过久
        info = ws.get_file(str(fid))
        path = ws.file_path(str(fid))
        if not info or not path:
            results.append({"id": fid, "name": "?", "ok": False, "error": "文件不存在"})
            continue
        try:
            md_text = await anyio.to_thread.run_sync(registry.convert_file, path)
            ws.save_md(str(fid), md_text)
            results.append({"id": fid, "name": info["name"], "ok": True,
                            "md_size": len(md_text.encode("utf-8"))})
        except Exception as e:  # noqa: BLE001 - ConversionError 等统一返回给前端
            results.append({"id": fid, "name": info["name"], "ok": False,
                            "error": str(e)})
    return {"results": results, "files": ws.list_files()}


@app.post("/api/download/zip")
async def download_zip(request: Request, body: dict):
    """把已转换的 markdown 打包成 zip 下载。"""
    ws = _workspace(request)
    ids = body.get("ids") or []
    buf = io.BytesIO()
    count = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fid in ids[:50]:
            md_text = ws.load_md(str(fid))
            info = ws.get_file(str(fid))
            if md_text is None or not info:
                continue
            arc = os.path.splitext(info["name"])[0] + ".md"
            if arc in zf.namelist():  # 同名时加 id 前缀
                arc = f"{fid}_{arc}"
            zf.writestr(arc, md_text)
            count += 1
    if not count:
        raise HTTPException(400, "勾选的文件都还没有转换结果")
    buf.seek(0)
    return _bytes_download(buf.getvalue(), "filecraft-markdown.zip", "application/zip")


# ---- AI 总结（SSE 流式进度）--------------------------------------------------
@app.post("/api/summarize")
async def summarize(request: Request, body: dict):
    ai_limiter.check(request.state.sid)
    ws = _workspace(request)
    ids = body.get("ids") or []
    extra = (body.get("extra") or "").strip()
    files_info = []
    for fid in ids[:20]:
        md_text = ws.load_md(str(fid))
        info = ws.get_file(str(fid))
        if md_text is None or not info:
            raise HTTPException(400, f"「{info['name'] if info else fid}」还没有转换结果，请先转换")
        files_info.append(FileInfo(name=info["name"], markdown=md_text))
    if not files_info:
        raise HTTPException(400, "请先勾选文件并转换")
    names = "、".join(f.name for f in files_info)
    title = f"文档总结（{len(files_info)} 份）"

    progress_q: queue.Queue = queue.Queue()

    def run() -> None:
        try:
            s = Summarizer(config.llm_config())
            if extra:
                # 额外要求并入系统提示，保证对分块/合并全程生效
                s.SYSTEM_PROMPT = s.SYSTEM_PROMPT.rstrip("。") + f"。用户额外要求：{extra}"
            md_text = s.summarize(files_info, progress=progress_q.put)
            progress_q.put(("__done__", md_text))
        except Exception as e:  # noqa: BLE001
            progress_q.put(("__error__", f"{type(e).__name__}: {e}"))

    def sse():
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        while True:
            try:
                item = progress_q.get(timeout=120)
            except queue.Empty:
                yield _sse_event({"type": "progress", "message": "仍在等待模型响应…"})
                continue
            # Summarizer 的 progress 回调推入的是单个字符串；
            # run() 自身用 ("__done__"/"__error__", 载荷) 元组作控制标记
            if isinstance(item, tuple):
                kind, payload = item
            else:
                kind, payload = "progress", item
            if kind == "__done__":
                summary_id = ws.save_summary(payload, title)
                ws.add_summary_history(summary_id, title,
                                       [f.name for f in files_info], extra, "ai")
                yield _sse_event({"type": "done", "summary_md": payload,
                                  "summary_id": summary_id,
                                  "html": _render_html(payload)})
                break
            if kind == "__error__":
                yield _sse_event({"type": "error", "message": str(payload)})
                break
            yield _sse_event({"type": "progress", "message": str(payload)})

    log.info("summarize: %s (%s)", names, _client_ip(request))
    return StreamingResponse(sse(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


# ---- 文档问答 ----------------------------------------------------------------
@app.post("/api/qa")
async def qa(request: Request, body: dict):
    ai_limiter.check(request.state.sid)
    ws = _workspace(request)
    ids = body.get("ids") or []
    question = (body.get("question") or "").strip()
    history = body.get("history") or []
    if not question:
        raise HTTPException(400, "问题不能为空")
    files: list[tuple[str, str]] = []
    for fid in ids[:20]:
        md_text = ws.load_md(str(fid))
        info = ws.get_file(str(fid))
        if md_text is None or not info:
            raise HTTPException(400, f"还有未转换的文件，请先转换再提问")
        files.append((info["name"], md_text))
    if not files:
        raise HTTPException(400, "请先勾选文件并转换")
    try:
        engine = QAEngine(config.llm_config())
        answer = engine.ask(question, files, history=history[-12:])
    except QAError as e:
        raise HTTPException(502, f"模型调用失败：{e}")
    # 会话历史：客户端带 session_id 则续会话，否则开新会话
    session_id = (body.get("session_id") or "").strip()
    if not re.fullmatch(r"[0-9a-f]{12}", session_id or ""):
        session_id = uuid.uuid4().hex[:12]
    ws.qa_append(session_id, question[:40], [n for n, _ in files],
                 [str(i) for i in ids[:20]], question, answer)
    log.info("qa: %s… (%s)", question[:50], _client_ip(request))
    return {"answer": answer, "html": _render_html(answer), "session_id": session_id}


# ---- 历史记录（总结 / 问答会话）------------------------------------------------
@app.get("/api/history/summaries")
async def summary_history(request: Request):
    return {"items": _workspace(request).list_summary_history()}


@app.get("/api/history/summaries/{summary_id}")
async def summary_history_item(request: Request, summary_id: str):
    ws = _workspace(request)
    md_text = ws.get_summary_history_md(summary_id)
    if md_text is None:
        raise HTTPException(404, "该总结不存在（可能已被删除）")
    return {"id": summary_id, "md": md_text, "html": _render_html(md_text)}


@app.delete("/api/history/summaries/{summary_id}")
async def summary_history_delete(request: Request, summary_id: str):
    if not _workspace(request).delete_summary_history(summary_id):
        raise HTTPException(404, "该总结不存在")
    return {"ok": True}


@app.post("/api/summaries/save")
async def summary_save(request: Request, body: dict):
    """把编辑过的总结手动存入历史。"""
    md_text = (body.get("markdown") or "").strip()
    if not md_text:
        raise HTTPException(400, "内容为空，无法保存")
    ws = _workspace(request)
    title = (body.get("title") or "手动保存的总结").strip()[:60]
    file_names = [str(x)[:120] for x in (body.get("files") or [])][:20]
    summary_id = ws.save_summary(md_text, title)
    ws.add_summary_history(summary_id, title, file_names, "", "manual")
    return {"summary_id": summary_id}


@app.get("/api/history/qa")
async def qa_history(request: Request):
    return {"items": _workspace(request).qa_sessions()}


@app.get("/api/history/qa/{session_id}")
async def qa_history_item(request: Request, session_id: str):
    s = _workspace(request).qa_session(session_id)
    if not s:
        raise HTTPException(404, "该会话不存在（可能已被删除）")
    # 助手消息渲染成 HTML（已消毒），前端直接展示
    turns = [{"role": t["role"], "content": t["content"],
              **({"html": _render_html(t["content"])} if t["role"] == "assistant" else {})}
             for t in s.get("turns", [])]
    return {**s, "turns": turns}


@app.delete("/api/history/qa/{session_id}")
async def qa_history_delete(request: Request, session_id: str):
    if not _workspace(request).qa_delete(session_id):
        raise HTTPException(404, "该会话不存在")
    return {"ok": True}


# ---- 无状态渲染/导出 ----------------------------------------------------------
@app.post("/api/render")
async def render(body: dict):
    return {"html": _render_html(body.get("markdown") or "")}


@app.post("/api/export/pdf")
async def export_pdf(request: Request, body: dict):
    md_text = (body.get("markdown") or "").strip()
    title = (body.get("title") or "文档总结").strip()[:60]
    if not md_text:
        raise HTTPException(400, "内容为空，无法导出")
    import anyio, tempfile
    fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        await anyio.to_thread.run_sync(markdown_to_pdf, md_text, tmp_path, title)
        with open(tmp_path, "rb") as f:
            data = f.read()
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
    return _bytes_download(data, f"{title}.pdf", "application/pdf")


@app.post("/api/export/mindmap")
async def export_mindmap(request: Request, body: dict):
    md_text = (body.get("markdown") or "").strip()
    title = (body.get("title") or "思维导图").strip()[:60]
    if not md_text:
        raise HTTPException(400, "内容为空，无法生成思维导图")
    import tempfile
    fd, tmp_path = tempfile.mkstemp(suffix=".html")
    os.close(fd)
    try:
        markdown_to_mindmap_html(md_text, tmp_path, title)
        with open(tmp_path, "r", encoding="utf-8") as f:
            data = f.read()
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
    return HTMLResponse(data, headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(title + '.html')}"
    })


# ---- 静态资源 ----------------------------------------------------------------
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---- 辅助函数 ----------------------------------------------------------------
def _render_html(md_text: str) -> str:
    """markdown -> 消毒后的 HTML。

    python-markdown 会原样放行文档内嵌的 <script>/<iframe>，
    公网站点必须在返回给浏览器前用 allowlist 过滤（nh3/ammonia）。
    """
    html = md_lib.markdown(md_text, extensions=["tables", "fenced_code"])
    if nh3 is not None:
        html = nh3.clean(html)
    return html


def _sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _content_disposition(filename: str) -> str:
    quoted = urllib.parse.quote(filename)
    return f"attachment; filename*=UTF-8''{quoted}"


def _file_download(path: str, filename: str) -> FileResponse:
    return FileResponse(path, filename=os.path.basename(filename),
                        headers={"Content-Disposition": _content_disposition(filename)})


def _bytes_download(data: bytes, filename: str, media_type: str) -> Response:
    return Response(data, media_type=media_type,
                    headers={"Content-Disposition": _content_disposition(filename)})


# ---- 后台清理（逻辑在 lifespan 中）-------------------------------------------


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="info")
