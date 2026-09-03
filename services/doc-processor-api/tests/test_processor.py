from app.processor import process_pdf

def test_sample1_structure():
    doc = process_pdf("tests/fixtures/sample1.pdf", document_id="torm_sample1")

    assert doc.document_id == "torm_sample1"
    assert doc.page_count == 1

    page = doc.pages[0]
    assert len(page.tables) == 3
    assert any("EARNINGS PER SHARE" in t.section.upper() or "NOTE 26" in t.section
                for t in page.tables)

    # the known wrapped-cell bug — assert it's still there so a docling
    # upgrade or code change that silently fixes/breaks it gets caught
    jv_table = page.tables[0]
    assert jv_table.num_rows == 5  # was 4 before the num_rows counting fix
    assert len(jv_table.rows) == jv_table.num_rows # documents the current known limitation