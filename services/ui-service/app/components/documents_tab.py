import gradio as gr

from client import get_documents, get_document_detail


def _format_structured_values(values: dict) -> str:
    if not values:
        return "_No structured values extracted._"
    return "\n".join(f"- **{k}**: {v}" for k, v in values.items())


def build_documents_tab():
    with gr.Column():
        gr.Markdown(
            "### Indexed Documents\n"
            "Inspect what doc-processor-api extracted from each PDF — "
            "page count, detected tables, and structured values."
        )

        refresh_btn = gr.Button("Refresh")
        doc_table = gr.Dataframe(
            headers=["document_id", "name", "pages", "tables_detected"],
            label="Indexed documents",
            interactive=False,
        )

        gr.Markdown("---")
        gr.Markdown("### Inspect a document")
        doc_id_input = gr.Textbox(
            label="document_id",
            placeholder="e.g. doc_017",
        )
        inspect_btn = gr.Button("Inspect")
        detail_output = gr.Markdown()

        def load_documents():
            docs = get_documents()
            rows = [
                [d["document_id"], d["name"], d["pages"], d.get("tables_detected", 0)]
                for d in docs
            ]
            return rows

        def inspect_document(document_id: str):
            document_id = document_id.strip()
            if not document_id:
                return "_Enter a document_id above, or pick one from the table._"

            doc = get_document_detail(document_id)
            if "error" in doc:
                return f"⚠️ {doc['error']}"

            structured = _format_structured_values(doc.get("structured_values", {}))
            return (
                f"**{doc['name']}** (`{doc['document_id']}`)\n\n"
                f"- Pages: {doc['pages']}\n"
                f"- Tables detected: {doc.get('tables_detected', 0)}\n\n"
                f"**Structured values**\n{structured}"
            )

        def select_row(evt: gr.SelectData):
            # clicking a row in the table auto-fills the document_id box
            return evt.row_value[0]

        refresh_btn.click(fn=load_documents, outputs=[doc_table])
        doc_table.select(fn=select_row, outputs=[doc_id_input])
        inspect_btn.click(fn=inspect_document, inputs=[doc_id_input], outputs=[detail_output])

    return load_documents, [doc_table]
