import json
from backend.embeddings import LocalNomicIndex

class FakeIndex(LocalNomicIndex):
    def embed(self, texts):
        table = {
            "engineering scholarship": [1.0, 0.0, 0.0],
            "medical scholarship": [0.0, 1.0, 0.0],
            "engineering funding": [0.9, 0.1, 0.0],
            "engineering": [1.0, 0.0, 0.0],
            "medical": [0.0, 1.0, 0.0],
        }
        return [table.get(t, [0.5, 0.5, 0.0]) for t in texts]

def test_index_build_persists_and_reloads(tmp_path):
    corpus = ["engineering scholarship", "medical scholarship"]
    first = FakeIndex(model="nomic-test", index_dir=str(tmp_path))
    result = first.ensure(corpus)
    assert result["rebuilt"] is True
    assert (tmp_path / "metadata.json").exists()
    assert (tmp_path / "vectors.json").exists()

    second = FakeIndex(model="nomic-test", index_dir=str(tmp_path))
    loaded = second.ensure(corpus)
    assert loaded["rebuilt"] is False
    assert second.texts == corpus
    assert second.search("engineering", 1)[0][0] == 0

def test_changed_corpus_triggers_rebuild(tmp_path):
    first = FakeIndex(model="nomic-test", index_dir=str(tmp_path))
    first.ensure(["engineering scholarship", "medical scholarship"])
    second = FakeIndex(model="nomic-test", index_dir=str(tmp_path))
    result = second.ensure(["engineering funding", "medical scholarship"])
    assert result["rebuilt"] is True
    assert second.texts[0] == "engineering funding"

def test_model_change_never_reuses_old_vectors(tmp_path):
    FakeIndex(model="nomic-v1", index_dir=str(tmp_path)).ensure(["engineering scholarship"])
    second = FakeIndex(model="nomic-v2", index_dir=str(tmp_path))
    assert second.load(["engineering scholarship"]) is False
    assert second.ensure(["engineering scholarship"])["rebuilt"] is True

def test_empty_corpus_rejected(tmp_path):
    index = FakeIndex(index_dir=str(tmp_path))
    try:
        index.build([])
    except ValueError as exc:
        assert "empty corpus" in str(exc)
    else:
        raise AssertionError("empty corpus should be rejected")
