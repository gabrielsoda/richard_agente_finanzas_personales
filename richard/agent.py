"""
richard/agent.py

Grafo ReAct de LangGraph para RICHARD.
Define el estado, nodos, grafo compilado y helpers de observabilidad.
"""

from typing import Annotated
from typing_extensions import TypedDict
from datetime import date

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, ToolMessage
from langgraph.graph import StateGraph, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from richard.tools import (
    agregar_gasto,
    consultar_con_codigo,
    generar_grafico_con_codigo,
)
from richard.prompts import SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Estado del agente
# ---------------------------------------------------------------------------


class State(TypedDict):
    messages: Annotated[list, add_messages]
    ultima_imagen: str | None


# ---------------------------------------------------------------------------
# Herramientas y LLM
# ---------------------------------------------------------------------------

tools = [agregar_gasto, consultar_con_codigo, generar_grafico_con_codigo]

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=1.0,
)

llm_with_tools = llm.bind_tools(tools)


# ---------------------------------------------------------------------------
# Nodos
# ---------------------------------------------------------------------------


def assistant(state: State):
    """Nodo principal del agente: razona y decide que herramienta usar."""
    today = date.today().isoformat()
    sys_msg = SystemMessage(content=SYSTEM_PROMPT.format(today=today))
    response = llm_with_tools.invoke([sys_msg] + state["messages"])
    return {"messages": [response]}


def parser(state: State):
    """Revisa si el último ToolMessage viene de generar_grafico_con_codigo,
    guarda la ruta en ultima_imagen.
    """
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            break
        if isinstance(msg, ToolMessage) and msg.name == "generar_grafico_con_codigo":
            contenido = (
                msg.content if isinstance(msg.content, str) else str(msg.content)
            )
            if "Gráfico generado correctamente:" in contenido:
                ruta = contenido.split("Gráfico generado correctamente:")[-1].strip()
                # tomar solo la primera linea (la ruta, sin los "Datos calculados:")
                ruta = ruta.split("\n")[0].strip()
                return {"ultima_imagen": ruta}
            break
    return {"ultima_imagen": None}


# ---------------------------------------------------------------------------
# Construccion del grafo
# ---------------------------------------------------------------------------


def build_graph():
    """Construye y compila el grafo ReAct."""
    builder = StateGraph(State)

    builder.add_node("assistant", assistant)
    builder.add_node("tools", ToolNode(tools))
    builder.add_node("parser", parser)

    builder.add_edge(START, "assistant")
    builder.add_conditional_edges(
        "assistant",
        tools_condition,
    )
    builder.add_edge("tools", "parser")
    builder.add_edge("parser", "assistant")

    return builder.compile()


# ---------------------------------------------------------------------------
# Observabilidad (Langfuse)
# ---------------------------------------------------------------------------


def get_langfuse_handler():
    """Retorna un CallbackHandler de Langfuse si las keys estan configuradas, sino None."""
    from richard.config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST

    if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY:
        return None
    try:
        from langfuse import Langfuse
        from langfuse.langchain import CallbackHandler

        Langfuse(
            public_key=LANGFUSE_PUBLIC_KEY,
            secret_key=LANGFUSE_SECRET_KEY,
            host=LANGFUSE_HOST,
        )
        return CallbackHandler()
    except ImportError:
        return None
