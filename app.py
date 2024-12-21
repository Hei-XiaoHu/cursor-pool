from flask import Flask, request, jsonify, Response, stream_with_context
from openai import OpenAI
from config import BASE_URL, SECRET
from pool_manager import PoolManager
import asyncio
import httpx
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
pool_manager = PoolManager()
executor = ThreadPoolExecutor(max_workers=20)  # 创建线程池

# 预先创建 OpenAI 客户端池
client_pool = {}


def get_client(token, checksum):
    """获取或创建 OpenAI 客户端"""
    key = f"{token}:{checksum}"
    if key not in client_pool:
        api_base = BASE_URL if BASE_URL.endswith('/v1') else f"{BASE_URL.rstrip('/')}/v1"
        client_pool[key] = OpenAI(
            base_url=api_base,
            api_key=token,
            default_headers={'x-cursor-checksum': checksum},
            timeout=httpx.Timeout(60.0, connect=5.0)  # 设置超时
        )
    return client_pool[key]


def verify_secret():
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return False
    token = auth_header.split(' ')[1]
    return token == SECRET


@app.before_request
def check_auth():
    if request.path != '/health':
        if not verify_secret():
            return jsonify({'error': 'Unauthorized'}), 401


@app.route('/v1/chat/completions', methods=['POST'])
def chat_completions():
    try:
        token_info = pool_manager.get_next_token_info()
        if not token_info:
            return jsonify({'error': 'No tokens in pool'}), 400

        token, checksum = token_info
        request_json = request.get_json()
        is_stream = request_json.get('stream', False)

        # 获取或创建客户端
        client = get_client(token, checksum)

        if is_stream:
            def generate():
                request_data = request_json.copy()
                request_data.pop('stream', None)

                try:
                    stream = client.chat.completions.create(
                        **request_data,
                        stream=True
                    )
                    for chunk in stream:
                        yield f"data: {chunk.model_dump_json()}\n\n"
                except Exception as e:
                    yield f"data: {{\"error\": \"{str(e)}\"}}\n\n"
                finally:
                    yield "data: [DONE]\n\n"

            return Response(
                stream_with_context(generate()),
                content_type='text/event-stream',
                headers={
                    'Cache-Control': 'no-cache',
                    'Connection': 'keep-alive',
                    'X-Accel-Buffering': 'no',
                    'Transfer-Encoding': 'chunked'
                }
            )
        else:
            def make_request():
                return client.chat.completions.create(**request_json)

            # 使用线程池处理非流式请求
            future = executor.submit(make_request)
            response = future.result(timeout=30)  # 设置超时时间
            return jsonify(response.model_dump()), 200

    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'error': str(e)}), 500


# 添加健康检查端点
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy'}), 200


if __name__ == '__main__':
    # 使用 gevent 或 eventlet 来运行
    from gevent.pywsgi import WSGIServer

    http_server = WSGIServer(('0.0.0.0', 3200), app)
    http_server.serve_forever()