# 语音约碰面地点

第一版：同一座城市内，用语音帮两个人找中间的碰面地点。

当前进度：项目骨架 + 后端 `GET /health` + 可打开的前端基础页。录音和其他业务接口尚未实现。

## 环境

- Python 3.11
- Node.js 22.12 及以上的 22.x
- 后端 `http://localhost:8003`
- 前端 `http://localhost:5175`

## 后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8003
```

密钥可先不填。没有 `.env` 时，健康检查也应返回成功。

## 前端

```powershell
cd frontend
npm install
npm run dev
```

浏览器打开 `http://localhost:5175`（不要用 `127.0.0.1`，CORS 只放行 localhost）。

## 验证健康检查

- 浏览器：`http://localhost:8003/health`
- FastAPI 文档：`http://localhost:8003/docs`，执行 `GET /health`
- 前端页打开后会请求一次健康检查

预期：HTTP 200，JSON 含 `request_id` 和 `data.status = "ok"`。

## 模拟测试

在 `backend` 目录、已激活虚拟环境后：

```powershell
pytest
```

当前仅覆盖 `GET /health`。Mock 通过不能证明真实外部服务已跑通；本阶段也尚未接入外部服务。
