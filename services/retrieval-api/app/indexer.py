import os
import json
import httpx  # or import requests

# Make sure this matches your running FastAPI port
API_URL = "http://localhost:8000/ingest" 
FOLDER_PATH = "./data/processed" # The folder where you unzipped the JSONs

def index_all_files():
    # Loop through every file in the folder
    for filename in os.listdir(FOLDER_PATH):
        if filename.endswith(".json"):
            file_path = os.path.join(FOLDER_PATH, filename)
            
            # Read the JSON file
            with open(file_path, "r", encoding="utf-8") as f:
                doc_payload = json.load(f)
                
            print(f"Indexing {filename}...")
            
            try:
                # Send it to your /ingest endpoint
                # Timeout is high because FastEmbed might take a few seconds per file
                response = httpx.post(API_URL, json=doc_payload, timeout=120.0)
                
                if response.status_code == 200:
                    print(f"✅ Success: {response.json()}")
                else:
                    print(f"❌ Failed {filename}: {response.status_code} - {response.text}")
                    
            except Exception as e:
                print(f"⚠️ Error on {filename}: {str(e)}")

if __name__ == "__main__":
    index_all_files()