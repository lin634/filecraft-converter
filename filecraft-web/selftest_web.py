"""filecraft-web 端到端自测 v1.1：登录鉴权 + 账号隔离 + 历史记录 + 全功能。

用法（先启动 python server.py，再运行）：
    python selftest_web.py
"""
from __future__ import annotations

import io
import json
import os
import sys
import zipfile

import httpx

BASE = os.environ.get("FC_TEST_BASE", "http://127.0.0.1:3100")
TESTDATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "filecraft", "testdata")

results: list[tuple[bool, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((ok, name, detail))
    print(("✓" if ok else "✗"), name, (f"—— {detail}" if detail else ""))


def sample_bytes(name: str) -> bytes:
    with open(os.path.join(TESTDATA, name), "rb") as f:
        return f.read()


def main() -> int:
    anon = httpx.Client(base_url=BASE, timeout=180, follow_redirects=False)

    # ---- 0. 未登录拦截 ----
    r = anon.get("/api/files")
    check("未登录 API 返回 401", r.status_code == 401)
    r = anon.get("/")
    check("未登录页面跳转 /login", r.status_code == 302 and "/login" in r.headers.get("location", ""))
    r = anon.get("/login")
    check("登录页可访问", r.status_code == 200 and "FileCraft" in r.text)
    r = anon.post("/api/login", json={"username": "test1", "password": "wrong"})
    check("错误密码被拒绝", r.status_code == 401)

    # ---- 1. 登录 test1（空白账号）----
    c = httpx.Client(base_url=BASE, timeout=180, follow_redirects=False)
    r = c.post("/api/login", json={"username": "test1", "password": "test123456"})
    check("test1 登录", r.status_code == 200)
    r = c.get("/api/me")
    check("会话有效(/api/me)", r.status_code == 200 and r.json()["username"] == "test1")
    check("test1 工作区为空", c.get("/api/files").json()["files"] == [])

    # ---- 2. 上传 + 转换 ----
    names = ["report.docx", "sales.xlsx"]
    files = [("files", (n, sample_bytes(n))) for n in names]
    up = c.post("/api/upload", files=files).json()
    ids = [f["id"] for f in up["files"]]
    check("上传2个文件", len(ids) == 2)
    conv = c.post("/api/convert", json={"ids": ids}).json()["results"]
    check("批量转换", all(x["ok"] for x in conv), f"{sum(x['ok'] for x in conv)}/2")

    # ---- 3. AI 总结 → 总结历史 ----
    events, buf = [], ""
    with c.stream("POST", "/api/summarize", json={"ids": ids, "extra": "100字以内"}) as r:
        check("总结SSE", r.status_code == 200)
        for chunk in r.iter_text():
            buf += chunk
            while "\n\n" in buf:
                raw, buf = buf.split("\n\n", 1)
                for line in raw.split("\n"):
                    if line.startswith("data:"):
                        events.append(json.loads(line[5:].strip()))
    done = next((e for e in events if e["type"] == "done"), None)
    check("AI总结成功", bool(done and len(done["summary_md"]) > 50))

    hist = c.get("/api/history/summaries").json()["items"]
    check("总结历史自动记录", len(hist) >= 1 and hist[0]["source"] == "ai"
          and "report.docx" in hist[0]["files"], f"{len(hist)} 条")
    item = c.get(f"/api/history/summaries/{hist[0]['id']}")
    check("载入历史总结", item.status_code == 200 and len(item.json()["md"]) > 50)
    r = c.post("/api/summaries/save", json={"markdown": "# 手动内容\n\n测试", "title": "手动保存", "files": names})
    check("手动存入历史", r.status_code == 200)
    hist2 = c.get("/api/history/summaries").json()["items"]
    check("手动条目在列", hist2[0]["source"] == "manual")
    c.delete(f"/api/history/summaries/{hist2[0]['id']}")
    check("删除历史总结", c.get("/api/history/summaries").json()["items"][0]["id"] == hist[0]["id"])

    # ---- 4. 问答（两轮，同一会话）→ 会话历史 ----
    r = c.post("/api/qa", json={"ids": ids, "question": "文档主题是什么？", "history": []})
    sid = r.json()["session_id"]
    check("问答第一轮", r.status_code == 200)
    r = c.post("/api/qa", json={"ids": ids, "question": "再补充一点", "history": [
        {"role": "user", "content": "文档主题是什么？"},
        {"role": "assistant", "content": r.json()["answer"]},
    ], "session_id": sid})
    check("追问续同一会话", r.status_code == 200 and r.json()["session_id"] == sid)

    qsessions = c.get("/api/history/qa").json()["items"]
    check("问答历史自动记录", len(qsessions) >= 1 and qsessions[0]["turns_count"] == 2,
          f"{len(qsessions)} 个会话")
    full = c.get(f"/api/history/qa/{sid}").json()
    check("打开会话含完整轮次", len(full["turns"]) == 4 and full["turns"][0]["role"] == "user")
    check("助手消息带消毒HTML", all("html" in t for t in full["turns"] if t["role"] == "assistant"))

    # ---- 5. test1 注销后无法访问；demo 账号预置与隔离 ----
    c.post("/api/logout")
    check("注销后 401", c.get("/api/files").status_code == 401)

    demo = httpx.Client(base_url=BASE, timeout=180, follow_redirects=False)
    demo.post("/api/login", json={"username": "demo", "password": "demo123"})
    dfiles = demo.get("/api/files").json()["files"]
    check("demo 预置样例文档", len(dfiles) == 4 and all(f["converted"] for f in dfiles),
          f"{[f['name'] for f in dfiles]}")
    check("账号隔离(demo看不到test1文件)",
          all(f["id"] not in ids for f in dfiles))
    check("账号隔离(demo历史为空)", demo.get("/api/history/qa").json()["items"] == [])

    # 收尾：清掉 test1 的测试痕迹
    c2 = httpx.Client(base_url=BASE, timeout=180)
    c2.post("/api/login", json={"username": "test1", "password": "test123456"})
    c2.delete(f"/api/history/qa/{sid}")
    for f in c2.get("/api/files").json()["files"]:
        c2.delete(f"/api/files/{f['id']}")
    hist1 = c2.get("/api/history/summaries").json()["items"]
    for it in hist1:
        c2.delete(f"/api/history/summaries/{it['id']}")
    c2.delete(f"/api/history/qa/{sid}")
    ok_clean = (c2.get("/api/files").json()["files"] == []
                and c2.get("/api/history/qa").json()["items"] == [])
    check("测试痕迹清理", ok_clean)

    anon.close(); c.close(); demo.close(); c2.close()

    print("\n========== 结果 ==========")
    failed = [x for x in results if not x[0]]
    print(f"共 {len(results)} 项，通过 {len(results) - len(failed)}，失败 {len(failed)}")
    for _, name, detail in failed:
        print(f"  ✗ {name}: {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
