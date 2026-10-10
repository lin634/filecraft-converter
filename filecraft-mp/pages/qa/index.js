const api = require('../../utils/api');
const { prettifyHtml } = require('../../utils/rich');
const fmt = require('../../utils/fmt');

Page({
  data: {
    selectedIds: [],
    selectedNames: [],
    messages: [], // {role:'user'|'assistant', content, html}
    inputValue: '',
    sending: false,
    sessionId: '',
    scrollInto: '',
    // 会话历史弹层
    historyVisible: false,
    historyLoading: false,
    sessions: []
  },

  onShow() {
    if (!api.getAuth()) {
      wx.reLaunch({ url: '/pages/login/index' });
      return;
    }
    // 从「历史」页点会话跳转过来（switchTab 不能带参）
    const app = getApp();
    if (app.globalData.pendingQaSession) {
      const sid = app.globalData.pendingQaSession;
      app.globalData.pendingQaSession = '';
      this.loadSessionById(sid);
    }
  },

  noopStop() {},

  openPicker() {
    this.selectComponent('#picker').open(this.data.selectedIds);
  },

  onPicked(e) {
    const ids = e.detail.ids || [];
    // 换文件后开新会话，避免旧会话上下文与新文档混淆
    const filesChanged = ids.join() !== this.data.selectedIds.join();
    this.setData({
      selectedIds: ids,
      selectedNames: ids.map((id) => {
        const f = this.selectComponent('#picker').data.files.find((x) => x.id === id);
        return f ? f.name : id;
      })
    });
    if (filesChanged && this.data.messages.length) {
      this.newSession(false);
      wx.showToast({ title: '文档已更换，开始新会话', icon: 'none' });
    }
  },

  onInput(e) {
    this.setData({ inputValue: e.detail.value });
  },

  newSession(toast) {
    this.setData({ messages: [], sessionId: '', scrollInto: '' });
    if (toast) wx.showToast({ title: '已开启新会话', icon: 'none' });
  },

  async send() {
    const question = this.data.inputValue.trim();
    if (!question || this.data.sending) return;
    if (!this.data.selectedIds.length) {
      wx.showToast({ title: '请先选择文档', icon: 'none' });
      return;
    }
    const messages = this.data.messages.concat({ role: 'user', content: question });
    const assistantMsg = { role: 'assistant', content: '', html: '<p style="color:#9ca3af">思考中…</p>' };
    this.setData({
      messages: messages.concat([assistantMsg]),
      inputValue: '',
      sending: true,
      scrollInto: `m${messages.length}`
    });
    try {
      const history = messages
        .filter((m) => m.content)
        .slice(-12)
        .map((m) => ({ role: m.role, content: m.content }));
      const res = await api.request('/api/qa', {
        method: 'POST',
        data: {
          ids: this.data.selectedIds,
          question,
          history,
          session_id: this.data.sessionId
        },
        timeout: 180000
      });
      const msgs = this.data.messages.slice();
      msgs[msgs.length - 1] = {
        role: 'assistant',
        content: res.answer || '',
        html: prettifyHtml(res.html || '')
      };
      this.setData({
        messages: msgs,
        sessionId: res.session_id || this.data.sessionId,
        scrollInto: `m${msgs.length - 1}`
      });
    } catch (e) {
      const msgs = this.data.messages.slice();
      msgs[msgs.length - 1] = {
        role: 'assistant',
        content: '',
        html: `<p style="color:#dc2626">${e.message || '请求失败'}</p>`
      };
      this.setData({ messages: msgs });
    } finally {
      this.setData({ sending: false });
    }
  },

  copyMessage(e) {
    const idx = e.currentTarget.dataset.index;
    const msg = this.data.messages[idx];
    if (!msg || !msg.content) return;
    wx.setClipboardData({ data: msg.content });
  },

  // ---- 会话历史 -----------------------------------------------------------
  async openHistory() {
    this.setData({ historyVisible: true, historyLoading: true });
    try {
      const res = await api.request('/api/history/qa');
      this.setData({
        sessions: (res.items || []).map((s) => Object.assign({}, s, {
          timeText: fmt.shortTime(s.time)
        }))
      });
    } catch (e) {
      wx.showToast({ title: e.message || '加载失败', icon: 'none' });
    } finally {
      this.setData({ historyLoading: false });
    }
  },

  closeHistory() {
    this.setData({ historyVisible: false });
  },

  async loadSession(e) {
    this.loadSessionById(e.currentTarget.dataset.id);
  },

  async loadSessionById(sid) {
    try {
      const s = await api.request(`/api/history/qa/${sid}`);
      const messages = (s.turns || []).map((t) => ({
        role: t.role,
        content: t.content,
        html: t.role === 'assistant' ? prettifyHtml(t.html || '') : ''
      }));
      this.setData({
        messages,
        sessionId: s.id || sid,
        historyVisible: false,
        scrollInto: `m${Math.max(messages.length - 1, 0)}`
      });
      wx.showToast({ title: '已载入会话', icon: 'none' });
    } catch (err) {
      wx.showToast({ title: err.message || '载入失败', icon: 'none' });
    }
  },

  deleteSession(e) {
    const sid = e.currentTarget.dataset.id;
    wx.showModal({
      title: '删除会话',
      content: '确定删除该问答会话？',
      confirmColor: '#dc2626',
      success: async (res) => {
        if (!res.confirm) return;
        try {
          await api.request(`/api/history/qa/${sid}`, { method: 'DELETE' });
          this.setData({
            sessions: this.data.sessions.filter((x) => x.id !== sid)
          });
          if (this.data.sessionId === sid) this.setData({ sessionId: '' });
        } catch (err) {
          wx.showToast({ title: err.message || '删除失败', icon: 'none' });
        }
      }
    });
  }
});
