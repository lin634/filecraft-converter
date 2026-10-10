const api = require('./utils/api');

App({
  globalData: {
    userInfo: null, // {username, display}
    serverVersion: ''
  },

  onLaunch() {
    api.onUnauthorized(() => {
      this.globalData.userInfo = null;
      const pages = getCurrentPages();
      const cur = pages[pages.length - 1];
      if (cur && cur.route === 'pages/login/index') return;
      wx.reLaunch({ url: '/pages/login/index' });
    });
    this.checkServer();
  },

  // 探测服务可用性（不要求登录），顺便取版本号
  checkServer() {
    api.request('/api/health', { method: 'GET' })
      .then((res) => {
        this.globalData.serverVersion = res.version || '';
      })
      .catch(() => {});
  }
});
