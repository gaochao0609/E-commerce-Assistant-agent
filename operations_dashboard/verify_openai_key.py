# verify_openai_key.py
import os
import sys

try:
    from openai import OpenAI
except ImportError:
    print("未找到 openai SDK，请先执行: pip install openai>=1.0")
    sys.exit(1)

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("环境变量 OPENAI_API_KEY 未设置或为空。")
    sys.exit(1)

print("已读取环境变量 OPENAI_API_KEY（出于安全考虑不打印明文）。")

client = OpenAI(api_key=api_key)

try:
    response = client.models.list()
except Exception as exc:
    print("与 OpenAI 通信失败：")
    print(repr(exc))
    sys.exit(1)
else:
    print("调用成功，返回模型数量:", len(response.data))
    print("示例模型 ID:", response.data[0].id if response.data else "无模型返回")
    print("OPENAI_API_KEY 可用。")
