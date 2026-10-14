import io
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# isolate the database/uploads for the whole test session BEFORE importing the app
_TMP = tempfile.mkdtemp(prefix="tm_test_")
os.environ["TM_DATA_DIR"] = _TMP

import pytest  # noqa: E402

SAMPLES = Path(__file__).parent / "samples"


def make_pdf(text: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for line in text.split("\n"):
        c.drawString(40, y, line[:110])
        y -= 14
        if y < 40:
            c.showPage()
            y = 800
    c.save()
    return buf.getvalue()


def make_docx(text: str) -> bytes:
    import docx
    d = docx.Document()
    for line in text.split("\n"):
        d.add_paragraph(line)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


@pytest.fixture(scope="session")
def jd_text():
    return (SAMPLES / "jd_python.txt").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def resume_a():
    return (SAMPLES / "resume_a.txt").read_text(encoding="utf-8")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A fresh, empty database and upload folder for every test (tests must not see each other's resumes)."""
    from talentmatch import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "talentmatch.db")
    from talentmatch.web import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()
