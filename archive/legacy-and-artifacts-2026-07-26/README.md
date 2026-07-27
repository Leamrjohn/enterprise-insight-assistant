# 归档说明

本目录保存不参与当前 Enterprise Insight Assistant 网站运行的历史示例、测试录制和临时产物：

- 根目录 Flask/Docker 示例：`app.py`、`Dockerfile`、`requirements.txt`；当前网站使用 `backend/` 的 FastAPI 和 Dockerfile。
- `docker-learning/`：独立 Docker 学习示例。
- `output/`：历史简历和页面截图。
- `tmp/`：历史测试数据、PDF 渲染和 Worker 日志。
- `.impeccable/`、`.playwright-cli/`、`frontend-playwright-recordings/`：设计与浏览器自动化的本地录制产物。

归档时仍在被运行中服务写入的三个日志保留于项目根目录 `tmp/`：
`frontend-api-8001.err.log`、`frontend-api-8001.out.log`、`frontend-vite.log`。
