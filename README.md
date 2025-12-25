# SSH MCP Server

一个基于 Model Context Protocol (MCP) 的 SSH 服务器，提供通过 SSH 连接到远程服务器并执行命令的功能。

## 功能特性

- 🔐 支持密码和SSH密钥认证
- 🌐 **支持多个命名SSH连接**
- 🚀 执行远程shell命令
- 📊 获取命令执行结果（成功/失败状态、退出码）
- 📝 获取命令输出内容（stdout、stderr）
- 🔄 支持交互式命令执行
- 📤 支持文件上传（SFTP）
- ⚡ 基于环境变量的灵活配置
- 🛡️ 完善的错误处理和日志记录
- ♻️ 向后兼容传统单连接配置

## 安装

```bash
pip install paramiko mcp
```

## 配置

### 多连接配置（推荐）

通过环境变量配置多个命名SSH连接，格式为 `SSH_{连接名}_{参数名}`：

```bash
# 生产环境连接
SSH_PROD_HOST=prod.example.com
SSH_PROD_USERNAME=admin
SSH_PROD_PASSWORD=prod_password
SSH_PROD_PORT=22

# 测试环境连接
SSH_TEST_HOST=test.example.com
SSH_TEST_USERNAME=tester
SSH_TEST_KEY_PATH=/path/to/test_key
SSH_TEST_PORT=2222

# 开发环境连接
SSH_DEV_HOST=dev.example.com
SSH_DEV_USERNAME=developer
SSH_DEV_PASSWORD=dev_password

# 设置默认连接（可选）
SSH_DEFAULT_CONNECTION=prod
```

**连接命名规则**：
- 连接名使用大写字母和下划线，如 `PROD`、`TEST`、`DEV_SERVER`
- 在工具调用时使用小写形式，如 `connection_name="prod"`

**支持的参数**：
- `HOST`: 目标服务器的IP地址或主机名（必需）
- `USERNAME`: SSH登录用户名（必需）
- `PASSWORD`: SSH登录密码（与 KEY_PATH 二选一）
- `KEY_PATH`: SSH私钥文件路径（与 PASSWORD 二选一）
- `PORT`: SSH端口号，默认为22（可选）

### 单连接配置（向后兼容）

传统的单连接配置方式仍然支持，会被自动注册为 `default` 连接：

```bash
SSH_HOST=your-server-ip-or-hostname
SSH_USERNAME=your-username
SSH_PASSWORD=your-password
# 或使用SSH密钥（推荐）
SSH_KEY_PATH=/path/to/your/private/key
SSH_PORT=22  # 可选，默认为22
```

### 日志配置（可选）

```bash
SAVE_EXEC_LOG=false
EXEC_LOG_FILE=exec_log.json
```

## 可用工具

### 1. list_ssh_connections

列出所有可用的SSH连接配置。

**返回**：
```json
{
  "connections": {
    "prod": {
      "name": "prod",
      "host": "prod.example.com",
      "port": 22,
      "username": "admin",
      "auth_method": "password"
    },
    "test": {
      "name": "test",
      "host": "test.example.com",
      "port": 2222,
      "username": "tester",
      "auth_method": "key"
    }
  },
  "default_connection": "prod",
  "total_count": 2
}
```

### 2. execute_command

执行shell命令并返回完整结果。

**参数**：
- `command` (str): 要执行的shell命令
- `timeout` (int, 可选): 超时时间，默认30秒
- `connection_name` (str, 可选): 连接名称，不指定则使用默认连接

**返回**：
```json
{
  "success": true/false,
  "exit_code": 0,
  "stdout": "命令输出",
  "stderr": "错误输出",
  "error": null,
  "connection": "prod"
}
```

### 4. check_ssh_connection

检查SSH连接状态。

**参数**：
- `connection_name` (str, 可选): 连接名称，不指定则使用默认连接

**返回**：
```json
{
  "connected": true/false,
  "connection_name": "prod",
  "host": "prod.example.com",
  "port": 22,
  "username": "admin",
  "test_output": "连接测试成功",
  "error": null
}
```

### 5. execute_interactive_command

执行交互式命令（可以发送输入数据）。

**参数**：
- `command` (str): 要执行的shell命令
- `input_data` (str, 可选): 要发送给命令的输入数据
- `timeout` (int, 可选): 超时时间，默认30秒
- `connection_name` (str, 可选): 连接名称，不指定则使用默认连接

**返回**：同 `execute_command`

### 6. upload_file

使用SFTP协议上传文件到远程服务器。

**参数**：
- `local_path` (str): 本地文件路径
- `remote_path` (str): 远程服务器文件路径
- `timeout` (int, 可选): 传输超时时间，默认60秒
- `connection_name` (str, 可选): 连接名称，不指定则使用默认连接

**返回**：
```json
{
  "success": true/false,
  "local_path": "/path/to/local/file",
  "remote_path": "/path/to/remote/file",
  "file_size": 1024,
  "connection": "prod",
  "error": null
}
```

### 7. download_file

使用SFTP协议从远程服务器下载文件到本地。

**参数**：
- `remote_path` (str): 远程服务器文件路径（绝对路径）
- `local_path` (str): 本地文件保存路径
- `timeout` (int, 可选): 传输超时时间，默认60秒
- `connection_name` (str, 可选): 连接名称，不指定则使用默认连接

**返回**：
```json
{
  "success": true/false,
  "remote_path": "/path/to/remote/file",
  "local_path": "/path/to/local/file",
  "file_size": 1024,
  "connection": "prod",
  "error": null
}
```

### 8. list_directory

获取远程目录的结构化文件列表。

**参数**：
- `remote_path` (str, 可选): 远程目录路径，默认为当前目录 "."
- `timeout` (int, 可选): 操作超时时间，默认30秒
- `connection_name` (str, 可选): 连接名称，不指定则使用默认连接

**返回**：
```json
{
  "success": true/false,
  "path": "/path/to/directory",
  "files": [
    {
      "name": "example.txt",
      "type": "file",
      "size": 1024,
      "permissions": "rw-r--r--",
      "modified_time": 1701234567,
      "owner_uid": 1000,
      "group_gid": 1000
    },
    {
      "name": "subdir",
      "type": "directory",
      "size": null,
      "permissions": "rwxr-xr-x",
      "modified_time": 1701234567,
      "owner_uid": 1000,
      "group_gid": 1000
    }
  ],
  "total_count": 2,
  "connection": "prod",
  "error": null
}
```

## 使用示例

### 列出所有连接

```python
# 查看所有可用连接
connections = list_ssh_connections()
print(f"共有 {connections['total_count']} 个连接")
print(f"默认连接: {connections['default_connection']}")
```

### 文件下载

```python
# 从生产环境下载文件
result = download_file(
    remote_path="/path/to/remote/file.txt",
    local_path="/path/to/local/file.txt",
    connection_name="prod"
)
if result["success"]:
    print(f"文件下载成功: {result['file_size']} 字节")
```

### 目录列表

```python
# 列出生产环境的目录内容
result = list_directory(
    remote_path="/var/log",
    connection_name="prod"
)
if result["success"]:
    print(f"目录包含 {result['total_count']} 项:")
    for file in result["files"]:
        file_type = file["type"]
        name = file["name"]
        if file_type == "file":
            size = file["size"]
            print(f"  [文件] {name} ({size} 字节)")
        elif file_type == "directory":
            print(f"  [目录] {name}/")
```

### 使用默认连接

```python
# 不指定连接名，使用默认连接
result = execute_command("ls -la")
print(result["stdout"])

```

### 使用指定连接

```python
# 在生产环境执行命令
result = execute_command("df -h", connection_name="prod")
print(result["stdout"])

# 在测试环境执行命令
result = execute_command("ps aux", connection_name="test")
print(result["stdout"])
```

### 检查连接状态

```python
# 检查默认连接
status = check_ssh_connection()
if status["connected"]:
    print(f"已连接到 {status['host']}")

# 检查特定连接
status = check_ssh_connection(connection_name="prod")
if status["connected"]:
    print(f"生产环境连接正常")
```

### 交互式命令

```python
# 在指定连接上执行需要输入的命令
result = execute_interactive_command(
    command="sudo apt update",
    input_data="your-password\n",
    connection_name="dev"
)
```

### 文件上传

```python
# 上传文件到生产环境
result = upload_file(
    local_path="/path/to/local/file.txt",
    remote_path="/path/to/remote/file.txt",
    connection_name="prod"
)
if result["success"]:
    print(f"文件上传成功: {result['file_size']} 字节")
```

## 安全注意事项

1. **密钥认证优于密码认证**：推荐使用SSH密钥而不是密码
2. **环境变量安全**：不要在代码中硬编码敏感信息，使用 `.env` 文件并加入 `.gitignore`
3. **网络安全**：确保SSH连接在安全的网络环境中
4. **权限控制**：使用具有适当权限的用户账户
5. **连接隔离**：为不同环境（生产、测试、开发）配置独立的连接

## 错误处理

服务器会处理以下常见错误：

- SSH认证失败
- 网络连接问题
- 命令执行超时
- 权限不足
- 连接不存在

所有错误都会记录到日志中，并返回详细的错误信息。

## 项目结构

```
ssh-mcp/
├── ssh_server.py          # 主服务器文件
├── .env.example           # 环境变量配置示例
├── pyproject.toml         # 项目配置
├── LICENSE                # MIT 许可证
└── README.md              # 项目文档
```

## 更新日志

### v2.0.0 - 多连接支持
- ✨ 新增多个命名SSH连接支持
- ✨ 新增 `list_ssh_connections` 工具
- ✨ 所有工具函数支持 `connection_name` 参数
- ✨ 自动发现和加载环境变量中的连接配置
- ♻️ 保持向后兼容传统单连接配置

## 许可证

MIT License