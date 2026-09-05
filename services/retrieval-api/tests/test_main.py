from fastapi.testclient import TestClient
from app.main import app
from shared.schemas.document import ProcessedDocument
from app.chunker import create_chunks

# Initialize the test client
client = TestClient(app)

# Reusable mock data simulating the parser's output
MOCK_DOCUMENT = {
    "document_id": "doc_10k_2023",
    "source_filename": "q3_report.pdf",
    "page_count": 1,
    "pages": [
        {
            "page_number": 1,
            "blocks": [
                {
                    "block_id": "b1",
                    "content_type": "heading",
                    "text": "Q3 European Cloud Sales",
                    "section": "Revenue",
                    "bbox": [0.0, 0.0, 100.0, 20.0]
                },
                {
                    "block_id": "b2",
                    "content_type": "paragraph",
                    "text": "Revenue grew by 15% due to enterprise contract renewals.",
                    "section": "Revenue",
                    "bbox": [0.0, 25.0, 200.0, 50.0]
                }
            ],
            "tables": [
                {
                    "table_id": "t1",
                    "content_type": "table",
                    "section": "Financials",
                    "caption": "Quarterly Profit Margins",
                    "bbox": [0.0, 60.0, 300.0, 150.0],
                    "num_rows": 2,
                    "num_cols": 2,
                    "rows": [
                        ["Region", "Profit"],
                        ["Europe", "$4.2M"]
                    ]
                }
            ]
        }
    ]
}

def test_chunker_logic():
    """Unit test to verify parent-child and table-aware chunking rules."""
    doc = ProcessedDocument(**MOCK_DOCUMENT)
    chunks = create_chunks(doc)
    
    assert len(chunks) == 2, "Should create exactly one text chunk and one table chunk"
    
    # Verify Parent-Child logic (Heading + Paragraph)
    assert "Q3 European Cloud Sales" in chunks[0].text
    assert "Revenue grew by 15%" in chunks[0].text
    assert chunks[0].metadata["type"] == "text"

    # Verify Table-Aware logic
    assert "Quarterly Profit Margins" in chunks[1].text
    assert "Europe | $4.2M" in chunks[1].text
    assert chunks[1].metadata["type"] == "table"

def test_ingest_endpoint():
    """Integration test to verify document vectorization and DB upsert."""
    response = client.post("/ingest", json=MOCK_DOCUMENT)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["total_chunks"] == 2

def test_search_endpoint():
    """Integration test to verify hybrid retrieval and RRF fusion."""
    # Ensure data is ingested first for this test run
    client.post("/ingest", json=MOCK_DOCUMENT)
    
    search_payload = {
        "query": "How much did European revenue grow?",
        "document_id": "doc_10k_2023",
        "limit": 2
    }
    
    response = client.post("/search", json=search_payload)
    
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert len(data["results"]) > 0
    
    # The top result should ideally be the text chunk about 15% growth
    top_result = data["results"][0]
    assert "score" in top_result
    assert "text" in top_result
    assert top_result["metadata"]["document_id"] == "doc_10k_2023"