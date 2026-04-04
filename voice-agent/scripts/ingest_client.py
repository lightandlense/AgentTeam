"""
CLI to ingest a document into a client's knowledge base.

Run from the voice-agent/ directory:
    python scripts/ingest_client.py --client-id <uuid> --file /path/to/doc.pdf
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.services.ingestion import ingest_document


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest a document into a voice-agent client's knowledge base."
    )
    parser.add_argument("--client-id", required=True, help="Client UUID (required)")
    parser.add_argument("--file", required=True, help="Path to document file (required)")
    return parser.parse_args()


async def run_ingest(client_id: str, filename: str, content: bytes) -> dict:
    async with AsyncSessionLocal() as session:
        return await ingest_document(session, client_id, filename, content)


def main() -> None:
    args = parse_args()
    client_id = args.client_id.strip()
    file_path = args.file.strip()

    if not client_id:
        print("ERROR: --client-id must be a non-empty string", file=sys.stderr)
        sys.exit(1)

    if not file_path:
        print("ERROR: --file must be a non-empty path", file=sys.stderr)
        sys.exit(1)

    doc_path = Path(file_path)
    if not doc_path.exists():
        print(f"ERROR: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    if not doc_path.is_file():
        print(f"ERROR: Path is not a file: {file_path}", file=sys.stderr)
        sys.exit(1)

    try:
        settings = get_settings()
        if not settings.openai_api_key:
            print("ERROR: OPENAI_API_KEY is not set in environment", file=sys.stderr)
            sys.exit(1)
    except Exception as exc:
        print(f"ERROR: Failed to load settings: {exc}", file=sys.stderr)
        sys.exit(1)

    content = doc_path.read_bytes()
    filename = doc_path.name

    result = asyncio.run(run_ingest(client_id=client_id, filename=filename, content=content))

    print(
        f"Ingested {result['chunks_ingested']} chunks from {result['doc_name']} "
        f"into client {client_id}"
    )


if __name__ == "__main__":
    main()
