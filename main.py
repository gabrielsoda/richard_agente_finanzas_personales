from typing_extensions import TypedDict
from datetime import datetime, date
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, ToolMessage
from langgraph.graph import StateGraph, START
from langgraph.prebuilt import ToolNode, tools_condition

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
    pass


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


def generar_grafico():
        """
    Genera un grafico ejecutando codigo Python.


    Args:
        codigo_python: Codigo Python completo que genera un grafico y lo guarda en RUTA_SALIDA.

    Returns:
        Mensaje con la ruta del archivo PNG generado, o el error si fallo la ejecucion.
    """


# state del agente

class State(TypedDict):
    graph_state: str

# herramientas
tools = [agregar_gasto, consultar_gastos, generar_grafico]


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
    llm_with_tools = llm_with_tools()
    response = llm_with_tools.invoke([sys_msg] + state["messages"])
    return {"messages": [response]}


# grafo ReAct
builder = StateGraph(State)

# nodos
builder.add_node("assistant", assistant)
builder.add_node("tools", ToolNode(tools))

# edges
builder.add_edge(START, "assistant")
builder.add_conditional_edges(
    "assistant",
    tools_condition,
)
builder.add_edge("tools", "assistant")

react_graph = builder.compile()

def main():
    print("Hello from taligent-agente-hf!")


if __name__ == "__main__":
    main()
