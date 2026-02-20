"""
Agente de Gastos Financieros con LangGraph + Gemini
Arquitectura ReAct

Tools:
1. agregar_gasto              
    - Registra un gasto en la base de datos CSV
2. consultar_gastos           
    - Consulta y filtra gastos registrados
3. generar_grafico_con_codigo 
    - El LLM genera codigo Python (pandas/matplotlib/seaborn)
"""
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from typing import Annotated
from typing_extensions import TypedDict
from datetime import datetime, date
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, ToolMessage
from langgraph.graph import StateGraph, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from config import CSV_PATH, CSV_COLUMNS, GRAFICOS_DIR
from prompts import SYSTEM_PROMPT




def agregar_gasto(fecha: str, categoria: str, descripcion: str, monto: float) -> str:
    """
    Registra un nuevo gasto en la base de datos.

    Args:
        fecha: Fecha del gasto en formato YYYY-MM-DD (ejemplo: 2026-02-15).
        categoria: Categoria del gasto (ejemplo: comida, transporte, servicios, entretenimiento, salud, educacion, deporte, otros).
        descripcion: Descripcion breve del gasto (ejemplo: almuerzo en restaurante).
        monto: Monto del gasto en valor numerico (ejemplo: 50.00).

    Returns:
        Mensaje de confirmacion con los datos registrados.
    """
    df = pd.read_csv(CSV_PATH)
    df = pd.DataFrame(columns=CSV_COLUMNS)
    nuevo_gasto = pd.DataFrame([{
        "fecha": fecha,
        "categoria": categoria.lower().strip(),
        "descripcion": descripcion.strip(),
        "monto": float(monto),
    }])
    df = pd.concat([df, nuevo_gasto], ignore_index=True)
    df.to_csv(CSV_PATH, index=False)
    return (
        f"Gasto registrado correctamente:\n"
        f"      Fecha:       {fecha}\n"
        f"      Categoría:   {categoria}\n"
        f"      Descripción: {descripcion}\n"
        f"      Monto:       ${monto:.2f}"
    )


def consultar_gastos(categoria: str = "", fecha_inicio: str = "", fecha_fin: str = "") -> str:
    """
    Consulta los gastos registrados con filtros opcionales.

    Args:
        categoria: Filtrar por categoria (opcional, dejar vacio para todas). Ejemplo: comida, transporte.
        fecha_inicio: Fecha de inicio del rango en formato YYYY-MM-DD (opcional). Ejemplo: 2026-02-01.
        fecha_fin: Fecha de fin del rango en formato YYYY-MM-DD (opcional). Ejemplo: 2026-02-28.

    Returns:
        Resumen textual de los gastos encontrados con totales y desglose.
    """
    pass


def generar_grafico_con_codigo():
        """
    Genera un grafico ejecutando codigo Python.


    Args:
        codigo_python: Codigo Python completo que genera un grafico y lo guarda en RUTA_SALIDA.

    Returns:
        Mensaje con la ruta del archivo PNG generado, o el error si fallo la ejecucion.
    """

# state del agente

class State(TypedDict):
    messages: Annotated[list, add_messages]
    ultima_imagen: str | None

# herramientas
tools = [agregar_gasto, consultar_gastos, generar_grafico_con_codigo]


# llm
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=1.0,
)

# vincula llm y herramientas
llm_with_tools = llm.bind_tools(tools)



# NODOS:

def assistant(state: State):
    """Nodo principal del agente: razona y decide que herramienta usar."""
    today = date.today().isoformat()
    sys_msg = SystemMessage(content=SYSTEM_PROMPT.format(today=today))
    response = llm_with_tools.invoke([sys_msg] + state["messages"])
    return {"messages": [response]}


# grafo ReAct
def build_graph():
    "construye y compila grafo ReAct."
    builder = StateGraph(State)


    builder.add_node("assistant", assistant)
    builder.add_node("tools", ToolNode(tools))

    builder.add_edge(START, "assistant")
    builder.add_conditional_edges(
        "assistant",
        tools_condition,
    )
    builder.add_edge("tools", "assistant")

    return builder.compile()

def main():
    print("Hello from taligent-agente-hf!")


if __name__ == "__main__":
    main()
