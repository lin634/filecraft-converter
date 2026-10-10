/** 小的展示辅助函数 */

function formatBytes(n) {
  const v = Number(n) || 0;
  if (v < 1024) return `${v} B`;
  if (v < 1024 * 1024) return `${(v / 1024).toFixed(1)} KB`;
  return `${(v / 1024 / 1024).toFixed(1)} MB`;
}

/** 扩展名 -> 徽标文字（不含点） */
function extBadge(name) {
  const m = String(name || '').toLowerCase().match(/\.([a-z0-9]+)$/);
  return m ? m[1].toUpperCase() : '?';
}

const EXT_COLORS = {
  docx: '#2b579a',
  pptx: '#d24726',
  xlsx: '#217346',
  pdf: '#dc2626'
};

function extColor(name) {
  const m = String(name || '').toLowerCase().match(/\.([a-z0-9]+)$/);
  return (m && EXT_COLORS[m[1]]) || '#6b7280';
}

/** 历史时间字符串 "2026-09-20 01:02:03" -> "09-20 01:02" */
function shortTime(s) {
  const m = String(s || '').match(/^\d{4}-(\d{2}-\d{2}) (\d{2}:\d{2})/);
  return m ? `${m[1]} ${m[2]}` : String(s || '');
}

module.exports = { formatBytes, extBadge, extColor, shortTime };
