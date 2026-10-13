from openpyxl import Workbook

from te_mailer.core.recipients import (
    Recipient, is_suppressed, is_valid_email, merge, parse_file, parse_suppression, parse_text,
)


def emails(result):
    return [r.email for r in result.recipients]


def test_parse_mixed_text():
    text = """Sarah Khan <Sarah.Khan@Gmail.com>
    john@outlook.com, John Smith
    maria@hotmail.com; leo@icloud.com
    "Ali Raza" <ali.raza@yahoo.com>
    sarah.khan@gmail.com
    not-an-email
    broken@domain
    """
    result = parse_text(text)
    assert emails(result) == ["sarah.khan@gmail.com", "john@outlook.com", "maria@hotmail.com",
                              "leo@icloud.com", "ali.raza@yahoo.com"]
    names = {r.email: r.name for r in result.recipients}
    assert names["sarah.khan@gmail.com"] == "Sarah Khan"
    assert names["john@outlook.com"] == "John Smith"
    assert names["ali.raza@yahoo.com"] == "Ali Raza"
    assert names["maria@hotmail.com"] == ""
    assert result.duplicates == 1
    assert "broken@domain" in result.invalid


def test_validation():
    assert is_valid_email("a.b+tag@sub.example.co.uk")
    assert not is_valid_email("a..b@example.com")
    assert not is_valid_email(".a@example.com")
    assert not is_valid_email("a@example")
    assert not is_valid_email("a@-example.com")


def test_csv_with_headers(tmp_path):
    path = tmp_path / "customers.csv"
    path.write_text("First Name;Last Name;E-mail;Phone\nSarah;Khan;sarah@x.com;123\n"
                    "John;;JOHN@x.com;456\n;;bad@;0\n", encoding="utf-8")
    result = parse_file(path)
    assert [(r.email, r.name) for r in result.recipients] == [("sarah@x.com", "Sarah Khan"),
                                                              ("john@x.com", "John")]


def test_xlsx_import(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.append(["Customer Name", "Email Address"])
    ws.append(["Leo Messi", "leo@example.com"])
    ws.append([None, "maria@example.com"])
    path = tmp_path / "list.xlsx"
    wb.save(path)
    result = parse_file(path)
    assert [(r.email, r.name) for r in result.recipients] == [("leo@example.com", "Leo Messi"),
                                                              ("maria@example.com", "")]


def test_csv_without_headers(tmp_path):
    path = tmp_path / "plain.csv"
    path.write_text("Sarah,sarah@x.com\nleo@y.com\n", encoding="utf-8")
    assert emails(parse_file(path)) == ["sarah@x.com", "leo@y.com"]


def test_merge_fills_missing_names():
    existing = [Recipient("a@x.com", "")]
    merged, added, dupes = merge(existing, [Recipient("a@x.com", "Ann"), Recipient("b@x.com", "")])
    assert (added, dupes) == (1, 1)
    assert merged[0].name == "Ann"


def test_suppression_by_address_and_domain():
    entries = parse_suppression("stop@x.com\n@competitor.com, other.org")
    assert is_suppressed("STOP@x.com", entries)
    assert is_suppressed("anyone@competitor.com", entries)
    assert is_suppressed("me@other.org", entries)
    assert not is_suppressed("ok@x.com", entries)


def test_first_and_last_name():
    r = Recipient("a@x.com", "Sarah Jane Khan")
    assert r.first_name == "Sarah"
    assert r.last_name == "Khan"
