const api = require('../../utils/api');
const sse = require('../../utils/sse');
const { prettifyHtml } = require('../../utils/rich');

const PHASE = {
  idle: 'idle',       // 未开始
  running: 'running', // 总结中
  done: 'done'        // 有结果
};

Page({
  data: {
    phase: PHASE.idle,
    selectedIds: [],
    selectedNames: [],
    extra: '',
    progressText: '',
    logs: [],
    summaryMd: '',
    summaryId: '',
    richHtml: '',
    viewMode: 'edit'
  },

  _task: null,

  onShow() {
    if (!api.getAuth()) {
      wx.reLaunch({ url: '/pages/login/index' });
      return;
    }
    // 从文件页切回来时同步一下最新状态（如果正在跑就不动）
  },

  onHide() {
    // 保留后台任务继续跑（RequestTask 不随页面隐藏取消）
  },

  onUnload() {
    if (this._task) {
      try { this._task.abort(); } catch (e) { /* 忽略 */ }
    }
  },

  openPicker() {
    if (this.data.phase === PHASE.running) return;
    this.selectComponent('#picker').open(this.data.selectedIds);
  },

  onPicked(e) {
    const ids = e.detail.ids || [];
    const names = ids.map((id) => {
      const f = this.selectComponent('#picker').data.files.find((x) => x.id === id);
      return f ? f.name : id;
    });
    this.setData({ selectedIds: ids, selectedNames: names });
  },

  onExtra(e) {
    this.setData({ extra: e.detail.value });
  },

  start() {
    if (this.data.phase === PHASE.running) return;
    if (!this.data.selectedIds.length) {
      wx.showToast({ title: '请先选择文档', icon: 'none' });
      return;
    }
    this.setData({
      phase: PHASE.running,
      logs: [],
      progressText: '已提交，正在等待模型…',
      summaryMd: '',
      summaryId: '',
      richHtml: '',
      viewMode: 'edit'
    });
    const appendLog = (msg) => {
      if (!msg) return;
      const logs = this.data.logs.concat(msg);
      this.setData({ logs, progressText: msg });
    };
    const task = sse.summarize(
      { ids: this.data.selectedIds, extra: this.data.extra.trim() },
      {
        onProgress: appendLog,
        onDone: (res) => {
          this.setData({
            phase: PHASE.done,
            progressText: '总结完成',
            summaryMd: res.summaryMd,
            summaryId: res.summaryId,
            richHtml: prettifyHtml(res.html || '')
          });
        },
        onError: (msg) => {
          this.setData({
            phase: this.data.summaryMd ? PHASE.done : PHASE.idle,
            progressText: msg === '已取消' ? '已取消' : ''
          });
          if (msg !== '已取消') {
            wx.showToast({ title: msg, icon: 'none' });
          }
        }
      }
    );
    this._task = task;
  },

  cancel() {
    if (this._task) {
      try { this._task.abort(); } catch (e) { /* 忽略 */ }
    }
    this.setData({ phase: PHASE.idle, progressText: '已取消' });
  },

  onMdInput(e) {
    this.setData({ summaryMd: e.detail.value });
  },

  switchView(e) {
    this.setData({ viewMode: e.currentTarget.dataset.mode });
  },

  copyResult() {
    if (!this.data.summaryMd) return;
    wx.setClipboardData({ data: this.data.summaryMd });
  },

  /** 手动把（可能编辑过的）总结存入服务器历史 */
  async saveHistory() {
    if (!this.data.summaryMd.trim()) {
      wx.showToast({ title: '内容为空', icon: 'none' });
      return;
    }
    try {
      await api.request('/api/summaries/save', {
        method: 'POST',
        data: {
          markdown: this.data.summaryMd,
          title: `文档总结（${this.data.selectedIds.length} 份）`,
          files: this.data.selectedNames
        }
      });
      wx.showToast({ title: '已保存到历史', icon: 'success' });
    } catch (e) {
      wx.showToast({ title: e.message || '保存失败', icon: 'none' });
    }
  },

  /** 导出 PDF：二进制落盘后用系统预览/分享 */
  async exportPdf() {
    if (!this.data.summaryMd.trim()) {
      wx.showToast({ title: '内容为空', icon: 'none' });
      return;
    }
    wx.showLoading({ title: '生成 PDF…', mask: true });
    try {
      const res = await api.request('/api/export/pdf', {
        method: 'POST',
        data: { markdown: this.data.summaryMd, title: '文档总结' },
        responseType: 'arraybuffer'
      });
      const fsm = wx.getFileSystemManager();
      const dst = `${wx.env.USER_DATA_PATH}/总结_${Date.now()}.pdf`;
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
