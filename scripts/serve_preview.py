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

"""Run the app locally on an in-memory SQLite copy of the Access exports.

For trying changes without a MariaDB server. Sign-in is off and you act as Admin.
Data lives in memory only: every restart reloads it from exports/access_csv/.

Usage, from the repository root:
    python scripts/serve_preview.py [port]      (default port 5055)
"""
import csv
import os
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5055
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["AUTH_MODE"] = "dev"
sys.path.insert(0, PROJECT)

from sqlalchemy import Integer  # noqa: E402

from config import Config  # noqa: E402
from app import create_app  # noqa: E402
from app.audit import AuditLog  # noqa: E402
from app.extensions import db  # noqa: E402
from app.target_models import Account, AdPlacement  # noqa: E402

AdPlacement.__table__.c.id.type = Integer()
AuditLog.__table__.c.id.type = Integer()
CSV_DIR = os.path.join(PROJECT, "exports", "access_csv")


def blank(v):
    v = (v or "").strip()
    return v or None


def pdate(v):
    v = blank(v)
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y"):
        try:
            return datetime.strptime(v, fmt).date() if v else None
        except ValueError:
            pass
    return None


def pdec(v, lo=None, hi=None):
    v = blank(v)
    try:
        d = Decimal(v) if v else None
    except InvalidOperation:
        return None
    if d is not None and lo is not None and not (lo <= d <= hi):
        return None
    return d


def yes(v):
    return (v or "").strip().upper() in ("TRUE", "YES", "Y", "1", "-1")


class PreviewConfig(Config):
    AUTH_MODE = "dev"
    DEV_ROLE = "Admin"
    DEV_USER_NAME = "Preview User"
    SESSION_COOKIE_SECURE = False


app = create_app(PreviewConfig)
with app.app_context():
    db.create_all()
    with open(os.path.join(CSV_DIR, "tbl_ProgressContacts_01.csv"), encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if blank(r["AccountNumber"]):
                db.session.add(Account(
                    account_number=r["AccountNumber"].strip()[:6], advertiser=blank(r["Advertiser"]),
                    contact_name=blank(r["Contact"]), address1=blank(r["Address"]), city=blank(r["City"]),
                    state_code=blank(r["State"]), postal_code=blank(r["Zip"]), phone=blank(r["Phone"]),
                    category=blank(r["Category"]), directory_years=blank(r["DirectoryYears"]),
                    is_current_advertiser=yes(r["CurrentAdvertiser"]), is_email_list=yes(r["EmailList"]),
                ))
    db.session.flush()
    known = {a for (a,) in db.session.query(Account.account_number)}
    with open(os.path.join(CSV_DIR, "tbl_ProgressAds_01.csv"), encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            acct = (blank(r["AccountNumber"]) or "")[:6] or None
            db.session.add(AdPlacement(
                legacy_account_number=acct, account_number=acct if acct in known else None,
                commission_percent=pdec(r["CommissionPercent"], Decimal(0), Decimal(1)),
                date_sold=pdate(r["DateSold"]), date_run=pdate(r["DateRun"]), description=blank(r["Description"]),
                sales_rep_raw=blank(r["Sales"]), amount=pdec(r["Amount"]), size_raw=blank(r["Size"]),
                section_raw=blank(r["Section"]), ad_page=blank(r["AdPage"]), bill_number=blank(r["BillNumber"]),
            ))
    db.session.commit()

app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)
