from te_mailer.core.htmlutil import build_email_html, extract_inline_images
from te_mailer.core.signature import build_signature_html, normalized, social_url


def icons(kind, name):
    return f"https://icons.test/{kind}/{name}.png"


def test_defaults_contain_travel_essence_details():
    html = build_signature_html({}, icons)
    assert 'href="mailto:sales.marketing@travelessence.mv"' in html
    assert 'href="tel:+9607978580"' in html
    assert "H.Finivairoalhi, 2nd Floor<br>Raivilla Magu, Henveiru" in html
    assert 'href="https://travelessence.mv"' in html and ">travelessence.mv</a>" in html
    assert "background-color:#2B2B2B" in html
    assert "/social/" not in html            # no social links configured yet


def test_social_urls():
    assert social_url("facebook", "travelessence") == "https://www.facebook.com/travelessence"
    assert social_url("instagram", "@travel.essence") == "https://www.instagram.com/travel.essence"
    assert social_url("whatsapp", "+960 797-8580") == "https://wa.me/9607978580"
    assert social_url("tiktok", "@travelessence") == "https://www.tiktok.com/@travelessence"
    assert social_url("linkedin", "https://www.linkedin.com/company/te") == "https://www.linkedin.com/company/te"
    assert social_url("x", "x.com/travelessence") == "https://x.com/travelessence"
    assert social_url("youtube", "") == ""


def test_hidden_fields_socials_logo_and_escaping():
    cfg = {"phone": "", "address": "", "name": "Aisha <Sales>", "theme": "light", "accent": "#0B7A8F",
           "socials": {"instagram": "@travelessence", "whatsapp": "+960 7978580"}}
    html = build_signature_html(cfg, icons, logo_src="https://icons.test/logo.png")
    assert "tel:" not in html and "maps" not in html
    assert "Aisha &lt;Sales&gt;" in html
    assert html.index("/social/instagram.png") < html.index("/social/whatsapp.png")
    assert 'href="https://wa.me/9607978580"' in html
    assert 'src="https://icons.test/logo.png"' in html and 'width="200"' in html
    assert "color:#0B7A8F" in html and "background-color:#FFFFFF" in html


def test_normalized_keeps_old_settings_working():
    cfg = normalized({"email": "x@y.mv", "socials": {"facebook": "te"}})
    assert cfg["email"] == "x@y.mv" and cfg["socials"]["facebook"] == "te" and cfg["socials"]["x"] == ""
    assert cfg["website"] == "travelessence.mv"


def test_signature_images_become_inline_attachments(tmp_path):
    icon = tmp_path / "email.png"
    icon.write_bytes(b"\x89PNG")
    url = "file:///" + str(icon).lstrip("/")
    doc = build_email_html("<html><body><p>Hello</p></body></html>",
                           build_signature_html({}, lambda kind, name: url))
    assert doc.index("Hello") < doc.index("sales.marketing@travelessence.mv")
    rewritten, images = extract_inline_images(doc)
    assert len(images) == 1 and "file:///" not in rewritten
