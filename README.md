# NWC Ads

The advertising database for *Northwest Catholic*, the magazine of the Archdiocese of Seattle. It replaces the Access database `NWC_ADV_DB_2015.accdb` with a web application: advertiser accounts, ad placements, search, commission and publication reports, mailing labels, and Excel exports.

**Stack:** Python 3.11, Flask, SQLAlchemy, MariaDB, Microsoft Entra ID sign-in, Gunicorn and Nginx on an Azure Debian VM.

**Production:** https://nwcads.archseattle.org (Archdiocese networks only)

## Documentation

| Document | Read it when you want to |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Understand how the system is built and why |
| [docs/developer-guide.md](docs/developer-guide.md) | Set up a workstation, follow the conventions, and make a change (with recipes) |
| [docs/operations.md](docs/operations.md) | Deploy, configure, manage users, back up, run the cutover, or troubleshoot production |
| [docs/backlog.md](docs/backlog.md) | See what is left to do, what is waiting on decisions, and ideas for later |
| [docs/access_application_spec.md](docs/access_application_spec.md) | Look up how the Access forms, reports, and queries worked |
| [decisions.md](decisions.md) | Read the decision log |
| In-app **Help** | Learn how staff use each screen (source: `app/templates/help/topics/`) |

## Quick start (Windows workstation)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env          # Then set AUTH_MODE=dev for local work
python scripts/serve_preview.py      # http://127.0.0.1:5055, with the Access exports in memory
python tests/smoke_test.py           # Expect: FAILURES: none
```

The preview and the tests need the Access CSV exports in `exports/access_csv/`, which are not in Git. See [docs/developer-guide.md](docs/developer-guide.md) section 1.

## Deploy an update

```bash
cd /opt/aos_nwc_ads
git pull
sudo systemctl restart aosnwcads
```

For updates with migrations or new packages, see [docs/operations.md](docs/operations.md) section 3.

## License

Copyright 2026 Archdiocese of Seattle. Author: Kevin F Benz.

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE). Each source file carries the standard Apache header; add it to new files as well.
