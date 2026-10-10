/**
 * API 封装：Cookie 会话鉴权 + 统一错误处理。
 *
 * 后端（filecraft-web）用 fc_auth Cookie 做会话；小程序不会自动
 * 管理 Cookie，所以登录后把 sid 存 Storage，每次请求手动带上
 * `Cookie: fc_auth=<sid>` 头。401 时通知 app 重新登录。
 */
const config = require('../config');

const AUTH_KEY = 'fc_auth';

let unauthorizedHandler = null;

function onUnauthorized(cb) {
  unauthorizedHandler = cb;
}

/** 401 时触发全局回调（api 内部与 sse.js 用） */
function emitUnauthorized() {
  setAuth(null);
  if (unauthorizedHandler) unauthorizedHandler();
}

function getAuth() {
  return wx.getStorageSync(AUTH_KEY) || null; // {sid, username, display}
}

function setAuth(auth) {
  if (auth) wx.setStorageSync(AUTH_KEY, auth);
  else wx.removeStorageSync(AUTH_KEY);
}

function authHeader() {
  const auth = getAuth();
  return auth && auth.sid ? { Cookie: `fc_auth=${auth.sid}` } : {};
}

/** 从登录响应头解析 fc_auth=sid（字段名大小写/多值都要兼容） */
function parseSidFromHeaders(header) {
  if (!header) return '';
  let raw = header['Set-Cookie'] || header['set-cookie'] || '';
  if (Array.isArray(raw)) raw = raw.join(';');
  const m = String(raw).match(/fc_auth=([^;,\s]+)/);
  return m ? m[1] : '';
}

/**
 * 基础 JSON 请求。resolve 业务数据；reject Error(message)。
 * FastAPI 错误体是 {detail: "..."}，直接作为提示语。
 */
function request(path, options) {
  const opts = options || {};
  return new Promise((resolve, reject) => {
    wx.request({
      url: config.BASE_URL + path,
      method: opts.method || 'GET',
      data: opts.data,
      header: Object.assign(
        { 'Content-Type': 'application/json' },
        authHeader(),
        opts.header || {}
      ),
      responseType: opts.responseType || 'text',
      timeout: opts.timeout,
      success(res) {
        if (res.statusCode === 401) {
          emitUnauthorized();
          reject(new Error('登录已过期，请重新登录'));
          return;
        }
        // 二进制响应（如导出 PDF）直接透传
        if (opts.responseType === 'arraybuffer') {
          if (res.statusCode >= 200 && res.statusCode < 300) {
            resolve({ data: res.data, header: res.header, statusCode: res.statusCode });
          } else {
            let msg = `请求失败（${res.statusCode}）`;
            try {
              const utf8 = require('./utf8');
              const err = JSON.parse(utf8.decodeAll(res.data));
              if (err.detail) msg = err.detail;
            } catch (e) { /* 保留默认提示 */ }
            reject(new Error(msg));
          }
          return;
        }
        let body = res.data;
        if (typeof body === 'string') {
          try {
            body = JSON.parse(body);
          } catch (e) { /* 保持字符串 */ }
        }
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(body);
        } else {
          const msg = (body && body.detail) || `请求失败（${res.statusCode}）`;
          const err = new Error(msg);
          err.statusCode = res.statusCode;
          reject(err);
        }
      },
      fail(err) {
        reject(new Error(err.errMsg && err.errMsg.includes('timed out')
          ? '请求超时，请重试'
          : '网络不可用或服务器无法访问'));
      }
    });
  });
}

/** 登录：成功后保存会话到 Storage */
function login(username, password) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${config.BASE_URL}/api/login`,
      method: 'POST',
      data: { username, password },
      header: { 'Content-Type': 'application/json' },
      success(res) {
        let body = res.data;
        if (typeof body === 'string') {
          try { body = JSON.parse(body); } catch (e) { body = null; }
        }
        if (res.statusCode !== 200 || !body || !body.ok) {
          reject(new Error((body && body.detail) || '登录失败'));
          return;
        }
        const sid = parseSidFromHeaders(res.header);
        if (!sid) {
          reject(new Error('未能取得会话，请检查服务器配置'));
          return;
        }
        const auth = { sid, username: body.username, display: body.display };
        setAuth(auth);
        resolve(auth);
      },
      fail() {
        reject(new Error('网络不可用或服务器无法访问'));
      }
    });
  });
}

function logout() {
  return request('/api/logout', { method: 'POST' }).catch(() => {}).then(() => {
    setAuth(null);
  });
}

/** multipart 上传单个文件；resolve {files, errors} */
function uploadFile(filePath, fileName) {
  return new Promise((resolve, reject) => {
    wx.uploadFile({
      url: `${config.BASE_URL}/api/upload`,
      filePath,
      name: 'files',
      formData: { filename: fileName },
      header: authHeader(),
      timeout: 300000,
      success(res) {
        let body = res.data;
        if (typeof body === 'string') {
          try { body = JSON.parse(body); } catch (e) { body = null; }
        }
        if (res.statusCode === 401) {
          emitUnauthorized();
          reject(new Error('登录已过期，请重新登录'));
          return;
        }
        if (res.statusCode >= 200 && res.statusCode < 300 && body) {
          resolve(body);
        } else {
          reject(new Error((body && body.detail) || `上传失败（${res.statusCode}）`));
        }
      },
      fail() {
        reject(new Error('上传失败：网络不可用'));
      }
    });
  });
}

/** GET 下载到临时文件（带鉴权头），resolve {tempFilePath} */
function downloadFile(path) {
  return new Promise((resolve, reject) => {
    wx.downloadFile({
      url: config.BASE_URL + path,
      header: authHeader(),
      timeout: 300000,
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve({ tempFilePath: res.tempFilePath, header: res.header });
        } else {
          reject(new Error(`下载失败（${res.statusCode}）`));
        }
      },
      fail() {
        reject(new Error('下载失败：网络不可用'));
      }
    });
  });
}

function getAuthSync() {
  return getAuth();
}

module.exports = {
  request,
  login,
  logout,
  uploadFile,
  downloadFile,
  onUnauthorized,
  emitUnauthorized,
  getAuth: getAuthSync,
  setAuth
};
