const api = require('../../utils/api');
const fmt = require('../../utils/fmt');

Page({
  data: {
    type: 'summary', // summary | qa
    items: [],
    loading: false,
    loaded: false
  },

  onLoad(query) {
    const type = query.type === 'qa' ? 'qa' : 'summary';
    this.setData({ type });
    wx.setNavigationBarTitle({
      title: type === 'qa' ? '问答历史' : '总结历史'
    });
  },

  onShow() {
    if (!api.getAuth()) {
      wx.reLaunch({ url: '/pages/login/index' });
      return;
    }
    this.load();
  },

  async load() {
    this.setData({ loading: true });
    try {
      const path = this.data.type === 'qa'
        ? '/api/history/qa'
        : '/api/history/summaries';
      const res = await api.request(path);
      const items = (res.items || []).map((it) => Object.assign({}, it, {
        timeText: fmt.shortTime(it.time),
        filesText: (it.files || []).length ? it.files.join('、') : '',
        badge: this.data.type === 'summary'
          ? (it.source === 'manual' ? '手动' : 'AI')
          : `${it.turns_count || 0} 轮`
      }));
      this.setData({ items, loaded: true });
    } catch (e) {
      wx.showToast({ title: e.message || '加载失败', icon: 'none' });
    } finally {
      this.setData({ loading: false });
    }
  },

  openItem(e) {
    const { id } = e.currentTarget.dataset;
    if (this.data.type === 'summary') {
      wx.navigateTo({ url: `/pages/doc-view/index?type=summary&id=${id}` });
      return;
    }
    // qa 页是 tabBar 页面，switchTab 不能带参，走全局暂存
    getApp().globalData.pendingQaSession = id;
    wx.switchTab({ url: '/pages/qa/index' });
  },

  deleteItem(e) {
    const { id } = e.currentTarget.dataset;
    wx.showModal({
      title: '删除记录',
      content: this.data.type === 'qa' ? '确定删除该问答会话？' : '确定删除该总结？',
      confirmColor: '#dc2626',
      success: async (res) => {
        if (!res.confirm) return;
        try {
          await api.request(
            this.data.type === 'qa'
              ? `/api/history/qa/${id}`
              : `/api/history/summaries/${id}`,
            { method: 'DELETE' }
          );
          this.setData({ items: this.data.items.filter((x) => x.id !== id) });
          wx.showToast({ title: '已删除', icon: 'success' });
        } catch (err) {
          wx.showToast({ title: err.message || '删除失败', icon: 'none' });
        }
      }
    });
  }
});
