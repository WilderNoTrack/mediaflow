#!/usr/bin/env python3
"""
MediaFlow Service Manager - 跨平台服务管理脚本

用法:
    python services.py start    # 启动所有服务
    python services.py stop     # 停止所有服务
    python services.py status   # 查看服务状态
    python services.py restart  # 重启所有服务
"""

import os
import sys
import time
import signal
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Dict, List

# 颜色输出
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color
    
    @classmethod
    def print_color(cls, color: str, message: str):
        """打印带颜色的消息"""
        print(f"{color}{message}{cls.NC}")

# 项目路径
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
LOGS_DIR = PROJECT_ROOT / "logs"
PID_DIR = LOGS_DIR

# 服务配置
XHS_MCP_DIR = PROJECT_ROOT / "xiaohongshu-mcp"
CHROME_BIN = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

SERVICES = {
    "xiaohongshu_mcp": {
        "name": "小红书 MCP 服务",
        "port": 18060,
        "health_url": "http://localhost:18060/health",
        "command": [
            str(XHS_MCP_DIR / "xiaohongshu-mcp.exe"),
            "-port", ":18060",
            "-bin", CHROME_BIN,
        ],
        "cwd": XHS_MCP_DIR,
        "log_file": LOGS_DIR / "xiaohongshu-mcp.log",
        "pid_file": PID_DIR / "xiaohongshu-mcp.pid",
        "new_window": True,  # 在独立终端窗口中运行，方便查看日志
    },
    "backend": {
        "name": "Backend API",
        "port": 8000,
        "health_url": "http://localhost:8000/health",
        "command": [sys.executable, "main.py"],
        "cwd": PROJECT_ROOT / "backend",
        "log_file": LOGS_DIR / "backend.log",
        "pid_file": PID_DIR / "backend.pid",
    },
    "frontend": {
        "name": "Frontend Dev Server",
        "port": 5173,
        "health_url": "http://localhost:5173",
        # Windows: npm is npm.cmd; Unix: npm
        "command": ["npm.cmd" if sys.platform == "win32" else "npm", "run", "dev"],
        "cwd": PROJECT_ROOT / "frontend",
        "log_file": LOGS_DIR / "frontend.log",
        "pid_file": PID_DIR / "frontend.pid",
    }
}


def ensure_directories():
    """确保日志和PID目录存在"""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def is_port_in_use(port: int) -> bool:
    """检查端口是否被占用。

    必须同时探测 IPv4 和 IPv6：Vite 默认只监听 [::1]:5173，
    只用 AF_INET 探测会误判为"端口空闲"——导致停服时跳过按端口兜底查杀，
    启动时也检测不出端口冲突。
    """
    import socket
    for family, addr in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as s:
                s.settimeout(1.5)
                if s.connect_ex((addr, port)) == 0:
                    return True
        except OSError:
            continue
    return False


def check_health(url: str, timeout: int = 5) -> bool:
    """检查健康检查端点（绕过系统代理，避免 Clash/V2Ray 拦截 localhost）"""
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        req = urllib.request.Request(url)
        with opener.open(req, timeout=timeout) as response:
            return response.status == 200
    except Exception:
        return False


def wait_for_health(service_key: str, max_attempts: int = 30, interval: int = 2) -> bool:
    """等待服务健康检查通过"""
    service = SERVICES[service_key]
    url = service["health_url"]
    name = service["name"]
    
    Colors.print_color(Colors.YELLOW, f"等待 {name} 启动... ({url})")
    
    for attempt in range(1, max_attempts + 1):
        if check_health(url):
            Colors.print_color(Colors.GREEN, f"[OK] {name} 已就绪!")
            return True
        
        if attempt % 5 == 0:
            Colors.print_color(Colors.YELLOW, f"  尝试 {attempt}/{max_attempts}: {name} 尚未就绪...")
        time.sleep(interval)
    
    Colors.print_color(Colors.RED, f"[FAIL] {name} 启动超时 ({max_attempts * interval}秒)")
    return False


def read_pid(service_key: str) -> Optional[int]:
    """读取PID文件"""
    pid_file = SERVICES[service_key]["pid_file"]
    if pid_file.exists():
        try:
            return int(pid_file.read_text().strip())
        except (ValueError, IOError):
            return None
    return None


def write_pid(service_key: str, pid: int):
    """写入PID文件"""
    pid_file = SERVICES[service_key]["pid_file"]
    pid_file.write_text(str(pid))


def remove_pid(service_key: str):
    """删除PID文件"""
    pid_file = SERVICES[service_key]["pid_file"]
    if pid_file.exists():
        pid_file.unlink()


def is_process_running(pid: int) -> bool:
    """检查进程是否运行 (跨平台兼容)"""
    if sys.platform == "win32":
        # Windows: 使用 tasklist 检查进程
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True,
                text=True,
                timeout=5
            )
            # 如果输出包含 PID，说明进程存在
            return str(pid) in result.stdout
        except Exception:
            return False
    else:
        # Unix: 使用信号0检查
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


def find_process_by_port(port: int) -> Optional[int]:
    """通过端口号查找进程PID"""
    try:
        # 使用 netstat 查找监听端口的进程
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        for line in result.stdout.split('\n'):
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                if len(parts) >= 5:
                    try:
                        return int(parts[-1])  # 最后一列是PID
                    except ValueError:
                        continue
    except Exception as e:
        Colors.print_color(Colors.RED, f"查找端口进程失败: {e}")
    
    return None


def start_service(service_key: str) -> bool:
    """启动单个服务"""
    service = SERVICES[service_key]
    name = service["name"]
    port = service["port"]
    
    # 检查端口是否已被占用
    if is_port_in_use(port):
        Colors.print_color(Colors.RED, f"[FAIL] 端口 {port} 已被占用 ({name})")
        return False
    
    Colors.print_color(Colors.BLUE, f"启动 {name}...")
    
    # 准备日志文件
    log_file = service["log_file"]
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        if service.get("new_window") and sys.platform == "win32":
            # 在新终端窗口中启动（用户可直接看到输出）
            process = subprocess.Popen(
                service["command"],
                cwd=service["cwd"],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            write_pid(service_key, process.pid)
            Colors.print_color(Colors.GREEN, f"  已在新窗口启动 PID: {process.pid}")
        else:
            # 后台启动，输出写入日志文件
            with open(log_file, 'w', encoding='utf-8') as log:
                process = subprocess.Popen(
                    service["command"],
                    cwd=service["cwd"],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True
                )
            write_pid(service_key, process.pid)
            Colors.print_color(Colors.GREEN, f"  PID: {process.pid}")

        return True

    except Exception as e:
        Colors.print_color(Colors.RED, f"[FAIL] 启动 {name} 失败: {e}")
        return False


def kill_process(pid: int, force: bool = False):
    """终止进程 (跨平台兼容)"""
    if sys.platform == "win32":
        # Windows: 使用 taskkill 命令
        # /T 连同子进程一起终止——前端记录的是 npm.cmd 的 cmd.exe 包装进程，
        # 真正监听 5173 的 node 是它的子进程；不带 /T 只会杀掉外壳，
        # dev server 仍然活着占着端口。
        try:
            args = ["taskkill", "/PID", str(pid), "/T"]
            if force:
                args.append("/F")
            subprocess.run(args, capture_output=True, timeout=10)
        except Exception:
            # Fallback: 使用 os.kill with SIGTERM
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass
    else:
        # Unix: 使用信号
        if force:
            os.kill(pid, signal.SIGKILL)
        else:
            os.kill(pid, signal.SIGTERM)


def stop_service(service_key: str, force: bool = False) -> bool:
    """停止单个服务"""
    service = SERVICES[service_key]
    name = service["name"]
    port = service["port"]
    
    # 方法1: 通过PID文件停止
    pid = read_pid(service_key)
    
    if pid and is_process_running(pid):
        Colors.print_color(Colors.BLUE, f"停止 {name} (PID: {pid})...")
        try:
            kill_process(pid, force=force)
            time.sleep(1)
            
            # 检查是否已停止
            if is_process_running(pid):
                if not force:
                    Colors.print_color(Colors.YELLOW, "  强制终止...")
                    kill_process(pid, force=True)
                    time.sleep(1)
        except Exception as e:
            Colors.print_color(Colors.RED, f"  终止进程失败: {e}")
    
    # 方法2: 通过端口查找进程并停止 (fallback)
    if is_port_in_use(port):
        Colors.print_color(Colors.YELLOW, f"  通过端口 {port} 查找进程...")
        pid_by_port = find_process_by_port(port)
        if pid_by_port and pid_by_port != pid:
            Colors.print_color(Colors.YELLOW, f"  找到进程 PID: {pid_by_port}")
            try:
                kill_process(pid_by_port, force=True)
                time.sleep(1)
            except Exception as e:
                Colors.print_color(Colors.RED, f"  终止进程失败: {e}")
    
    # 验证是否已停止
    if is_port_in_use(port):
        Colors.print_color(Colors.RED, f"[FAIL] {name} 未能完全停止")
        return False
    else:
        Colors.print_color(Colors.GREEN, f"[OK] {name} 已停止")
        remove_pid(service_key)
        return True


def start_all():
    """启动所有服务"""
    Colors.print_color(Colors.BLUE, "=" * 50)
    Colors.print_color(Colors.BLUE, "启动 MediaFlow 服务")
    Colors.print_color(Colors.BLUE, "=" * 50)
    Colors.print_color(Colors.BLUE, f"项目根目录: {PROJECT_ROOT}")
    Colors.print_color(Colors.BLUE, f"日志目录: {LOGS_DIR}")
    print()
    
    ensure_directories()
    
    # 按顺序启动服务
    for service_key in ["xiaohongshu_mcp", "backend", "frontend"]:
        if not start_service(service_key):
            Colors.print_color(Colors.RED, f"\n启动失败，停止已启动的服务...")
            for key in ["frontend", "backend", "xiaohongshu_mcp"]:
                if key != service_key and read_pid(key):
                    stop_service(key, force=True)
            sys.exit(1)

        if service_key == "frontend":
            # Frontend: 等待端口监听
            Colors.print_color(Colors.YELLOW, "等待 Frontend 启动...")
            for _ in range(15):
                if is_port_in_use(5173):
                    Colors.print_color(Colors.GREEN, "[OK] Frontend 已就绪!")
                    break
                time.sleep(1)
        elif service_key == "xiaohongshu_mcp":
            # MCP: Chrome 启动需要更长时间，等待最多 60 秒
            if not wait_for_health(service_key, max_attempts=30, interval=2):
                Colors.print_color(Colors.YELLOW, "[WARN] 小红书 MCP 健康检查超时，继续启动其他服务（MCP 可能还在初始化）")
        else:
            if not wait_for_health(service_key):
                Colors.print_color(Colors.RED, f"\n健康检查失败，停止所有服务...")
                stop_service(service_key, force=True)
                for key in ["frontend", "backend", "xiaohongshu_mcp"]:
                    if key != service_key and read_pid(key):
                        stop_service(key, force=True)
                sys.exit(1)

    print()
    Colors.print_color(Colors.GREEN, "=" * 50)
    Colors.print_color(Colors.GREEN, "[OK] 所有服务启动成功!")
    Colors.print_color(Colors.GREEN, "=" * 50)
    Colors.print_color(Colors.GREEN, f"小红书 MCP:   http://localhost:18060")
    Colors.print_color(Colors.GREEN, f"Backend API:  http://localhost:8000")
    Colors.print_color(Colors.GREEN, f"Frontend:     http://localhost:5173")
    Colors.print_color(Colors.GREEN, f"日志文件: {LOGS_DIR}")
    Colors.print_color(Colors.GREEN, "=" * 50)


def stop_all(force: bool = False):
    """停止所有服务"""
    Colors.print_color(Colors.BLUE, "=" * 50)
    Colors.print_color(Colors.BLUE, "停止 MediaFlow 服务")
    Colors.print_color(Colors.BLUE, "=" * 50)
    print()
    
    # 按相反顺序停止服务
    for service_key in ["frontend", "backend", "xiaohongshu_mcp"]:
        stop_service(service_key, force=force)
    
    print()
    Colors.print_color(Colors.GREEN, "[OK] 所有服务已停止")


def show_status():
    """显示服务状态"""
    Colors.print_color(Colors.BLUE, "=" * 50)
    Colors.print_color(Colors.BLUE, "MediaFlow 服务状态")
    Colors.print_color(Colors.BLUE, "=" * 50)
    print()
    
    for service_key, service in SERVICES.items():
        name = service["name"]
        port = service["port"]
        url = service["health_url"]
        
        pid = read_pid(service_key)
        running = pid and is_process_running(pid)
        port_used = is_port_in_use(port)
        healthy = check_health(url) if service_key != "frontend" else port_used
        
        status_color = Colors.GREEN if running and healthy else Colors.RED
        status = "运行中" if running else ("端口被占用" if port_used else "已停止")
        health_status = "健康" if healthy else "不健康"
        
        Colors.print_color(Colors.BLUE, f"{name}:")
        Colors.print_color(status_color, f"  状态: {status}")
        if pid:
            Colors.print_color(Colors.YELLOW, f"  PID: {pid}")
        Colors.print_color(Colors.YELLOW, f"  端口: {port}")
        Colors.print_color(Colors.YELLOW, f"  健康检查: {health_status}")
        print()
    
    Colors.print_color(Colors.BLUE, "=" * 50)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "start":
        start_all()
    elif command == "stop":
        force = "-f" in sys.argv or "--force" in sys.argv
        stop_all(force=force)
    elif command == "status":
        show_status()
    elif command == "restart":
        stop_all()
        print()
        time.sleep(2)
        start_all()
    else:
        Colors.print_color(Colors.RED, f"未知命令: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()