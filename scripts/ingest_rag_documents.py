import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from google import genai
from google.genai import types

from core.config import settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = PROJECT_ROOT / "docs" / "rag_sources"
MANIFEST_PATH = SOURCE_ROOT / "manifest.json"
POLL_INTERVAL_SECONDS = 2
UPLOAD_TIMEOUT_SECONDS = 180


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def metadata_value(metadata: list | None, key: str) -> str | None:
    for item in metadata or []:
        if getattr(item, "key", None) == key:
            return getattr(item, "string_value", None)

    return None


def wait_for_upload(client, operation, filename: str) -> None:
    deadline = time.monotonic() + UPLOAD_TIMEOUT_SECONDS

    while not operation.done:
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Timed out waiting for indexing of {filename}. "
                "Check the store before retrying."
            )

        time.sleep(POLL_INTERVAL_SECONDS)
        operation = client.operations.get(operation=operation)

    if operation.error:
        raise RuntimeError(f"Upload/indexing failed for {filename}: {operation.error}")

    print(f"Indexed successfully: {filename}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingest verified AquaTrace RAG documents."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Upload documents after validation. Without this flag, only preview.",
    )
    args = parser.parse_args()

    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    if not settings.gemini_file_search_store_name:
        raise RuntimeError("GEMINI_FILE_SEARCH_STORE_NAME is not configured.")

    if not MANIFEST_PATH.is_file():
        raise FileNotFoundError(f"Manifest not found: {MANIFEST_PATH}")

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    if not isinstance(manifest, list) or not manifest:
        raise ValueError("The manifest must be a non-empty JSON list.")

    required_fields = {"document", "sha256", "category", "status"}
    entries = []
    seen_names = set()

    print("VALIDATING LOCAL DOCUMENTS")

    for entry in manifest:
        if not isinstance(entry, dict):
            raise ValueError("Every manifest entry must be a JSON object.")

        missing_fields = required_fields - entry.keys()
        if missing_fields:
            raise ValueError(
                f"Manifest entry is missing fields: {sorted(missing_fields)}"
            )

        filename = entry["document"]

        if (
            not isinstance(filename, str)
            or not filename
            or Path(filename).name != filename
        ):
            raise ValueError(f"Invalid document filename: {filename!r}")

        if filename in seen_names:
            raise ValueError(f"Duplicate manifest entry: {filename}")

        seen_names.add(filename)
        path = SOURCE_ROOT / filename

        if not path.is_file():
            raise FileNotFoundError(f"Source document not found: {path}")

        actual_hash = sha256_file(path)

        if actual_hash != entry["sha256"]:
            raise ValueError(
                f"SHA-256 mismatch for {filename}. No documents have been uploaded."
            )

        if not entry["category"] or not entry["status"]:
            raise ValueError(f"Category or review status is empty for {filename}.")

        entries.append((entry, path))
        print(
            f"OK: {filename} | category={entry['category']} | status={entry['status']}"
        )

    client = genai.Client(api_key=settings.gemini_api_key)
    store_name = settings.gemini_file_search_store_name

    store = client.file_search_stores.get(name=store_name)
    print(f"\nTarget store: {store.name}")
    print(f"Display name: {store.display_name}")

    existing_by_name = {}

    for document in client.file_search_stores.documents.list(parent=store_name):
        display_name = getattr(document, "display_name", None)

        if display_name:
            existing_by_name.setdefault(display_name, []).append(document)

    to_upload = []

    print("\nCHECKING EXISTING DOCUMENTS")

    for entry, path in entries:
        filename = entry["document"]
        existing = existing_by_name.get(filename, [])

        if not existing:
            to_upload.append((entry, path))
            print(f"NEW: {filename}")
            continue

        if len(existing) > 1:
            raise RuntimeError(
                f"Multiple store documents use display name {filename!r}. "
                "Resolve the duplicates before continuing."
            )

        stored_hash = metadata_value(
            getattr(existing[0], "custom_metadata", None),
            "source_sha256",
        )

        if stored_hash == entry["sha256"]:
            print(f"ALREADY INDEXED; SKIPPING: {filename}")
            continue

        raise RuntimeError(
            f"CONFLICT: {filename!r} already exists in the store, "
            "but its source SHA-256 does not match the manifest or "
            "cannot be verified. No new uploads have been started."
        )

    if not to_upload:
        print("\nAll manifest documents are already indexed.")
        return 0

    print(f"\nDocuments ready to upload: {len(to_upload)}")

    for entry, _ in to_upload:
        print(
            f"  {entry['document']} | "
            f"category={entry['category']} | status={entry['status']}"
        )

    if not args.apply:
        print("\nDRY RUN ONLY: no documents were uploaded.")
        print("Review the list, then rerun with --apply to upload.")
        return 0

    print("\nUPLOADING DOCUMENTS")

    for entry, path in to_upload:
        filename = entry["document"]

        config = types.UploadToFileSearchStoreConfig(
            display_name=filename,
            mime_type="text/markdown",
            custom_metadata=[
                types.CustomMetadata(
                    key="category",
                    string_value=entry["category"],
                ),
                types.CustomMetadata(
                    key="review_status",
                    string_value=entry["status"],
                ),
                types.CustomMetadata(
                    key="source_sha256",
                    string_value=entry["sha256"],
                ),
            ],
        )

        operation = client.file_search_stores.upload_to_file_search_store(
            file_search_store_name=store_name,
            file=str(path),
            config=config,
        )

        print(f"Upload submitted: {filename}")
        wait_for_upload(client, operation, filename)

    print("\nIngestion finished.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
