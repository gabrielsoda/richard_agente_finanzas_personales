"""
richard/tools.py

Funciones puras de las herramientas de RICHARD.
Estas funciones son independientes de LangGraph y pueden ser reutilizadas
por el MCP Server, el A2A Server o cualquier otro cliente.
"""

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from datetime import datetime, date, timedelta

from richard.config import CSV_PATH, CSV_COLUMNS, GRAFICOS_DIR, CATEGORIAS_VALIDAS


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _load_gastos(parse_dates: bool = True) -> pd.DataFrame | None:
    """Lee el CSV de gastos. Retorna el DataFrame o None si no existe o está vacío."""
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
    code = code.replace("\\'", "'")
    code = code.replace("\\$", "$")

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


# ---------------------------------------------------------------------------
# Tools públicas
# ---------------------------------------------------------------------------


def agregar_gasto(fecha: str, categoria: str, descripcion: str, monto: float) -> str:
    """
    Registra un nuevo gasto en la base de datos.

    Args:
        fecha: Fecha del gasto en formato YYYY-MM-DD (ejemplo: 2026-02-15).
        categoria: Categoria del gasto (ejemplo: comida, transporte, servicios,
            entretenimiento, salud, educacion, deporte, otros).
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
        codigo_python: Código Python que analiza el DataFrame y setea la variable
            'resultado' con un string descriptivo de la respuesta.
            Variables disponibles: df, pd, datetime, date, timedelta.
            El código SIEMPRE debe terminar seteando:
            resultado = "...texto con la respuesta..."

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
        codigo_python: Codigo Python completo que genera un grafico y lo guarda
            en RUTA_SALIDA.
            Variables disponibles: df, pd, plt, sns, datetime, date, timedelta,
            RUTA_SALIDA.
            El codigo SIEMPRE debe terminar con:
            fig.savefig(RUTA_SALIDA, dpi=150, bbox_inches='tight')

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
        extra_context={
            "plt": plt,
            "sns": sns,
            "RUTA_SALIDA": str(ruta_salida),
            "resultado": "",
        },
    )
    plt.close("all")
    if not result["ok"]:
        return f"Error ejecutando el codigo: {result['error']}"
    if ruta_salida.exists():
        msg = f"Gráfico generado correctamente: {ruta_salida}"
        # si el llm seteó resultado con datos extra se incluyen en la respuesta para
        # que los use en la respuesta y no invente valores
        resultado_extra = result["context"].get("resultado", "")
        if resultado_extra:
            msg += f"\n\nDatos calculados:\n{resultado_extra}"
        return msg
    return (
        "El codigo se ejecuto sin errores pero no se genero el archivo PNG. "
        "Asegurate de usar fig.savefig(RUTA_SALIDA, dpi=150, bbox_inches='tight')"
    )
