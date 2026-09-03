from datasets import load_dataset

# stream=True avoids downloading the whole zip up front
ds = load_dataset("next-tat/TAT-DQA", split="test", streaming=True)

sample = []
for i, ex in enumerate(ds):
    sample.append(ex)
    if i >= 9:  # grab 10 examples
        break

from docling.document_converter import DocumentConverter
converter = DocumentConverter()
result = converter.convert("sample.pdf")
print(result.document.export_to_markdown())