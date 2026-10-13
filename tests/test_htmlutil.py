from te_mailer.core.htmlutil import (
    build_email_html, extract_inline_images, html_to_text, is_blank_html, merge_into_signature,
    personalize,
)
from te_mailer.core.recipients import Recipient


def test_personalize_text_and_html():
    r = Recipient("sarah@x.com", "Sarah <Khan>")
    assert personalize("Hi {first_name} / { NAME } / {email}", r) == "Hi Sarah / Sarah <Khan> / sarah@x.com"
    assert personalize("<p>{name}</p>", r, is_html=True) == "<p>Sarah &lt;Khan&gt;</p>"


def test_personalize_fallback():
    r = Recipient("x@y.com", "")
    assert personalize("Dear {first_name},", r, "Valued Customer") == "Dear Valued Customer,"


def test_build_email_html_keeps_body_style():
    qt_html = ('<!DOCTYPE HTML><html><head><meta name="qrichtext" content="1" /></head>'
               '<body style=" font-family:\'Calibri\'; font-size:11pt;"><p>Hello</p></body></html>')
    out = build_email_html(qt_html)
    assert "qrichtext" not in out
    assert "<div style=\"font-family:'Calibri'; font-size:11pt;\"><p>Hello</p></div>" in out


def test_inline_images_become_cid(tmp_path):
    img = tmp_path / "banner.png"
    img.write_bytes(b"\x89PNG fake")
    html = f'<p><img src="file:///{str(img).lstrip("/")}" width="600" /></p><img src="https://x.com/a.png">'
    rewritten, images = extract_inline_images(html)
    assert len(images) == 1
    cid, path = images[0]
    assert path.endswith("banner.png")
    assert f'src="cid:{cid}"' in rewritten
    assert 'src="https://x.com/a.png"' in rewritten


def test_signature_merge():
    sig = '<html><body lang="EN-GB"><div>-- <br>Travel Essence</div></body></html>'
    out = merge_into_signature(sig, "<html><body><p>Hi</p></body></html>")
    assert out.index("<p>Hi</p>") < out.index("Travel Essence")


def test_text_fallback_and_blank():
    assert html_to_text("<p>Hello <a href='https://te.com'>site</a></p><ul><li>One</li></ul>") == \
        "Hello site (https://te.com)\n\n - One"
    assert is_blank_html("<html><body><p><br /></p></body></html>")
    assert not is_blank_html('<p><img src="x.png"></p>')
