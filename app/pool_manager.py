import json
import random
import string
from threading import Lock


class PoolManager:
    def __init__(self):
        self.file_path = "../data/pool.json"
        self.lock = Lock()
        self.current_index = 0
        self.load_pool()

    def generate_custom_string(self):
        def random_string(length):
            return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

        result = 'zo' + random_string(70) + '/' + random_string(64)
        return result

    def load_pool(self):
        try:
            with open(self.file_path, 'r') as f:
                self.pool = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.pool = {}

    def save_pool(self):
        with open(self.file_path, 'w') as f:
            json.dump(self.pool, f, indent=2)

    def add_token(self, token):
        with self.lock:
            if token not in self.pool:
                self.pool[token] = self.generate_custom_string()
                self.save_pool()
                return True
            return False

    def delete_token(self, token):
        with self.lock:
            if token in self.pool:
                del self.pool[token]
                self.save_pool()
                return True
            return False

    def get_all_tokens(self):
        return self.pool

    def empty_pool(self):
        with self.lock:
            self.pool = {}
            self.save_pool()

    def get_next_token_info(self):
        with self.lock:
            if not self.pool:
                return None
            tokens = list(self.pool.items())
            self.current_index = (self.current_index + 1) % len(tokens)
            return tokens[self.current_index - 1]