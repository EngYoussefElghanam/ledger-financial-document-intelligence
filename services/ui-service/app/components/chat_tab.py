import gradio as gr

from client import ask_question
from components.format_answer import format_answer


def build_chat_tab():
    with gr.Column():
        gr.Markdown(
            "### Corpus-wide Q&A\n"
            "Ask a question without naming the document — LEDGER finds the source."
        )

        doc_scope = gr.Textbox(
            label="Optional: scope to a document_id",
            placeholder="Leave blank to search the full corpus",
        )

        def respond(message, history, scope):
            scope = scope.strip() or None
            try:
                raw = ask_question(message, document_id=scope)
            except Exception as e:
                return f"⚠️ **Request failed:** {e}"
            return format_answer(raw)

        gr.ChatInterface(
            fn=respond,
            additional_inputs=[doc_scope],
            title=None,
        )
