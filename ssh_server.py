import os
import asyncio
from typing import Optional, Dict, Any
import paramiko
from mcp.server.fastmcp import FastMCP, Context
from mcp.types import TextContent
import io
import logging
import json
import time
from threading import Lock
from pathlib import Path

# 加载 .env 文件（如果存在）
def load_env_file():
    """加载 .env 文件到环境变量"""
    env_file = Path(__file__).parent / '.env'
    if env_file.exists():
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    # 只有在环境变量未设置时才从 .env 文件读取
                    if key.strip() not in os.environ:
                        os.environ[key.strip()] = value.strip()
        logger.info(f"已加载配置文件: {env_file}")

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 加载环境变量
load_env_file()

# 创建 MCP 服务器
mcp = FastMCP(name="SSH Server", description="SSH连接管理和命令执行服务器")

class ExecLogManager:
    """命令执行日志管理类"""
    
    def __init__(self):
        self.save_log = os.getenv('SAVE_EXEC_LOG', 'false').lower() in ('true', '1', 'yes')
        self.log_file = os.getenv('EXEC_LOG_FILE', 'exec_log.json')
        self.lock = Lock()
        
        # 如果启用日志且文件不存在，初始化为空数组
        if self.save_log and not os.path.exists(self.log_file):
            self._initialize_log_file()
    
    def _initialize_log_file(self):
        """初始化日志文件"""
        try:
            with open(self.log_file, 'w', encoding='utf-8') as f:
                json.dump([], f)
            logger.info(f"初始化日志文件: {self.log_file}")
        except Exception as e:
            logger.error(f"初始化日志文件失败: {e}")
    
    def save_execution_log(self, command: str, result: Dict[str, Any]):
        """保存命令执行日志"""
        if not self.save_log:
            return
        
        try:
            with self.lock:
                # 读取现有日志
                logs = []
                if os.path.exists(self.log_file):
                    try:
                        with open(self.log_file, 'r', encoding='utf-8') as f:
                            logs = json.load(f)
                    except (json.JSONDecodeError, FileNotFoundError):
                        logs = []
                
                # 构建日志条目
                log_entry = {
                    "command": command,
                    "result": "success" if result.get("success") else "failure",
                    "output": result.get("stdout", "") or result.get("stderr", "") or result.get("error", ""),
                    "timestamp": int(time.time())
                }
                
                # 追加新日志
                logs.append(log_entry)
                
                # 写回文件
                with open(self.log_file, 'w', encoding='utf-8') as f:
                    json.dump(logs, f, ensure_ascii=False, indent=2)
                
                logger.debug(f"已保存命令执行日志: {command}")
        except Exception as e:
            logger.error(f"保存执行日志失败: {e}")

class SSHConnection:
    """单个SSH连接配置类"""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        """
        初始化SSH连接配置
        
        Args:
            name: 连接名称
            config: 连接配置字典，包含 host, username, password, key_path, port 等
        """
        self.name = name
        self.ssh_host = config.get('host')
        self.ssh_port = int(config.get('port', 22))
        self.ssh_username = config.get('username')
        self.ssh_password = config.get('password')
        self.ssh_key_path = config.get('key_path')
        
        if not self.ssh_host or not self.ssh_username:
            raise ValueError(f"连接 '{name}' 必须设置 host 和 username")
        
        if not self.ssh_password and not self.ssh_key_path:
            raise ValueError(f"连接 '{name}' 必须设置 password 或 key_path")
    
    def create_client(self) -> paramiko.SSHClient:
        """创建并配置SSH客户端"""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        return client
    
    def connect(self, client: paramiko.SSHClient) -> None:
        """建立SSH连接"""
        try:
            if self.ssh_key_path and os.path.exists(self.ssh_key_path):
                # 使用密钥认证
                key = paramiko.RSAKey.from_private_key_file(self.ssh_key_path)
                client.connect(
                    hostname=self.ssh_host,
                    port=self.ssh_port,
                    username=self.ssh_username,
                    pkey=key,
                    timeout=10
                )
            else:
                # 使用密码认证
                client.connect(
                    hostname=self.ssh_host,
                    port=self.ssh_port,
                    username=self.ssh_username,
                    password=self.ssh_password,
                    timeout=10
                )
            logger.info(f"成功连接到 {self.ssh_host}:{self.ssh_port} (连接名: {self.name})")
        except Exception as e:
            logger.error(f"SSH连接失败 (连接名: {self.name}): {e}")
            raise
    
    def get_info(self) -> Dict[str, Any]:
        """获取连接信息（不包含敏感数据）"""
        return {
            "name": self.name,
            "host": self.ssh_host,
            "port": self.ssh_port,
            "username": self.ssh_username,
            "auth_method": "key" if self.ssh_key_path else "password",
            "key_path": self.ssh_key_path if self.ssh_key_path else None
        }


class SSHConnectionManager:
    """SSH连接管理器，支持多个命名连接"""
    
    def __init__(self):
        self.connections: Dict[str, SSHConnection] = {}
        self.default_connection_name: Optional[str] = None
        self._discover_connections()
    
    def _discover_connections(self):
        """从环境变量中发现并加载所有SSH连接配置"""
        # 1. 发现命名连接 (格式: SSH_{NAME}_{PARAM})
        named_configs = {}
        
        for key, value in os.environ.items():
            if key.startswith('SSH_') and key.count('_') >= 2:
                parts = key.split('_', 2)
                if len(parts) == 3:
                    _, name, param = parts
                    param_lower = param.lower()
                    
                    # 跳过特殊配置项
                    if name in ['DEFAULT', 'EXEC', 'LOG']:
                        continue
                    
                    if name not in named_configs:
                        named_configs[name] = {}
                    
                    # 映射参数名
                    if param_lower == 'host':
                        named_configs[name]['host'] = value
                    elif param_lower == 'username':
                        named_configs[name]['username'] = value
                    elif param_lower == 'password':
                        named_configs[name]['password'] = value
                    elif param_lower in ['key', 'keypath', 'key_path']:
                        named_configs[name]['key_path'] = value
                    elif param_lower == 'port':
                        named_configs[name]['port'] = value
        
        # 2. 注册命名连接
        for name, config in named_configs.items():
            try:
                connection_name = name.lower()
                self.connections[connection_name] = SSHConnection(connection_name, config)
                logger.info(f"已注册命名连接: {connection_name} -> {config.get('host')}")
            except ValueError as e:
                logger.warning(f"跳过无效的连接配置 '{name}': {e}")
        
        # 3. 检查传统单连接配置（向后兼容）
        legacy_config = {}
        if os.getenv('SSH_HOST'):
            legacy_config['host'] = os.getenv('SSH_HOST')
        if os.getenv('SSH_USERNAME'):
            legacy_config['username'] = os.getenv('SSH_USERNAME')
        if os.getenv('SSH_PASSWORD'):
            legacy_config['password'] = os.getenv('SSH_PASSWORD')
        if os.getenv('SSH_KEY_PATH'):
            legacy_config['key_path'] = os.getenv('SSH_KEY_PATH')
        if os.getenv('SSH_PORT'):
            legacy_config['port'] = os.getenv('SSH_PORT')
        
        # 如果存在传统配置且没有名为 'default' 的命名连接，则注册为 'default'
        if legacy_config.get('host') and 'default' not in self.connections:
            try:
                self.connections['default'] = SSHConnection('default', legacy_config)
                logger.info(f"已注册传统配置为 'default' 连接 -> {legacy_config.get('host')}")
            except ValueError as e:
                logger.warning(f"传统配置无效: {e}")
        
        # 4. 设置默认连接
        default_name = os.getenv('SSH_DEFAULT_CONNECTION', '').lower()
        if default_name and default_name in self.connections:
            self.default_connection_name = default_name
            logger.info(f"默认连接设置为: {default_name}")
        elif self.connections:
            # 如果没有指定默认连接，使用第一个可用连接
            self.default_connection_name = list(self.connections.keys())[0]
            logger.info(f"默认连接自动设置为: {self.default_connection_name}")
        
        if not self.connections:
            logger.warning("未找到任何SSH连接配置")
    
    def get_connection(self, name: Optional[str] = None) -> SSHConnection:
        """
        获取指定名称的连接，如果未指定则返回默认连接
        
        Args:
            name: 连接名称，如果为 None 则使用默认连接
            
        Returns:
            SSHConnection 实例
            
        Raises:
            ValueError: 如果连接不存在或没有可用连接
        """
        if not self.connections:
            raise ValueError("没有可用的SSH连接配置")
        
        if name is None:
            if self.default_connection_name is None:
                raise ValueError("没有设置默认连接")
            name = self.default_connection_name
        
        name = name.lower()
        if name not in self.connections:
            available = ', '.join(self.connections.keys())
            raise ValueError(f"连接 '{name}' 不存在。可用连接: {available}")
        
        return self.connections[name]
    
    def list_connections(self) -> Dict[str, Dict[str, Any]]:
        """列出所有可用连接及其信息"""
        return {
            name: conn.get_info() 
            for name, conn in self.connections.items()
        }
    
    def get_default_connection_name(self) -> Optional[str]:
        """获取默认连接名称"""
        return self.default_connection_name


# 全局SSH连接管理器
ssh_manager = SSHConnectionManager()

# 全局日志管理器
log_manager = ExecLogManager()

@mcp.tool()
def list_ssh_connections() -> Dict[str, Any]:
    """
    列出所有可用的SSH连接配置
    
    Returns:
        Dict包含连接列表和默认连接：
        - connections: 所有连接的详细信息
        - default_connection: 默认连接名称
        - total_count: 连接总数
    """
    connections = ssh_manager.list_connections()
    return {
        "connections": connections,
        "default_connection": ssh_manager.get_default_connection_name(),
        "total_count": len(connections)
    }

@mcp.tool()
def execute_command(command: str, timeout: int = 30, connection_name: Optional[str] = None) -> Dict[str, Any]:
    """
    在远程服务器上执行shell命令
    
    Args:
        command: 要执行的shell命令
        timeout: 命令执行超时时间（秒），默认30秒
        connection_name: SSH连接名称，如果不指定则使用默认连接
    
    Returns:
        Dict包含执行结果：
        - success: 是否成功执行
        - exit_code: 命令退出码
        - stdout: 标准输出
        - stderr: 标准错误输出
        - error: 错误信息（如果有）
        - connection: 使用的连接名称
    """
    client = None
    try:
        connection = ssh_manager.get_connection(connection_name)
        client = connection.create_client()
        connection.connect(client)
        
        # 执行命令
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        
        # 等待命令完成并获取结果
        exit_code = stdout.channel.recv_exit_status()
        stdout_data = stdout.read().decode('utf-8', errors='replace')
        stderr_data = stderr.read().decode('utf-8', errors='replace')
        
        result = {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "stdout": stdout_data,
            "stderr": stderr_data,
            "error": None,
            "connection": connection.name
        }
        
        logger.info(f"命令执行完成 [{connection.name}]: '{command}', 退出码: {exit_code}")
        log_manager.save_execution_log(command, result)
        return result
        
    except ValueError as e:
        error_msg = str(e)
        logger.error(error_msg)
        result = {
            "success": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": "",
            "error": error_msg,
            "connection": connection_name
        }
        log_manager.save_execution_log(command, result)
        return result
    except paramiko.AuthenticationException:
        error_msg = "SSH认证失败，请检查用户名和密码/密钥"
        logger.error(error_msg)
        result = {
            "success": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": "",
            "error": error_msg,
            "connection": connection_name
        }
        log_manager.save_execution_log(command, result)
        return result
    except paramiko.SSHException as e:
        error_msg = f"SSH连接错误: {str(e)}"
        logger.error(error_msg)
        result = {
            "success": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": "",
            "error": error_msg,
            "connection": connection_name
        }
        log_manager.save_execution_log(command, result)
        return result
    except Exception as e:
        error_msg = f"命令执行失败: {str(e)}"
        logger.error(error_msg)
        result = {
            "success": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": "",
            "error": error_msg,
            "connection": connection_name
        }
        log_manager.save_execution_log(command, result)
        return result
    finally:
        if client:
            client.close()

@mcp.tool()
def check_ssh_connection(connection_name: Optional[str] = None) -> Dict[str, Any]:
    """
    检查SSH连接状态
    
    Args:
        connection_name: SSH连接名称，如果不指定则使用默认连接
    
    Returns:
        Dict包含连接状态信息：
        - connected: 是否能够连接
        - connection_name: 连接名称
        - host: 目标主机
        - port: 目标端口
        - username: 用户名
        - error: 错误信息（如果有）
    """
    client = None
    try:
        connection = ssh_manager.get_connection(connection_name)
        client = connection.create_client()
        connection.connect(client)
        
        # 执行一个简单的命令来测试连接
        stdin, stdout, stderr = client.exec_command('echo "连接测试成功"', timeout=5)
        output = stdout.read().decode('utf-8', errors='replace').strip()
        
        return {
            "connected": True,
            "connection_name": connection.name,
            "host": connection.ssh_host,
            "port": connection.ssh_port,
            "username": connection.ssh_username,
            "test_output": output,
            "error": None
        }
        
    except ValueError as e:
        error_msg = str(e)
        logger.error(error_msg)
        return {
            "connected": False,
            "connection_name": connection_name,
            "host": None,
            "port": None,
            "username": None,
            "test_output": "",
            "error": error_msg
        }
    except Exception as e:
        error_msg = f"SSH连接测试失败: {str(e)}"
        logger.error(error_msg)
        try:
            connection = ssh_manager.get_connection(connection_name)
            return {
                "connected": False,
                "connection_name": connection.name,
                "host": connection.ssh_host,
                "port": connection.ssh_port,
                "username": connection.ssh_username,
                "test_output": "",
                "error": error_msg
            }
        except:
            return {
                "connected": False,
                "connection_name": connection_name,
                "host": None,
                "port": None,
                "username": None,
                "test_output": "",
                "error": error_msg
            }
    finally:
        if client:
            client.close()

@mcp.tool()
def execute_interactive_command(command: str, input_data: str = "", timeout: int = 30, connection_name: Optional[str] = None) -> Dict[str, Any]:
    """
    执行交互式命令（可以发送输入数据）
    
    Args:
        command: 要执行的shell命令
        input_data: 要发送给命令的输入数据
        timeout: 命令执行超时时间（秒），默认30秒
        connection_name: SSH连接名称，如果不指定则使用默认连接
    
    Returns:
        Dict包含执行结果（同execute_command）
    """
    client = None
    try:
        connection = ssh_manager.get_connection(connection_name)
        client = connection.create_client()
        connection.connect(client)
        
        # 执行命令
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        
        # 如果有输入数据，发送给命令
        if input_data:
            stdin.write(input_data)
            stdin.flush()
        
        # 关闭stdin以表示输入结束
        stdin.close()
        
        # 等待命令完成并获取结果
        exit_code = stdout.channel.recv_exit_status()
        stdout_data = stdout.read().decode('utf-8', errors='replace')
        stderr_data = stderr.read().decode('utf-8', errors='replace')
        
        result = {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "stdout": stdout_data,
            "stderr": stderr_data,
            "error": None,
            "connection": connection.name
        }
        
        logger.info(f"交互式命令执行完成 [{connection.name}]: '{command}', 退出码: {exit_code}")
        log_manager.save_execution_log(command, result)
        return result
        
    except ValueError as e:
        error_msg = str(e)
        logger.error(error_msg)
        result = {
            "success": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": "",
            "error": error_msg,
            "connection": connection_name
        }
        log_manager.save_execution_log(command, result)
        return result
    except Exception as e:
        error_msg = f"交互式命令执行失败: {str(e)}"
        logger.error(error_msg)
        result = {
            "success": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": "",
            "error": error_msg,
            "connection": connection_name
        }
        log_manager.save_execution_log(command, result)
        return result
    finally:
        if client:
            client.close()

@mcp.tool()
def upload_file(local_path: str, remote_path: str, timeout: int = 60, connection_name: Optional[str] = None) -> Dict[str, Any]:
    """
    使用SFTP协议上传文件到远程服务器
    
    Args:
        local_path: 本地文件路径
                   推荐使用绝对路径以避免路径解析问题
                   如果使用相对路径，将基于MCP服务器的工作目录进行解析
        remote_path: 远程服务器文件路径（绝对路径）
        timeout: 传输超时时间（秒），默认60秒
        connection_name: SSH连接名称，如果不指定则使用默认连接
    
    Returns:
        Dict包含上传结果：
        - success: 是否成功上传
        - local_path: 本地文件路径（转换为绝对路径后）
        - remote_path: 远程文件路径
        - file_size: 文件大小（字节）
        - connection: 使用的连接名称
        - error: 错误信息（如果有）
    """
    client = None
    sftp = None
    try:
        # 将本地路径转换为绝对路径，提高兼容性
        local_path = os.path.abspath(local_path)
        
        # 检查本地文件是否存在
        if not os.path.exists(local_path):
            error_msg = f"本地文件不存在: {local_path} (已转换为绝对路径，请确认文件路径是否正确)"
            logger.error(error_msg)
            return {
                "success": False,
                "local_path": local_path,
                "remote_path": remote_path,
                "file_size": 0,
                "connection": connection_name,
                "error": error_msg
            }
        
        # 获取文件大小
        file_size = os.path.getsize(local_path)
        
        # 建立SSH连接
        connection = ssh_manager.get_connection(connection_name)
        client = connection.create_client()
        connection.connect(client)
        
        # 创建SFTP客户端
        sftp = client.open_sftp()
        
        # 设置超时
        sftp.get_channel().settimeout(timeout)
        
        # 确保远程目录存在
        remote_dir = os.path.dirname(remote_path)
        if remote_dir:
            try:
                # 尝试创建远程目录（如果不存在）
                stdin, stdout, stderr = client.exec_command(f'mkdir -p "{remote_dir}"')
                stdout.channel.recv_exit_status()  # 等待命令完成
            except Exception as e:
                logger.warning(f"创建远程目录时出现警告: {e}")
        
        # 上传文件
        logger.info(f"开始上传文件 [{connection.name}]: {local_path} -> {remote_path} ({file_size} 字节)")
        sftp.put(local_path, remote_path)
        
        # 验证上传是否成功
        try:
            remote_stat = sftp.stat(remote_path)
            if remote_stat.st_size == file_size:
                logger.info(f"文件上传成功 [{connection.name}]: {local_path} -> {remote_path}")
                return {
                    "success": True,
                    "local_path": local_path,
                    "remote_path": remote_path,
                    "file_size": file_size,
                    "connection": connection.name,
                    "error": None
                }
            else:
                error_msg = f"文件上传验证失败: 远程文件大小({remote_stat.st_size})与本地文件大小({file_size})不匹配"
                logger.error(error_msg)
                return {
                    "success": False,
                    "local_path": local_path,
                    "remote_path": remote_path,
                    "file_size": file_size,
                    "connection": connection.name,
                    "error": error_msg
                }
        except Exception as e:
            error_msg = f"无法验证远程文件: {str(e)}"
            logger.warning(error_msg)
            # 即使验证失败，我们仍然认为上传可能成功了
            return {
                "success": True,
                "local_path": local_path,
                "remote_path": remote_path,
                "file_size": file_size,
                "connection": connection.name,
                "error": f"上传完成但验证失败: {error_msg}"
            }
        
    except ValueError as e:
        error_msg = str(e)
        logger.error(error_msg)
        return {
            "success": False,
            "local_path": local_path,
            "remote_path": remote_path,
            "file_size": 0,
            "connection": connection_name,
            "error": error_msg
        }
    except paramiko.AuthenticationException:
        error_msg = "SSH认证失败，请检查用户名和密码/密钥"
        logger.error(error_msg)
        return {
            "success": False,
            "local_path": local_path,
            "remote_path": remote_path,
            "file_size": 0,
            "connection": connection_name,
            "error": error_msg
        }
    except paramiko.SSHException as e:
        error_msg = f"SSH连接错误: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "local_path": local_path,
            "remote_path": remote_path,
            "file_size": 0,
            "connection": connection_name,
            "error": error_msg
        }
    except FileNotFoundError:
        error_msg = f"本地文件未找到: {local_path} (请确认使用正确的绝对路径)"
        logger.error(error_msg)
        return {
            "success": False,
            "local_path": local_path,
            "remote_path": remote_path,
            "file_size": 0,
            "connection": connection_name,
            "error": error_msg
        }
    except PermissionError:
        error_msg = f"权限错误: 无法访问本地文件 {local_path} 或远程路径 {remote_path}"
        logger.error(error_msg)
        return {
            "success": False,
            "local_path": local_path,
            "remote_path": remote_path,
            "file_size": 0,
            "connection": connection_name,
            "error": error_msg
        }
    except Exception as e:
        error_msg = f"文件上传失败: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "local_path": local_path,
            "remote_path": remote_path,
            "file_size": 0,
            "connection": connection_name,
            "error": error_msg
        }
    finally:
        if sftp:
            sftp.close()
        if client:
            client.close()

@mcp.tool()
def download_file(remote_path: str, local_path: str, timeout: int = 60, connection_name: Optional[str] = None) -> Dict[str, Any]:
    """
    使用SFTP协议从远程服务器下载文件到本地
    
    Args:
        remote_path: 远程服务器文件路径（绝对路径）
        local_path: 本地文件保存路径
                   推荐使用绝对路径以避免路径解析问题
                   如果使用相对路径，将基于MCP服务器的工作目录进行解析
        timeout: 传输超时时间（秒），默认60秒
        connection_name: SSH连接名称，如果不指定则使用默认连接
    
    Returns:
        Dict包含下载结果：
        - success: 是否成功下载
        - remote_path: 远程文件路径
        - local_path: 本地文件路径（转换为绝对路径后）
        - file_size: 文件大小（字节）
        - connection: 使用的连接名称
        - error: 错误信息（如果有）
    """
    client = None
    sftp = None
    try:
        # 将本地路径转换为绝对路径，提高兼容性
        local_path = os.path.abspath(local_path)
        
        # 建立SSH连接
        connection = ssh_manager.get_connection(connection_name)
        client = connection.create_client()
        connection.connect(client)
        
        # 创建SFTP客户端
        sftp = client.open_sftp()
        
        # 设置超时
        sftp.get_channel().settimeout(timeout)
        
        # 检查远程文件是否存在
        try:
            remote_stat = sftp.stat(remote_path)
            file_size = remote_stat.st_size
        except FileNotFoundError:
            error_msg = f"远程文件不存在: {remote_path}"
            logger.error(error_msg)
            return {
                "success": False,
                "remote_path": remote_path,
                "local_path": local_path,
                "file_size": 0,
                "connection": connection.name,
                "error": error_msg
            }
        
        # 确保本地目录存在
        local_dir = os.path.dirname(local_path)
        if local_dir and not os.path.exists(local_dir):
            try:
                os.makedirs(local_dir, exist_ok=True)
                logger.info(f"创建本地目录: {local_dir}")
            except Exception as e:
                error_msg = f"创建本地目录失败: {e}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "remote_path": remote_path,
                    "local_path": local_path,
                    "file_size": 0,
                    "connection": connection.name,
                    "error": error_msg
                }
        
        # 下载文件
        logger.info(f"开始下载文件 [{connection.name}]: {remote_path} -> {local_path} ({file_size} 字节)")
        sftp.get(remote_path, local_path)
        
        # 验证下载是否成功
        if os.path.exists(local_path):
            local_size = os.path.getsize(local_path)
            if local_size == file_size:
                logger.info(f"文件下载成功 [{connection.name}]: {remote_path} -> {local_path}")
                return {
                    "success": True,
                    "remote_path": remote_path,
                    "local_path": local_path,
                    "file_size": file_size,
                    "connection": connection.name,
                    "error": None
                }
            else:
                error_msg = f"文件下载验证失败: 本地文件大小({local_size})与远程文件大小({file_size})不匹配"
                logger.error(error_msg)
                return {
                    "success": False,
                    "remote_path": remote_path,
                    "local_path": local_path,
                    "file_size": file_size,
                    "connection": connection.name,
                    "error": error_msg
                }
        else:
            error_msg = "下载后本地文件不存在"
            logger.error(error_msg)
            return {
                "success": False,
                "remote_path": remote_path,
                "local_path": local_path,
                "file_size": file_size,
                "connection": connection.name,
                "error": error_msg
            }
        
    except ValueError as e:
        error_msg = str(e)
        logger.error(error_msg)
        return {
            "success": False,
            "remote_path": remote_path,
            "local_path": local_path,
            "file_size": 0,
            "connection": connection_name,
            "error": error_msg
        }
    except paramiko.AuthenticationException:
        error_msg = "SSH认证失败，请检查用户名和密码/密钥"
        logger.error(error_msg)
        return {
            "success": False,
            "remote_path": remote_path,
            "local_path": local_path,
            "file_size": 0,
            "connection": connection_name,
            "error": error_msg
        }
    except paramiko.SSHException as e:
        error_msg = f"SSH连接错误: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "remote_path": remote_path,
            "local_path": local_path,
            "file_size": 0,
            "connection": connection_name,
            "error": error_msg
        }
    except PermissionError:
        error_msg = f"权限错误: 无法访问远程文件 {remote_path} 或本地路径 {local_path}"
        logger.error(error_msg)
        return {
            "success": False,
            "remote_path": remote_path,
            "local_path": local_path,
            "file_size": 0,
            "connection": connection_name,
            "error": error_msg
        }
    except Exception as e:
        error_msg = f"文件下载失败: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "remote_path": remote_path,
            "local_path": local_path,
            "file_size": 0,
            "connection": connection_name,
            "error": error_msg
        }
    finally:
        if sftp:
            sftp.close()
        if client:
            client.close()

@mcp.tool()
def list_directory(remote_path: str = ".", timeout: int = 30, connection_name: Optional[str] = None) -> Dict[str, Any]:
    """
    获取远程目录的结构化文件列表
    
    Args:
        remote_path: 远程目录路径，默认为当前目录 "."
        timeout: 操作超时时间（秒），默认30秒
        connection_name: SSH连接名称，如果不指定则使用默认连接
    
    Returns:
        Dict包含目录列表结果：
        - success: 是否成功获取
        - path: 目录路径
        - files: 文件列表，每个文件包含：
            - name: 文件名
            - type: 类型 (file/directory/symlink/other)
            - size: 文件大小（字节，仅文件类型）
            - permissions: 权限字符串（如 "rwxr-xr-x"）
            - modified_time: 修改时间（Unix时间戳）
            - owner_uid: 所有者UID
            - group_gid: 组GID
        - total_count: 文件总数
        - connection: 使用的连接名称
        - error: 错误信息（如果有）
    """
    client = None
    sftp = None
    try:
        # 建立SSH连接
        connection = ssh_manager.get_connection(connection_name)
        client = connection.create_client()
        connection.connect(client)
        
        # 创建SFTP客户端
        sftp = client.open_sftp()
        
        # 设置超时
        sftp.get_channel().settimeout(timeout)
        
        # 获取目录列表
        logger.info(f"获取目录列表 [{connection.name}]: {remote_path}")
        
        try:
            # 列出目录内容
            file_attrs = sftp.listdir_attr(remote_path)
        except FileNotFoundError:
            error_msg = f"远程目录不存在: {remote_path}"
            logger.error(error_msg)
            return {
                "success": False,
                "path": remote_path,
                "files": [],
                "total_count": 0,
                "connection": connection.name,
                "error": error_msg
            }
        except PermissionError:
            error_msg = f"权限不足，无法访问目录: {remote_path}"
            logger.error(error_msg)
            return {
                "success": False,
                "path": remote_path,
                "files": [],
                "total_count": 0,
                "connection": connection.name,
                "error": error_msg
            }
        
        # 解析文件属性
        files = []
        for attr in file_attrs:
            import stat
            
            # 判断文件类型
            if stat.S_ISDIR(attr.st_mode):
                file_type = "directory"
            elif stat.S_ISREG(attr.st_mode):
                file_type = "file"
            elif stat.S_ISLNK(attr.st_mode):
                file_type = "symlink"
            else:
                file_type = "other"
            
            # 转换权限为字符串格式
            def mode_to_permissions(mode):
                """将数字权限转换为字符串格式"""
                perms = ""
                # 所有者权限
                perms += "r" if mode & stat.S_IRUSR else "-"
                perms += "w" if mode & stat.S_IWUSR else "-"
                perms += "x" if mode & stat.S_IXUSR else "-"
                # 组权限
                perms += "r" if mode & stat.S_IRGRP else "-"
                perms += "w" if mode & stat.S_IWGRP else "-"
                perms += "x" if mode & stat.S_IXGRP else "-"
                # 其他用户权限
                perms += "r" if mode & stat.S_IROTH else "-"
                perms += "w" if mode & stat.S_IWOTH else "-"
                perms += "x" if mode & stat.S_IXOTH else "-"
                return perms
            
            file_info = {
                "name": attr.filename,
                "type": file_type,
                "size": attr.st_size if file_type == "file" else None,
                "permissions": mode_to_permissions(attr.st_mode),
                "modified_time": attr.st_mtime,
                "owner_uid": attr.st_uid,
                "group_gid": attr.st_gid
            }
            files.append(file_info)
        
        # 按名称排序（目录在前，文件在后）
        files.sort(key=lambda x: (x["type"] != "directory", x["name"]))
        
        logger.info(f"成功获取目录列表 [{connection.name}]: {remote_path}, 共 {len(files)} 项")
        return {
            "success": True,
            "path": remote_path,
            "files": files,
            "total_count": len(files),
            "connection": connection.name,
            "error": None
        }
        
    except ValueError as e:
        error_msg = str(e)
        logger.error(error_msg)
        return {
            "success": False,
            "path": remote_path,
            "files": [],
            "total_count": 0,
            "connection": connection_name,
            "error": error_msg
        }
    except paramiko.AuthenticationException:
        error_msg = "SSH认证失败，请检查用户名和密码/密钥"
        logger.error(error_msg)
        return {
            "success": False,
            "path": remote_path,
            "files": [],
            "total_count": 0,
            "connection": connection_name,
            "error": error_msg
        }
    except paramiko.SSHException as e:
        error_msg = f"SSH连接错误: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "path": remote_path,
            "files": [],
            "total_count": 0,
            "connection": connection_name,
            "error": error_msg
        }
    except Exception as e:
        error_msg = f"获取目录列表失败: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "path": remote_path,
            "files": [],
            "total_count": 0,
            "connection": connection_name,
            "error": error_msg
        }
    finally:
        if sftp:
            sftp.close()
        if client:
            client.close()

def main():
    """主函数入口点"""
    try:
        # 在启动时显示所有可用连接
        logger.info("正在加载SSH连接配置...")
        connections_info = list_ssh_connections()
        
        if connections_info["total_count"] > 0:
            logger.info(f"已加载 {connections_info['total_count']} 个SSH连接:")
            for name, info in connections_info["connections"].items():
                logger.info(f"  - {name}: {info['username']}@{info['host']}:{info['port']} ({info['auth_method']})")
            logger.info(f"默认连接: {connections_info['default_connection']}")
            
            # 测试默认连接
            logger.info("正在测试默认连接...")
            test_result = check_ssh_connection()
            if test_result["connected"]:
                logger.info(f"默认连接测试成功: {test_result['connection_name']}")
            else:
                logger.warning(f"默认连接测试失败: {test_result['error']}")
        else:
            logger.warning("未找到任何SSH连接配置，服务器将以受限模式启动")
        
        # 启动MCP服务器
        mcp.run()
    except Exception as e:
        logger.error(f"服务器启动失败: {e}")
        exit(1)

if __name__ == "__main__":
    main()