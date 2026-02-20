from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt
from rich.text import Text
from rich import box
from langchain_core.messages import HumanMessage


console = Console()


def print_welcome():
    welcome = Text()
    welcome.append("Asistente de Gastos Financieros\n", style="bold cyan")
    welcome.append("LangGraph + Gemini\n\n", style="dim")
    welcome.append("Puedo ayudarte a:\n", style="bold white")
    welcome.append("  • Registrar tus gastos\n", style="green")
    welcome.append("  • Consultar cuánto gastaste\n", style="green")
    welcome.append("  • Generar gráficos de tus gastos\n", style="green")
    welcome.append("\nEscribí ", style="dim")
    welcome.append("'salir'", style="bold red")
    welcome.append(" para terminar.", style="dim")

    console.print(
        Panel(welcome, box=box.DOUBLE_EDGE, border_style="cyan", padding=(1, 2))
    )
    console.print()


def print_response(text: str):
    try:
        md = Markdown(text)
        console.print(
            Panel(
                md,
                title="[bold green]Agente[/bold green]",
                border_style="green",
                padding=(0, 1),
            )
        )
    except Exception:
        console.print(
            Panel(
                text,
                title="[bold green]Agente[/bold green]",
                border_style="green",
                padding=(0, 1),
            )
        )
    console.print()


def mostrar_imagen(ruta: str):
    """Muestra la imagen en la terminal si el protocolo es soportado, sino imprime la ruta."""
    try:
        from term_image.image import AutoImage

        console.print()
        AutoImage(ruta).draw()
        console.print()
    except Exception:
        console.print(
            f"[dim]Gráfico guardado en:[/dim] [bold cyan]{ruta}[/bold cyan]\n"
        )


def extract_response_text(last_message) -> str:
    if hasattr(last_message, "text"):
        return last_message.text
    elif hasattr(last_message, "content"):
        if isinstance(last_message.content, list):
            parts = []
            for block in last_message.content:
                if isinstance(block, dict) and "text" in block:
                    parts.append(block["text"])
                elif isinstance(block, str):
                    parts.append(block)
            return "\n".join(parts)
        else:
            return last_message.content
    return str(last_message)


def main():
    """Loop principal del agente en terminal con rich."""
    print_welcome()
    from main import build_graph, get_langfuse_handler

    graph = build_graph()
    langfuse_handler = get_langfuse_handler()
    if langfuse_handler:
        console.print(
            "[bold yellow][[Langfuse]][/bold yellow] Observabilidad activada.\n"
        )
    else:
        console.print(
            "[dim][[Langfuse]] No configurado — ejecutando sin observabilidad.[/dim]\n"
        )

    state = {"messages": [], "ultima_imagen": None}

    while True:
        try:
            user_input = Prompt.ask("[bold cyan]Vos[/bold cyan]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[bold red]Hasta luego![/bold red]")
            break
        if not user_input:
            continue
        if user_input.lower() in ("salir", "exit", "quit", "q"):
            console.print("\n[bold red]Hasta luego![/bold red]")
            break
        state["messages"].append(HumanMessage(content=user_input))
        config = {}
        if langfuse_handler:
            config["callbacks"] = [langfuse_handler]
        with console.status("[bold green]Pensando...[/bold green]", spinner="dots"):
            try:
                result = graph.invoke(state, config=config if config else None)
                state = result
                last_message = result["messages"][-1]
                response_text = extract_response_text(last_message)
            except Exception as e:
                console.print(f"\n[bold red][Error][/bold red] {e}\n")
                if state["messages"] and isinstance(
                    state["messages"][-1], HumanMessage
                ):
                    state["messages"].pop()
                continue
        print_response(response_text)
        # Mostrar imagen si el agente generó un gráfico
        if state.get("ultima_imagen"):
            mostrar_imagen(state["ultima_imagen"])
            state["ultima_imagen"] = None
