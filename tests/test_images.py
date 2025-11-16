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

if not getattr(httprint, 'IMAGE_SUPPORT', False) or not hasattr(httprint, 'img2pdf'):
    import pytest
    pytest.skip('image conversion dependencies not available', allow_module_level=True)



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

    # Create a fake portrait image (height > width)
    from PIL import Image
    img_path = tmp_path / "sample.jpg"
    portrait_img = Image.new('RGB', (100, 200), color='red')
    portrait_img.save(str(img_path))

    out_pdf = tmp_path / "out.pdf"

    success, has_rotated = handler.convert_images_to_pdf([str(img_path)], str(out_pdf))

    assert success is True
    assert has_rotated is False  # Portrait image should not be rotated
    assert out_pdf.read_bytes() == b"%PDF-1.4\n"
    assert captured["rotation"] == httprint.img2pdf.Rotation.ifvalid
    # Portrait image should not be rotated, so original path is used
    assert captured["files"] == [str(img_path)]

    assert "layout_fun" in captured and captured["layout_fun"] is not None


def test_convert_landscape_image_rotates_90_degrees(tmp_path, monkeypatch):
    """Test that landscape images (width > height) are rotated 90 degrees clockwise."""
    handler = httprint.UploadHandler.__new__(httprint.UploadHandler)
    monkeypatch.setattr(httprint, "IMAGE_SUPPORT", True)

    captured = {}
    rotated_image_data = {}

    def fake_convert(files, *, layout_fun=None, rotation=None, **kwargs):
        captured["files"] = files
        captured["layout_fun"] = layout_fun
        captured["rotation"] = rotation

        # Capture the rotated image data before it gets cleaned up
        from PIL import Image
        for f in files:
            if '_rotated' in f:
                with Image.open(f) as img:
                    rotated_image_data['size'] = img.size

        return b"%PDF-1.4\n"

    monkeypatch.setattr(httprint.img2pdf, "convert", fake_convert)
    monkeypatch.setattr(httprint.img2pdf, "get_layout_fun", lambda _: object())

    # Create a landscape image (width > height)
    from PIL import Image
    img_path = tmp_path / "landscape.jpg"
    landscape_img = Image.new('RGB', (400, 200), color='blue')
    landscape_img.save(str(img_path))

    out_pdf = tmp_path / "out.pdf"

    success, has_rotated = handler.convert_images_to_pdf([str(img_path)], str(out_pdf))

    assert success is True
    assert has_rotated is True  # Landscape image should be rotated
    assert out_pdf.read_bytes() == b"%PDF-1.4\n"

    # Landscape image should be rotated, so a temporary rotated file is used
    assert len(captured["files"]) == 1
    assert captured["files"][0].endswith('_rotated.jpg')

    # Verify the rotated image has swapped dimensions (200x400 instead of 400x200)
    assert rotated_image_data['size'] == (200, 400)  # width and height swapped


def test_convert_portrait_image_not_rotated(tmp_path, monkeypatch):
    """Test that portrait images (height >= width) are not rotated."""
    handler = httprint.UploadHandler.__new__(httprint.UploadHandler)
    monkeypatch.setattr(httprint, "IMAGE_SUPPORT", True)

    captured = {}

    def fake_convert(files, *, layout_fun=None, rotation=None, **kwargs):
        captured["files"] = files
        return b"%PDF-1.4\n"

    monkeypatch.setattr(httprint.img2pdf, "convert", fake_convert)
    monkeypatch.setattr(httprint.img2pdf, "get_layout_fun", lambda _: object())

    # Create a portrait image (height > width)
    from PIL import Image
    img_path = tmp_path / "portrait.jpg"
    portrait_img = Image.new('RGB', (200, 400), color='green')
    portrait_img.save(str(img_path))

    out_pdf = tmp_path / "out.pdf"

    success, has_rotated = handler.convert_images_to_pdf([str(img_path)], str(out_pdf))

    assert success is True
    assert has_rotated is False  # Portrait image should not be rotated
    # Portrait image should use original path (not rotated)
    assert captured["files"] == [str(img_path)]


def test_convert_square_image_not_rotated(tmp_path, monkeypatch):
    """Test that square images (width == height) are not rotated."""
    handler = httprint.UploadHandler.__new__(httprint.UploadHandler)
    monkeypatch.setattr(httprint, "IMAGE_SUPPORT", True)

    captured = {}

    def fake_convert(files, *, layout_fun=None, rotation=None, **kwargs):
        captured["files"] = files
        return b"%PDF-1.4\n"

    monkeypatch.setattr(httprint.img2pdf, "convert", fake_convert)
    monkeypatch.setattr(httprint.img2pdf, "get_layout_fun", lambda _: object())

    # Create a square image (width == height)
    from PIL import Image
    img_path = tmp_path / "square.jpg"
    square_img = Image.new('RGB', (300, 300), color='yellow')
    square_img.save(str(img_path))

    out_pdf = tmp_path / "out.pdf"

    success, has_rotated = handler.convert_images_to_pdf([str(img_path)], str(out_pdf))

    assert success is True
    assert has_rotated is False  # Square image should not be rotated
    # Square image should use original path (not rotated)
    assert captured["files"] == [str(img_path)]


def test_convert_mixed_orientations(tmp_path, monkeypatch):
    """Test converting multiple images with mixed orientations."""
    handler = httprint.UploadHandler.__new__(httprint.UploadHandler)
    monkeypatch.setattr(httprint, "IMAGE_SUPPORT", True)

    captured = {}

    def fake_convert(files, *, layout_fun=None, rotation=None, **kwargs):
        captured["files"] = files
        return b"%PDF-1.4\n"

    monkeypatch.setattr(httprint.img2pdf, "convert", fake_convert)
    monkeypatch.setattr(httprint.img2pdf, "get_layout_fun", lambda _: object())

    # Create images with different orientations
    from PIL import Image

    portrait_path = tmp_path / "portrait.jpg"
    portrait_img = Image.new('RGB', (200, 400), color='red')
    portrait_img.save(str(portrait_path))

    landscape_path = tmp_path / "landscape.jpg"
    landscape_img = Image.new('RGB', (400, 200), color='blue')
    landscape_img.save(str(landscape_path))

    square_path = tmp_path / "square.jpg"
    square_img = Image.new('RGB', (300, 300), color='green')
    square_img.save(str(square_path))

    out_pdf = tmp_path / "out.pdf"

    success, has_rotated = handler.convert_images_to_pdf(
        [str(portrait_path), str(landscape_path), str(square_path)],
        str(out_pdf)
    )

    assert success is True
    assert has_rotated is True  # At least one image (landscape) was rotated
    assert len(captured["files"]) == 3

    # First image (portrait) should not be rotated
    assert captured["files"][0] == str(portrait_path)

    # Second image (landscape) should be rotated
    assert captured["files"][1].endswith('_rotated.jpg')

    # Third image (square) should not be rotated
    assert captured["files"][2] == str(square_path)
