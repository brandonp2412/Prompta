import json

from prompta import web


def test_pwa_manifest_has_complete_metadata_and_served_assets() -> None:
    manifest = json.loads((web._STATIC_ROOT / "manifest.webmanifest").read_text(encoding="utf-8"))

    assert manifest["name"] == "Prompta Job Manager"
    assert manifest["short_name"] == "Prompta"
    assert manifest["id"] == "/"
    assert manifest["start_url"] == "/"
    assert manifest["scope"] == "/"
    assert manifest["display"] == "standalone"
    assert manifest["prefer_related_applications"] is False
    assert {"productivity", "utilities"} <= set(manifest["categories"])

    icons = manifest["icons"]
    assert any(icon["sizes"] == "192x192" and icon["purpose"] == "any" for icon in icons)
    assert any(icon["sizes"] == "512x512" and icon["purpose"] == "any" for icon in icons)
    assert any(icon["sizes"] == "512x512" and icon["purpose"] == "maskable" for icon in icons)

    assets = [icon["src"] for icon in icons]
    assets.extend(screenshot["src"] for screenshot in manifest["screenshots"])
    for source in assets:
        name = source.removeprefix("./")
        assert name in web._ALLOWED_STATIC
        assert (web._STATIC_ROOT / name).is_file()


def test_html_uses_png_touch_icon() -> None:
    html = (web._STATIC_ROOT / "index.html").read_text(encoding="utf-8")

    assert 'rel="apple-touch-icon" href="./apple-touch-icon.png"' in html
    assert 'rel="manifest" href="./manifest.webmanifest"' in html
