module.exports = {
  apps: [
    {
      name: 'filecraft-web',                 // 与 vibenav 不同的独立进程名
      script: 'server.py',
      cwd: '/var/www/filecraft',
      interpreter: '/var/www/filecraft/venv/bin/python',  // 用项目自己的 venv
      instances: 1,
      exec_mode: 'fork',
      max_memory_restart: '300M',
      autorestart: true,
      restart_delay: 3000,
      error_file: '/var/log/filecraft-web/error.log',
      out_file: '/var/log/filecraft-web/out.log',
      time: true,
    },
  ],
};
