from http.server import BaseHTTPRequestHandler
import json
import os
import requests
from datetime import datetime

# OpenRouter API配置
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
# 从环境变量获取API密钥
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()
        
    def do_POST(self):
        # 读取请求体
        content_length = int(self.headers.get('Content-Length', 0))
        request_body = self.rfile.read(content_length)
        request_json = json.loads(request_body) if content_length > 0 else {}
        
        # 记录请求
        request_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{request_time}] 收到请求: {json.dumps(request_json)}")
        
        # 准备转发到OpenRouter的请求
        headers = {
            'Authorization': f'Bearer {OPENROUTER_API_KEY}',
            'Content-Type': 'application/json',
            'HTTP-Referer': 'https://your-site-name.vercel.app'  # 替换为你的Vercel域名
        }
        
        # 转发请求到OpenRouter
        try:
            response = requests.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=request_json,
                timeout=60
            )
            
            # 获取OpenRouter的响应
            response_data = response.json()
            
            # 记录响应
            print(f"[{request_time}] 收到响应: {json.dumps(response_data)}")
            
            # 返回响应给客户端
            self.send_response(response.status_code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode('utf-8'))
            
        except Exception as e:
            # 处理错误
            error_message = f"转发请求时出错: {str(e)}"
            print(f"[{request_time}] ERROR: {error_message}")
            
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"error": error_message}).encode('utf-8'))
    
    def do_GET(self):
        # 简单的健康检查
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps({
            "status": "ok",
            "message": "OpenRouter代理服务运行正常"
        }).encode('utf-8'))
