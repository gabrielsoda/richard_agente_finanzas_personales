# config.py
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # Se ejecuta aquí, una sola vez

# Rutas
BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "gastos.csv"
GRAFICOS_DIR = BASE_DIR / "graficos"
GRAFICOS_DIR.mkdir(exist_ok=True)

# Columnas del CSV
CSV_COLUMNS = ["fecha", "categoria", "descripcion", "monto"]

# API Keys
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")
LANGFUSE_HOST = os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")