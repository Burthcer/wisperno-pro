"""Old build/installer versions are pruned; the newest two and everything else stay.

Run: python tests/test_prune_builds.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from prune_builds import prune  # noqa: E402


def test_keeps_newest_two() -> None:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for v in ("1.0.0", "1.3.0", "1.4.0", "1.10.0"):
            (root / f"v{v}").mkdir()
            (root / f"WispernoPro-Setup-v{v}.exe").write_bytes(b"x")
            (root / f"WispernoPro-Setup-v{v}-1.bin").write_bytes(b"x")
        (root / "README-INSTALL.txt").write_text("keep me")
        (root / "notes").mkdir()
        gone = {p.name for p in prune(root)}
        assert gone == {f"{n}{v}{s}" for v in ("1.0.0", "1.3.0") for n, s in (("v", ""), ("WispernoPro-Setup-v", ".exe"), ("WispernoPro-Setup-v", "-1.bin"))}, gone
        assert sorted(p.name for p in root.iterdir() if p.name.startswith("v")) == ["v1.10.0", "v1.4.0"]
        assert (root / "README-INSTALL.txt").exists() and (root / "notes").exists()
        assert prune(root, dry_run=True) == []
    print("PASS: only the newest two versions stay; other files untouched.")


if __name__ == "__main__":
    test_keeps_newest_two()
