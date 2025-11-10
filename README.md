# SSH MCP Server

一个基于 Model Context Protocol (MCP) 的 SSH 服务器，提供通过 SSH 连接到远程服务器并执行命令的功能。

## 功能特性

- 🔐 支持密码和SSH密钥认证
- 🚀 执行远程shell命令
- 📊 获取命令执行结果（成功/失败状态、退出码）
- 📝 获取命令输出内容（stdout、stderr）
- 🔄 支持交互式命令执行
- ⚡ 基于环境变量的灵活配置
- 🛡️ 完善的错误处理和日志记录

## 安装

```bash
pip install paramiko mcp
```

## 配置

### 环境变量配置

在启动时通过环境变量设置SSH连接信息：

```bash
# 必需配置
SSH_HOST=your-server-ip-or-hostname
SSH_USERNAME=your-username

# 认证方式（选择其一）
SSH_PASSWORD=your-password
# 或者使用SSH密钥（推荐）
SSH_KEY_PATH=/path/to/your/private/key

# 可选配置
SSH_PORT=22  # 默认为22
```

### 配置说明

- `SSH_HOST`: 目标服务器的IP地址或主机名
- `SSH_USERNAME`: SSH登录用户名
- `SSH_PASSWORD`: SSH登录密码
- `SSH_KEY_PATH`: SSH私钥文件路径（如果使用密钥认证）
- `SSH_PORT`: SSH端口号，默认为22

**注意**：必须设置 `SSH_PASSWORD` 或 `SSH_KEY_PATH` 其中之一。如果同时设置，将优先使用密钥认证。


## 可用工具

### 1. execute_command

执行shell命令并返回完整结果。

**参数**：
- `command` (str): 要执行的shell命令
- `timeout` (int, 可选): 超时时间，默认30秒

**返回**：
```json
{
  "success": true/false,
  "exit_code": 0,
  "stdout": "命令输出",
  "stderr": "错误输出",
  "error": null
}
```

### 2. get_command_output

执行命令并仅返回标准输出内容。

**参数**：
- `command` (str): 要执行的shell命令
- `timeout` (int, 可选): 超时时间，默认30秒

**返回**：命令的标准输出内容（字符串）

### 3. check_ssh_connection

检查SSH连接状态。

**返回**：
```json
{
  "connected": true/false,
  "host": "192.168.1.100",
  "port": 22,
  "username": "admin",
  "test_output": "连接测试成功",
  "error": null
}
```

### 4. execute_interactive_command

执行交互式命令（可以发送输入数据）。

**参数**：
- `command` (str): 要执行的shell命令
- `input_data` (str, 可选): 要发送给命令的输入数据
- `timeout` (int, 可选): 超时时间，默认30秒

**返回**：同 `execute_command`

## 使用示例

### 基本命令执行

```python
# 执行简单命令
result = execute_command("ls -la")
print(result["stdout"])

# 获取系统信息
system_info = get_command_output("uname -a")
print(system_info)
```

### 交互式命令

```python
# 执行需要输入的命令
result = execute_interactive_command(
    command="sudo apt update",
    input_data="your-password\n"
)
```

### 连接检查

```python
# 检查连接状态
status = check_ssh_connection()
if status["connected"]:
    print(f"已连接到 {status['host']}")
else:
    print(f"连接失败: {status['error']}")
```

## 安全注意事项

1. **密钥认证优于密码认证**：推荐使用SSH密钥而不是密码
2. **环境变量安全**：不要在代码中硬编码敏感信息
3. **网络安全**：确保SSH连接在安全的网络环境中
4. **权限控制**：使用具有适当权限的用户账户

## 错误处理

服务器会处理以下常见错误：

- SSH认证失败
- 网络连接问题
- 命令执行超时
- 权限不足

所有错误都会记录到日志中，并返回详细的错误信息。

## 项目结构

```
ssh-mcp/
├── ssh_server.py          # 主服务器文件
├── test_client.py         # 测试客户端
├── config_example.env     # 环境变量示例
├── pyproject.toml         # 项目配置
├── setup.py              # 安装脚本
└── README.md             # 项目文档
```

## 许可证

MIT License 