#!/usr/bin/env python3
"""测试服务器POST请求"""
import requests
import os

# 测试文件路径
script_file = 'test_input/script-test.md'
srt_file = 'test_input/input.srt'

if not os.path.exists(script_file):
    print(f"错误：找不到文件 {script_file}")
    exit(1)

if not os.path.exists(srt_file):
    print(f"错误：找不到文件 {srt_file}")
    exit(1)

# 准备POST数据
url = 'http://127.0.0.1:5000/review'

with open(script_file, 'rb') as f:
    script_data = f.read()

with open(srt_file, 'rb') as f:
    srt_data = f.read()

# 创建multipart/form-data请求
files = {
    'script_file': ('script-test.md', script_data, 'text/markdown'),
    'srt_file': ('input.srt', srt_data, 'text/plain')
}

print("正在发送POST请求到服务器 (V1 算法)...")

try:
    response = requests.post(url, files=files, timeout=30)

    print(f"\n✅ 服务器响应成功!")
    print(f"状态码: {response.status_code}")
    print(f"响应大小: {len(response.content)} 字节")

    if response.status_code == 200:
        # 检查是否包含预期的HTML内容
        if '字幕校对工具' in response.text:
            print("✅ 响应包含正确的HTML内容")
        else:
            print("⚠️  响应不包含预期的HTML内容")

    else:
        print(f"⚠️  状态码异常: {response.status_code}")
        print(f"响应内容:\n{response.text[:500]}")

except requests.exceptions.RequestException as e:
    print(f"❌ 请求失败: {e}")
except Exception as e:
    print(f"❌ 未知错误: {e}")
