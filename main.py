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
from datetime import datetime, date, timedelta
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, ToolMessage
from langgraph.graph import StateGraph, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from config import CSV_PATH, CSV_COLUMNS, GRAFICOS_DIR, CATEGORIAS_VALIDAS
from prompts import SYSTEM_PROMPT


def _load_gastos(parse_dates: bool = True) -> pd.DataFrame | None:
    """Lee el CSV de gastos. Retorna el DataFrame o None si no existe o está vacío"""
    try:
        kwargs = {"parse_dates": ["fecha"]} if parse_dates else {}
        df = pd.read_csv(CSV_PATH, **kwargs)
        if df.empty:
            return None
        return df
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return None


def _execute_llm_code(
    code: str, df: pd.DataFrame, extra_context: dict | None = None
) -> dict:
    """Ejecuta código Python generado por el LLM en un contexto controlado.
    Returns:
        dict con claves:
            - "ok": bool
            - "context": dict con el contexto post-ejecución
            - "error": str | None
    """
    contexto = {
        "pd": pd,
        "df": df,
        "date": date,
        "datetime": datetime,
        "timedelta": timedelta,
    }
    if extra_context:
        contexto.update(extra_context)
    try:
        exec(code, contexto, contexto)
        return {"ok": True, "context": contexto, "error": None}
    except Exception as e:
        return {"ok": False, "context": contexto, "error": str(e)}


def agregar_gasto(fecha: str, categoria: str, descripcion: str, monto: float) -> str:
    """
    Registra un nuevo gasto en la base de datos.

    Args:
        fecha: Fecha del gasto en formato YYYY-MM-DD (ejemplo: 2026-02-15).
        categoria: Categoria del gasto (ejemplo: comida, transporte, servicios, entretenimiento, salud, educacion, deporte, otros).
        descripcion: Descripción breve del gasto (ejemplo: almuerzo en restaurante).
        monto: Monto del gasto en valor numérico (ejemplo: 50.00).

    Returns:
        Mensaje de confirmación con los datos registrados.
    """
    # validar fecha
    try:
        datetime.strptime(fecha, "%Y-%m-%d")
    except ValueError:
        return f"Error: La fecha '{fecha}' no tiene formato válido (YYYY-MM-DD)."
    # validar categoría
    cat = categoria.lower().strip()
    if cat not in CATEGORIAS_VALIDAS:
        return (
            f"Error: La categoría '{categoria}' no es válida. "
            f"Opciones: {', '.join(CATEGORIAS_VALIDAS)}"
        )
    # validar monto
    if monto <= 0:
        return f"Error: El monto debe ser positivo, se recibió {monto}."

    # Cargar o crear DataFrame
    df = _load_gastos(parse_dates=False)
    if df is None:
        df = pd.DataFrame(columns=CSV_COLUMNS)

    nuevo_gasto = pd.DataFrame(
        [
            {
                "fecha": fecha,
                "categoria": categoria.lower().strip(),
                "descripcion": descripcion.strip(),
                "monto": float(monto),
            }
        ]
    )
    df = pd.concat([df, nuevo_gasto], ignore_index=True)
    df.to_csv(CSV_PATH, index=False)
    return (
        f"Gasto registrado correctamente:\n"
        f"      Fecha:       {fecha}\n"
        f"      Categoría:   {categoria}\n"
        f"      Descripción: {descripcion}\n"
        f"      Monto:       ${monto:.2f}"
    )


def consultar_con_codigo(codigo_python: str) -> str:
    """
    Consulta y analiza los gastos ejecutando código Python escrito por el LLM.
    Args:
        codigo_python: Código Python que analiza el DataFrame y setea la variable 'resultado'
            con un string descriptivo de la respuesta.
            Variables disponibles: df, pd, datetime, date, timedelta.
            El código SIEMPRE debe terminar seteando: resultado = "...texto con la respuesta..."
    Returns:
        El valor de la variable 'resultado' seteada por el codigo, o el error si fallo.
    """
    df = _load_gastos()
    if df is None:
        return "No hay gastos registrados todavía."

    result = _execute_llm_code(codigo_python, df, extra_context={"resultado": ""})
    if not result["ok"]:
        return f"Error ejecutando el codigo: {result['error']}"
    return str(
        result["context"].get(
            "resultado", "El código no seteó la variable 'resultado'."
        )
    )


def generar_grafico_con_codigo(codigo_python: str) -> str:
    """
    Genera un grafico ejecutando codigo Python escrito por el LLM.
    Args:
        codigo_python: Codigo Python completo que genera un grafico y lo guarda en RUTA_SALIDA.
            Variables disponibles: df, pd, plt, sns, datetime, date, timedelta, RUTA_SALIDA.
            El codigo SIEMPRE debe terminar con: fig.savefig(RUTA_SALIDA, dpi=150, bbox_inches='tight')
    Returns:
        Mensaje con la ruta del archivo PNG generado, o el error si fallo la ejecucion.
    """
    df = _load_gastos()
    if df is None:
        return "No hay gastos registrados todavía."

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta_salida = GRAFICOS_DIR / f"grafico_{timestamp}.png"

    result = _execute_llm_code(
        codigo_python,
        df,
        extra_context={"plt": plt, "sns": sns, "RUTA_SALIDA": str(ruta_salida)},
    )
    plt.close("all")
    if not result["ok"]:
        return f"Error ejecutando el codigo: {result['error']}"
    if ruta_salida.exists():
        return f"Gráfico generado correctamente: {ruta_salida}"
    return (
        "El codigo se ejecuto sin errores pero no se genero el archivo PNG. "
        "Asegurate de usar fig.savefig(RUTA_SALIDA, dpi=150, bbox_inches='tight')"
    )


# state del agente


class State(TypedDict):
    messages: Annotated[list, add_messages]
    ultima_imagen: str | None


# herramientas
tools = [agregar_gasto, consultar_con_codigo, generar_grafico_con_codigo]


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


def parser(state: State):
    """Revisa si el último ToolMessage viene de generar_grafico_con_codigo,
    guarda la ruta en ultima_imagen
    """
    for msg in reversed(state["messages"]):
        if isinstance(msg, ToolMessage) and msg.name == "generar_grafico_con_codigo":
            # El mensaje tiene formato: "Gráfico generado correctamente: /ruta/al/archivo.png"
            if "Gráfico generado correctamente:" in msg.content:
                ruta = msg.content.split("Gráfico generado correctamente:")[-1].strip()
                return {"ultima_imagen": ruta}
            break
    return {"ultima_imagen": None}


# grafo ReAct
def build_graph():
    "construye y compila grafo ReAct."
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


def get_langfuse_handler():
    """Retorna un CallbackHandler de Langfuse si las keys estan configuradas, sino None."""
    from config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST

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


def main():
    print("Hello from taligent-agente-hf!")


if __name__ == "__main__":
    from ui import main as ui_main

    ui_main()
