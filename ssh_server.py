import os
import asyncio
from typing import Optional, Dict, Any
import paramiko
from mcp.server.fastmcp import FastMCP, Context
from mcp.types import TextContent
import io
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建 MCP 服务器
mcp = FastMCP(name="SSH Server", description="SSH连接管理和命令执行服务器")

class SSHConnection:
    """SSH连接管理类"""
    
    def __init__(self):
        self.ssh_host = os.getenv('SSH_HOST')
        self.ssh_port = int(os.getenv('SSH_PORT', '22'))
        self.ssh_username = os.getenv('SSH_USERNAME')
        self.ssh_password = os.getenv('SSH_PASSWORD')
        self.ssh_key_path = os.getenv('SSH_KEY_PATH')
        
        if not self.ssh_host or not self.ssh_username:
            raise ValueError("必须设置 SSH_HOST 和 SSH_USERNAME 环境变量")
        
        if not self.ssh_password and not self.ssh_key_path:
            raise ValueError("必须设置 SSH_PASSWORD 或 SSH_KEY_PATH 环境变量")
    
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
            logger.info(f"成功连接到 {self.ssh_host}:{self.ssh_port}")
        except Exception as e:
            logger.error(f"SSH连接失败: {e}")
            raise

# 全局SSH连接管理器
ssh_manager = SSHConnection()

@mcp.tool()
def execute_command(command: str, timeout: int = 30) -> Dict[str, Any]:
    """
    在远程服务器上执行shell命令
    
    Args:
        command: 要执行的shell命令
        timeout: 命令执行超时时间（秒），默认30秒
    
    Returns:
        Dict包含执行结果：
        - success: 是否成功执行
        - exit_code: 命令退出码
        - stdout: 标准输出
        - stderr: 标准错误输出
        - error: 错误信息（如果有）
    """
    client = None
    try:
        client = ssh_manager.create_client()
        ssh_manager.connect(client)
        
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
            "error": None
        }
        
        logger.info(f"命令执行完成: '{command}', 退出码: {exit_code}")
        return result
        
    except paramiko.AuthenticationException:
        error_msg = "SSH认证失败，请检查用户名和密码/密钥"
        logger.error(error_msg)
        return {
            "success": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": "",
            "error": error_msg
        }
    except paramiko.SSHException as e:
        error_msg = f"SSH连接错误: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": "",
            "error": error_msg
        }
    except Exception as e:
        error_msg = f"命令执行失败: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": "",
            "error": error_msg
        }
    finally:
        if client:
            client.close()

@mcp.tool()
def get_command_output(command: str, timeout: int = 30) -> str:
    """
    执行命令并仅返回标准输出内容
    
    Args:
        command: 要执行的shell命令
        timeout: 命令执行超时时间（秒），默认30秒
    
    Returns:
        命令的标准输出内容
    """
    result = execute_command(command, timeout)
    
    if result["success"]:
        return result["stdout"]
    else:
        # 如果命令失败，返回错误信息
        error_info = f"命令执行失败 (退出码: {result['exit_code']})"
        if result["stderr"]:
            error_info += f"\n错误输出: {result['stderr']}"
        if result["error"]:
            error_info += f"\n错误信息: {result['error']}"
        return error_info

@mcp.tool()
def check_ssh_connection() -> Dict[str, Any]:
    """
    检查SSH连接状态
    
    Returns:
        Dict包含连接状态信息：
        - connected: 是否能够连接
        - host: 目标主机
        - port: 目标端口
        - username: 用户名
        - error: 错误信息（如果有）
    """
    client = None
    try:
        client = ssh_manager.create_client()
        ssh_manager.connect(client)
        
        # 执行一个简单的命令来测试连接
        stdin, stdout, stderr = client.exec_command('echo "连接测试成功"', timeout=5)
        output = stdout.read().decode('utf-8', errors='replace').strip()
        
        return {
            "connected": True,
            "host": ssh_manager.ssh_host,
            "port": ssh_manager.ssh_port,
            "username": ssh_manager.ssh_username,
            "test_output": output,
            "error": None
        }
        
    except Exception as e:
        error_msg = f"SSH连接测试失败: {str(e)}"
        logger.error(error_msg)
        return {
            "connected": False,
            "host": ssh_manager.ssh_host,
            "port": ssh_manager.ssh_port,
            "username": ssh_manager.ssh_username,
            "test_output": "",
            "error": error_msg
        }
    finally:
        if client:
            client.close()

@mcp.tool()
def execute_interactive_command(command: str, input_data: str = "", timeout: int = 30) -> Dict[str, Any]:
    """
    执行交互式命令（可以发送输入数据）
    
    Args:
        command: 要执行的shell命令
        input_data: 要发送给命令的输入数据
        timeout: 命令执行超时时间（秒），默认30秒
    
    Returns:
        Dict包含执行结果（同execute_command）
    """
    client = None
    try:
        client = ssh_manager.create_client()
        ssh_manager.connect(client)
        
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
            "error": None
        }
        
        logger.info(f"交互式命令执行完成: '{command}', 退出码: {exit_code}")
        return result
        
    except Exception as e:
        error_msg = f"交互式命令执行失败: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": "",
            "error": error_msg
        }
    finally:
        if client:
            client.close()

@mcp.tool()
def upload_file(local_path: str, remote_path: str, timeout: int = 60) -> Dict[str, Any]:
    """
    使用SFTP协议上传文件到远程服务器
    
    Args:
        local_path: 本地文件路径
        remote_path: 远程服务器文件路径
        timeout: 传输超时时间（秒），默认60秒
    
    Returns:
        Dict包含上传结果：
        - success: 是否成功上传
        - local_path: 本地文件路径
        - remote_path: 远程文件路径
        - file_size: 文件大小（字节）
        - error: 错误信息（如果有）
    """
    client = None
    sftp = None
    try:
        # 检查本地文件是否存在
        if not os.path.exists(local_path):
            error_msg = f"本地文件不存在: {local_path}"
            logger.error(error_msg)
            return {
                "success": False,
                "local_path": local_path,
                "remote_path": remote_path,
                "file_size": 0,
                "error": error_msg
            }
        
        # 获取文件大小
        file_size = os.path.getsize(local_path)
        
        # 建立SSH连接
        client = ssh_manager.create_client()
        ssh_manager.connect(client)
        
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
        logger.info(f"开始上传文件: {local_path} -> {remote_path} ({file_size} 字节)")
        sftp.put(local_path, remote_path)
        
        # 验证上传是否成功
        try:
            remote_stat = sftp.stat(remote_path)
            if remote_stat.st_size == file_size:
                logger.info(f"文件上传成功: {local_path} -> {remote_path}")
                return {
                    "success": True,
                    "local_path": local_path,
                    "remote_path": remote_path,
                    "file_size": file_size,
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
                "error": f"上传完成但验证失败: {error_msg}"
            }
        
    except paramiko.AuthenticationException:
        error_msg = "SSH认证失败，请检查用户名和密码/密钥"
        logger.error(error_msg)
        return {
            "success": False,
            "local_path": local_path,
            "remote_path": remote_path,
            "file_size": 0,
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
            "error": error_msg
        }
    except FileNotFoundError:
        error_msg = f"本地文件未找到: {local_path}"
        logger.error(error_msg)
        return {
            "success": False,
            "local_path": local_path,
            "remote_path": remote_path,
            "file_size": 0,
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
        # 在启动时测试SSH连接配置
        logger.info("正在验证SSH连接配置...")
        test_result = check_ssh_connection()
        if test_result["connected"]:
            logger.info(f"SSH配置验证成功，连接到 {test_result['host']}:{test_result['port']}")
        else:
            logger.warning(f"SSH配置验证失败: {test_result['error']}")
        
        # 启动MCP服务器
        mcp.run()
    except Exception as e:
        logger.error(f"服务器启动失败: {e}")
        exit(1)

if __name__ == "__main__":
    main() 