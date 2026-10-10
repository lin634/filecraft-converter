const api = require('../../utils/api');
const fmt = require('../../utils/fmt');

const ALLOWED = ['docx', 'pptx', 'xlsx', 'pdf'];

Page({
  data: {
    files: [],
    filtered: [],
    keyword: '',
    selected: {}, // id -> true
    selectedCount: 0,
    loading: false,
    uploading: false,
    converting: false,
    loaded: false
  },

  onShow() {
    if (!api.getAuth()) {
      wx.reLaunch({ url: '/pages/login/index' });
      return;
    }
    this.refresh();
  },

  onPullDownRefresh() {
    this.refresh().finally(() => wx.stopPullDownRefresh());
  },

  async refresh() {
    this.setData({ loading: true });
    try {
      const res = await api.request('/api/files');
      const files = (res.files || []).map((f) => this.decorate(f));
      this.setData({ files, loaded: true });
      this.applyFilter();
    } catch (e) {
      wx.showToast({ title: e.message || '加载失败', icon: 'none' });
    } finally {
      this.setData({ loading: false });
    }
  },

  decorate(f) {
    return Object.assign({}, f, {
      badge: fmt.extBadge(f.name),
      color: fmt.extColor(f.name),
      sizeText: fmt.formatBytes(f.size),
      mdSizeText: f.converted ? fmt.formatBytes(f.md_size) : ''
    });
  },

  applyFilter() {
    const kw = this.data.keyword.trim().toLowerCase();
    const filtered = kw
      ? this.data.files.filter((f) => f.name.toLowerCase().includes(kw))
      : this.data.files;
    this.setData({ filtered });
  },

  onSearch(e) {
    this.setData({ keyword: e.detail.value });
    this.applyFilter();
  },

  toggle(e) {
    const id = e.currentTarget.dataset.id;
    const selected = Object.assign({}, this.data.selected);
    if (selected[id]) delete selected[id];
    else selected[id] = true;
    this.setData({ selected, selectedCount: Object.keys(selected).length });
  },

  /** 全选 / 取消全选（仅当前筛选结果） */
  toggleAll() {
    const all = this.data.filtered.length > 0
      && this.data.filtered.every((f) => this.data.selected[f.id]);
    const selected = Object.assign({}, this.data.selected);
    this.data.filtered.forEach((f) => {
      if (all) delete selected[f.id];
      else selected[f.id] = true;
    });
    this.setData({ selected, selectedCount: Object.keys(selected).length });
  },

  // ---- 上传 -------------------------------------------------------------
  async upload() {
    const self = this;
    wx.chooseMessageFile({
      count: 10,
      type: 'file',
      // extension 不带点；安卓端大小写敏感，两种都列出
      extension: ALLOWED.concat(ALLOWED.map((x) => x.toUpperCase())),
      success(res) {
        self.uploadMany(res.tempFiles || []);
      },
      fail(err) {
        if (err.errMsg && err.errMsg.includes('cancel')) return;
        // 某些机型不支持 extension 过滤，退化为不限类型再自行校验
        wx.chooseMessageFile({
          count: 10,
          type: 'file',
          success(res2) {
            self.uploadMany(res2.tempFiles || []);
          }
        });
      }
    });
  },

  async uploadMany(tempFiles) {
    const fsm = wx.getFileSystemManager();
    const picked = [];
    const nameCount = {};
    let skipped = 0;
    for (const tf of tempFiles) {
      const name = tf.name || tf.path.split('/').pop();
      const ext = (name.split('.').pop() || '').toLowerCase();
      if (!ALLOWED.includes(ext) || !tf.size) {
        skipped += 1;
        continue;
      }
      // 复制到用户目录、用原始文件名命名，保证服务端收到的
      // multipart filename 是真实文件名（wx.uploadFile 用路径末段）
      nameCount[name] = (nameCount[name] || 0) + 1;
      let stored = name;
      if (nameCount[name] > 1) {
        const dot = name.lastIndexOf('.');
        stored = dot > 0
          ? `${name.slice(0, dot)}(${nameCount[name]})${name.slice(dot)}`
          : `${name}(${nameCount[name]})`;
      }
      const dst = `${wx.env.USER_DATA_PATH}/${stored}`;
      try {
        fsm.copyFileSync(tf.path, dst);
        picked.push({ path: dst, name: stored, temp: true });
      } catch (e) {
        skipped += 1;
      }
    }
    if (!picked.length) {
      wx.showToast({ title: `没有可上传的文件（仅支持 ${ALLOWED.join('/')}）`, icon: 'none' });
      return;
    }
    this.setData({ uploading: true });
    wx.showLoading({ title: `上传中 0/${picked.length}`, mask: true });
    const errors = [];
    let done = 0;
    for (const f of picked) {
      try {
        // eslint-disable-next-line no-await-in-loop
        const res = await api.uploadFile(f.path, f.name);
        (res.errors || []).forEach((er) => errors.push(`${er.name}：${er.error}`));
      } catch (e) {
        errors.push(`${f.name}：${e.message}`);
      }
      done += 1;
      wx.showLoading({ title: `上传中 ${done}/${picked.length}`, mask: true });
      if (f.temp) {
        try { fsm.unlinkSync(f.path); } catch (e) { /* 忽略 */ }
      }
    }
    wx.hideLoading();
    this.setData({ uploading: false });
    if (errors.length) {
      wx.showModal({ title: '部分文件上传失败', content: errors.join('\n'), showCancel: false });
    } else {
      wx.showToast({ title: `已上传 ${picked.length} 个文件`, icon: 'success' });
    }
    this.refresh();
  },

  // ---- 转换 -------------------------------------------------------------
  async convertSelected() {
    const ids = Object.keys(this.data.selected);
    if (!ids.length) {
      wx.showToast({ title: '请先勾选文件', icon: 'none' });
      return;
    }
    this.setData({ converting: true });
    wx.showLoading({ title: '正在转换…', mask: true });
    try {
      const res = await api.request('/api/convert', { method: 'POST', data: { ids } });
      wx.hideLoading();
      const fail = (res.results || []).filter((r) => !r.ok);
      if (fail.length) {
        wx.showModal({
          title: `${res.results.length - fail.length} 个转换成功，${fail.length} 个失败`,
          content: fail.map((r) => `${r.name}：${r.error}`).join('\n'),
          showCancel: false
        });
      } else {
        wx.showToast({ title: `转换完成（${res.results.length}）`, icon: 'success' });
      }
      this.setData({ selected: {}, selectedCount: 0 });
      this.refresh();
    } catch (e) {
      wx.hideLoading();
      wx.showToast({ title: e.message || '转换失败', icon: 'none' });
    } finally {
      this.setData({ converting: false });
    }
  },

  // ---- 删除 -------------------------------------------------------------
  deleteSelected() {
    const ids = Object.keys(this.data.selected);
    if (!ids.length) {
      wx.showToast({ title: '请先勾选文件', icon: 'none' });
      return;
    }
    wx.showModal({
      title: '删除文件',
      content: `确定删除选中的 ${ids.length} 个文件？转换结果一并删除。`,
      confirmColor: '#dc2626',
      success: async (res) => {
        if (!res.confirm) return;
        wx.showLoading({ title: '删除中…', mask: true });
        try {
          // eslint-disable-next-line no-await-in-loop
          for (const id of ids) await api.request(`/api/files/${id}`, { method: 'DELETE' });
          wx.hideLoading();
          wx.showToast({ title: '已删除', icon: 'success' });
          this.setData({ selected: {}, selectedCount: 0 });
          this.refresh();
        } catch (e) {
          wx.hideLoading();
          wx.showToast({ title: e.message || '删除失败', icon: 'none' });
        }
      }
    });
  },

  // ---- 预览 -------------------------------------------------------------
  async openFile(e) {
    const file = this.data.files.find((f) => f.id === e.currentTarget.dataset.id);
    if (!file) return;
    if (!file.converted) {
      this.previewRaw(file);
      return;
    }
    wx.showActionSheet({
      itemList: ['预览 Markdown', '预览原文件', '复制 Markdown'],
      success: (res) => {
        if (res.tapIndex === 0) this.previewMd(file);
        else if (res.tapIndex === 1) this.previewRaw(file);
        else this.copyMd(file);
      }
    });
  },

  previewMd(file) {
    wx.navigateTo({ url: `/pages/doc-view/index?type=file&id=${file.id}` });
  },

  async copyMd(file) {
    try {
      const res = await api.request(`/api/files/${file.id}/markdown`);
      wx.setClipboardData({ data: res.md || '' });
    } catch (e) {
      wx.showToast({ title: e.message || '获取失败', icon: 'none' });
    }
  },

  /** 原文件下载后用系统预览（openDocument 支持 pdf/docx/xlsx/pptx） */
  async previewRaw(file) {
    const ext = (file.ext || '').replace('.', '').toLowerCase();
    wx.showLoading({ title: '下载中…', mask: true });
    try {
      const res = await api.downloadFile(`/api/files/${file.id}/raw`);
      const fsm = wx.getFileSystemManager();
      const dst = `${wx.env.USER_DATA_PATH}/preview_${Date.now()}.${ext || 'dat'}`;
      try { fsm.unlinkSync(dst); } catch (e) { /* 不存在忽略 */ }
      fsm.copyFileSync(res.tempFilePath, dst);
      wx.hideLoading();
      wx.openDocument({
        filePath: dst,
        fileType: ext,
        showMenu: true,
        fail: () => wx.showToast({ title: '该格式暂不支持在线预览', icon: 'none' })
      });
    } catch (e) {
      wx.hideLoading();
      wx.showToast({ title: e.message || '下载失败', icon: 'none' });
    }
  }
});
