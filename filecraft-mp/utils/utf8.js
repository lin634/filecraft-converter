/**
 * 流式 UTF-8 解码器。
 *
 * 小程序没有全局 TextDecoder（低版本基础库），而 SSE 分段
 * （onChunkReceived 的 ArrayBuffer）可能在多字节汉字中间截断，
 * 所以按字节累积、遇到不完整序列就留到下一块。
 */
function Utf8Stream() {
  this.pending = []; // 上一块遗留的不完整字节
}

Utf8Stream.prototype.push = function (buf) {
  if (!buf) return '';
  const u8 = new Uint8Array(buf);
  const bytes = this.pending.concat(Array.prototype.slice.call(u8));
  this.pending = [];
  let out = '';
  let i = 0;
  const n = bytes.length;
  while (i < n) {
    const b = bytes[i];
    let need = 0;
    if (b < 0x80) need = 1;
    else if (b >= 0xc0 && b < 0xe0) need = 2;
    else if (b >= 0xe0 && b < 0xf0) need = 3;
    else if (b >= 0xf0 && b < 0xf8) need = 4;
    else {
      // 非法字节，跳过
      i += 1;
      continue;
    }
    if (i + need > n) {
      // 序列不完整，留给下一块
      this.pending = bytes.slice(i);
      break;
    }
    let cp = 0;
    let ok = true;
    if (need === 1) {
      cp = b;
    } else {
      cp = b & (0xff >> (need + 1));
      for (let k = 1; k < need; k += 1) {
        const cb = bytes[i + k];
        if ((cb & 0xc0) !== 0x80) {
          ok = false;
          break;
        }
        cp = (cp << 6) | (cb & 0x3f);
      }
    }
    if (!ok) {
      i += 1;
      continue;
    }
    i += need;
    if (cp >= 0x10000) {
      // 代理对
      cp -= 0x10000;
      out += String.fromCharCode(0xd800 + (cp >> 10), 0xdc00 + (cp & 0x3ff));
    } else {
      out += String.fromCharCode(cp);
    }
  }
  return out;
};

/** 一次性 ArrayBuffer -> 字符串 */
function decodeAll(buf) {
  return new Utf8Stream().push(buf);
}

module.exports = { Utf8Stream, decodeAll };
