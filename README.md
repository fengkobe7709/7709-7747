# CSOP Premium Monitor

监控 7709 / 7747 的 CSOP 官网 iNAV、Market Price，并计算折溢价。

## 本地运行

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

打开：http://127.0.0.1:8000

## Render 部署

Build Command:

```bash
pip install -r requirements.txt
```

Start Command:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```
