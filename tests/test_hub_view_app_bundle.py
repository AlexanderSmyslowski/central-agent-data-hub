from __future__ import annotations

from pathlib import Path


def test_hub_view_bundle_declares_german_localization() -> None:
    script = Path("script/build_and_run.sh").read_text(encoding="utf-8")

    assert "<key>CFBundleDevelopmentRegion</key>" in script
    assert "<string>de</string>" in script
    assert "<key>CFBundleLocalizations</key>" in script
