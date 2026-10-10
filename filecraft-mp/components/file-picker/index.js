const api = require('../../utils/api');
const fmt = require('../../utils/fmt');

/**
 * 文件多选弹层：总结页 / 问答页共用。
 * open(selectedIds) 打开；confirm 事件带选中的 id 数组。
 */
Component({
  options: {
    // 允许页面/app.wxss 的公共样式（.muted/.empty）作用于组件内部
    styleIsolation: 'apply-shared'
  },

  data: {
    visible: false,
    files: [],
    checked: {}, // id -> true
    loading: false
  },

  methods: {
    noop() {},

    open(selectedIds) {
      this.setData({ visible: true, checked: {} });
      (selectedIds || []).forEach((id) => {
        this.setData({ [`checked.${id}`]: true });
      });
      this.load();
    },

    async load() {
      this.setData({ loading: true });
      try {
        const res = await api.request('/api/files');
        const files = (res.files || []).map((f) => Object.assign({}, f, {
          badge: fmt.extBadge(f.name),
          color: fmt.extColor(f.name),
          sizeText: fmt.formatBytes(f.size)
        }));
        this.setData({ files });
      } catch (e) {
        wx.showToast({ title: e.message || '加载文件失败', icon: 'none' });
      } finally {
        this.setData({ loading: false });
      }
    },

    toggle(e) {
      const id = e.currentTarget.dataset.id;
      this.setData({ [`checked.${id}`]: !this.data.checked[id] });
    },

    close() {
      this.setData({ visible: false });
    },

    confirm() {
      const ids = Object.keys(this.data.checked).filter((k) => this.data.checked[k]);
      this.triggerEvent('confirm', { ids });
      this.setData({ visible: false });
    }
  }
});
