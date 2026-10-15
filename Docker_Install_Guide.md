# Docker Desktop 安装指南

## 系统要求

- Windows 10 64位（专业版/企业版/教育版 Build 19044+）或 Windows 11
- 启用 WSL 2 或 Hyper-V
- 至少 4GB 内存

## 安装步骤

### 1. 下载 Docker Desktop

**官方下载地址：**
```
https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe
```

或者访问官网：
```
https://www.docker.com/products/docker-desktop/
```

### 2. 安装 Docker Desktop

1. 双击下载的 `Docker Desktop Installer.exe`
2. 按照向导完成安装
3. 安装过程中会自动启用 WSL 2
4. 安装完成后重启电脑

### 3. 验证安装

打开 PowerShell 或 CMD，运行：
```powershell
docker --version
docker-compose --version
```

### 4. 配置 Docker

打开 Docker Desktop 设置：
- **General**: 勾选 "Start Docker Desktop when you log in"
- **Resources**: 调整内存（建议至少 4GB）
- **WSL Integration**: 启用 WSL 2 集成

## 常见问题

### 问题1：WSL 2 未安装

如果提示 WSL 2 未安装，在 PowerShell（管理员）运行：
```powershell
wsl --install
```

然后重启电脑。

### 问题2：Hyper-V 未启用

在 PowerShell（管理员）运行：
```powershell
Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V -All
```

### 问题3：虚拟化未启用

需要在 BIOS 中启用 Intel VT-x 或 AMD-V。

## 安装完成后

验证 Docker 是否正常工作：
```powershell
# 运行测试容器
docker run hello-world

# 查看 Docker 版本
docker version
```

## 下一步

安装完成后，我们就可以运行 xiaohongshu-mcp 的多账号管理器了。
