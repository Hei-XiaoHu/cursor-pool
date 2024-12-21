import os
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv('base_url')
SECRET = os.getenv('secret')