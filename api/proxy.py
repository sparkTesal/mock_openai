import json
import os
import requests
import time
import uuid
from http.server import BaseHTTPRequestHandler

# 配置项
OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"

MODEL_NAME_MAP = {
    "gpt-4o": "anthropic/claude-3.7-sonnet",
    "gpt-3.5-turbo": "anthropic/claude-3.5-sonnet",
    "gpt-4": "anthropic/claude-3.7-sonnet:thinking"
}


def get_api_key():
    return os.environ.get("OPENROUTER_API_KEY", "")


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """处理健康检查请求"""
        request_id = str(uuid.uuid4())[:8]
        print(f"[{request_id}] 收到GET请求: {self.path}")

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        response_data = {
            "status": "ok",
            "message": "OpenRouter代理服务运行正常",
            "version": "1.1.0"
        }
        self.wfile.write(json.dumps(response_data).encode())
        print(f"[{request_id}] 健康检查响应完成")

    def do_OPTIONS(self):
        """处理预检请求"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        """处理API转发请求"""
        request_id = str(uuid.uuid4())[:8]
        start_time = time.time()

        # 读取请求内容
        content_length = int(self.headers.get('Content-Length', 0))
        request_body = self.rfile.read(content_length).decode('utf-8')

        try:
            # 解析请求
            request_data = json.loads(request_body)

            # 记录请求信息
            print(f"[{request_id}] 收到请求: ")
            print(f"{json.dumps(request_data, ensure_ascii=False)}")

            if "model" in request_data:
                request_data["model"] = MODEL_NAME_MAP.get(request_data["model"], request_data["model"])

            # 检查是否请求流式响应
            stream_mode = request_data.get('stream', False)
            print(f"[{request_id}] 流式模式: {stream_mode}")

            # 准备发送到OpenRouter的请求
            openrouter_url = f"{OPENROUTER_API_BASE}/chat/completions"
            openrouter_headers = {
                "Authorization": f"Bearer {get_api_key()}",
                "HTTP-Referer": self.headers.get('Referer', 'https://proxy.example.com'),
                "X-Title": "OpenRouter Proxy",
                "Content-Type": "application/json"
            }

            # 发送请求到OpenRouter
            print(f"[{request_id}] 发送请求到OpenRouter，模型: {request_data.get('model', 'default')}")
            try:
                if stream_mode:
                    # 流式响应处理
                    self._handle_streaming_response(request_id, request_data, openrouter_url, openrouter_headers,
                                                    start_time)
                else:
                    # 普通响应处理
                    self._handle_normal_response(request_id, request_data, openrouter_url, openrouter_headers,
                                                 start_time)
            except Exception as e:
                # 处理请求失败
                print(f"[{request_id}] 请求处理错误: {str(e)}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()

                error_response = {
                    "error": True,
                    "message": f"请求处理失败: {str(e)}",
                    "request_id": request_id
                }
                self.wfile.write(json.dumps(error_response).encode())

        except json.JSONDecodeError:
            # 处理JSON解析错误
            print(f"[{request_id}] 无效的JSON格式")
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()

            error_response = {
                "error": True,
                "message": "无效的请求格式，请提供有效的JSON",
                "request_id": request_id
            }
            self.wfile.write(json.dumps(error_response).encode())

        except Exception as e:
            # 处理其他错误
            print(f"[{request_id}] 发生未预期的错误: {str(e)}")
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()

            error_response = {
                "error": True,
                "message": f"服务器内部错误: {str(e)}",
                "request_id": request_id
            }
            self.wfile.write(json.dumps(error_response).encode())

    def _handle_normal_response(self, request_id, request_data, openrouter_url, openrouter_headers, start_time):
        """处理普通（非流式）响应"""
        response = requests.post(
            openrouter_url,
            headers=openrouter_headers,
            json=request_data,
            timeout=600  # 长超时以适应较长的请求
        )

        # 获取完整响应数据
        response_time = time.time() - start_time
        response_data = response.json()

        # 记录响应
        print(f"[{request_id}] OpenRouter响应 ({response.status_code})")
        print(f"{json.dumps(response_data, ensure_ascii=False)}")
        print(f"[{request_id}] 响应耗时: {response_time:.2f}秒")

        # 记录工具调用（如果有）
        self._log_tool_calls(request_id, response_data)

        # 将响应发送回客户端
        self.send_response(response.status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        self.wfile.write(json.dumps(response_data).encode())
        print(f"[{request_id}] 请求处理完成")

    def _handle_streaming_response(self, request_id, request_data, openrouter_url, openrouter_headers, start_time):
        """处理流式响应"""
        # 确保启用流
        request_data['stream'] = True

        # 设置响应头
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'close')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        print(f"[{request_id}] 开始流式响应")

        try:
            with requests.post(
                    openrouter_url,
                    headers=openrouter_headers,
                    json=request_data,
                    stream=True,
                    timeout=600
            ) as response:

                if response.status_code != 200:
                    # 处理非200响应
                    error_data = response.json()
                    print(f"[{request_id}] OpenRouter返回错误: {response.status_code}, {json.dumps(error_data)}")
                    error_event = f"data: {json.dumps(error_data)}\n\n"
                    self.wfile.write(error_event.encode())
                    self.wfile.write("data: [DONE]\n\n".encode())
                    self.wfile.flush()
                    return

                # 简单转发流式响应
                for line in response.iter_lines():
                    if not line:
                        continue

                    # 直接转发原始数据
                    if line.startswith(b"data: "):
                        line = line[6:]  # 去掉 "data: " 前缀
                        if line == b': OPENROUTER PROCESSING':
                            continue
                        self.wfile.write(line + b"\n\n")
                    else:
                        self.wfile.write(b"data: " + line + b"\n\n")
                    
                    self.wfile.flush()
                    
                    # 如果是结束标记，退出循环
                    if line == b"data: [DONE]" or line == b"[DONE]":
                        break

        except Exception as e:
            print(f"[{request_id}] 流式响应处理错误: {str(e)}")
            error_event = f"data: {{\"error\":\"流式响应处理错误: {str(e)}\"}}\n\n"
            self.wfile.write(error_event.encode())
            self.wfile.write("data: [DONE]\n\n".encode())
            self.wfile.flush()

        response_time = time.time() - start_time
        print(f"[{request_id}] 流式响应完成，耗时: {response_time:.2f}秒")

    def _log_tool_calls(self, request_id, response_data):
        """记录工具调用详情"""
        if 'choices' in response_data and len(response_data['choices']) > 0:
            choice = response_data['choices'][0]
            if 'message' in choice and 'tool_calls' in choice['message'] and choice['message']['tool_calls']:
                tool_calls = choice['message']['tool_calls']
                print(f"[{request_id}] 检测到{len(tool_calls)}个工具调用:")

                for i, tool_call in enumerate(tool_calls):
                    function_name = tool_call.get('function', {}).get('name', 'unknown')
                    # 尝试格式化参数JSON以更好地显示
                    try:
                        arguments = json.loads(tool_call.get('function', {}).get('arguments', '{}'))
                        formatted_args = json.dumps(arguments, ensure_ascii=False, indent=2)
                    except:
                        formatted_args = tool_call.get('function', {}).get('arguments', '{}')

                    print(f"[{request_id}] 工具调用 #{i + 1}: {function_name}")
                    print(f"[{request_id}] 参数: {formatted_args}")
