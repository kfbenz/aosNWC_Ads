# Copyright 2026 Archdiocese of Seattle
# Author: Kevin F Benz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Smoke tests for NWC Ads against an in-memory SQLite copy of the Access exports.

Needs the Access CSV exports in exports/access_csv/ (not in git; see docs/developer-guide.md).

Usage, from the repository root:
    python tests/smoke_test.py

Prints PASS or FAIL for each check and exits with status 1 if any check fails.
"""
import csv
import json
import os
import re
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urlparse

PROJECT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["AUTH_MODE"] = "dev"
sys.path.insert(0, PROJECT)

from flask import g  # noqa: E402
from sqlalchemy import Integer, select  # noqa: E402

from config import Config  # noqa: E402
import app.auth as auth_module  # noqa: E402
from app import create_app  # noqa: E402
from app.audit import AuditLog  # noqa: E402
from app.auth import CurrentUser  # noqa: E402
from app.extensions import db  # noqa: E402
from app.target_models import Account, AdPlacement  # noqa: E402

CSV_DIR = os.path.join(PROJECT, "exports", "access_csv")
failures = []


def check(label, cond):
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        failures.append(label)


# ---------------------------------------------------------------- data loading
def blank(v):
    v = (v or "").strip()
    return v or None


def parse_date(v):
    v = blank(v)
    if not v:
        return None
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            pass
    return None


def parse_dec(v, lo=None, hi=None):
    v = blank(v)
    if v is None:
        return None
    try:
        d = Decimal(v)
    except InvalidOperation:
        return None
    if lo is not None and not (lo <= d <= hi):
        return None
    return d


def truthy(v):
    return (v or "").strip().upper() in ("TRUE", "YES", "Y", "1", "-1")


# SQLite only auto-increments INTEGER PRIMARY KEY, not BIGINT; test-only adjustment.
AdPlacement.__table__.c.id.type = Integer()
AuditLog.__table__.c.id.type = Integer()
from app.target_models import AdNormalizationMap, AdSection, AdSize, BillingStatus, SalesRep  # noqa: E402
for _m in (AdNormalizationMap, AdSection, AdSize, BillingStatus, SalesRep):
    _m.__table__.c.id.type = Integer()


def load_data(app, ad_limit=None):
    with app.app_context():
        db.create_all()
        with open(os.path.join(CSV_DIR, "tbl_ProgressContacts_01.csv"), encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                acct = blank(r["AccountNumber"])
                if not acct:
                    continue
                db.session.add(Account(
                    account_number=acct[:6], advertiser=blank(r["Advertiser"]), contact_name=blank(r["Contact"]),
                    address1=blank(r["Address"]), address2=blank(r["Address2"]), city=blank(r["City"]),
                    state_code=blank(r["State"]), postal_code=blank(r["Zip"]), phone=blank(r["Phone"]),
                    email=blank(r["Email"]), category=blank(r["Category"]), is_email_list=truthy(r["EmailList"]),
                    fax=blank(r["Fax"]), website=blank(r["Website"]), ad_ops=blank(r["AdOps"]),
                    contact_notes=blank(r["ConNotes"]),
                    directory_years=blank(r["DirectoryYears"]), is_current_advertiser=truthy(r["CurrentAdvertiser"]),
                    is_past_advertiser=truthy(r["PastAdvertiser"]), is_prospect=truthy(r["Prospect"]),
                ))
        db.session.flush()
        known = {a for (a,) in db.session.query(Account.account_number)}
        with open(os.path.join(CSV_DIR, "tbl_ProgressAds_01.csv"), encoding="utf-8-sig", newline="") as f:
            for i, r in enumerate(csv.DictReader(f)):
                if ad_limit and i >= ad_limit:
                    break
                legacy = blank(r["AccountNumber"])
                legacy = legacy[:6] if legacy else None
                db.session.add(AdPlacement(
                    legacy_account_number=legacy, account_number=legacy if legacy in known else None,
                    commission_percent=parse_dec(r["CommissionPercent"], Decimal(0), Decimal(1)),
                    date_sold=parse_date(r["DateSold"]), date_run=parse_date(r["DateRun"]),
                    description=blank(r["Description"]), authorized_by=blank(r["AuthorizedBy"]),
                    sales_rep_raw=blank(r["Sales"]), amount=parse_dec(r["Amount"]),
                    size_raw=blank(r["Size"]), section_raw=blank(r["Section"]), ad_page=blank(r["AdPage"]),
                    run_code=blank(r["Run #"]), bill_number=blank(r["BillNumber"]),
                    billed_raw=blank(r["Billed"]), ad_notes=blank(r["AdNotes"]),
                ))
        db.session.commit()
        # The bulk load is not user activity; clear what the audit listener recorded.
        db.session.execute(AuditLog.__table__.delete())
        db.session.commit()


# ================================================================ DEV MODE
class DevConfig(Config):
    TESTING = True
    AUTH_MODE = "dev"
    DEV_ROLE = "Admin"
    SESSION_COOKIE_SECURE = False
    WTF_CSRF_ENABLED = False  # CSRF is tested separately in Entra mode


print("== Dev mode (full data)")
dev_app = create_app(DevConfig)
load_data(dev_app)
client = dev_app.test_client()

with dev_app.app_context():
    orphan_id = db.session.scalar(select(AdPlacement.id).where(AdPlacement.account_number.is_(None)).limit(1))
    linked = db.session.scalars(select(AdPlacement).where(AdPlacement.account_number.is_not(None)).limit(1)).first()
    linked_id = linked.id
    sample_word = linked.account.advertiser.split()[0]


def get(c, url):
    resp = c.get(url)
    return resp.status_code, resp.get_data(as_text=True), resp


status, html, _ = get(client, "/")
check("index 200", status == 200)
check("index shows all 11,868 ads", "<strong>11,868</strong> ads" in html)
check("index total $4,720,332.27", "$4,720,332.27" in html)
check("index shows 50 rows", html.count('href="/ads/') == 50)
check("dev banner shown", "Development mode" in html)
check("menu: Ads link active", re.search(r'<li class="active">\s*<a href="/">Ads</a>', html) is not None)
check("menu: Admin > Audit log is a live link", 'href="/admin/audit"' in html)
check("menu: no Admin item shows 'soon' any more", "<em>soon</em>" not in html)
check("menu: role badge shows Admin", 'class="role-badge">Admin<' in html)
check("csrf meta tag present", 'name="csrf-token"' in html)

status, html, _ = get(client, "/?rep=kh")
m = re.search(r"<strong>([\d,]+)</strong> ads", html)
check("rep=kh returns 9,852", m and m.group(1) == "9,852")

status, html, _ = get(client, "/?q=" + sample_word)
check("search finds results", status == 200 and "No ads match" not in html)

status, html, _ = get(client, f"/ads/{linked_id}")
check("detail linked 200", status == 200 and "<title>Ad #" in html)
status, html, _ = get(client, f"/ads/{orphan_id}")
check("detail orphan shows notice", status == 200 and "orphan" in html)
status, html, _ = get(client, "/ads/99999999")
check("missing ad 404 page", status == 404 and "Page not found" in html)

status, html, _ = get(client, "/healthz")
check("healthz ok", status == 200 and html == "ok")

# ---- audit trail
with dev_app.test_request_context():
    g.user = CurrentUser(oid="oid-123", name="Pat Editor", username="pat@example.org", role="Editor")
    ad = db.session.get(AdPlacement, linked_id)
    old_amount = ad.amount
    ad.amount = Decimal("123.45")
    ad.description = "Changed by test"
    db.session.commit()

    upd = db.session.scalars(select(AuditLog).order_by(AuditLog.id.desc())).first()
    changes = json.loads(upd.changes)
    check("audit: update row written", upd.action == "update" and upd.entity == "ad_placements" and upd.entity_id == str(linked_id))
    check("audit: update records user", upd.user_name == "pat@example.org" and upd.user_oid == "oid-123")
    check("audit: update records old and new amount", changes.get("amount") == [str(old_amount), "123.45"])
    check("audit: updated_by not in change list", "updated_by" not in changes)
    check("audit: updated_by stamped on row", db.session.get(AdPlacement, linked_id).updated_by == "pat@example.org")

    acct = Account(account_number="ZZ9999", advertiser="Test Advertiser")
    db.session.add(acct)
    db.session.commit()
    ins = db.session.scalars(select(AuditLog).order_by(AuditLog.id.desc())).first()
    check("audit: insert row written", ins.action == "insert" and ins.entity == "accounts" and ins.entity_id == "ZZ9999")
    check("audit: insert stamps created_by", acct.created_by == "pat@example.org")

    db.session.delete(acct)
    db.session.commit()
    dele = db.session.scalars(select(AuditLog).order_by(AuditLog.id.desc())).first()
    check("audit: delete row with snapshot", dele.action == "delete" and json.loads(dele.changes).get("advertiser") == "Test Advertiser")

    # No-op change should not create an audit row.
    before = db.session.scalar(select(db.func.count(AuditLog.id)))
    ad = db.session.get(AdPlacement, linked_id)
    ad.description = "Changed by test"
    db.session.commit()
    after = db.session.scalar(select(db.func.count(AuditLog.id)))
    check("audit: no row for unchanged value", before == after)

status, html, _ = get(client, "/admin/audit")
check("audit page lists changes", status == 200 and "pat@example.org" in html and "123.45" in html)

# ---- accounts
print("-- accounts")
status, html, _ = get(client, "/accounts/")
check("accounts list 200 with 827 accounts", status == 200 and "<strong>827</strong> accounts" in html)
check("menu: Accounts active", re.search(r'<li class="active">\s*<a href="/accounts/">Accounts</a>', html) is not None)
status, html, _ = get(client, "/accounts/?flag=email")
check("accounts flag=email shows 105", "<strong>105</strong> accounts" in html)
for sort in ("name", "number", "recent", "bogus"):
    status, _, _ = get(client, f"/accounts/?sort={sort}")
    check(f"accounts sort={sort} 200", status == 200)
status, html, _ = get(client, "/accounts/?q=" + sample_word)
check("accounts search finds sample advertiser", sample_word in html and "No accounts match" not in html)
status, html, _ = get(client, "/accounts/?page=9999")
check("accounts page past end clamps to last page", status == 200 and "Page 17 of 17" in html)

status, html, _ = get(client, "/accounts/new")
check("new account suggests next number 004017", status == 200 and 'value="004017"' in html)
keys = html.split('class="two-col record-keys"')[1].split("<fieldset>")[0]
check("new: key row has Account input on the left and Advertiser input on the right",
      'id="account_number"' in keys and 'id="advertiser"' in keys
      and keys.index('id="account_number"') < keys.index('id="advertiser"'))

form_base = {
    "account_number": "004017", "advertiser": "St. Test Parish", "contact_name": "Fr. Test",
    "city": "Seattle", "state_code": "WA", "is_current_advertiser": "y", "is_email_list": "y",
}
resp = client.post("/accounts/new", data=form_base)
check("create account redirects to its page", resp.status_code == 302 and resp.headers["Location"].endswith("/accounts/004017"))
with dev_app.app_context():
    acct = db.session.get(Account, "004017")
    check("account saved with flags", acct and acct.is_current_advertiser and acct.is_email_list and not acct.is_prospect)
    check("account created_by stamped", acct.created_by == "dev@localhost")

resp = client.post("/accounts/new", data=form_base)
check("duplicate account number rejected", resp.status_code == 200 and "already in use" in resp.get_data(as_text=True))
resp = client.post("/accounts/new", data={**form_base, "account_number": "AB-1"})
check("invalid account number rejected", "letters and digits only" in resp.get_data(as_text=True))
resp = client.post("/accounts/new", data={**form_base, "account_number": "zz0001", "advertiser": "  "})
check("blank advertiser rejected", resp.status_code == 200 and "field is required" in resp.get_data(as_text=True))
resp = client.post("/accounts/new", data={**form_base, "account_number": "zz0002"})
check("lowercase account number stored uppercase", resp.headers.get("Location", "").endswith("/accounts/ZZ0002"))
client.post("/accounts/ZZ0002/delete")  # remove the test account so later counts match the Access data

status, html, _ = get(client, "/accounts/004017")
check("account page shows form and empty history", status == 200 and "St. Test Parish" in html and "No ads for this account yet" in html)
check("heading: label and bold name",
      '<span class="record-kind">View and Edit Advertiser:</span>' in html
      and '<strong class="record-name">St. Test Parish</strong>' in html)
keys = html.split('class="two-col record-keys"')[1].split("<fieldset>")[0]
check("edit: key row has 'Account:' with the number, then 'Advertiser:' with its input",
      re.search(r'Account:</span>\s*<strong class="record-number">004017</strong>', keys) is not None
      and keys.index("Account:") < keys.index("Advertiser:")
      and 'id="advertiser"' in keys and 'value="St. Test Parish"' in keys)
check("section names: Contact Information and Customer Information",
      "<legend class=\"section-title\">Contact Information</legend>" in html and "<legend>Customer Information</legend>" in html
      and "Client Information" not in html)
contact = html.split("<legend class=\"section-title\">Contact Information</legend>")[1].split("</fieldset>")[0]
check("edit: Advertiser and Account no longer in the Contact section",
      'id="advertiser"' not in contact and 'id="account_number"' not in contact)
check("account number has no input box on edit", 'id="account_number"' not in html)
check("account page has a Billing Information section", "<legend class=\"section-title\">Billing Information</legend>" in html and 'id="billing_city"' in html)
right = html.split('<div class="fieldset-stack">')[1]
check("Billing Information is first in the right column, level with Contact Information",
      right.index("<legend class=\"section-title\">Billing Information</legend>") < right.index("<legend>Customer Information</legend>"))
first_left = re.search(r'<label class="([^"]*)"[^>]*>\s*<span[^>]*>([^<]*)', contact)
billing_part = right.split("</fieldset>")[0]
first_right = re.search(r'<label class="([^"]*)"[^>]*>\s*<span[^>]*>([^<]*)', billing_part)
check("first line: 'Name:' (left) and 'Billing Name:' (right), each label and box on one line",
      first_left and first_left.group(2).strip() == "Name:" and "inline-field" in first_left.group(1)
      and first_right and first_right.group(2).strip() == "Billing Name:" and "inline-field" in first_right.group(1)
      and 'id="contact_name"' in contact and 'id="billing_name"' in billing_part)
version = re.search(r'id="version" name="version" type="hidden" value="([^"]*)"', html).group(1)

resp = client.post("/accounts/004017", data={**form_base, "account_number": "999999", "city": "Tacoma", "version": version})
check("edit account redirects", resp.status_code == 302)
with dev_app.app_context():
    check("edit saved; account number unchanged", db.session.get(Account, "004017").city == "Tacoma" and db.session.get(Account, "999999") is None)
    upd = db.session.scalars(select(AuditLog).where(AuditLog.entity_id == "004017").order_by(AuditLog.id.desc())).first()
    check("account edit audited with old and new city", json.loads(upd.changes).get("city") == ["Seattle", "Tacoma"])

resp = client.post("/accounts/004017", data={**form_base, "city": "Spokane", "version": version}, follow_redirects=True)
with dev_app.app_context():
    check("stale edit blocked (someone else saved)", db.session.get(Account, "004017").city == "Tacoma"
          and "Someone else saved this account" in resp.get_data(as_text=True))

status, html, _ = get(client, "/accounts/004017")
version = re.search(r'id="version" name="version" type="hidden" value="([^"]*)"', html).group(1)
billing = {"billing_name": "Pat Treasurer", "billing_address1": "PO Box 2015", "billing_city": "Seattle",
           "billing_state_code": "WA", "billing_postal_code": "98104"}
resp = client.post("/accounts/004017", data={**form_base, "city": "Tacoma", **billing, "version": version})
with dev_app.app_context():
    acct = db.session.get(Account, "004017")
    check("billing name and address saved, contact kept",
          (acct.billing_name, acct.billing_address1, acct.billing_city, acct.billing_state_code, acct.billing_postal_code)
          == ("Pat Treasurer", "PO Box 2015", "Seattle", "WA", "98104")
          and acct.city == "Tacoma" and acct.contact_name == form_base.get("contact_name") and acct.billing_address2 is None)
    upd = db.session.scalars(select(AuditLog).where(AuditLog.entity_id == "004017").order_by(AuditLog.id.desc())).first()
    check("billing address change audited", json.loads(upd.changes).get("billing_city") == [None, "Seattle"])
status, html, _ = get(client, "/accounts/004017")
check("billing address shown after save", 'value="PO Box 2015"' in html)

status, html, _ = get(client, f"/accounts/{linked.account_number}")
check("existing account shows its ads with Edit links", status == 200 and f'/ads/{linked_id}/edit' in html)
check("prev/next navigation present", "Previous (" in html or "Next (" in html)

# ---- ads
print("-- ads")
status, html, _ = get(client, "/accounts/004017/ads/new")
check("new ad form 200 with suggestions", status == 200 and '<datalist id="dl-size">' in html and "KH" in html)
ad_form = {"date_sold": "2026-11-01", "date_run": "2026-12-01", "amount": "500.00", "commission_pct": "10",
           "sales_rep_raw": "KH", "size_raw": "1/4 pg", "section_raw": "G", "description": "Christmas greeting"}
resp = client.post("/accounts/004017/ads/new", data=ad_form)
check("add ad redirects to account", resp.status_code == 302 and resp.headers["Location"].endswith("/accounts/004017"))
with dev_app.app_context():
    new_ad = db.session.scalars(select(AdPlacement).where(AdPlacement.account_number == "004017")).first()
    check("ad saved; 10% stored as 0.1000", new_ad and new_ad.commission_percent == Decimal("0.1000"))
    check("ad legacy account number set", new_ad.legacy_account_number == "004017")
    new_ad_id = new_ad.id

resp = client.post("/accounts/004017/ads/new", data={**ad_form, "date_run": "3006-01-01"})
check("impossible year rejected", "between 1990 and 2100" in resp.get_data(as_text=True))
resp = client.post("/accounts/004017/ads/new", data={**ad_form, "commission_pct": "150"})
check("commission over 100% rejected", "Enter 0 to 100" in resp.get_data(as_text=True))
resp = client.post("/accounts/004017/ads/new", data={**ad_form, "amount": "abc"})
check("non-numeric amount rejected", resp.status_code == 200 and "Not a valid decimal" in resp.get_data(as_text=True))

status, html, _ = get(client, "/accounts/004017/ads/new")
check("new ad pre-fills commission and rep from last ad", 'value="10.00"' in html and 'value="KH"' in html)

status, html, _ = get(client, f"/ads/{new_ad_id}/edit")
check("edit ad shows commission as 10.00", status == 200 and re.search(r'id="commission_pct"[^>]*value="10.00"', html) is not None)
ad_version = re.search(r'id="version" name="version" type="hidden" value="([^"]*)"', html).group(1)
resp = client.post(f"/ads/{new_ad_id}/edit", data={**ad_form, "amount": "650.00", "version": ad_version})
with dev_app.app_context():
    check("edit ad saved", db.session.get(AdPlacement, new_ad_id).amount == Decimal("650.00"))
    upd = db.session.scalars(select(AuditLog).where(AuditLog.entity == "ad_placements", AuditLog.entity_id == str(new_ad_id)).order_by(AuditLog.id.desc())).first()
    check("ad edit audited", json.loads(upd.changes).get("amount") == ["500.00", "650.00"])
resp = client.post(f"/ads/{new_ad_id}/edit", data={**ad_form, "amount": "1.00", "version": ad_version})
with dev_app.app_context():
    check("stale ad edit blocked", db.session.get(AdPlacement, new_ad_id).amount == Decimal("650.00"))

status, html, _ = get(client, f"/ads/{orphan_id}/edit")
check("orphan ad can be edited", status == 200 and "orphan" in html)

resp = client.post("/accounts/004017/delete", follow_redirects=True)
with dev_app.app_context():
    check("account with ads cannot be deleted", db.session.get(Account, "004017") is not None
          and "cannot be deleted" in resp.get_data(as_text=True))
resp = client.post(f"/ads/{new_ad_id}/delete")
resp = client.post("/accounts/004017/delete")
with dev_app.app_context():
    check("ad then account deleted", db.session.get(AdPlacement, new_ad_id) is None and db.session.get(Account, "004017") is None)
    dels = db.session.scalars(select(AuditLog.entity).where(AuditLog.action == "delete")).all()
    check("deletes audited", "ad_placements" in dels and dels.count("accounts") >= 2)

status, html, _ = get(client, f"/ads/{linked_id}")
check("ad detail has Edit and account links", f"/ads/{linked_id}/edit" in html and "Open account" in html)

# ---- reports (expected values computed independently from the CSV exports)
print("-- reports")
import io as _io  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

with open(os.path.join(CSV_DIR, "tbl_ProgressAds_01.csv"), encoding="utf-8-sig", newline="") as fh:
    csv_ads = list(csv.DictReader(fh))
with open(os.path.join(CSV_DIR, "tbl_ProgressContacts_01.csv"), encoding="utf-8-sig", newline="") as fh:
    csv_contacts = list(csv.DictReader(fh))

def money(d):
    return "${:,.2f}".format(d)

# Commission: calendar 2025 by sell date, commission > 0
from datetime import date as _date  # noqa: E402
exp = [(parse_dec(r["Amount"]) or Decimal(0), parse_dec(r["CommissionPercent"], Decimal(0), Decimal(1)) or Decimal(0))
       for r in csv_ads
       if (ds := parse_date(r["DateSold"])) and _date(2025, 1, 1) <= ds <= _date(2025, 12, 31)
       and (parse_dec(r["CommissionPercent"], Decimal(0), Decimal(1)) or 0) > 0]
exp_amount = sum(a for a, _ in exp)
exp_earned = sum(a * p for a, p in exp)
status, html, _ = get(client, "/reports/commission?start=2025-01-01&end=2025-12-31")
check(f"commission 2025: {len(exp)} ads", status == 200 and f"{len(exp)} ads" in html)
check(f"commission 2025 total {money(exp_amount)}", money(exp_amount) in html)
check(f"commission 2025 earned {money(exp_earned)}", money(exp_earned) in html)
check("commission has per-date subtotals", html.count('class="subtotal"') >= 1)
status, html, _ = get(client, "/reports/commission")
check("commission form defaults to previous month", status == 200 and 'name="start" value="' in html and "Commission Report for" not in html)
resp = client.get("/reports/commission?start=2025-01-01&end=2025-12-31&format=csv")
body = resp.get_data()
check("commission CSV download with BOM", resp.status_code == 200 and body.startswith(b"\xef\xbb\xbf") and b"Comm Earned" in body
      and "attachment" in resp.headers["Content-Disposition"])
status, html, _ = get(client, "/reports/commission?start=2025-12-31&end=2025-01-01")
check("commission swaps reversed dates", money(exp_amount) in html)

# Publication: the busiest run date
from collections import Counter  # noqa: E402
busiest, busiest_n = Counter(parse_date(r["DateRun"]) for r in csv_ads if parse_date(r["DateRun"])).most_common(1)[0]
status, html, _ = get(client, f"/reports/publication?date={busiest.isoformat()}")
check(f"publication {busiest}: {busiest_n} ads", status == 200 and f"{busiest_n} ads" in html)
check("publication numbered to last line", f'<td class="num">{busiest_n}</td>' in html)
check("publication prints landscape", "size: letter landscape" in html)
status, html, _ = get(client, "/reports/publication")
check("publication form offers recent issues", status == 200 and "Choose..." in html)
resp = client.get(f"/reports/publication?date={busiest.isoformat()}&format=csv")
check("publication CSV rows", resp.get_data(as_text=True).count("\n") == busiest_n + 1)

# Labels
year_counts = Counter(y for r in csv_contacts for y in re.findall(r"\d{4}", r["DirectoryYears"] or ""))
label_year, _n = year_counts.most_common(1)[0]
exp_labels = sum(1 for r in csv_contacts if (r["AccountNumber"] or "").strip() and label_year in (r["DirectoryYears"] or ""))
status, html, _ = get(client, f"/reports/labels?year={label_year}")
check(f"labels {label_year}: {exp_labels} labels", status == 200 and f"<strong>{exp_labels} labels</strong>" in html)
resp = client.get(f"/reports/labels?year={label_year}&format=pdf")
pdf = resp.get_data()
pages = len(re.findall(rb"/Type /Page\b", pdf))
check(f"labels PDF has {-(-exp_labels // 30)} pages", resp.status_code == 200 and pdf.startswith(b"%PDF") and pages == -(-exp_labels // 30))
resp = client.get(f"/reports/labels?year={label_year}&format=pdf&start_at=30")
pages2 = len(re.findall(rb"/Type /Page\b", resp.get_data()))
check("labels start_at=30 adds a page when needed", pages2 == -(-(exp_labels + 29) // 30))

# Advertiser lists
status, html, _ = get(client, "/reports/advertiser-lists")
check("advertiser lists form", status == 200 and "Advertiser Lists" in html and "Showing" not in html)
status, html, _ = get(client, "/reports/advertiser-lists?run=1&format=html&mode=advertisers")
check("advertiser lists requires a filter", "Choose at least one filter" in html)
status, html, _ = get(client, "/reports/advertiser-lists?run=1&format=html&mode=advertisers&flag_email=1")
check("advertiser list: e-mail list = 105", "<strong>105 advertisers</strong>" in html)
resp = client.get("/reports/advertiser-lists?run=1&format=xlsx&mode=advertisers&flag_email=1")
wb = load_workbook(_io.BytesIO(resp.get_data()))
check("advertiser list Excel has 105 rows + header", wb.active.max_row == 106)
exp_2025_ads = [r for r in csv_ads if (dr := parse_date(r["DateRun"])) and _date(2025, 1, 1) <= dr <= _date(2025, 12, 31)]
exp_2025_amount = sum((parse_dec(r["Amount"]) or Decimal(0)) for r in exp_2025_ads)
status, html, _ = get(client, "/reports/advertiser-lists?run=1&format=html&mode=ads&run_from=2025-01-01&run_to=2025-12-31")
check(f"advertiser list ads 2025: {len(exp_2025_ads)} ads, {money(exp_2025_amount)}",
      f"<strong>{len(exp_2025_ads):,} ads</strong>" in html and money(exp_2025_amount) in html)
check("preview capped at 500 rows", len(exp_2025_ads) <= 500 or "Showing the first 500" in html)
resp = client.get("/reports/advertiser-lists?run=1&format=xlsx&mode=ads&run_from=2025-01-01&run_to=2025-12-31")
ws = load_workbook(_io.BytesIO(resp.get_data())).active
check("ads Excel total row matches", ws.max_row == len(exp_2025_ads) + 2
      and abs(Decimal(str(ws.cell(ws.max_row, 18).value)) - exp_2025_amount) < Decimal("0.01"))
check("ads Excel formats Amount as currency", '"$"' in ws.cell(2, 18).number_format)
status, html, _ = get(client, f"/reports/advertiser-lists?run=1&format=html&mode=advertisers&issues={busiest.strftime('%m/%d/%Y')}")
check("issue-date list finds advertisers", "advertisers</strong>" in html and "Nothing matches" not in html)
resp = client.get(f"/reports/advertiser-lists?run=1&format=labels&directory_year={label_year}")
check("advertiser list labels PDF", resp.status_code == 200 and resp.get_data().startswith(b"%PDF"))

with dev_app.app_context():
    db.session.add(Account(account_number="ZZINJ1", advertiser="=HYPERLINK(\"http://x\")", is_prospect=True))
    db.session.commit()
resp = client.get("/reports/advertiser-lists?run=1&format=csv&mode=advertisers&flag_prospect=1&advertiser=HYPERLINK")
check("CSV neutralizes formulas", "'=HYPERLINK" in resp.get_data(as_text=True))
resp = client.get("/reports/advertiser-lists?run=1&format=xlsx&mode=advertisers&flag_prospect=1&advertiser=HYPERLINK")
cell = load_workbook(_io.BytesIO(resp.get_data())).active.cell(2, 2)
check("Excel neutralizes formulas", cell.data_type == "s" and str(cell.value).startswith("'="))

# Exports
resp = client.get("/reports/exports?start=2025-01-01&end=2025-12-31&kind=amount")
ws = load_workbook(_io.BytesIO(resp.get_data())).active
total = Decimal(str(ws.cell(ws.max_row, ws.max_column).value))
check(f"amount export grand total {money(exp_2025_amount)}", abs(total - exp_2025_amount) < Decimal("0.01"))
check("amount export has a column per run date", ws.cell(1, 3).value and re.match(r"\d{4}/\d{2}/\d{2}", ws.cell(1, 3).value))
exp_2025_earned = sum((parse_dec(r["Amount"]) or Decimal(0)) * (parse_dec(r["CommissionPercent"], Decimal(0), Decimal(1)) or Decimal(0)) for r in exp_2025_ads)
resp = client.get("/reports/exports?start=2025-01-01&end=2025-12-31&kind=commission")
ws = load_workbook(_io.BytesIO(resp.get_data())).active
total = Decimal(str(ws.cell(ws.max_row, ws.max_column).value))
check(f"commission export grand total {money(exp_2025_earned)}", abs(total - exp_2025_earned) < Decimal("0.01"))
status, html, _ = get(client, "/reports/exports")
check("exports form", status == 200 and "Export amounts" in html)

# ---- advanced search (expected values computed from the CSV exports)
print("-- search")
from urllib.parse import urlencode  # noqa: E402

contacts_by_acct = {r["AccountNumber"].strip(): r for r in csv_contacts if r["AccountNumber"].strip()}
ads_by_acct = {}
for r in csv_ads:
    ads_by_acct.setdefault(r["AccountNumber"].strip(), []).append(r)


def has(value, needle):
    return needle.lower() in (value or "").lower()


def search_total(params):
    status, html, _ = get(client, "/search/?" + urlencode({"run": "1", **params}))
    m = re.search(r"Search Results <small>([\d,]+) account", html)
    return status, (int(m.group(1).replace(",", "")) if m else None), html


exp = {a for a, c in contacts_by_acct.items() if has(c["City"], "seattle") or has(c["Advertiser"], "mary")}
status, n, html = search_total({"city": "Seattle", "advertiser": "Mary"})
check(f"OR: city Seattle or advertiser Mary = {len(exp)}", status == 200 and n == len(exp))

exp = {a for a, c in contacts_by_acct.items() if has(c["City"], "seattle")
       and any(has(ad["Size"], "1/4") for ad in ads_by_acct.get(a, []))}
status, n, _ = search_total({"mode": "and", "city": "Seattle", "size": "1/4"})
check(f"AND: Seattle and an ad sized 1/4 = {len(exp)}", n == len(exp))

same_ad = {a for a in contacts_by_acct if any(has(ad["Size"], "1/4") and has(ad["Section"], "G") for ad in ads_by_acct.get(a, []))}
any_ads = {a for a in contacts_by_acct if any(has(ad["Size"], "1/4") for ad in ads_by_acct.get(a, []))
           and any(has(ad["Section"], "G") for ad in ads_by_acct.get(a, []))}
status, n, _ = search_total({"mode": "and", "size": "1/4", "section": "G"})
check(f"AND on ad fields requires the same ad ({len(same_ad)}, not {len(any_ads)})", n == len(same_ad))

exp = {a for a, c in contacts_by_acct.items() if (c["Advertiser"] or "").lower().startswith("st.")}
status, n, _ = search_total({"advertiser": "St.*"})
check(f"wildcard St.* (starts with) = {len(exp)}", n == len(exp))
status, n, _ = search_total({"advertiser": "100%_"})
check("literal % and _ are not wildcards", status == 200 and n == 0)

for field, form_name, needle in [("Zip", "postal_code", "981"), ("Email", "email", "@"), ("Phone", "phone", "206"),
                                 ("DirectoryYears", "directory_years", "2007"), ("Website", "website", "www"),
                                 ("Fax", "fax", "206")]:
    exp = {a for a, c in contacts_by_acct.items() if has(c[field], needle)}
    status, n, _ = search_total({form_name: needle})
    check(f"previously broken field works: {field} '{needle}' = {len(exp)}", n == len(exp))

exp = {a for a in contacts_by_acct if any((d := parse_date(ad["DateRun"])) and _date(2025, 1, 1) <= d <= _date(2025, 12, 31)
                                          for ad in ads_by_acct.get(a, []))}
status, n, _ = search_total({"date_run_from": "2025-01-01", "date_run_to": "2025-12-31"})
check(f"date run range 2025 = {len(exp)} accounts", n == len(exp))

exp = {a for a in contacts_by_acct if any((amt := parse_dec(ad["Amount"])) is not None and 1000 <= amt <= 2000
                                          for ad in ads_by_acct.get(a, []))}
status, n, _ = search_total({"amount_min": "$1,000", "amount_max": "2000"})
check(f"amount $1,000-2000 = {len(exp)}", n == len(exp))

exp = {a for a in contacts_by_acct if any(parse_dec(ad["CommissionPercent"]) == Decimal("0.25") for ad in ads_by_acct.get(a, []))}
status, n, _ = search_total({"comm_pct": "25"})
check(f"comm 25% = {len(exp)}", n == len(exp))

current = {a for a, c in contacts_by_acct.items() if truthy(c["CurrentAdvertiser"])}
status, n, _ = search_total({"flag_current": "1"})
check(f"status only: current advertisers = {len(current)}", n == len(current))
exp = {a for a in current if has(contacts_by_acct[a]["City"], "seattle") or has(contacts_by_acct[a]["Advertiser"], "mary")}
status, n, _ = search_total({"flag_current": "1", "city": "Seattle", "advertiser": "Mary"})
check(f"status narrows OR search: current and (Seattle or Mary) = {len(exp)}", n == len(exp))

status, n, html = search_total({})
check("no criteria -> message", "Enter at least one search value" in html and n is None)
status, n, html = search_total({"date_run_from": "not-a-date"})
check("bad date -> message", "Date Run from: not a date" in html)
status, html, _ = get(client, "/search/")
check("search form loads with advertiser list", status == 200 and '<datalist id="dl-advertisers">' in html and "Results" not in html)
check("menu: Search active", re.search(r'<li class="active">\s*<a href="/search/">Search</a>', html) is not None)

seattle = {a for a, c in contacts_by_acct.items() if has(c["City"], "seattle")}
status, n, html = search_total({"city": "Seattle"})
check("results paginate and keep criteria", (n <= 50) or ("city=Seattle" in html and "page=2" in html))
resp = client.get("/search/?" + urlencode({"run": "1", "city": "Seattle", "format": "xlsx"}))
ws = load_workbook(_io.BytesIO(resp.get_data())).active
check(f"search Excel export has {len(seattle)} rows", ws.max_row == len(seattle) + 1 and ws.cell(1, 12).value == "Special Advertising Opportunities")
resp = client.get("/search/?" + urlencode({"run": "1", "city": "Seattle", "format": "csv"}))
csv_rows = list(csv.reader(_io.StringIO(resp.get_data(as_text=True).lstrip("﻿"))))
check(f"search CSV export has {len(seattle)} records (notes with line breaks stay in one record)",
      resp.status_code == 200 and len(csv_rows) == len(seattle) + 1 and csv_rows[0][0] == "Account")
resp = client.get("/search/?" + urlencode({"run": "1", "city": "Seattle", "format": "labels"}))
check("search labels PDF", resp.status_code == 200 and resp.get_data().startswith(b"%PDF"))

# ---- admin: orphan ads
print("-- admin: orphans")
with dev_app.app_context():
    orphan_total = db.session.scalar(select(db.func.count(AdPlacement.id)).where(AdPlacement.account_number.is_(None)))
    n755 = db.session.scalar(select(db.func.count(AdPlacement.id)).where(AdPlacement.account_number.is_(None), AdPlacement.legacy_account_number == "755"))
    n030 = db.session.scalar(select(db.func.count(AdPlacement.id)).where(AdPlacement.account_number.is_(None), AdPlacement.legacy_account_number == "000030"))
    has_000755 = db.session.get(Account, "000755") is not None
status, html, _ = get(client, "/admin/orphans")
check(f"orphans page shows {orphan_total} orphan ads", status == 200 and f"{orphan_total:,} ads under" in html)
status, html, _ = get(client, "/admin/orphans?q=755")
check("orphans: 755 suggests 000755", (not has_000755) or "Suggested: 000755" in html)
if has_000755 and n755:
    client.post("/admin/orphans/resolve", data={"legacy": "755", "action": "attach", "account_number": "000755"})
    with dev_app.app_context():
        moved = db.session.scalar(select(db.func.count(AdPlacement.id)).where(AdPlacement.account_number == "000755", AdPlacement.legacy_account_number == "755"))
        check(f"orphans: attach moved {n755} ads to 000755, legacy number kept", moved == n755)
resp = client.post("/admin/orphans/resolve", data={"legacy": "000030", "action": "create", "advertiser": ""}, follow_redirects=True)
check("orphans: create requires a name", "Enter the advertiser name" in resp.get_data(as_text=True))
resp = client.post("/admin/orphans/resolve", data={"legacy": "000030", "action": "attach", "account_number": "NOPE99"}, follow_redirects=True)
check("orphans: attach to missing account refused", "does not exist" in resp.get_data(as_text=True))
resp = client.post("/admin/orphans/resolve", data={"legacy": "000030", "action": "create", "advertiser": "Recovered Advertiser"}, follow_redirects=True)
with dev_app.app_context():
    acct = db.session.get(Account, "000030")
    attached = db.session.scalar(select(db.func.count(AdPlacement.id)).where(AdPlacement.account_number == "000030"))
    check(f"orphans: create account 000030 and attach {n030} ads", acct is not None and acct.advertiser == "Recovered Advertiser" and attached == n030)
    check("orphans: attach audited", db.session.scalar(select(db.func.count(AuditLog.id)).where(AuditLog.entity == "ad_placements", AuditLog.changes.contains('"account_number": [null, "000030"]'))) == n030)
status, html, _ = get(client, "/admin/orphans")
check("orphans: count drops after cleanup", f"{orphan_total - n030 - (n755 if has_000755 else 0):,} ads under" in html)

# ---- admin: lookup lists
print("-- admin: lookups")
status, html, _ = get(client, "/admin/lookups")
check("lookups overview lists all four", status == 200 and all(t in html for t in ("Sales reps", "Sizes", "Sections", "Billing statuses")))
status, html, _ = get(client, "/admin/lookups/size")
check("size list empty; picker shows values in use", "This list is empty" in html and 'value="2 col"' in html)
status, html, _ = get(client, f"/accounts/{linked.account_number}/ads/new")
check("ad form: size is free text while the list is empty", 'list="dl-size"' in html and '<select name="size_raw"' not in html)

client.post("/admin/lookups/size/add-many", data={"codes": ["2 col", "1/4 pg", "FP"]})
client.post("/admin/lookups/size/add", data={"code": "Half page", "label": "1/2 page"})
resp = client.post("/admin/lookups/size/add", data={"code": "2 COL"}, follow_redirects=True)
check("lookups: case-only duplicate refused", "already on the list" in resp.get_data(as_text=True))
with dev_app.app_context():
    sizes = {s.code: s for s in db.session.scalars(select(AdSize)).all()}
    check("lookups: 4 sizes added", set(sizes) == {"2 col", "1/4 pg", "FP", "Half page"} and sizes["Half page"].normalized_label == "1/2 page")
    half_id, fp_id, col_id = sizes["Half page"].id, sizes["FP"].id, sizes["2 col"].id
    legacy_ad = db.session.scalars(select(AdPlacement).where(AdPlacement.size_raw == "1/8 pg", AdPlacement.account_number.is_not(None)).limit(1)).first()
    legacy_ad_id = legacy_ad.id if legacy_ad else None

status, html, _ = get(client, f"/accounts/{linked.account_number}/ads/new")
check("ad form: size becomes a dropdown with list values", '<select name="size_raw"' in html and ">Half page - 1/2 page<" in html)
check("ad form: sales still free text (its list is empty)", 'list="dl-sales"' in html)
base = {"date_run": "2026-12-01", "amount": "100", "commission_pct": "10", "description": "Lookup test"}
resp = client.post(f"/accounts/{linked.account_number}/ads/new", data={**base, "size_raw": "made up size"})
check("ad form: value not on the list rejected", resp.status_code == 200 and "Choose a value from the list" in resp.get_data(as_text=True))
resp = client.post(f"/accounts/{linked.account_number}/ads/new", data={**base, "size_raw": "FP"})
check("ad form: value on the list accepted", resp.status_code == 302)
if legacy_ad_id:
    status, html, _ = get(client, f"/ads/{legacy_ad_id}/edit")
    check("ad form: legacy value kept and labeled", "1/8 pg (legacy, not on the list)" in html)
    ver = re.search(r'id="version" name="version" type="hidden" value="([^"]*)"', html).group(1)
    resp = client.post(f"/ads/{legacy_ad_id}/edit", data={**base, "size_raw": "1/8 pg", "version": ver})
    check("ad form: saving an old ad with its legacy value is allowed", resp.status_code == 302)

client.post(f"/admin/lookups/size/{fp_id}/update", data={"label": "Full page"})  # unticked = inactive
status, html, _ = get(client, f"/accounts/{linked.account_number}/ads/new")
check("lookups: inactive value leaves the dropdown", ">FP<" not in html and "FP - Full page" not in html)
resp = client.post(f"/admin/lookups/size/{col_id}/delete", follow_redirects=True)
check("lookups: value used by ads cannot be removed", "Deactivate it instead" in resp.get_data(as_text=True))
client.post(f"/admin/lookups/size/{half_id}/delete")
with dev_app.app_context():
    check("lookups: unused value removed", db.session.get(AdSize, half_id) is None)
    check("lookups: list changes audited", db.session.scalar(select(db.func.count(AuditLog.id)).where(AuditLog.entity == "ad_sizes")) >= 6)
check("lookups: unknown list is 404", client.get("/admin/lookups/bogus").status_code == 404)

client.post("/admin/lookups/sales/add", data={"code": "KH", "label": "Sales rep KH"})
status, html, _ = get(client, "/admin/lookups/sales")
check("lookups: case variants flagged for merging", 'differs from "KH" only by capitals' in html)

# ---- admin: merge spellings
print("-- admin: merge")
status, html, _ = get(client, "/admin/normalization?domain=sales")
check("merge page lists case variants", status == 200 and all(f'value="{v}"' in html for v in ("kh", "Kh", "kH")))
resp = client.post("/admin/normalization/sales/preview", data={"values": ["kh", "Kh", "kH", "KH"], "target": "KH"})
html = resp.get_data(as_text=True)
check("merge preview: 6 ads will change (2+3+1)", "<strong>6 ads</strong>" in html)
check("merge preview: target already on list (no add box)", "Also add" not in html)
client.post("/admin/normalization/sales/merge", data={"values": ["kh", "Kh", "kH", "KH"], "target": "KH"})
with dev_app.app_context():
    exact_kh = db.session.scalar(select(db.func.count(AdPlacement.id)).where(AdPlacement.sales_rep_raw == "KH"))
    variants = db.session.scalar(select(db.func.count(AdPlacement.id)).where(AdPlacement.sales_rep_raw.in_(["kh", "Kh", "kH"])))
    check(f"merge: all 9,852 KH ads now spelled exactly KH (got {exact_kh})", exact_kh == 9852 and variants == 0)
    maps = db.session.scalars(select(AdNormalizationMap).where(AdNormalizationMap.domain == "sales", AdNormalizationMap.approved_at.is_not(None))).all()
    check("merge: decisions recorded in normalization map", {m.raw_value for m in maps} == {"kh", "Kh", "kH"} and all(m.normalized_value == "KH" and m.approved_by == "dev@localhost" for m in maps))
    merge_rows = db.session.scalars(select(AuditLog).where(AuditLog.entity == "ad_placements", AuditLog.action == "update",
                                                           AuditLog.changes.contains('"sales_rep_raw"'))).all()
    to_kh = [r for r in merge_rows if json.loads(r.changes)["sales_rep_raw"][1] == "KH"]
    check(f"merge: each changed ad audited (6, got {len(to_kh)})", len(to_kh) == 6
          and {json.loads(r.changes)["sales_rep_raw"][0] for r in to_kh} == {"kh", "Kh", "kH"})
status, html, _ = get(client, "/admin/normalization?domain=sales")
check("merge: recent merges shown", "Recent merges for Sales" in html)
status, html, _ = get(client, "/?rep=KH")
check("merge: ads list still finds 9,852 KH ads", "<strong>9,852</strong> ads" in html)

resp = client.post("/admin/normalization/size/preview", data={"values": ["1/4 pg"], "target": "1/4 page"})
check("merge preview: offers to add a new target to the list", "Also add" in resp.get_data(as_text=True))
client.post("/admin/normalization/size/merge", data={"values": ["1/4 pg"], "target": "1/4 page", "add_to_list": "1"})
with dev_app.app_context():
    check("merge: new target added to list", db.session.scalars(select(AdSize).where(AdSize.code == "1/4 page")).first() is not None)
resp = client.post("/admin/normalization/size/preview", data={"values": ["2 col"], "target": "x" * 51}, follow_redirects=True)
check("merge: overlong target refused", "at most 50 characters" in resp.get_data(as_text=True))
resp = client.post("/admin/normalization/size/preview", data={"target": "FP"}, follow_redirects=True)
check("merge: nothing ticked refused", "Tick at least one value" in resp.get_data(as_text=True))

status, html, _ = get(client, "/")
check("menu: Admin items are live links", all(f'href="/admin/{p}"' in html for p in ("lookups", "orphans", "normalization", "audit")))

status, html, _ = get(client, "/")
check("menu: all five reports are live links", all(f'href="/reports/{p}"' in html for p in ("commission", "publication", "labels", "advertiser-lists", "exports")))
status, html, _ = get(client, "/admin/audit?entity=accounts")
check("audit page filter by table", status == 200 and "ZZ9999" in html and f"ad_placements #{linked_id}" not in html)

# ---- help
print("-- help")
from app.help import TOPICS, SCREEN_HELP
status, html, _ = get(client, "/help/")
check("help index 200 with all topics for Admin", status == 200 and all(f'href="/help/{slug}"' in html for slug, *_ in TOPICS))
check("menu has Help", 'href="/help/"' in html)
for slug, title, *_ in TOPICS:
    status, html, _ = get(client, f"/help/{slug}")
    check(f"help topic {slug} renders", status == 200 and f"<h2>{title}</h2>" in html and "{{" not in html and "{%" not in html)
    anchors = set(re.findall(r'href="(?:/help/([\w-]+))?#([\w-]+)"', html))
    for t_slug, anchor in anchors:
        target_html = html if not t_slug else get(client, f"/help/{t_slug}")[1]
        check(f"help link {t_slug or slug}#{anchor} from {slug} resolves", f'id="{anchor}"' in target_html)
for endpoint, (slug, anchor) in SCREEN_HELP.items():
    if anchor:
        check(f"screen help {endpoint} -> {slug}#{anchor} exists", f'id="{anchor}"' in get(client, f"/help/{slug}")[1])
check("unknown help topic 404", client.get("/help/bogus").status_code == 404)
status, html, _ = get(client, "/reports/labels")
check("header Help link is page-specific (labels)", 'href="/help/reports#labels"' in html)
status, html, _ = get(client, "/admin/orphans")
check("header Help link is page-specific (orphans)", 'href="/help/admin-orphans"' in html)
status, html, _ = get(client, "/help/?q=avery")
check("help search finds labels in Reports", status == 200 and 'href="/help/reports"' in html and "Avery" in html)
status, html, _ = get(client, "/help/?q=zzqqxx")
check("help search with no match", "Nothing found" in html)
status, html, _ = get(client, "/help/?q=<script>")
check("help search escapes the query", "<script>" not in html.split("<main")[1])


# ================================================================ ENTRA MODE
class FakeCCA:
    roles = ["NWCAds.Viewer"]
    instances = 0

    def __init__(self, client_id, authority=None, client_credential=None):
        FakeCCA.instances += 1
        self.authority = authority

    def initiate_auth_code_flow(self, scopes, redirect_uri=None):
        self.last_redirect_uri = redirect_uri
        return {"auth_uri": f"{self.authority}/oauth2/v2.0/authorize?state=abc", "state": "abc",
                "redirect_uri": redirect_uri}

    def acquire_token_by_auth_code_flow(self, flow, args):
        if args.get("state") != flow["state"]:
            raise ValueError("state mismatch")
        if args.get("error"):
            return {"error": args["error"], "error_description": "denied"}
        claims = {"oid": "oid-viewer", "name": "Val Viewer", "preferred_username": "val@example.org",
                  "tid": "tenant-guid"}
        if FakeCCA.roles is not None:
            claims["roles"] = FakeCCA.roles
        return {"id_token_claims": claims}


auth_module.msal.ConfidentialClientApplication = FakeCCA


class EntraConfig(Config):
    TESTING = True
    AUTH_MODE = "entra"
    ENTRA_TENANT_ID = "tenant-guid"
    ENTRA_CLIENT_ID = "client-guid"
    ENTRA_CLIENT_SECRET = "secret"
    SECRET_KEY = "x" * 48
    SESSION_COOKIE_SECURE = False


print()
print("== Entra mode (fake Microsoft sign-in, 200 ads)")
entra_app = create_app(EntraConfig)
load_data(entra_app, ad_limit=200)


def sign_in(c, roles, next_path=None):
    FakeCCA.roles = roles
    url = "/auth/login" + (f"?next={next_path}" if next_path else "")
    c.get(url)
    return c.get("/auth/callback?code=fake&state=abc")


c = entra_app.test_client()
resp = c.get("/ads/5?x=1")
check("unauthenticated request redirects to login", resp.status_code == 302 and resp.headers["Location"].startswith("/auth/login"))
check("login redirect keeps the requested page", parse_qs(urlparse(resp.headers["Location"]).query).get("next") == ["/ads/5?x=1"])

resp = c.get("/healthz")
check("healthz is public", resp.status_code == 200)

resp = c.get("/auth/login?next=/ads/5")
check("login redirects to Microsoft", resp.status_code == 302 and resp.headers["Location"].startswith("https://login.microsoftonline.com/tenant-guid/"))

resp = c.get("/auth/callback?code=fake&state=WRONG")
check("callback rejects wrong state", resp.status_code == 400)

resp = sign_in(c, ["NWCAds.Viewer"], next_path="/ads/5")
check("callback returns to requested page", resp.status_code == 302 and resp.headers["Location"] == "/ads/5")

resp = c.get("/")
html = resp.get_data(as_text=True)
check("viewer can see ads", resp.status_code == 200 and "Val Viewer" in html)
check("viewer badge", 'class="role-badge">Viewer<' in html)
check("viewer menu has no Admin", "Audit log" not in html and ">Admin" not in html)
check("no dev banner in entra mode", "Development mode" not in html)
check("sign-out link shown", 'href="/auth/logout"' in html)

resp = c.get("/admin/audit")
check("viewer blocked from admin (403)", resp.status_code == 403 and "Not allowed" in resp.get_data(as_text=True))

resp = c.get("/auth/logout")
check("logout redirects to Microsoft logout", resp.status_code == 302 and "/oauth2/v2.0/logout" in resp.headers["Location"]
      and "signed-out" in resp.headers["Location"])
resp = c.get("/")
check("after logout, pages require sign-in again", resp.status_code == 302)
resp = c.get("/auth/signed-out")
check("signed-out page is public", resp.status_code == 200)

c2 = entra_app.test_client()
resp = sign_in(c2, ["NWCAds.Viewer", "NWCAds.Admin"])
resp = c2.get("/admin/audit")
check("highest role wins (Viewer+Admin -> Admin)", resp.status_code == 200)

c3 = entra_app.test_client()
resp = sign_in(c3, None)
resp = c3.get("/")
check("signed in without a role -> 403 no access page", resp.status_code == 403 and "No access yet" in resp.get_data(as_text=True))

c4 = entra_app.test_client()
for evil in ("//evil.example.com/x", "https://evil.example.com/", "/\\evil.example.com"):
    resp = sign_in(c4, ["NWCAds.Viewer"], next_path=evil)
    check(f"open redirect blocked: {evil}", resp.headers["Location"] == "/")

c5 = entra_app.test_client()
c5.get("/auth/login")
resp = c5.get("/auth/callback?state=abc&error=access_denied")
check("Microsoft error shows failure page", resp.status_code == 401 and "Sign-in failed" in resp.get_data(as_text=True))

check("MSAL client created once and reused", FakeCCA.instances == 1)

# ---- roles on the forms, and CSRF
with entra_app.app_context():
    some_acct = db.session.scalar(select(AdPlacement.account_number).where(AdPlacement.account_number.is_not(None)).limit(1))
    some_ad = db.session.scalar(select(AdPlacement.id).limit(1))

cv = entra_app.test_client()
sign_in(cv, ["NWCAds.Viewer"])
resp = cv.get(f"/accounts/{some_acct}")
html = resp.get_data(as_text=True)
check("viewer sees account read-only (disabled, no Save)", resp.status_code == 200 and "disabled" in html and ">Save<" not in html)
check("viewer sees View links, not Edit", "/edit" not in html and "Add ad" not in html)
token = re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)
resp = cv.post(f"/accounts/{some_acct}", data={"csrf_token": token, "advertiser": "Hacked"})
check("viewer POST to account is 403", resp.status_code == 403)
for url in ("/accounts/new", f"/ads/{some_ad}/edit", f"/accounts/{some_acct}/ads/new"):
    check(f"viewer blocked from {url}", cv.get(url).status_code == 403)

ce = entra_app.test_client()
sign_in(ce, ["NWCAds.Editor"])
resp = ce.get(f"/accounts/{some_acct}")
html = resp.get_data(as_text=True)
check("editor sees Save and Add ad", ">Save<" in html and "Add ad" in html)
check("editor does not see Delete account", "Delete account" not in html)
token = re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)
resp = ce.post(f"/ads/{some_ad}/delete", data={"csrf_token": token})
check("editor cannot delete ads (Admin only)", resp.status_code == 403)
for url in ("/admin/lookups", "/admin/lookups/size", "/admin/orphans", "/admin/normalization"):
    check(f"editor blocked from {url}", ce.get(url).status_code == 403)
resp = ce.post("/admin/normalization/sales/merge", data={"csrf_token": token, "values": ["KH"], "target": "X"})
check("editor cannot merge (403)", resp.status_code == 403)
resp = ce.post(f"/accounts/{some_acct}", data={"advertiser": "No token"})
check("POST without CSRF token is rejected (400)", resp.status_code == 400)

for url in ("/search/", "/search/?run=1&city=a", "/reports/commission", "/reports/publication", "/reports/labels",
            "/reports/advertiser-lists", "/reports/exports"):
    check(f"viewer can open {url}", cv.get(url).status_code == 200)

html = cv.get("/help/").get_data(as_text=True)
check("viewer help index hides Admin topics", 'href="/help/ads"' in html and "/help/admin-" not in html)
check("viewer blocked from Admin help topic", cv.get("/help/admin-merge").status_code == 403)
html = cv.get("/help/?q=merge").get_data(as_text=True)
check("viewer help search skips Admin topics", "/help/admin-" not in html)
html = cv.get("/accounts/").get_data(as_text=True)
check("viewer header Help link for accounts", 'href="/help/accounts#list"' in html)
check("help requires sign-in", entra_app.test_client().get("/help/").status_code == 302)

# ---- startup validation
for label, overrides in [
    ("entra without IDs refuses to start", {"ENTRA_CLIENT_ID": ""}),
    ("entra with default SECRET_KEY refuses to start", {"SECRET_KEY": "dev-secret-key"}),
    ("unknown AUTH_MODE refuses to start", {"AUTH_MODE": "none"}),
]:
    bad = type("BadConfig", (EntraConfig,), overrides)
    try:
        create_app(bad)
        check(label, False)
    except RuntimeError:
        check(label, True)

print()
print("FAILURES:", failures if failures else "none")
sys.exit(1 if failures else 0)
