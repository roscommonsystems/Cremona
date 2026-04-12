import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("API_KEY", "")
OPEN_ROUTER_API_KEY = os.environ.get("OPEN_ROUTER_API_KEY", "")
