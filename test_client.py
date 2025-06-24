#!/usr/bin/env python3
"""
SSH MCP Server 测试客户端

使用此脚本测试SSH MCP Server的功能
"""

import asyncio
import os
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def test_ssh_server():
    """测试SSH MCP Server的各项功能"""
    
    # 设置服务器参数
    server_params = StdioServerParameters(
        command="python",
        args=["ssh_server.py"],
        env=None
    )
    
    print("🚀 启动 SSH MCP Server 测试...")
    
    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                # 初始化连接
                await session.initialize()
                print("✅ 与MCP服务器连接成功")
                
                # 列出可用工具
                tools = await session.list_tools()
                print(f"\n📋 可用工具: {len(tools.tools)} 个")
                for tool in tools.tools:
                    print(f"   - {tool.name}: {tool.description}")
                
                # 测试SSH连接状态
                print("\n🔍 测试SSH连接状态...")
                try:
                    result = await session.call_tool("check_ssh_connection", {})
                    connection_status = result.content[0].text if result.content else "无响应"
                    print(f"连接状态: {connection_status}")
                except Exception as e:
                    print(f"❌ SSH连接测试失败: {e}")
                
                # 测试基本命令执行
                print("\n🔧 测试基本命令执行...")
                try:
                    test_command = "echo 'Hello from SSH!'"
                    result = await session.call_tool("execute_command", {
                        "command": test_command,
                        "timeout": 10
                    })
                    command_result = result.content[0].text if result.content else "无响应"
                    print(f"命令执行结果: {command_result}")
                except Exception as e:
                    print(f"❌ 命令执行测试失败: {e}")
                
                # 测试获取命令输出
                print("\n📝 测试获取命令输出...")
                try:
                    result = await session.call_tool("get_command_output", {
                        "command": "whoami",
                        "timeout": 10
                    })
                    output = result.content[0].text if result.content else "无响应"
                    print(f"当前用户: {output.strip()}")
                except Exception as e:
                    print(f"❌ 获取输出测试失败: {e}")
                
                print("\n🎉 测试完成！")
                
    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")


def check_environment():
    """检查环境变量配置"""
    print("🔧 检查环境变量配置...")
    
    required_vars = ['SSH_HOST', 'SSH_USERNAME']
    auth_vars = ['SSH_PASSWORD', 'SSH_KEY_PATH']
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if not any(os.getenv(var) for var in auth_vars):
        missing_vars.extend(auth_vars)
        print(f"❌ 缺少认证配置: 必须设置 {' 或 '.join(auth_vars)} 其中之一")
    
    if missing_vars:
        print(f"❌ 缺少必需的环境变量: {', '.join(missing_vars)}")
        print("\n请设置以下环境变量:")
        print("export SSH_HOST=your-server-ip")
        print("export SSH_USERNAME=your-username")
        print("export SSH_PASSWORD=your-password  # 或使用SSH_KEY_PATH")
        print("\n或复制并编辑配置文件:")
        print("cp config_example.env .env")
        print("# 编辑 .env 文件")
        print("source .env")
        return False
    
    print("✅ 环境变量配置检查通过")
    print(f"   SSH_HOST: {os.getenv('SSH_HOST')}")
    print(f"   SSH_USERNAME: {os.getenv('SSH_USERNAME')}")
    print(f"   SSH_PORT: {os.getenv('SSH_PORT', '22')}")
    
    if os.getenv('SSH_KEY_PATH'):
        print(f"   认证方式: SSH密钥 ({os.getenv('SSH_KEY_PATH')})")
    else:
        print("   认证方式: 密码")
    
    return True


if __name__ == "__main__":
    print("=== SSH MCP Server 测试工具 ===\n")
    
    # 检查环境配置
    if not check_environment():
        exit(1)
    
    # 运行测试
    asyncio.run(test_ssh_server()) 