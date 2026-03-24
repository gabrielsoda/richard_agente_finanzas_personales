"""
a2a_server.py — RICHARD como A2A Server

Expone a RICHARD como un agente A2A-compliant, descubrible y colaborativo.
Otros agentes pueden encontrarlo via su Agent Card y delegarle tareas
de finanzas personales.

Protocolo: JSON-RPC 2.0 sobre HTTP (binding estandar de A2A)
Puerto:    9000 (configurable via variable de entorno A2A_PORT)

Arrancar:
    uv run a2a_server.py
    # o con puerto custom:
    A2A_PORT=8080 uv run a2a_server.py

Descubrir el agente (Agent Card):
    curl http://localhost:9000/.well-known/agent.json | python3 -m json.tool

Enviar un mensaje (JSON-RPC):
    curl -X POST http://localhost:9000 \\
      -H "Content-Type: application/json" \\
      -d '{
        "jsonrpc": "2.0",
        "id": "1",
        "method": "message/send",
        "params": {
          "message": {
            "role": "user",
            "parts": [{"kind": "text", "text": "Cuanto gaste en comida este mes?"}],
            "messageId": "msg-001"
          }
        }
      }'

Concepto clave — diferencia con MCP:
    - MCP:  el LLM del HOST llama herramientas de RICHARD directamente.
    - A2A:  otro AGENTE le delega una TAREA a RICHARD. RICHARD razona de
            forma autonoma (usando su propio LLM Gemini + LangGraph) y
            retorna el resultado como un Task completado.
"""

import asyncio
import logging
import os
import sys

import uvicorn

# ---- A2A SDK imports ----
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    Message,
    MessageSendParams,
    Part,
    Role,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
    Artifact,
)
from a2a.utils import new_task

# ---- RICHARD core ----
from richard.agent import build_graph, State
from langchain_core.messages import HumanMessage

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="[RICHARD-A2A] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


# Agent Card

PORT = int(os.getenv("A2A_PORT", "9000"))
BASE_URL = os.getenv("A2A_BASE_URL", f"http://localhost:{PORT}")

AGENT_CARD = AgentCard(
    name="RICHARD",
    description=(
        "Agente de finanzas personales. "
        "Registra gastos, consulta y analiza datos financieros, "
        "y genera reportes visuales en formato PNG. "
        "Responde en español. Los montos están en pesos argentinos."
    ),
    url=BASE_URL,
    version="1.0.0",
    default_input_modes=["text"],
    default_output_modes=["text"],
    capabilities=AgentCapabilities(
        streaming=False,  # No implementamos SSE en esta version
        push_notifications=False,  # No implementamos push en esta version
    ),
    skills=[
        AgentSkill(
            id="registrar-gasto",
            name="Registrar Gasto",
            description=(
                "Registra un nuevo gasto en la base de datos con fecha, "
                "categoria, descripcion y monto."
            ),
            tags=["finanzas", "gastos", "registro"],
            input_modes=["text"],
            output_modes=["text"],
            examples=[
                "Registrá un gasto de $5000 en comida de hoy",
                "Agregá 1500 en transporte del 2026-03-10",
            ],
        ),
        AgentSkill(
            id="consultar-gastos",
            name="Consultar Gastos",
            description=(
                "Responde preguntas sobre gastos registrados. "
                "Puede calcular totales, filtrar por categoria o periodo, "
                "y mostrar estadisticas."
            ),
            tags=["finanzas", "consulta", "estadisticas"],
            input_modes=["text"],
            output_modes=["text"],
            examples=[
                "Cuanto gaste en comida este mes?",
                "Cual fue el gasto mas alto?",
                "Mostrame todos los gastos de enero",
            ],
        ),
        AgentSkill(
            id="generar-reporte-visual",
            name="Generar Reporte Visual",
            description=(
                "Genera graficos y visualizaciones de gastos en formato PNG. "
                "Soporta tortas, barras, lineas de tiempo, etc."
            ),
            tags=["finanzas", "grafico", "visualizacion", "reporte"],
            input_modes=["text"],
            output_modes=["text", "file"],
            examples=[
                "Genera un grafico de torta con gastos por categoria",
                "Quiero ver la evolucion de gastos por mes en un grafico de barras",
            ],
        ),
    ],
)



# Agent executor

class RichardExecutor(AgentExecutor):
    """AgentExecutor que usa el grafo LangGraph de RICHARD para procesar tareas."""

    def __init__(self):
        # Compilamos el grafo una sola vez al iniciar el servidor
        logger.info("Inicializando grafo LangGraph de RICHARD...")
        self._graph = build_graph()
        logger.info("Grafo LangGraph listo.")

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """
        Ejecuta la tarea A2A usando el grafo ReAct de RICHARD.

        Pasos:
        1. Extraer el texto del mensaje A2A
        2. Correr el grafo LangGraph en un thread (es sincrono)
        3. Publicar TaskStatusUpdateEvent: working (procesando)
        4. Publicar Task completado con la respuesta como artifact de texto
        """
        # --- 1. Extraer input del usuario ---
        user_input = context.get_user_input()
        if not user_input:
            logger.warning("Mensaje A2A recibido sin contenido de texto.")
            user_input = "(sin mensaje)"

        logger.info("Procesando request A2A: '%s'", user_input[:80])

        # --- 2. Notificar que estamos trabajando ---
        # TaskStatusUpdateEvent informa al cliente que la tarea fue recibida
        # y está siendo procesada. Esto es importante para tasks largos.
        task = new_task(context.message)  # type: ignore[arg-type]
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=task.id,
                context_id=task.context_id,
                status=TaskStatus(
                    state=TaskState.working,
                ),
                final=False,
            )
        )

        # --- 3. Correr el grafo LangGraph ---
        # El grafo es sincrono (usa llm_with_tools.invoke()), entonces lo
        # corremos en un executor para no bloquear el event loop de asyncio.
        state: State = {
            "messages": [HumanMessage(content=user_input)],
            "ultima_imagen": None,
        }

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,  # usa el ThreadPoolExecutor por defecto
                lambda: self._graph.invoke(state),
            )
        except Exception as e:
            logger.error("Error ejecutando grafo LangGraph: %s", e)
            # Publicar tarea fallida
            await event_queue.enqueue_event(
                TaskStatusUpdateEvent(
                    task_id=task.id,
                    context_id=task.context_id,
                    status=TaskStatus(
                        state=TaskState.failed,
                        message=Message(
                            role=Role.agent,
                            parts=[Part(root=TextPart(text=f"Error interno: {e}"))],
                            message_id=f"{task.id}-error",
                        ),
                    ),
                    final=True,
                )
            )
            return

        # --- 4. Extraer la respuesta del ultimo mensaje del agente ---
        messages = result.get("messages", [])
        respuesta = ""
        if messages:
            last = messages[-1]
            if hasattr(last, "text"):
                respuesta = last.text
            elif hasattr(last, "content"):
                if isinstance(last.content, str):
                    respuesta = last.content
                elif isinstance(last.content, list):
                    # Contenido multimodal: extraer partes de texto
                    partes = []
                    for bloque in last.content:
                        if isinstance(bloque, dict) and "text" in bloque:
                            partes.append(bloque["text"])
                        elif isinstance(bloque, str):
                            partes.append(bloque)
                    respuesta = "\n".join(partes)

        if not respuesta:
            respuesta = (
                "El agente procesó la solicitud pero no generó una respuesta de texto."
            )

        # --- 5. Armar artifacts ---
        # Un Artifact es la salida producida por el agente.
        # En este caso es texto (la respuesta del LLM).
        artifacts = [
            Artifact(
                artifact_id="response-text",
                name="Respuesta",
                description="Respuesta del agente de finanzas RICHARD",
                parts=[Part(root=TextPart(text=respuesta))],
            )
        ]

        # Si se generó un gráfico, lo mencionamos en el artifact
        # (en una version futura se podriamos incluir el PNG como FilePart)
        ultima_imagen = result.get("ultima_imagen")
        if ultima_imagen:
            artifacts.append(
                Artifact(
                    artifact_id="chart-path",
                    name="Grafico generado",
                    description="Ruta del archivo PNG generado",
                    parts=[
                        Part(
                            root=TextPart(text=f"Grafico guardado en: {ultima_imagen}")
                        )
                    ],
                )
            )
            logger.info("Grafico generado: %s", ultima_imagen)

        # --- 6. Publicar Task completado ---
        # El Task completado incluye el estado final y los artifacts.
        # El DefaultRequestHandler lo serializa y lo retorna al cliente.
        await event_queue.enqueue_event(
            Task(
                id=task.id,
                context_id=task.context_id,
                status=TaskStatus(
                    state=TaskState.completed,
                    message=Message(
                        role=Role.agent,
                        parts=[Part(root=TextPart(text=respuesta))],
                        message_id=f"{task.id}-response",
                    ),
                ),
                artifacts=artifacts,
            )
        )
        logger.info("Task %s completado.", task.id)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancela una tarea en curso.

        En esta implementacion simple, publicamos inmediatamente el estado
        cancelled ya que no hay forma de interrumpir el grafo LangGraph
        sincrono una vez iniciado.
        """
        logger.info("Cancel request para task %s", context.task_id)
        if context.current_task:
            await event_queue.enqueue_event(
                TaskStatusUpdateEvent(
                    task_id=context.current_task.id,
                    context_id=context.current_task.context_id,
                    status=TaskStatus(state=TaskState.canceled),
                    final=True,
                )
            )


# Entry point:


def build_a2a_app():
    """Construye y retorna la aplicacion ASGI A2A."""
    executor = RichardExecutor()
    task_store = InMemoryTaskStore()

    # DefaultRequestHandler conecta el protocolo A2A con nuestro executor.
    # Maneja: message/send, tasks/get, tasks/cancel, etc.
    handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=task_store,
    )

    # A2AStarletteApplication es la app ASGI que:
    # - Sirve el Agent Card en GET /.well-known/agent.json
    # - Recibe requests JSON-RPC 2.0 en POST /
    # - Delega a DefaultRequestHandler
    app = A2AStarletteApplication(
        agent_card=AGENT_CARD,
        http_handler=handler,
    )
    return app.build()


if __name__ == "__main__":
    logger.info("Iniciando RICHARD A2A Server en %s", BASE_URL)
    logger.info("Agent Card disponible en: %s/.well-known/agent.json", BASE_URL)
    logger.info("Endpoint JSON-RPC: %s (POST)", BASE_URL)
    logger.info("Presiona Ctrl+C para detener.")

    uvicorn.run(
        build_a2a_app(),
        host="0.0.0.0",
        port=PORT,
        log_level="warning",  # uvicorn usa stderr, solo loggear warnings+
    )
