"""账号认证：PBKDF2 口令哈希 + 每账号固定派生的工作区 ID。

- 账号存 <DATA_DIR>/accounts.json（首次启动自动创建三个测试账号）
- 登录态 Cookie 的值 = workspace_id = HMAC-SHA256(密钥, username)[:32]，
  密钥来自环境变量 FILECRAFT_SECRET，未配置时自动生成并持久化到
  <DATA_DIR>/secret.txt（权限 600）。知道用户名猜不出工作区 ID。
- 测试账号：demo（预置样例文档）、test1 / test2（空白可直接使用）
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets

import config

ACCOUNTS_PATH = os.path.join(config.DATA_DIR, "accounts.json")

TEST_ACCOUNTS = [
    {"username": "demo",  "password": "demo123",    "display": "演示账号（预置样例文档）"},
    {"username": "test1", "password": "test123456", "display": "测试账号 1（空白）"},
    {"username": "test2", "password": "test123456", "display": "测试账号 2（空白）"},
]


def _hash_password(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), 120_000,
    ).hex()


def _secret() -> str:
    env = os.environ.get("FILECRAFT_SECRET", "").strip()
    if env:
        return env
    p = os.path.join(config.DATA_DIR, "secret.txt")
    try:
        with open(p, "r", encoding="utf-8") as f:
            s = f.read().strip()
        if s:
            return s
    except OSError:
        pass
    s = secrets.token_hex(32)
    os.makedirs(config.DATA_DIR, exist_ok=True)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(s)
    return s


def _load_accounts() -> dict:
    try:
        with open(ACCOUNTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_accounts(accounts: dict) -> None:
    os.makedirs(config.DATA_DIR, exist_ok=True)
    tmp = ACCOUNTS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(accounts, f, ensure_ascii=False, indent=1)
    os.replace(tmp, ACCOUNTS_PATH)


def ensure_accounts() -> dict:
    """确保账号文件存在；首次创建内置测试账号。返回 {username: {salt, hash, display}}。"""
    accounts = _load_accounts()
    if accounts:
        return accounts
    for acc in TEST_ACCOUNTS:
        salt = secrets.token_hex(16)
        accounts[acc["username"]] = {
            "salt": salt,
            "hash": _hash_password(acc["password"], salt),
            "display": acc["display"],
        }
    _save_accounts(accounts)
    return accounts


_ACCOUNTS: dict = {}


def init() -> None:
    """进程启动时调用一次：加载/初始化账号。"""
    global _ACCOUNTS
    _ACCOUNTS = ensure_accounts()


def workspace_id_for(username: str) -> str:
    return hmac.new(_secret().encode(), username.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def valid_workspace_ids() -> set[str]:
    return {workspace_id_for(u) for u in _ACCOUNTS}


def display_name(username: str) -> str:
    return _ACCOUNTS.get(username, {}).get("display", username)


def username_by_workspace_id(workspace_id: str) -> str | None:
    for u in _ACCOUNTS:
        if workspace_id_for(u) == workspace_id:
            return u
    return None


def verify(username: str, password: str) -> bool:
    acc = _ACCOUNTS.get(username)
    if not acc:
        # 仍做一次哈希，避免用户名枚举时间差
        _hash_password(password, "00" * 16)
        return False
    return hmac.compare_digest(_hash_password(password, acc["salt"]), acc["hash"])
