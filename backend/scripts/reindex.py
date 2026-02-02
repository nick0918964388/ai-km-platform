#!/usr/bin/env python3
"""Re-index documents from storage to Qdrant."""

import os
import sys
import requests
from pathlib import Path

API_URL = "http://localhost:8000"
API_KEY = "_lAWtCn29ETEomZjfz1Xa9SvVsrjOaCMvqt0htX3Shw"
STORAGE_DIR = Path(__file__).parent.parent / "storage" / "documents"

def upload_file(filepath: Path) -> dict:
    """Upload a file to the KB API."""
    headers = {"X-API-Key": API_KEY}
    with open(filepath, "rb") as f:
        files = {"file": (filepath.name, f)}
        response = requests.post(
            f"{API_URL}/api/kb/upload",
            headers=headers,
            files=files
        )
    return response.json()

def main():
    # Find all unique files
    seen = set()
    files_to_upload = []
    
    for doc_dir in STORAGE_DIR.iterdir():
        if doc_dir.is_dir():
            for f in doc_dir.iterdir():
                if f.suffix.lower() in ['.pdf', '.docx', '.xlsx', '.xls', '.png', '.jpg', '.jpeg']:
                    if f.name not in seen:
                        seen.add(f.name)
                        files_to_upload.append(f)
    
    print(f"Found {len(files_to_upload)} unique files to upload")
    print()
    
    success = 0
    failed = 0
    
    for i, f in enumerate(files_to_upload, 1):
        print(f"[{i}/{len(files_to_upload)}] Uploading: {f.name}")
        try:
            result = upload_file(f)
            if "document_id" in result:
                print(f"  ✅ Success: {result.get('message', 'OK')}")
                success += 1
            else:
                print(f"  ❌ Error: {result.get('detail', result)}")
                failed += 1
        except Exception as e:
            print(f"  ❌ Exception: {e}")
            failed += 1
    
    print()
    print("=" * 40)
    print(f"Done! Success: {success}, Failed: {failed}")
    
    # Get stats
    headers = {"X-API-Key": API_KEY}
    stats = requests.get(f"{API_URL}/api/kb/stats", headers=headers).json()
    print()
    print("KB Stats:")
    print(f"  Documents: {stats.get('total_documents', 0)}")
    print(f"  Text chunks: {stats.get('text_chunks', 0)}")
    print(f"  Image chunks: {stats.get('image_chunks', 0)}")

if __name__ == "__main__":
    main()
