"""Local document ingestion and immutable, fingerprinted search generations."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path

import faiss
import numpy as np
from filelock import FileLock, Timeout

from eve_ah.config import Settings
from eve_ah.models import EveError, Source

FORMAT_VERSION = 1
SUPPORTED = {".txt", ".md", ".pdf", ".docx"}


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class LocalEmbedder:
    """Lazy model loading keeps CLI help and process health lightweight."""

    def __init__(self, settings: Settings):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(settings.embed_model)
        self.tokenizer = self.model.tokenizer
        self.limit = int(self.model.max_seq_length) - self.tokenizer.num_special_tokens_to_add()
        revision = getattr(self.model[0].auto_model.config, "_commit_hash", None)
        self.fingerprint = {
            "model": settings.embed_model,
            "revision": revision,
            "dimension": self.model.get_sentence_embedding_dimension(),
            "tokenizer": _hash(self.tokenizer.backend_tokenizer.to_str().encode()),
            "max_tokens": self.limit,
            "normalized": True,
        }
        if settings.bot.chunk_tokens > self.limit:
            raise EveError(
                f"chunk_tokens exceeds this embedding model's limit ({self.limit}); update bot.yaml.",
                code="invalid_chunking",
            )

    def chunk(self, text: str, tokens: int, overlap: int) -> list[str]:
        if tokens > self.limit or overlap >= tokens:
            raise EveError("Invalid tokenizer chunk settings.", code="invalid_chunking")
        encoded = self.tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
        offsets = encoded["offset_mapping"]
        pieces = []
        start = 0
        while start < len(offsets):
            end = min(start + tokens, len(offsets))
            # Prefer a paragraph boundary in the latter half without exceeding token budget.
            if end < len(offsets):
                for boundary in range(end - 1, start + tokens // 2, -1):
                    gap = text[offsets[boundary - 1][1] : offsets[boundary][0]]
                    if "\n" in gap:
                        end = boundary
                        break
            piece = text[offsets[start][0] : offsets[end - 1][1]].strip()
            if piece:
                pieces.append(piece)
            if end == len(offsets):
                break
            start = max(start + 1, end - overlap)
        return pieces

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.asarray(
            self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False),
            dtype=np.float32,
        )


def _extract(path: Path, max_pages: int, max_bytes: int) -> list[dict]:
    """Runs in a child process; the parent applies a hard extraction timeout."""
    suffix = path.suffix.lower()
    pages = []
    if suffix in {".txt", ".md"}:
        pages = [{"page": None, "text": path.read_text(encoding="utf-8")}]
    elif suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ValueError("Encrypted PDF is unsupported")
        if len(reader.pages) > max_pages:
            raise ValueError("PDF exceeds page limit")
        for i, page in enumerate(reader.pages):
            pages.append({"page": i + 1, "text": page.extract_text() or ""})
            if sum(len(p["text"].encode()) for p in pages) > max_bytes:
                raise ValueError("Extracted text exceeds size limit")
    elif suffix == ".docx":
        from docx import Document

        with zipfile.ZipFile(path) as archive:
            if sum(i.file_size for i in archive.infolist()) > max_bytes * 5:
                raise ValueError("Expanded document exceeds size limit")
        document = Document(path)
        text = "\n".join(p.text for p in document.paragraphs)
        for table in document.tables:
            text += "\n" + "\n".join(" | ".join(c.text for c in row.cells) for row in table.rows)
        pages = [{"page": None, "text": text}]
    if sum(len(p["text"].encode()) for p in pages) > max_bytes:
        raise ValueError("Extracted text exceeds size limit")
    pages = [p for p in pages if p["text"].strip()]
    if not pages:
        raise ValueError("No extractable text; image-only PDFs require OCR")
    return pages


class Knowledge:
    def __init__(self, settings: Settings, embedder=None):
        self.settings = settings
        self._embedder = embedder
        self.index = None
        self.records = []
        self.generation = None

    @property
    def embedder(self):
        if self._embedder is None:
            self._embedder = LocalEmbedder(self.settings)
        return self._embedder

    def _fingerprint(self):
        return {
            "format": FORMAT_VERSION,
            "embedding": self.embedder.fingerprint,
            "chunk_tokens": self.settings.bot.chunk_tokens,
            "chunk_overlap": self.settings.bot.chunk_overlap,
        }

    def _read_generation(self):
        try:
            pointer = json.loads((self.settings.storage_dir / "active.json").read_text())
            generation = pointer["generation"]
            if not isinstance(generation, str) or len(generation) != 32:
                raise ValueError("Invalid generation")
            int(generation, 16)
            folder = self.settings.storage_dir / "generations" / generation
            manifest_bytes = (folder / "manifest.json").read_bytes()
            if _hash(manifest_bytes) != pointer["manifest_sha256"]:
                raise ValueError("Manifest checksum mismatch")
            manifest = json.loads(manifest_bytes)
            if manifest["fingerprint"] != self._fingerprint():
                raise EveError(
                    "Index is incompatible with configuration; run eve-ah ingest.",
                    code="index_incompatible",
                )
            record_bytes = (folder / "chunks.json").read_bytes()
            if _hash(record_bytes) != manifest["chunks_sha256"]:
                raise ValueError("Chunk checksum mismatch")
            index_bytes = (folder / "index.faiss").read_bytes()
            if _hash(index_bytes) != manifest["index_sha256"]:
                raise ValueError("Index checksum mismatch")
            records = json.loads(record_bytes)
            index = faiss.deserialize_index(np.frombuffer(index_bytes, dtype=np.uint8).copy())
            if index.ntotal != len(records) or index.d != self.embedder.fingerprint["dimension"]:
                raise ValueError("Index dimensions mismatch")
            return generation, index, records
        except EveError:
            raise
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            raise EveError(
                "Index unavailable or damaged; run eve-ah ingest.", code="index_unavailable"
            ) from exc

    def load(self):
        # Clear stale in-process data even when reload fails.
        self.index, self.records, self.generation = None, [], None
        generation, index, records = self._read_generation()
        if not records:
            raise EveError(
                "No documents indexed; add documents and run eve-ah ingest.", code="empty_index"
            )
        self.generation, self.index, self.records = generation, index, records

    def _files(self):
        root = self.settings.data_dir
        if root.is_symlink() or not root.is_dir():
            raise EveError(
                "The data directory must exist and must not be a symlink.", code="invalid_data"
            )
        files, skipped, total = [], [], 0

        def traversal_error(error):
            raise EveError(
                "Cannot read the complete data directory; check permissions.", code="invalid_data"
            ) from error

        for base, directories, names in os.walk(root, followlinks=False, onerror=traversal_error):
            for name in directories + names:
                if (Path(base) / name).is_symlink():
                    raise EveError(
                        "Symlinks are not allowed in the data directory.", code="invalid_data"
                    )
            for name in sorted(names):
                path = Path(base) / name
                relative = path.relative_to(root).as_posix()
                if path.suffix.lower() not in SUPPORTED:
                    skipped.append(relative)
                    continue
                size = path.stat().st_size
                total += size
                if size > self.settings.max_file_bytes or total > self.settings.max_corpus_bytes:
                    raise EveError(
                        "Document or corpus exceeds configured size limit.", code="size_limit"
                    )
                files.append((relative, path))
                if len(files) > 10000:
                    raise EveError("Corpus exceeds 10000 documents.", code="size_limit")
        return sorted(files), skipped

    def _parse(self, path):
        # Child process isolates slow parsers and can be killed on timeout.
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "eve_ah.knowledge",
                    "--extract",
                    str(path),
                    str(self.settings.max_pages),
                    str(self.settings.max_file_bytes),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
                env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
            )
            return json.loads(result.stdout)
        except (subprocess.SubprocessError, ValueError) as exc:
            raise EveError(
                f"Could not extract {path.name}; check format, size, page limits, or OCR requirements.",
                code="extraction_failed",
            ) from exc

    def ingest(self):
        self.settings.storage_dir.mkdir(parents=True, exist_ok=True)
        try:
            with FileLock(str(self.settings.storage_dir / "writer.lock"), timeout=0):
                return self._ingest_locked()
        except Timeout as exc:
            raise EveError("An ingestion is already running.", code="ingestion_busy") from exc

    def _ingest_locked(self):
        files, skipped = self._files()
        fingerprint = self._fingerprint()
        previous = {}
        try:
            _, old_index, old_records = self._read_generation()
            vectors = old_index.reconstruct_n(0, old_index.ntotal)
            previous = {r["text_hash"]: vectors[i] for i, r in enumerate(old_records)}
        except EveError:
            pass  # A complete rebuild repairs an absent, incompatible, or damaged index.
        records, hashes, extracted_bytes = [], {}, 0
        for name, path in files:
            hashes[name] = _hash(path.read_bytes())
            for page in self._parse(path):
                extracted_bytes += len(page["text"].encode())
                if extracted_bytes > self.settings.max_corpus_bytes:
                    raise EveError(
                        "Extracted corpus exceeds configured size limit.", code="size_limit"
                    )
                chunks = self.embedder.chunk(
                    page["text"],
                    self.settings.bot.chunk_tokens,
                    self.settings.bot.chunk_overlap,
                )
                for i, text in enumerate(chunks):
                    text_hash = _hash(text.encode())
                    source_id = "c-" + _hash(f"{name}:{page['page']}:{i}:{text_hash}".encode())[:16]
                    records.append(
                        {
                            "id": source_id,
                            "name": name,
                            "page": page["page"],
                            "text": text,
                            "text_hash": text_hash,
                        }
                    )
        dimension = self.embedder.fingerprint["dimension"]
        missing = {r["text_hash"]: r["text"] for r in records if r["text_hash"] not in previous}
        if missing:
            keys = list(missing)
            for start in range(0, len(keys), 64):
                batch = keys[start : start + 64]
                encoded = self.embedder.embed([missing[k] for k in batch])
                if encoded.shape != (len(batch), dimension) or not np.isfinite(encoded).all():
                    raise EveError(
                        "Embedding model returned invalid vectors.", code="embedding_failed"
                    )
                previous.update(zip(batch, encoded))
        index = faiss.IndexFlatIP(dimension)
        if records:
            vectors = np.asarray([previous[r["text_hash"]] for r in records], dtype=np.float32)
            faiss.normalize_L2(vectors)
            index.add(vectors)
        generation = uuid.uuid4().hex
        generations = self.settings.storage_dir / "generations"
        generations.mkdir(exist_ok=True)
        draft = Path(tempfile.mkdtemp(prefix=".build-", dir=generations))
        try:
            chunks_bytes = json.dumps(records, ensure_ascii=False).encode()
            index_bytes = faiss.serialize_index(index).tobytes()
            (draft / "chunks.json").write_bytes(chunks_bytes)
            (draft / "index.faiss").write_bytes(index_bytes)
            manifest = {
                "fingerprint": fingerprint,
                "files": hashes,
                "count": len(records),
                "chunks_sha256": _hash(chunks_bytes),
                "index_sha256": _hash(index_bytes),
            }
            manifest_bytes = json.dumps(manifest, sort_keys=True).encode()
            (draft / "manifest.json").write_bytes(manifest_bytes)
            draft.rename(generations / generation)
            pointer = {"generation": generation, "manifest_sha256": _hash(manifest_bytes)}
            pending = self.settings.storage_dir / f".active-{generation}.json"
            pending.write_text(json.dumps(pointer))
            os.replace(pending, self.settings.storage_dir / "active.json")
        finally:
            if draft.exists():
                shutil.rmtree(draft)
        return {
            "accepted": [name for name, _ in files],
            "skipped": skipped,
            "chunks": len(records),
            "generation": generation,
            "embedded": len(missing),
        }

    def search(self, query: str) -> list[Source]:
        if self.index is None:
            raise EveError("Index not loaded; restart after ingestion.", code="index_unavailable")
        vector = np.asarray(self.embedder.embed([query]), dtype=np.float32)
        faiss.normalize_L2(vector)
        scores, indices = self.index.search(
            vector, min(self.index.ntotal, self.settings.bot.top_k * 3)
        )
        results, seen, remaining = [], set(), self.settings.bot.context_chars
        for score, i in zip(scores[0], indices[0]):
            if i < 0 or score < self.settings.bot.min_score:
                continue
            record = self.records[i]
            if record["text_hash"] in seen:
                continue
            text = record["text"]
            if len(text) > remaining:
                continue
            seen.add(record["text_hash"])
            remaining -= len(text)
            results.append(
                Source(
                    id=record["id"],
                    name=record["name"],
                    page=record["page"],
                    text=text,
                    score=float(score),
                )
            )
            if len(results) >= self.settings.bot.top_k:
                break
        return results


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "--extract":
        try:
            print(json.dumps(_extract(Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]))))
        except Exception:
            sys.exit(1)
    else:
        sys.exit(2)
