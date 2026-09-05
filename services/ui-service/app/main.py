import gradio as gr

from theme import theme, CUSTOM_CSS
from components.chat_tab import build_chat_tab
from components.dashboard_tab import build_dashboard_tab
from components.documents_tab import build_documents_tab

with gr.Blocks(title="LEDGER") as demo:
    gr.HTML(
        """
        <div id="ledger-masthead">
            <h1>LEDGER<span id="ledger-cursor">_</span></h1>
            <p>FINANCIAL DOCUMENT INTELLIGENCE — CORPUS-WIDE QUESTION ANSWERING</p>
        </div>
        """
    )

    with gr.Tab("Chat"):
        build_chat_tab()

    with gr.Tab("Dashboard"):
        load_fn, outputs = build_dashboard_tab()
        demo.load(fn=load_fn, outputs=outputs)

    with gr.Tab("Documents"):
        docs_load_fn, docs_outputs = build_documents_tab()
        demo.load(fn=docs_load_fn, outputs=docs_outputs)

if __name__ == "__main__":
    
    demo.launch(
        server_name="0.0.0.0",
        theme=theme,
        css=CUSTOM_CSS,
    )