from pathlib import Path

import gradio as gr
import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse

from app.client import ORCHESTRATOR_URL, runtime_status
from app.components.chat_tab import build_chat_tab
from app.components.dashboard_tab import build_dashboard_tab
from app.components.documents_tab import build_documents_tab
from app.theme import CUSTOM_CSS, theme

status = runtime_status()

with gr.Blocks(title="LEDGER") as demo:
    gr.HTML(
        """
        <div id="ledger-masthead">
            <h1>LEDGER<span id="ledger-cursor">_</span></h1>
            <p>FINANCIAL DOCUMENT INTELLIGENCE — CORPUS-WIDE QUESTION ANSWERING</p>
        </div>
        """
    )
    if status["mock"]:
        gr.Markdown(
            "**MOCK MODE** - answers and document data are canned and do not "
            "use the validation or retrieval pipeline."
        )
    else:
        gr.Markdown(f"**LIVE MODE** - connected to `{status['orchestrator_url']}`")

    with gr.Tab("Chat"):
        build_chat_tab()

    with gr.Tab("Dashboard"):
        load_fn, outputs = build_dashboard_tab()
        demo.load(fn=load_fn, outputs=outputs)

    with gr.Tab("Documents"):
        docs_load_fn, docs_outputs = build_documents_tab()
        demo.load(fn=docs_load_fn, outputs=docs_outputs)

_SERVICE_DIR = Path(__file__).resolve().parents[1]
_STATIC_DIR = Path(__file__).resolve().parent / "static"
_PDFJS_DIR = _SERVICE_DIR / "node_modules" / "pdfjs-dist"

app = FastAPI(title="LEDGER UI")
app.mount("/viewer", StaticFiles(directory=_STATIC_DIR, html=True), name="viewer")
app.mount("/assets/pdfjs", StaticFiles(directory=_PDFJS_DIR), name="pdfjs")


@app.get("/api/documents/{document_id}/pdf")
async def proxy_document_pdf(
    document_id: str,
    range_header: str | None = Header(None, alias="Range"),
):
    """Same-origin proxy required by PDF.js; forwards byte-range requests."""
    client = httpx.AsyncClient()
    headers = {"Range": range_header} if range_header else None
    try:
        upstream = await client.send(
            client.build_request(
                "GET", f"{ORCHESTRATOR_URL}/documents/{document_id}/pdf", headers=headers
            ),
            stream=True,
        )
    except httpx.HTTPError as exc:
        await client.aclose()
        raise HTTPException(status_code=502, detail="Could not retrieve the source PDF") from exc
    if upstream.status_code >= 400:
        status_code = 404 if upstream.status_code == 404 else 502
        await upstream.aclose()
        await client.aclose()
        raise HTTPException(status_code=status_code, detail="Source PDF is unavailable")

    forwarded = {
        key: value for key, value in upstream.headers.items()
        if key.lower() in {
            "accept-ranges", "content-disposition", "content-length", "content-range",
            "etag", "last-modified",
        }
    }

    async def body():
        async for chunk in upstream.aiter_bytes():
            yield chunk

    async def close_upstream():
        await upstream.aclose()
        await client.aclose()

    return StreamingResponse(
        body(),
        status_code=upstream.status_code,
        media_type="application/pdf",
        headers=forwarded,
        background=BackgroundTask(close_upstream),
    )


app = gr.mount_gradio_app(app, demo, path="/", theme=theme, css=CUSTOM_CSS)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=7860)
