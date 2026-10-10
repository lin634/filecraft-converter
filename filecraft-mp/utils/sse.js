/**
 * AI 总结的 SSE 客户端。
 *
 * 服务端 /api/summarize 用 text/event-stream 推进度。小程序里：
 * - 优先 enableChunked 分段接收，把「正在转换/正在总结第 N 段…」
 *   实时回调给页面；
 * - 兜底：某些环境分段收不到，success 时拿到完整 body
 *   （多个 `data: {...}\n\n` 事件拼在一起），统一解析后取最后的
 *   done/error 事件。结果只以 success 解析为准，保证不重不漏。
 */
const { Utf8Stream, decodeAll } = require('./utf8');
const config = require('../config');
const api = require('./api');

/** 从完整 SSE 文本中解析全部事件（按出现顺序） */
function parseEvents(text) {
  const events = [];
  const blocks = String(text).split('\n\n');
  for (const block of blocks) {
    for (const line of block.split('\n')) {
      const m = line.match(/^data:\s?(.*)$/);
      if (!m) continue;
      try {
        events.push(JSON.parse(m[1]));
      } catch (e) { /* 忽略残缺块 */ }
    }
  }
  return events;
}

/**
 * 发起总结。
 * @param {object} payload {ids: [...], extra: '附加要求'}
 * @param {object} cbs {onProgress(msg), onDone({summaryMd, html, summaryId}), onError(msg)}
 * @returns {RequestTask} 可 abort()
 */
function summarize(payload, cbs) {
  const stream = new Utf8Stream();
  let full = ''; // 分段收到的完整文本（success 兜底解析用）
  let buf = '';  // 尚未凑成完整事件的尾部
  let settled = false;

  const finishWith = (fn, arg) => {
    if (settled) return;
    settled = true;
    if (fn) fn(arg);
  };

  const handleEvent = (ev) => {
    if (!ev || settled) return;
    if (ev.type === 'progress') {
      if (cbs.onProgress) cbs.onProgress(ev.message || '');
    } else if (ev.type === 'done') {
      finishWith(cbs.onDone, {
        summaryMd: ev.summary_md || '',
        html: ev.html || '',
        summaryId: ev.summary_id || ''
      });
    } else if (ev.type === 'error') {
      finishWith(cbs.onError, ev.message || '总结失败');
    }
  };

  const auth = api.getAuth();
  const task = wx.request({
    url: `${config.BASE_URL}/api/summarize`,
    method: 'POST',
    data: payload,
    header: Object.assign({
      'Content-Type': 'application/json',
      Accept: 'text/event-stream'
    }, auth && auth.sid ? { Cookie: `fc_auth=${auth.sid}` } : {}),
    enableChunked: true,
    timeout: 300000,
    success(res) {
      if (res.statusCode === 401) {
        api.emitUnauthorized();
        finishWith(cbs.onError, '登录已过期，请重新登录');
        return;
      }
      // 完整 body 优先用分段累积的文本；某些基础库 success.data 为空
      let body = full + buf;
      if (!body && res.data) {
        body = typeof res.data === 'string' ? res.data : decodeAll(res.data);
      }
      const events = parseEvents(body);
      const last = events[events.length - 1];
      if (!last) {
        finishWith(cbs.onError, '服务器未返回结果，请稍后重试');
        return;
      }
      // 从头再走一遍事件（进度已被 settled 屏蔽，只剩最终事件生效）
      for (const ev of events) handleEvent(ev);
      finishWith(cbs.onError, '服务器未返回结果，请稍后重试');
    },
    fail(err) {
      if (settled) return;
      const msg = err && err.errMsg && err.errMsg.includes('abort')
        ? '已取消'
        : '网络不可用或服务器无法访问';
      finishWith(cbs.onError, msg);
    }
  });

  if (task && task.onChunkReceived) {
    task.onChunkReceived((res) => {
      try {
        full += stream.push(res.text || res.data || new ArrayBuffer(0));
        buf = full; // 从头切分即可（事件数量少，代价可忽略）
        const idx = buf.lastIndexOf('\n\n');
        if (idx === -1) return;
        const ready = buf.slice(0, idx + 2);
        for (const ev of parseEvents(ready)) handleEvent(ev);
      } catch (e) { /* 单块解析失败不影响后续 */ }
    });
  }

  return task;
}

module.exports = { summarize, parseEvents };
