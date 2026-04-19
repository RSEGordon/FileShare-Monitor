# FileShare + System Monitor

文件共享 + 系统监控服务，基于 Python + Flask。

## 功能

- **文件共享**：通过浏览器上传/下载文件，支持目录浏览
- **系统监控**：CPU各核心、内存、磁盘、网络、进程监控
- **OpenClaw Gateway 监控**：main / jim / hjkv 三个实例状态
- **博客导航**：内置导航栏快速访问博客

## 依赖

```
Flask
psutil
```

## 运行

```bash
pip install flask psutil
python combined_app5.py
```

默认端口：**19995**  
访问地址：http://localhost:19995

## 配置

- 端口修改：`PORT` 变量
- 文件上传目录：`UPLOAD_FOLDER`
- systemd 自启：参考 `combined.service`

## 项目结构

- `combined_app5.py` — 主服务脚本
- `index.html` — 前端模板
