import hashlib
import re

import numpy as np
import pytest
from filelock import FileLock

from eve_ah.config import BotConfig, Settings
from eve_ah.knowledge import Knowledge
from eve_ah.models import EveError


class FakeEmbedder:
    fingerprint = {"model": "fixture", "revision": "1", "dimension": 32, "tokenizer": "words"}

    def __init__(self):
        self.calls = []

    def chunk(self, text, tokens, overlap):
        words = text.split()
        return [" ".join(words[i : i + tokens]) for i in range(0, len(words), tokens - overlap)]

    def embed(self, texts):
        self.calls.extend(texts)
        rows = []
        for text in texts:
            v = np.zeros(32, dtype=np.float32)
            for word in re.findall(r"\w+", text.lower()):
                v[int(hashlib.sha256(word.encode()).hexdigest()[:8], 16) % 32] += 1
            v /= max(np.linalg.norm(v), 1)
            rows.append(v)
        return np.array(rows, dtype=np.float32)


@pytest.fixture
def settings(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    return Settings(data_dir=data, storage_dir=tmp_path / "storage", bot=BotConfig(min_score=0))


def test_ingest_search_reuse_and_delete(settings):
    file = settings.data_dir / "policy.md"
    file.write_text("Refunds are available within fourteen days.")
    embedder = FakeEmbedder()
    kb = Knowledge(settings, embedder)
    first = kb.ingest()
    assert first["accepted"] == ["policy.md"]
    assert first["chunks"] == 1
    kb.load()
    hit = kb.search("refunds")[0]
    assert hit.name == "policy.md"
    assert "fourteen" in hit.text
    assert hit.id.startswith("c-")
    embedder.calls.clear()
    kb.ingest()
    assert embedder.calls == []
    file.write_text("Refunds are available within thirty days.")
    kb.ingest()
    kb.load()
    assert "thirty" in kb.search("refunds")[0].text
    file.unlink()
    report = kb.ingest()
    assert report["chunks"] == 0
    with pytest.raises(EveError, match="No documents"):
        kb.load()


def test_ingestion_builds_source_linked_topic_catalog(settings):
    (settings.data_dir / "returns.md").write_text(
        "# Returns and refunds\n\nUnused products can be returned within 30 days."
    )
    kb = Knowledge(settings, FakeEmbedder())
    kb.ingest()
    kb.load()
    overview = kb.overview()
    assert overview["topics"][0]["name"] == "Returns and refunds"
    assert overview["topics"][0]["sources"] == ["returns.md"]
    assert overview["topics"][0]["source_ids"][0].startswith("c-")
    assert "Unused products" in overview["topics"][0]["description"]


def test_configured_catalog_and_questions_are_validated(settings):
    from eve_ah.config import TopicConfig

    (settings.data_dir / "returns.md").write_text("# Returns\n\nReturn facts.")
    settings.bot.topics = [
        TopicConfig(name="Shop policies", description="Returns and refunds", sources=["returns.md"])
    ]
    settings.bot.suggested_questions = ["What is the return window?"]
    kb = Knowledge(settings, FakeEmbedder())
    kb.ingest()
    kb.load()
    assert kb.overview()["suggested_questions"] == ["What is the return window?"]
    settings.bot.topics[0].sources = ["missing.md"]
    with pytest.raises(EveError, match="unknown source"):
        kb.ingest()


def test_catalog_config_change_requires_reingestion(settings):
    (settings.data_dir / "returns.md").write_text("# Returns\n\nReturn facts.")
    settings.bot.suggested_questions = ["What is the return window?"]
    kb = Knowledge(settings, FakeEmbedder())
    kb.ingest()
    settings.bot.suggested_questions = ["Can I return an item?"]
    with pytest.raises(EveError, match="incompatible"):
        kb.load()
    kb.ingest()
    kb.load()
    assert kb.overview()["suggested_questions"] == ["Can I return an item?"]


def test_deleted_document_removes_catalog_topic(settings):
    returns = settings.data_dir / "returns.md"
    returns.write_text("# Returns\n\nReturn facts.")
    shipping = settings.data_dir / "shipping.md"
    shipping.write_text("# Shipping\n\nShipping facts.")
    kb = Knowledge(settings, FakeEmbedder())
    kb.ingest()
    shipping.unlink()
    kb.ingest()
    kb.load()
    assert [topic["name"] for topic in kb.overview()["topics"]] == ["Returns"]


def test_failed_file_keeps_previous_generation(settings):
    (settings.data_dir / "good.txt").write_text("Useful facts about returns.")
    kb = Knowledge(settings, FakeEmbedder())
    old = kb.ingest()["generation"]
    (settings.data_dir / "bad.pdf").write_bytes(b"not a pdf")
    with pytest.raises(EveError):
        kb.ingest()
    assert (settings.storage_dir / "active.json").read_text().find(old) >= 0
    kb.load()
    assert kb.search("returns")[0].name == "good.txt"


def test_incompatible_embedding_rejected(settings):
    (settings.data_dir / "facts.txt").write_text("Useful facts.")
    kb = Knowledge(settings, FakeEmbedder())
    kb.ingest()
    other = FakeEmbedder()
    other.fingerprint = {**other.fingerprint, "revision": "2"}
    with pytest.raises(EveError, match="incompatible"):
        Knowledge(settings, other).load()


def test_missing_folder_does_not_erase_index(settings):
    kb = Knowledge(settings, FakeEmbedder())
    settings.data_dir.rmdir()
    with pytest.raises(EveError, match="data directory"):
        kb.ingest()


def test_reject_symlink_and_oversized_file(settings, tmp_path):
    external = tmp_path / "private.txt"
    external.write_text("private")
    (settings.data_dir / "link.txt").symlink_to(external)
    kb = Knowledge(settings, FakeEmbedder())
    with pytest.raises(EveError, match="Symlinks"):
        kb.ingest()
    (settings.data_dir / "link.txt").unlink()
    settings.max_file_bytes = 3
    (settings.data_dir / "large.txt").write_text("too long")
    with pytest.raises(EveError, match="size limit"):
        kb.ingest()


def test_single_writer_lock(settings):
    settings.storage_dir.mkdir()
    with FileLock(str(settings.storage_dir / "writer.lock")):
        with pytest.raises(EveError, match="already running"):
            Knowledge(settings, FakeEmbedder()).ingest()


def test_empty_supported_file_aborts(settings):
    (settings.data_dir / "empty.md").write_text("   ")
    with pytest.raises(EveError, match="extract"):
        Knowledge(settings, FakeEmbedder()).ingest()


def test_unsupported_file_reported(settings):
    (settings.data_dir / "image.png").write_bytes(b"png")
    report = Knowledge(settings, FakeEmbedder()).ingest()
    assert report["skipped"] == ["image.png"]


def test_docx_and_pdf_metadata(settings):
    from docx import Document
    from pypdf import PdfWriter

    doc = Document()
    doc.add_paragraph("Delivery takes three business days.")
    doc.save(settings.data_dir / "delivery.docx")
    # Blank/image-only PDF must be reported as requiring OCR, never activated silently.
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(settings.data_dir / "scan.pdf")
    kb = Knowledge(settings, FakeEmbedder())
    with pytest.raises(EveError, match="extract"):
        kb.ingest()
    (settings.data_dir / "scan.pdf").unlink()
    kb.ingest()
    kb.load()
    assert kb.search("delivery")[0].name == "delivery.docx"


def test_retrieval_score_and_context_limits(settings):
    (settings.data_dir / "facts.txt").write_text("refund policy " * 1000)
    kb = Knowledge(settings, FakeEmbedder())
    kb.ingest()
    kb.load()
    settings.bot.context_chars = 1000
    result = kb.search("refund")
    assert sum(len(s.text) for s in result) <= 1000
    settings.bot.min_score = 1
    assert kb.search("unrelated subject") == []


def test_hybrid_search_recovers_exact_identifier_missed_by_dense_rank(settings):
    class DenseBiasEmbedder(FakeEmbedder):
        def embed(self, texts):
            rows = []
            for text in texts:
                vector = np.zeros(32, dtype=np.float32)
                if "SKU-42" in text and "warranty" in text:
                    vector[1] = 1
                else:
                    vector[0] = 1
                rows.append(vector)
            return np.array(rows, dtype=np.float32)

    settings.bot.top_k = 1
    (settings.data_dir / "general.md").write_text("Generic shopping help and overview.")
    (settings.data_dir / "codes.md").write_text("Product SKU-42 warranty lasts two years.")
    kb = Knowledge(settings, DenseBiasEmbedder())
    kb.ingest()
    kb.load()
    assert kb.search("SKU-42", mode="dense")[0].name == "general.md"
    result = kb.search("SKU-42", mode="hybrid")
    assert result[0].name == "codes.md"
    assert result[0].score > 0


def test_lexical_index_checksum_is_verified(settings):
    (settings.data_dir / "facts.txt").write_text("Useful exact-term facts.")
    kb = Knowledge(settings, FakeEmbedder())
    report = kb.ingest()
    folder = settings.storage_dir / "generations" / report["generation"]
    (folder / "lexical.json").write_text("{}")
    with pytest.raises(EveError, match="damaged"):
        kb.load()


def test_pdf_page_reference(settings):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 20 250 Td (Warranty lasts twelve months.) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(settings.data_dir / "warranty.pdf")
    kb = Knowledge(settings, FakeEmbedder())
    kb.ingest()
    kb.load()
    hit = kb.search("warranty")[0]
    assert hit.page == 1
    assert "twelve months" in hit.text


def test_corrupt_index_is_rejected(settings):
    (settings.data_dir / "facts.txt").write_text("Useful facts.")
    kb = Knowledge(settings, FakeEmbedder())
    report = kb.ingest()
    (settings.storage_dir / "generations" / report["generation"] / "index.faiss").write_bytes(
        b"bad"
    )
    with pytest.raises(EveError, match="damaged"):
        kb.load()


def test_parsing_timeout_is_actionable(settings, monkeypatch):
    import subprocess

    (settings.data_dir / "slow.txt").write_text("Useful facts.")

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("parser", 30)

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(EveError, match="extract"):
        Knowledge(settings, FakeEmbedder()).ingest()
    assert not (settings.storage_dir / "active.json").exists()


def test_token_windows_preserve_text_and_overlap():
    from eve_ah.knowledge import LocalEmbedder

    class Tokenizer:
        def __call__(self, text, **kwargs):
            return {"offset_mapping": [m.span() for m in re.finditer(r"\S+", text)]}

    embedder = object.__new__(LocalEmbedder)
    embedder.tokenizer = Tokenizer()
    embedder.limit = 20
    text = " ".join(f"word{i}" for i in range(45))
    chunks = embedder.chunk(text, 20, 4)
    assert all(len(c.split()) <= 20 for c in chunks)
    assert chunks[0].split()[-4:] == chunks[1].split()[:4]
    assert "word44" in chunks[-1]
    with pytest.raises(EveError, match="settings"):
        embedder.chunk(text, 21, 4)


def test_interrupted_activation_keeps_previous_generation(settings, monkeypatch):
    import os

    path = settings.data_dir / "facts.txt"
    path.write_text("The warranty is twelve months.")
    kb = Knowledge(settings, FakeEmbedder())
    before = kb.ingest()["generation"]
    path.write_text("The warranty is twenty four months.")

    def fail_replace(*args):
        raise OSError("simulated interrupted activation")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError):
        kb.ingest()
    kb.load()
    assert kb.generation == before
    assert "twelve" in kb.search("warranty")[0].text


def test_traversal_failure_preserves_index(settings, monkeypatch):
    (settings.data_dir / "facts.txt").write_text("Returns within thirty days.")
    kb = Knowledge(settings, FakeEmbedder())
    kb.ingest()
    pointer = (settings.storage_dir / "active.json").read_bytes()

    def denied_walk(root, *, followlinks, onerror):
        onerror(PermissionError("unreadable directory"))
        return iter(())

    monkeypatch.setattr("eve_ah.knowledge.os.walk", denied_walk)
    with pytest.raises(EveError, match="permissions"):
        kb.ingest()
    assert (settings.storage_dir / "active.json").read_bytes() == pointer
    kb.load()
    assert kb.search("returns")[0].name == "facts.txt"
