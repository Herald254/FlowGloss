#!/usr/bin/env python3
"""
FlowGloss 智能安装脚本

功能：
- 自动检测硬件环境（GPU/CPU）
- 检测CUDA版本和驱动兼容性
- 自动选择合适的依赖版本
- 提供交互式安装选项


使用方法：
    python install.py
    python install.py --gpu
    python install.py --cpu
    python install.py --dev
"""

import os
import sys
import subprocess
import platform
from pathlib import Path


def run_command(cmd, check=True):
    """执行命令并返回结果"""
    print(f"执行命令: {cmd}")
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            check=check,
            capture_output=True,
            text=True
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        return False, e.stdout, e.stderr


def check_nvidia_gpu():
    """检测NVIDIA GPU"""
    success, stdout, stderr = run_command("nvidia-smi --query-gpu=name --format=csv,noheader", check=False)
    if success and stdout.strip():
        gpu_name = stdout.strip()
        print(f"✓ 检测到NVIDIA GPU: {gpu_name}")
        return True, gpu_name
    else:
        print("✗ 未检测到NVIDIA GPU或nvidia-smi未安装")
        return False, None

def check_cuda_version():
    """检测CUDA版本"""
    success, stdout, stderr = run_command("nvcc --version", check=False)
    if success:
        version = stdout.split()[-1]
        print(f"✓ CUDA版本: {version}")
        return version
    else:
        print("✗ 未检测到CUDA编译器")
        return None

def check_python_version():
    """检查Python版本"""
    version = sys.version_info
    print(f"✓ Python版本: {version.major}.{version.minor}.{version.micro}")
    
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("✗ 警告: 推荐使用Python 3.8+")
        return False
    return True

def check_pip_version():
    """检查pip版本"""
    success, stdout, stderr = run_command("pip --version")
    if success:
        version = stdout.split()[-1]
        print(f"✓ pip版本: {version}")
        return True
    else:
        print("✗ 未检测到pip")
        return False

def install_requirements(requirements_file):
    """安装指定的requirements文件"""
    if not Path(requirements_file).exists():
        print(f"✗ 错误: 找不到文件 {requirements_file}")
        return False
    
    print(f"\n正在安装 {requirements_file} 中的依赖...")
    success, stdout, stderr = run_command(f"pip install -r {requirements_file}")
    
    if success:
        print(f"\n✓ {requirements_file} 安装成功！")
        return True
    else:
        print(f"\n✗ {requirements_file} 安装失败！")
        print(f"错误信息: {stderr}")
        return False

def main():
    """主函数"""
    print("=" * 60)
    print("FlowGloss 智能安装脚本")
    print("=" * 60)
    print()
    
    # 解析命令行参数
    force_gpu = '--gpu' in sys.argv
    force_cpu = '--cpu' in sys.argv
    install_dev = '--dev' in sys.argv
    
    # 检查Python版本
    print("[1/5] 检查Python版本...")
    if not check_python_version():
        print("\n请先升级Python版本到3.8+")
        sys.exit(1)
    
    # 检查pip版本
    print("\n[2/5] 检查pip版本...")
    if not check_pip_version():
        print("\n请先安装pip")
        sys.exit(1)
    
    # 检测GPU环境
    print("\n[3/5] 检测GPU环境...")
    has_gpu, gpu_name = check_nvidia_gpu()
    cuda_version = check_cuda_version()
    
    # 选择依赖版本
    print("\n[4/5] 选择依赖版本...")
    
    if force_gpu:
        print("用户强制使用GPU版本")
        requirements_file = "requirements-gpu.txt"
    elif force_cpu:
        print("用户强制使用CPU版本")
        requirements_file = "requirements-cpu.txt"
    elif has_gpu and cuda_version:
        print("自动选择GPU版本")
        requirements_file = "requirements-gpu.txt"
    else:
        print("自动选择CPU版本")
        requirements_file = "requirements-cpu.txt"
    
    # 安装依赖
    print("\n[5/5] 安装依赖...")
    
    if not install_requirements(requirements_file):
        sys.exit(1)
    
    # 安装开发依赖
    if install_dev:
        print("\n安装开发依赖...")
        dev_requirements = """
pytest>=7.4.0
pytest-asyncio>=0.21.0
black>=23.12.0
mypy>=1.8.0
pylint>=3.0.0
"""
        
        # 创建临时文件
        temp_file = "requirements-dev.txt"
        with open(temp_file, 'w') as f:
            f.write(dev_requirements)
        
        if not install_requirements(temp_file):
            os.remove(temp_file)
            sys.exit(1)
        
        os.remove(temp_file)
        print("\n✓ 开发依赖安装成功！")
    
    print("\n" + "=" * 60)
    print("安装完成！")
    print("=" * 60)
    print()
    print("使用方法：")
    print("  python main.py")
    print()
    print("注意事项：")
    print("  - 首次运行可能需要较长时间（加载模型）")
    print("  - GPU版本需要8GB+显存（推荐16GB）")
    print("  - 如遇问题，请查看logs/flowgloss.log")
    print()

if __name__ == "__main__":
    main()