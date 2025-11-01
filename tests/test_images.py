import importlib.util
from pathlib import Path

import pytest


def _load_module():
    repo_root = Path(__file__).resolve().parents[1]
    mod_path = repo_root / "httprint.py"
    spec = importlib.util.spec_from_file_location("httprint", mod_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader, "cannot load module spec"
    spec.loader.exec_module(mod)
    return mod


httprint = _load_module()


def test_convert_images_to_pdf_uses_safe_rotation(tmp_path, monkeypatch):
    handler = httprint.UploadHandler.__new__(httprint.UploadHandler)
    monkeypatch.setattr(httprint, "IMAGE_SUPPORT", True)

    captured = {}

    def fake_convert(files, *, layout_fun=None, rotation=None, **kwargs):
        captured["files"] = files
        captured["layout_fun"] = layout_fun
        captured["rotation"] = rotation
        return b"%PDF-1.4\n"

    monkeypatch.setattr(httprint.img2pdf, "convert", fake_convert)
    monkeypatch.setattr(httprint.img2pdf, "get_layout_fun", lambda _: object())

    img_path = tmp_path / "sample.jpg"
    img_path.write_bytes(b"not-really-an-image")
    out_pdf = tmp_path / "out.pdf"

    result = handler.convert_images_to_pdf([str(img_path)], str(out_pdf))

    assert result is True
    assert out_pdf.read_bytes() == b"%PDF-1.4\n"
    assert captured["rotation"] == httprint.img2pdf.Rotation.ifvalid
    assert captured["files"] == [str(img_path)]

    assert "layout_fun" in captured and captured["layout_fun"] is not None
