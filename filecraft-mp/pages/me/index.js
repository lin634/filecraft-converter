const api = require('../../utils/api');

Page({
  data: {
    display: '',
    username: '',
    serverVersion: ''
  },

  onShow() {
    if (!api.getAuth()) {
      wx.reLaunch({ url: '/pages/login/index' });
      return;
    }
    const auth = api.getAuth();
    const app = getApp();
    this.setData({
      display: auth.display || auth.username,
      username: auth.username,
      serverVersion: app.globalData.serverVersion
    });
  },

  goHistory(e) {
    const type = e.currentTarget.dataset.type;
    wx.navigateTo({ url: `/pages/history/index?type=${type}` });
  },

  about() {
    const app = getApp();
    wx.showModal({
      title: '关于 FileCraft',
      content: `FileCraft 小程序 v1.0.0\n服务器版本：${app.globalData.serverVersion || '未知'}\n\n` +
        '上传 Word / PPT / Excel / PDF 转成 Markdown，' +
        'AI 总结与导出 PDF，基于文档的多轮问答。\n' +
        '文件与历史按账号隔离，服务器保留 7 天。',
      showCancel: false
    });
  },

  logout() {
    wx.showModal({
      title: '退出登录',
      content: '确定退出当前账号？',
      success: async (res) => {
        if (!res.confirm) return;
        await api.logout();
        getApp().globalData.userInfo = null;
        wx.reLaunch({ url: '/pages/login/index' });
      }
    });
  }
});
