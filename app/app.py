# 文件开头添加
from gevent import monkey
monkey.patch_all()  # 移到最前面，在其他导入之前

# ... 其他导入 ...
from flask import Flask, request, jsonify, Response, stream_with_context
from openai import OpenAI
from config import BASE_URL, SECRET
from pool_manager import PoolManager
import threading
import httpx
from concurrent.futures import ThreadPoolExecutor
from gevent.pywsgi import WSGIServer

# 应用初始化
app = Flask(__name__)
pool_manager = PoolManager()
executor = ThreadPoolExecutor(max_workers=50)
client_pool = {}
client_pool_lock = threading.Lock()

def get_client(token, checksum):
    """获取或创建 OpenAI 客户端"""
    key = f"{token}:{checksum}"
    with client_pool_lock:
        if key not in client_pool:
            api_base = BASE_URL if BASE_URL.endswith('/v1') else f"{BASE_URL.rstrip('/')}/v1"
            client_pool[key] = OpenAI(
                base_url=api_base,
                api_key=token,
                default_headers={'x-cursor-checksum': checksum},
                timeout=httpx.Timeout(120.0, connect=10.0)  # 增加超时时间
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
            return jsonify({'error': 'No available tokens'}), 503  # 改用503状态码

        token, checksum = token_info
        request_json = request.get_json()

        if not request_json:
            return jsonify({'error': 'Invalid JSON'}), 400

        is_stream = request_json.get('stream', False)
        client = get_client(token, checksum)

        if is_stream:
            def generate():
                request_data = request_json.copy()
                request_data.pop('stream', None)
                try:
                    stream = client.chat.completions.create(
                        **request_data,
                        stream=True,
                        timeout=120  # 添加超时设置
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
            future = executor.submit(
                lambda: client.chat.completions.create(**request_json)
            )
            response = future.result(timeout=60)  # 增加超时时间到60秒
            return jsonify(response.model_dump()), 200

    except Exception as e:
        app.logger.error(f"Error in chat_completions: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/pool/add', methods=['POST'])
def add_token():
    token = request.json.get('token')
    if not token:
        return jsonify({'error': 'Token is required'}), 400

    if pool_manager.add_token(token):
        return jsonify({'message': 'Token added successfully'})
    return jsonify({'error': 'Token already exists'}), 400


@app.route('/pool/del', methods=['POST'])
def delete_token():
    token = request.json.get('token')
    if not token:
        return jsonify({'error': 'Token is required'}), 400

    if pool_manager.delete_token(token):
        return jsonify({'message': 'Token deleted successfully'})
    return jsonify({'error': 'Token not found'}), 404


@app.route('/pool/disp', methods=['GET'])
def display_tokens():
    return jsonify(pool_manager.get_all_tokens())


@app.route('/pool/empty', methods=['POST'])
def empty_pool():
    pool_manager.empty_pool()
    return jsonify({'message': 'Pool emptied successfully'})

# 添加健康检查端点
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy'}), 200




if __name__ == '__main__':
    import logging

    logging.basicConfig(level=logging.INFO)

    # 移除 monkey.patch_all() 因为已经移到文件开头

    http_server = WSGIServer(('0.0.0.0', 3200), app, log=app.logger)
    print("Server starting on port 3200...")
    http_server.serve_forever()