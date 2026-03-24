"""
RICHARD - Entry point del CLI.

Para arrancar el agente en modo conversacional:
    python main.py
    uv run main.py
"""

if __name__ == "__main__":
    from ui import main as ui_main

    ui_main()
