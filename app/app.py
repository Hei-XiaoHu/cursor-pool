from flask import Flask, request, jsonify, Response, stream_with_context
from openai import OpenAI
from config import BASE_URL, SECRET
from pool_manager import PoolManager

app = Flask(__name__)
pool_manager = PoolManager()


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


@app.route('/v1/chat/completions', methods=['POST'])
def chat_completions():
    try:
        token_info = pool_manager.get_next_token_info()
        if not token_info:
            return jsonify({'error': 'No tokens in pool'}), 400

        token, checksum = token_info

        # 获取请求数据
        request_json = request.get_json()
        is_stream = request_json.get('stream', False)

        # 确保 BASE_URL 以 /v1 结尾
        api_base = BASE_URL
        if not api_base.endswith('/v1'):
            api_base = api_base.rstrip('/') + '/v1'

        # 创建OpenAI客户端
        client = OpenAI(
            base_url=api_base,
            api_key=token,
            default_headers={
                'x-cursor-checksum': checksum
            }
        )

        if is_stream:
            def generate():
                request_data = request_json.copy()
                request_data.pop('stream', None)

                stream = client.chat.completions.create(
                    **request_data,
                    stream=True
                )
                for chunk in stream:
                    yield f"data: {chunk.model_dump_json()}\n\n"
                yield "data: [DONE]\n\n"

            return Response(
                stream_with_context(generate()),
                content_type='text/event-stream',
                headers={
                    'Cache-Control': 'no-cache',
                    'Connection': 'keep-alive',
                    'X-Accel-Buffering': 'no'
                }
            )
        else:
            response = client.chat.completions.create(**request_json)
            return jsonify(response.model_dump()), 200

    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3200, threaded=True)