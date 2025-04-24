import json
import os
import requests
import time
import uuid
from http.server import BaseHTTPRequestHandler

# 配置项
OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"

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
            
            # 记录请求信息（不记录敏感内容）
            sanitized_request = self._sanitize_request(request_data.copy())
            print(f"[{request_id}] 收到请求: {json.dumps(sanitized_request, ensure_ascii=False)}")
            
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
                    self._handle_streaming_response(request_id, request_data, openrouter_url, openrouter_headers, start_time)
                else:
                    # 普通响应处理
                    self._handle_normal_response(request_id, request_data, openrouter_url, openrouter_headers, start_time)
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
            timeout=120  # 长超时以适应较长的请求
        )
        
        # 获取完整响应数据
        response_time = time.time() - start_time
        response_data = response.json()
        
        # 记录响应
        sanitized_response = self._sanitize_response(response_data.copy())
        print(f"[{request_id}] 收到OpenRouter响应 ({response.status_code}): {json.dumps(sanitized_response, ensure_ascii=False)}")
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
        
        # 用于存储完整的流式响应
        complete_response = {
            "id": f"chatcmpl-{uuid.uuid4()}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": request_data.get("model", "unknown"),
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": []
                    },
                    "finish_reason": None
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        }
        
        has_tool_calls = False
        current_tool_call = None
        
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
                timeout=180  # 更长的超时
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
                
                # 处理流式响应
                for line in response.iter_lines():
                    if not line:
                        continue
                    
                    if line.startswith(b"data: "):
                        line = line[6:]  # 去掉 "data: " 前缀
                    
                    # 流结束标记
                    if line == b"[DONE]":
                        self.wfile.write("data: [DONE]\n\n".encode())
                        self.wfile.flush()
                        break
                    
                    try:
                        chunk = json.loads(line)
                        
                        # 转发chunk给客户端
                        chunk_event = f"data: {json.dumps(chunk)}\n\n"
                        self.wfile.write(chunk_event.encode())
                        self.wfile.flush()  # 确保数据立即发送
                        
                        # 更新完整响应
                        if 'choices' in chunk and len(chunk['choices']) > 0:
                            choice = chunk['choices'][0]
                            delta = choice.get('delta', {})
                            
                            # 处理内容增量
                            if 'content' in delta and delta['content']:
                                complete_response['choices'][0]['message']['content'] += delta['content']
                            
                            # 处理工具调用
                            if 'tool_calls' in delta and delta['tool_calls']:
                                has_tool_calls = True
                                
                                # 确保工具调用数组存在
                                if 'tool_calls' not in complete_response['choices'][0]['message']:
                                    complete_response['choices'][0]['message']['tool_calls'] = []
                                
                                # 处理每个工具调用增量
                                for tool_call_delta in delta['tool_calls']:
                                    # 获取当前工具调用数组
                                    tool_calls = complete_response['choices'][0]['message']['tool_calls']
                                    
                                    # 检查是否需要创建新的工具调用
                                    if not tool_calls or (tool_call_delta.get('id') and not any(tc.get('id') == tool_call_delta.get('id') for tc in tool_calls)):
                                        # 创建新的工具调用
                                        new_tool_call = {
                                            'id': tool_call_delta.get('id'),
                                            'type': tool_call_delta.get('type', 'function'),
                                            'function': {
                                                'name': '',
                                                'arguments': ''
                                            }
                                        }
                                        tool_calls.append(new_tool_call)
                                    
                                    # 找到要更新的工具调用
                                    target_tool_call = None
                                    if tool_call_delta.get('id'):
                                        # 如果有ID，按ID查找
                                        for tc in tool_calls:
                                            if tc.get('id') == tool_call_delta.get('id'):
                                                target_tool_call = tc
                                                break
                                    else:
                                        # 如果没有ID，使用最后一个工具调用
                                        target_tool_call = tool_calls[-1] if tool_calls else None
                                    
                                    # 更新工具调用
                                    if target_tool_call and 'function' in tool_call_delta:
                                        function_delta = tool_call_delta['function']
                                        if 'name' in function_delta and function_delta['name']:
                                            target_tool_call['function']['name'] = function_delta['name']
                                        if 'arguments' in function_delta and function_delta['arguments']:
                                            target_tool_call['function']['arguments'] += function_delta['arguments']
                        
                            # 更新完成原因
                            if 'finish_reason' in choice and choice['finish_reason']:
                                complete_response['choices'][0]['finish_reason'] = choice['finish_reason']
                        
                        # 更新使用量（如果有）
                        if 'usage' in chunk:
                            complete_response['usage'] = chunk['usage']
                    
                    except json.JSONDecodeError as e:
                        # 处理非JSON格式的消息
                        try:
                            status_message = line.decode('utf-8').strip("'")
                            print(f"[{request_id}] 收到状态消息: {status_message}")
                        except:
                            print(f"[{request_id}] 无法解析流式响应块: {e}, 原始数据: {line}")
                        continue
        
        except Exception as e:
            print(f"[{request_id}] 流式响应处理错误: {str(e)}")
            error_event = f"data: {{\"error\":\"流式响应处理错误: {str(e)}\"}}\n\n"
            self.wfile.write(error_event.encode())
            self.wfile.write("data: [DONE]\n\n".encode())
            self.wfile.flush()
        
        # 记录完整响应
        response_time = time.time() - start_time
        sanitized_complete_response = self._sanitize_response(complete_response.copy())
        
        print(f"[{request_id}] 流式响应完成，耗时: {response_time:.2f}秒")
        print(f"[{request_id}] 完整响应: {json.dumps(sanitized_complete_response, ensure_ascii=False)}")
        
        # 如果有工具调用，单独记录
        if has_tool_calls:
            self._log_tool_calls(request_id, complete_response)
        
        # 确保连接被关闭
        try:
            self.wfile.flush()
            # 强制关闭连接
            if hasattr(self.wfile, 'close'):
                self.wfile.close()
        except Exception as e:
            print(f"[{request_id}] 关闭连接时出错: {str(e)}")
    
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
                    
                    print(f"[{request_id}] 工具调用 #{i+1}: {function_name}")
                    print(f"[{request_id}] 参数: {formatted_args}")
    
    def _sanitize_request(self, request_data):
        """清理请求数据以便于日志记录（移除敏感信息）"""
        # 如果包含消息，只保留每条消息的role和内容长度
        if 'messages' in request_data:
            sanitized_messages = []
            for msg in request_data['messages']:
                sanitized_msg = {
                    "role": msg.get("role", "unknown")
                }
                if "content" in msg:
                    content = msg["content"]
                    # 如果内容很长，只保留摘要
                    if isinstance(content, str) and len(content) > 100:
                        sanitized_msg["content_length"] = len(content)
                        sanitized_msg["content_preview"] = content[:50] + "..."
                    else:
                        sanitized_msg["content"] = content
                sanitized_messages.append(sanitized_msg)
            request_data['messages'] = sanitized_messages
        
        return request_data
    
    def _sanitize_response(self, response_data):
        """清理响应数据以便于日志记录（保持关键信息，移除过长内容）"""
        if 'choices' in response_data and len(response_data['choices']) > 0:
            for choice in response_data['choices']:
                if 'message' in choice:
                    message = choice['message']
                    if 'content' in message and isinstance(message['content'], str) and len(message['content']) > 200:
                        content = message['content']
                        message['content_length'] = len(content)
                        message['content_preview'] = content[:100] + "..." + content[-100:]
                
                # 确保工具调用记录完整
                if 'message' in choice and 'tool_calls' in choice['message']:
                    # 保留工具调用信息，不做修改
                    pass
        
        return response_data
