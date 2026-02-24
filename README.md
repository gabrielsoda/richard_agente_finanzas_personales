# RICHARD - Agente de finanzas personales

_**R**eceptor de **I**nformación de **C**onsumos **H**umanos para **A**dministración y **R**egistro del **D**inero_

---

El presente proyecto (MVP) es un agente conversacional de finanzas personales que corre como aplicación de terminal (CLI). Está construido con **LangGraph**, arquitectura ReAct, y usa **Google Gemini 2.5 Flash** como LLM.
El agente permite al usuario, mediante lenguaje natural en español:

- **Registrar gastos** en una base de datos CSV (`agregar_gasto`)
- **Consultar y analizar gastos** mediante código Python generado por el LLM (`consultar_con_codigo`)
- **Generar gráficos** personalizados con matplotlib/seaborn (`generar_grafico_con_codigo`)

La interfaz de terminal usa **Rich** para el renderizado en Markdown, colores, paneles estilizados y spinners de carga mientras se espera la respuesta. 
El sistema se integra con **Langfuse** para observabilidad y trazabilidad de las interacciones con el agente.

**Stack:** Python 3.12, LangGraph, LangChain, Google Gemini 2.5 Flash, Pandas, Matplotlib, Seaborn, Rich, Langfuse.

## Arquitectura ReAct del Agente

![Grafo del agente con el ciclo Thought - Action - Observation](doc_images/grafo_agente.png)

---

*Nota:* Existe la intensión de agregar las siguientes features en el futuro:

| **Migración de CSV a SQLite** | Reemplazar el almacenamiento CSV por una base **SQLite**. Mejora rendimiento, concurrencia, y habilita queries complejas nativas. Especialmente relevante si se escala a multiples usuarios (Telegram).                                                                                                        |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Análisis de imágenes**      | Integrar un VLM o utilizar la funcionalidad de Gemini para poder analizar Recibos y registrar el gasto a partir de eso.                                                                                                                                                                                        |
| **Alertas de presupuesto**    | Definir **topes mensuales por categoría**. El agente avisa proactivamente cuando el usuario se acerca o supera el límite definido.                                                                                                                                                                             |
| **Gastos recurrentes**        | **Permitir registrar gastos recurrentes** (ej: alquiler, streaming, servicios) que se agregan automáticamente cada mes, reduciendo la carga manual del usuario.<br>*Nota:* debería consultar al principio de mes sobre los mismos para corroborar si no hubo cambios de monto o si siguen estando por ejemplo. |
| **Agregar nuevas categorías** | Permitir al usuario agregar nuevas categorías o (incluso subcategorías con un campo extra) agregando un parámetro opcional a `agregar_gasto` y ajustando la validación `nueva_categoria: bool = False,`                                                                                                        |
