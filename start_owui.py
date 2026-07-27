"""Start Open WebUI on port 3000 with Foundry Manager integration."""
import os

os.environ["OPENAI_API_BASE_URL"] = "http://127.0.0.1:8000/v1"
os.environ["OPENAI_API_KEY"] = "foundry-manager"
os.environ["WEBUI_AUTH"] = "false"
os.environ["OLLAMA_BASE_URL"] = ""
os.environ["DATA_DIR"] = "C:/Users/reese/Projects/open-webui-foundry/data"
os.environ["WEBUI_SECRET_KEY"] = "test-secret-key-123"

from open_webui.main import app
import uvicorn

uvicorn.run(app, host="127.0.0.1", port=3000)
