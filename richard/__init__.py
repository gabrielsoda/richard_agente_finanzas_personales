"""
RICHARD - Receptor de Informacion de Consumos Humanos para Administracion y Registro del Dinero

Paquete principal del agente de finanzas personales.
"""

from richard.tools import (
    agregar_gasto,
    consultar_con_codigo,
    generar_grafico_con_codigo,
)
from richard.agent import build_graph, get_langfuse_handler

__all__ = [
    "agregar_gasto",
    "consultar_con_codigo",
    "generar_grafico_con_codigo",
    "build_graph",
    "get_langfuse_handler",
]
