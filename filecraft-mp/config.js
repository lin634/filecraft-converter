// 服务器地址：线上部署（filecraft-web，Nginx 反代）。
// 本地调试时改成 http://127.0.0.1:3100，并在开发者工具里勾选
// 「不校验合法域名、web-view（业务域名）、TLS 版本以及 HTTPS 证书」。
module.exports = {
  BASE_URL: 'https://filecraft.vibenav.xyz',
  VERSION: '1.0.0'
};
