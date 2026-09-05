import gradio as gr

from client import get_dashboard_data


def build_dashboard_tab():
    with gr.Column():
        gr.Markdown("### Corpus Dashboard")

        refresh_btn = gr.Button("Refresh")
        num_docs = gr.Number(label="Indexed documents", interactive=False)
        doc_table = gr.Dataframe(
            headers=["document_id", "name", "pages"],
            label="Indexed documents",
            interactive=False,
        )
        query_table = gr.Dataframe(
            headers=["question", "latency_ms"],
            label="Recent queries",
            interactive=False,
        )

        def load():
            data = get_dashboard_data()
            docs = [
                [d["document_id"], d["name"], d["pages"]]
                for d in data.get("documents", [])
            ]
            queries = [
                [q["question"], q["latency_ms"]]
                for q in data.get("recent_queries", [])
            ]
            return data.get("num_documents", 0), docs, queries

        refresh_btn.click(fn=load, outputs=[num_docs, doc_table, query_table])

    # returned so app.py can wire demo.load() to populate on first render
    return load, [num_docs, doc_table, query_table]
