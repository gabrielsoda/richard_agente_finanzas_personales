"""
mcp_server.py — RICHARD como MCP Server

Expone las capacidades de RICHARD a cualquier host MCP-compatible
(Claude Desktop, Claude Code, VS Code, etc.).

Primitivas implementadas:
  - Tools:     agregar_gasto, consultar_con_codigo, generar_grafico_con_codigo
  - Resources: gastos://datos, gastos://resumen
  - Prompts:   analizar-gastos, resumen-mensual

Transporte: STDIO (para uso local).

Arrancar manualmente:
    uv run mcp_server.py

Testear con el MCP Inspector:
    npx @modelcontextprotocol/inspector uv run mcp_server.py

Conectar con Claude Desktop (claude_desktop_config.json):
    {
      "mcpServers": {
        "richard-finanzas": {
          "command": "uv",
          "args": ["--directory", "/ruta/al/proyecto", "run", "mcp_server.py"]
        }
      }
    }

Importante sobre STDIO:
    Para servidores STDIO, NUNCA usar print() que escriba a stdout.
    Todo log debe ir a stderr. El SDK maneja esto automáticamente.
"""

import sys
import logging

# ---- Configurar logging a stderr (NUNCA a stdout en servidores STDIO) ----
logging.basicConfig(
    stream=sys.stderr,
    level=logging.WARNING,
    format="[RICHARD-MCP] %(levelname)s: %(message)s",
)

from mcp.server.fastmcp import FastMCP

# Importar las tools y helpers del paquete richard
from richard.tools import (
    agregar_gasto as _agregar_gasto,
    consultar_con_codigo as _consultar_con_codigo,
    generar_grafico_con_codigo as _generar_grafico_con_codigo,
    _load_gastos,
)
from richard.config import CATEGORIAS_VALIDAS

# instancia del servidor mcp
mcp = FastMCP(
    name="richard-finanzas",
    instructions=(
        "RICHARD es un agente de finanzas personales. "
        "Puede registrar gastos, consultar y analizar datos financieros, "
        "y generar graficos. Los montos estan en pesos argentinos."
    ),
)



# TOOLS

@mcp.tool()
def agregar_gasto(fecha: str, categoria: str, descripcion: str, monto: float) -> str:
    """Registra un nuevo gasto en la base de datos de finanzas personales.

    Args:
        fecha: Fecha del gasto en formato YYYY-MM-DD (ejemplo: 2026-03-11).
        categoria: Categoria del gasto. Valores validos: comida, transporte,
            servicios, entretenimiento, salud, educacion, deporte, otros.
        descripcion: Descripcion breve del gasto (ejemplo: almuerzo en restaurante).
        monto: Monto del gasto como numero positivo (ejemplo: 1500.00).

    Returns:
        Mensaje de confirmacion con los datos registrados, o mensaje de error
        si los datos son invalidos.
    """
    return _agregar_gasto(fecha, categoria, descripcion, monto)


@mcp.tool()
def consultar_con_codigo(codigo_python: str) -> str:
    """Consulta y analiza los gastos ejecutando codigo Python contra el DataFrame.

    El codigo tiene acceso a las siguientes variables:
    - df: pandas DataFrame con columnas: fecha (Timestamp), categoria (str),
      descripcion (str), monto (float)
    - pd: pandas
    - datetime, date, timedelta: del modulo datetime

    El codigo DEBE terminar seteando la variable 'resultado' con un string
    descriptivo de la respuesta. Ejemplo:
        resultado = f"Total gastado: ${df['monto'].sum():.2f}"

    Args:
        codigo_python: Codigo Python valido que analiza df y setea 'resultado'.

    Returns:
        El valor de la variable 'resultado', o el mensaje de error si el
        codigo fallo al ejecutarse.
    """
    return _consultar_con_codigo(codigo_python)


@mcp.tool()
def generar_grafico_con_codigo(codigo_python: str) -> str:
    """Genera un grafico PNG ejecutando codigo Python con matplotlib/seaborn.

    El codigo tiene acceso a las siguientes variables:
    - df: pandas DataFrame con columnas: fecha (Timestamp), categoria (str),
      descripcion (str), monto (float)
    - pd: pandas, plt: matplotlib.pyplot, sns: seaborn
    - datetime, date, timedelta: del modulo datetime
    - RUTA_SALIDA: string con la ruta donde DEBE guardarse el PNG

    El codigo DEBE terminar con:
        fig.savefig(RUTA_SALIDA, dpi=150, bbox_inches='tight')

    En titulos/etiquetas usar \\$ en vez de $ para simbolo de peso/dolar.

    Args:
        codigo_python: Codigo Python completo que genera un grafico matplotlib
            y lo guarda en RUTA_SALIDA.

    Returns:
        Ruta del archivo PNG generado, o el mensaje de error si fallo.
    """
    return _generar_grafico_con_codigo(codigo_python)


# ===========================================================================
# RESOURCES
# ===========================================================================
# Los resources son fuentes de datos de solo lectura que el host puede leer
# para dar contexto al LLM. El host decide como usarlos (embeddings, RAG, etc.)
# El host descubre los resources via resources/list y lee via resources/read.
# ===========================================================================


@mcp.resource("gastos://datos")
def gastos_datos() -> str:
    """Datos completos de gastos en formato CSV.

    Proporciona acceso de solo lectura a todos los gastos registrados.
    Columnas: fecha, categoria, descripcion, monto.
    """
    df = _load_gastos(parse_dates=False)
    if df is None:
        return "No hay gastos registrados todavia."
    return df.to_csv(index=False)


@mcp.resource("gastos://resumen")
def gastos_resumen() -> str:
    """Resumen estadistico de los gastos registrados en formato Markdown.

    Incluye: total general, total por categoria, gasto mas reciente,
    gasto mas alto, cantidad de registros.
    """
    df = _load_gastos()
    if df is None:
        return "No hay gastos registrados todavia."

    total = df["monto"].sum()
    cant = len(df)
    por_categoria = df.groupby("categoria")["monto"].sum().sort_values(ascending=False)
    mas_reciente = df.loc[df["fecha"].idxmax()]
    mas_alto = df.loc[df["monto"].idxmax()]

    lineas = [
        "# Resumen de Gastos — RICHARD",
        "",
        f"**Total registros:** {cant}",
        f"**Total gastado:** ${total:,.2f}",
        "",
        "## Por Categoria",
        "",
    ]
    for cat, subtotal in por_categoria.items():
        pct = (subtotal / total * 100) if total > 0 else 0
        lineas.append(f"- **{cat}**: ${subtotal:,.2f} ({pct:.1f}%)")

    lineas += [
        "",
        "## Destacados",
        "",
        f"- **Gasto mas reciente:** {mas_reciente['fecha'].strftime('%Y-%m-%d')} — "
        f"{mas_reciente['descripcion']} (${mas_reciente['monto']:,.2f})",
        f"- **Gasto mas alto:** {mas_alto['descripcion']} "
        f"(${mas_alto['monto']:,.2f} — {mas_alto['categoria']})",
    ]
    return "\n".join(lineas)


# ===========================================================================
# PROMPTS
# ===========================================================================
# Los prompts son plantillas reutilizables que el usuario puede invocar
# explicitamente. Ayudan a estructurar interacciones complejas con el LLM.
# El host descubre los prompts via prompts/list y obtiene su contenido
# via prompts/get.
# ===========================================================================


@mcp.prompt()
def analizar_gastos(periodo: str = "ultimo mes") -> str:
    """Analiza los gastos de un periodo especifico.

    Args:
        periodo: Periodo a analizar (ej: 'enero 2026', 'ultimo mes', 'este año').
    """
    return (
        f"Analiza en detalle mis gastos del {periodo}. "
        "Usa la tool consultar_con_codigo para obtener:\n"
        "1. Total gastado en el periodo\n"
        "2. Desglose por categoria con porcentajes\n"
        "3. Los 3 gastos mas altos\n"
        "4. Promedio diario de gasto\n"
        "Presenta los resultados de forma clara y con recomendaciones."
    )


@mcp.prompt()
def resumen_mensual(mes: str = "", anio: str = "2026") -> str:
    """Genera un resumen mensual completo de finanzas.

    Args:
        mes: Numero del mes (1-12). Si se omite, usa el mes actual.
        anio: Año del resumen (default: 2026).
    """
    periodo = f"mes {mes}/{anio}" if mes else f"mes actual de {anio}"
    return (
        f"Genera un resumen financiero completo del {periodo}:\n"
        "1. Usa consultar_con_codigo para calcular totales y estadisticas\n"
        "2. Usa generar_grafico_con_codigo para crear un grafico de torta "
        "con gastos por categoria\n"
        "3. Identifica la categoria con mayor gasto\n"
        "4. Sugiere donde se podria reducir el gasto\n"
        "Presenta todo de forma estructurada y visual."
    )


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    # transport="stdio": el servidor lee/escribe JSON-RPC por stdin/stdout.
    # Esto permite que cualquier host MCP lo lance como subproceso.
    # El SDK maneja el framing y parsing del protocolo automaticamente.
    mcp.run(transport="stdio")
