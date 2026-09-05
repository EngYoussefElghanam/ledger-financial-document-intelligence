import json
from document import ProcessedDocument

with open("document.schema.json", "w") as f:
    json.dump(ProcessedDocument.model_json_schema(), f, indent=2)