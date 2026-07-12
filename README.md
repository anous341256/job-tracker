# Job Tracker

基于 Django 5.2 和 MySQL 8.4 的多用户求职管理系统。

## 本地启动

```powershell
cd "D:\New project"
powershell -ExecutionPolicy Bypass -File .\scripts\start-mysql.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start-web.ps1
```

访问 `http://127.0.0.1:8000/`。后台地址为 `http://127.0.0.1:8000/admin/`。

## 测试

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test --keepdb
```

## 邮件与邮箱账户

- 系统提醒由 `.env` 中的 SMTP 设置发送；开发默认输出到控制台。
- Gmail 回调地址：`http://127.0.0.1:8000/email/callback/gmail/`
- Outlook 回调地址：`http://127.0.0.1:8000/email/callback/outlook/`
- 在 Google Cloud 和 Microsoft Entra 创建 OAuth 应用后，将客户端 ID/Secret 写入 `.env`。
- OAuth token 使用 `OAUTH_ENCRYPTION_KEY` 加密，禁止在已有数据后更换该密钥。

## 后台任务

生产或持续运行的开发环境需要 Redis。配置 Redis 后，将 `CELERY_TASK_ALWAYS_EAGER=False`，分别启动：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-worker.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start-beat.ps1
```

当前电脑没有检测到 Redis 或 Docker，因此本地 `.env` 使用 eager 模式；普通页面可完整使用，但定时提醒和自动邮箱同步需要 Redis worker/beat 常驻后才会自动执行。页面上的手动邮箱同步不依赖 Celery。

## 数据与隐私

- 所有业务查询都按当前用户过滤。
- 私有附件下载会校验所有者。
- `.env`、`media`、MySQL 数据和 OAuth token 不进入 Git。
- 数据模型基线见 `docs/data-model.md`。
