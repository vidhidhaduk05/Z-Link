#!/usr/bin/env python3
"""
Launcher script for Co-Scientist Reference Auditor & Zotero Linker.
Runs the local FastAPI backend server on port 8765.
"""
import sys
import uvicorn

def main():
    port = 8765
    print("=" * 70)
    print("📚 Co-Scientist Reference Auditor & Zotero Linker Server")
    print(f"👉 Local Web App & API: http://localhost:{port}")
    print("=" * 70)
    uvicorn.run("server.main:app", host="0.0.0.0", port=port, reload=False)

if __name__ == "__main__":
    main()

