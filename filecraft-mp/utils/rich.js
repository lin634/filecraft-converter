/**
 * 服务端返回的消毒 HTML（python-markdown + nh3）→ rich-text 友好 HTML。
 *
 * rich-text 只认内联样式，不认 class；这里给常见标签注入内联样式，
 * 让文档渲染有基本的排版（标题/表格/引用/代码块等）。
 * 服务端 nh3 已剥掉 style 属性，所以直接匹配裸标签即可。
 */
const STYLES = {
  h1: 'font-size:40rpx;font-weight:700;color:#111827;margin:28rpx 0 14rpx;line-height:1.4;',
  h2: 'font-size:36rpx;font-weight:700;color:#111827;margin:26rpx 0 12rpx;line-height:1.4;',
  h3: 'font-size:32rpx;font-weight:700;color:#1f2328;margin:22rpx 0 10rpx;',
  h4: 'font-size:30rpx;font-weight:700;color:#1f2328;margin:20rpx 0 8rpx;',
  h5: 'font-size:28rpx;font-weight:700;color:#1f2328;',
  h6: 'font-size:28rpx;font-weight:700;color:#6b7280;',
  p: 'margin:12rpx 0;',
  table: 'border-collapse:collapse;width:100%;margin:16rpx 0;font-size:24rpx;',
  th: 'border:1px solid #d1d5db;background:#f9fafb;padding:10rpx 12rpx;text-align:left;font-weight:600;',
  td: 'border:1px solid #d1d5db;padding:10rpx 12rpx;',
  ul: 'margin:12rpx 0;padding-left:44rpx;',
  ol: 'margin:12rpx 0;padding-left:44rpx;',
  li: 'margin:6rpx 0;',
  blockquote: 'margin:16rpx 0;padding:12rpx 20rpx;border-left:6rpx solid #93c5fd;background:#f8fafc;color:#4b5563;',
  pre: 'background:#f6f8fa;padding:16rpx;border-radius:8rpx;margin:12rpx 0;font-size:24rpx;white-space:pre-wrap;word-break:break-all;',
  code: 'background:#eef1f5;padding:2rpx 8rpx;border-radius:6rpx;font-size:26rpx;',
  hr: 'border:none;border-top:2rpx solid #e5e7eb;margin:24rpx 0;',
  a: 'color:#2563eb;',
  img: 'max-width:100%;'
};

function prettifyHtml(html) {
  let out = String(html || '');
  Object.keys(STYLES).forEach((tag) => {
    const re = new RegExp(`<${tag}(\\s|>)`, 'gi');
    out = out.replace(re, `<${tag} style="${STYLES[tag]}"$1`);
  });
  return out;
}

/** 转义 wxml 插值里的内容不需要（rich-text nodes 字符串会自行解析） */
module.exports = { prettifyHtml };
