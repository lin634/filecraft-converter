const api = require('../../utils/api');
const { prettifyHtml } = require('../../utils/rich');

Page({
  data: {
    type: 'file',   // file | summary
    id: '',
    title: '',
    md: '',
    richHtml: '',
    viewMode: 'preview', // preview | raw
    loading: true,
    error: ''
  },

  onLoad(query) {
    this.setData({
      type: query.type === 'summary' ? 'summary' : 'file',
      id: query.id || ''
    });
    wx.setNavigationBarTitle({
      title: this.data.type === 'summary' ? '总结详情' : '文档预览'
    });
    this.load();
  },

  async load() {
    const path = this.data.type === 'summary'
      ? `/api/history/summaries/${this.data.id}`
      : `/api/files/${this.data.id}/markdown`;
    try {
      const res = await api.request(path);
      this.setData({
        md: res.md || '',
        richHtml: prettifyHtml(res.html || ''),
        title: res.name || '',
        loading: false
      });
    } catch (e) {
      this.setData({ loading: false, error: e.message || '加载失败' });
    }
  },

  switchView(e) {
    this.setData({ viewMode: e.currentTarget.dataset.mode });
  },

  copyAll() {
    if (!this.data.md) return;
    wx.setClipboardData({ data: this.data.md });
  },

  async exportPdf() {
    if (!this.data.md.trim()) return;
    const title = this.data.type === 'summary'
      ? (this.data.title || '文档总结')
      : (this.data.title || '文档').replace(/\.[^.]+$/, '');
    wx.showLoading({ title: '生成 PDF…', mask: true });
    try {
      const res = await api.request('/api/export/pdf', {
        method: 'POST',
        data: { markdown: this.data.md, title },
        responseType: 'arraybuffer'
      });
      const fsm = wx.getFileSystemManager();
      const dst = `${wx.env.USER_DATA_PATH}/${title}_${Date.now()}.pdf`;
      try { fsm.unlinkSync(dst); } catch (e) { /* 忽略 */ }
      fsm.writeFileSync(dst, res.data, 'binary');
      wx.hideLoading();
      wx.openDocument({
        filePath: dst,
        fileType: 'pdf',
        showMenu: true,
        fail: () => wx.showToast({ title: '无法打开 PDF', icon: 'none' })
      });
    } catch (e) {
      wx.hideLoading();
      wx.showToast({ title: e.message || '导出失败', icon: 'none' });
    }
  }
});
