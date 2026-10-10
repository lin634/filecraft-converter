const api = require('../../utils/api');

Page({
  data: {
    username: '',
    password: '',
    loading: false,
    error: ''
  },

  onLoad() {
    // 已登录直接进文件页
    if (api.getAuth()) {
      wx.switchTab({ url: '/pages/files/index' });
    }
  },

  onInput(e) {
    const field = e.currentTarget.dataset.field;
    this.setData({ [field]: e.detail.value, error: '' });
  },

  async submit() {
    const username = this.data.username.trim();
    const password = this.data.password;
    if (!username || !password) {
      this.setData({ error: '请输入用户名和密码' });
      return;
    }
    this.setData({ loading: true, error: '' });
    try {
      const auth = await api.login(username, password);
      const app = getApp();
      app.globalData.userInfo = { username: auth.username, display: auth.display };
      wx.switchTab({ url: '/pages/files/index' });
    } catch (e) {
      this.setData({ error: e.message || '登录失败' });
    } finally {
      this.setData({ loading: false });
    }
  }
});
