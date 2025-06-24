#!/usr/bin/env python3
"""
SSH MCP Server 快速安装脚本

自动安装依赖和配置环境
"""

import os
import subprocess
import sys
from pathlib import Path


def run_command(cmd, description):
    """运行命令并处理错误"""
    print(f"🔧 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} 完成")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} 失败: {e}")
        if e.stdout:
            print(f"输出: {e.stdout}")
        if e.stderr:
            print(f"错误: {e.stderr}")
        return False


def check_python_version():
    """检查Python版本"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print(f"❌ Python版本过低: {version.major}.{version.minor}")
        print("请使用Python 3.8或更高版本")
        return False
    
    print(f"✅ Python版本检查通过: {version.major}.{version.minor}.{version.micro}")
    return True


def install_dependencies():
    """安装项目依赖"""
    print("\n📦 安装依赖包...")
    
    # 检查是否有uv
    try:
        subprocess.run(['uv', '--version'], check=True, capture_output=True)
        use_uv = True
        print("🚀 检测到uv，使用uv安装依赖")
    except (subprocess.CalledProcessError, FileNotFoundError):
        use_uv = False
        print("📋 使用pip安装依赖")
    
    if use_uv:
        # 使用uv安装
        commands = [
            ('uv add paramiko', '安装paramiko'),
            ('uv add "mcp[cli]"', '安装MCP CLI'),
        ]
    else:
        # 使用pip安装
        commands = [
            ('pip install paramiko', '安装paramiko'),
            ('pip install mcp', '安装MCP'),
        ]
    
    for cmd, desc in commands:
        if not run_command(cmd, desc):
            return False
    
    return True


def create_config_file():
    """创建配置文件"""
    config_path = Path('.env')
    example_path = Path('config_example.env')
    
    if config_path.exists():
        print("⚠️  .env文件已存在，跳过创建")
        return True
    
    if not example_path.exists():
        print("❌ 配置示例文件不存在")
        return False
    
    try:
        # 复制示例配置文件
        with open(example_path, 'r', encoding='utf-8') as src:
            content = src.read()
        
        with open(config_path, 'w', encoding='utf-8') as dst:
            dst.write(content)
        
        print("✅ 已创建 .env 配置文件")
        print("📝 请编辑 .env 文件配置您的SSH连接信息")
        return True
        
    except Exception as e:
        print(f"❌ 创建配置文件失败: {e}")
        return False


def display_next_steps():
    """显示后续步骤"""
    print("\n🎉 安装完成！")
    print("\n📋 后续步骤:")
    print("1. 编辑 .env 文件配置SSH连接信息:")
    print("   - SSH_HOST=your-server-ip")
    print("   - SSH_USERNAME=your-username")
    print("   - SSH_PASSWORD=your-password (或使用SSH_KEY_PATH)")
    print("\n2. 测试SSH MCP Server:")
    print("   python test_client.py")
    print("\n3. 启动SSH MCP Server:")
    print("   python ssh_server.py")
    print("\n4. 安装到Claude Desktop:")
    print("   uv run mcp install ssh_server.py --name 'SSH Server'")
    print("\n📖 更多信息请查看 README.md")


def main():
    """主安装流程"""
    print("=== SSH MCP Server 安装程序 ===\n")
    
    # 检查Python版本
    if not check_python_version():
        return 1
    
    # 安装依赖
    if not install_dependencies():
        print("\n❌ 依赖安装失败，请手动安装依赖")
        return 1
    
    # 创建配置文件
    if not create_config_file():
        print("\n⚠️  配置文件创建失败，请手动复制 config_example.env 到 .env")
    
    # 显示后续步骤
    display_next_steps()
    
    return 0


if __name__ == "__main__":
    sys.exit(main()) 