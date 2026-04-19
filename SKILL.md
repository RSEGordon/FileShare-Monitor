# FileShare + System Monitor Skill

文件共享 + 系统监控服务的管理 skill。

## 服务信息

- **脚本**：`~/桌面/OpenClawFile/combined_app5.py`
- **模板**：`~/桌面/OpenClawFile/templates/index.html`
- **systemd**：`~/.config/systemd/user/combined.service`
- **端口**：19995
- **FileShare 直链基础**：`https://frp-run.com:45775/files/`
- **GitHub**：`https://github.com/RSEGordon/FileShare-Monitor`

## 服务管理命令

```bash
# 查看状态
systemctl --user status combined.service

# 重启服务
systemctl --user restart combined.service

# 查看日志
journalctl --user -u combined.service -f

# 手动启动
python ~/桌面/OpenClawFile/combined_app5.py
```

## 功能说明

- 文件上传下载（FileShare）
- CPU 各核心监控
- 内存、磁盘、网络监控
- OpenClaw Gateway（main/jim/hjkv）状态监控
- 导航栏可跳转博客

## 端口占用

如 19995 被占用，检查：
```bash
ss -tlnp | grep 19995
lsof -i :19995
```

## FileShare 外链格式

```
https://frp-run.com:45775/files/download/<filename>
```

## 构建/修改后

修改 `combined_app5.py` 或 `index.html` 后：
```bash
systemctl --user restart combined.service
```
