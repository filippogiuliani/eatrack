# eaTrack – baby weaning diary

> **Disclaimer / Esclusione di responsabilità.** eaTrack is provided *as is*, without any warranty: the authors accept **no responsibility or liability** for data loss, security problems, missed reminders, wrong information or any other consequence of using it. Read [DISCLAIMER.md](DISCLAIMER.md) before using it with real data. · Il software è fornito *così com'è*, senza garanzie: gli autori **non hanno alcuna responsabilità**. Leggi [DISCLAIMER.md](DISCLAIMER.md).

A weaning diary shared by the whole family: meals per child, jars of baby food in the fridge and
freezer, foods introduced, statistics and the pediatrician's weekly plan. Multi-user; the interface
is available in Italian, English, Spanish, Portuguese (Portugal), French and German.

- `backend/` – Flask API + SQLite (served by waitress on port 3000)
- `frontend/` – Svelte + Vite interface, built into the Docker image

> **Made with AI.** This project was written almost entirely by an AI assistant (Anthropic's Claude),
> following a user's requests, and has not been professionally audited. Read the
> [disclaimer](#disclaimer) before using it.

## Running with Docker

```sh
cp .env.example .env    # set the URL, SMTP and, optionally, OIDC providers
./rebuild.sh
```

Data lives in `./eaTrack_data/` (mounted on `/app/data`): `eatrack.db` and `backups/`
(one automatic backup a day, plus copies before migrations, imports and deletions).

### Upgrading from an earlier version
On start-up the database is upgraded automatically (a copy is saved first as `backups/pre-migration-*.db`):
- from v1/v2 (single family, no accounts) the data goes into a family with no members:
  **the first user who signs up becomes its owner**, so sign up yourself before opening the app to others;
- from v3/v4 (Italian table names) the schema and stored values are renamed; accounts and sessions keep working.

`.json` backups exported by earlier versions can still be imported.

## Accounts and families
- Sign up with email/password, or with Google / any OIDC provider (see `.env.example`).
- With `EATRACK_SIGNUP=closed` new accounts can only join through an invitation link (OIDC included).
- Each family shares its children, foods and pantry; other people are invited with a link (valid 7 days, single use).
- Each family sees **only** its own data; export and import only cover the current family.
- Deleting an account deletes its data (and the family, if it was the only member).

## Weekly plan
Per child and fully optional: how many times a week to offer each food group (min/max), and/or a menu
for each weekday and meal. The diary shows the week's progress and pre-fills empty meals from the menu.

## Administration (command line)
```sh
docker exec eatrack python manage.py backup          # backup right now
docker exec eatrack python manage.py backups         # list backups
docker exec eatrack python manage.py users           # users and families
# full restore: stop the container, then
docker run --rm -v "$(pwd)/eaTrack_data:/app/data" eatrack python manage.py restore <file.db>
```

## Before opening it to the public
- Complete the privacy notice and have it reviewed (`frontend/src/lib/privacy/index.js`, fields in `[ ]`, every language):
  the diary holds health data about minors (GDPR art. 9).
- Serve the app over HTTPS (reverse proxy) with `EATRACK_COOKIE_SECURE=1` and `EATRACK_PROXY=1`.
- Configure a real SMTP server, otherwise email confirmation and password recovery won't arrive.

## Languages
Available: English (`en`, the default), Italian (`it`), Spanish (`es`), Portuguese – Portugal (`pt`), French (`fr`), German (`de`).

The language is picked automatically from the browser (the first supported one in its preference list;
regional variants such as `pt-BR` or `de-CH` use the base language) and falls back to English.
Dates follow the browser's region (e.g. `en-GB` day/month, `en-US` month/day). A language chosen in the app,
or saved in the user's profile, always wins.

To add one:
- interface: `frontend/src/lib/locales/<code>.js` (same keys as `it.js`) + a line in `LANGUAGES` (`frontend/src/lib/i18n.svelte.js`);
- privacy notice: an entry in `frontend/src/lib/privacy/index.js`;
- server (errors, emails, export labels, starter food catalog): `backend/i18n.py`.
The code itself is in English; values stored in the database are stable keys (`lunch`, `half`, `freezer`, …)
translated when displayed.

## Development
```sh
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
cd backend && ../.venv/bin/python app.py      # API on :3000
cd frontend && npm install && npm run dev     # UI on :5173, proxying /api
```

### Tests
```sh
.venv/bin/pip install -r backend/requirements-dev.txt
.venv/bin/python -m pytest          # from the project root
```
The tests (`backend/tests/`) use a fresh temporary database every time: they never touch real data,
send no email and use a fake OIDC provider.

## Made with AI
The code, tests, translations and documentation in this repository were generated by an AI assistant
(Anthropic's Claude) and reviewed only by running the automated tests and manual checks of the app.
They may contain bugs, security issues or translation mistakes that nobody has spotted yet.
Review the code yourself before relying on it, especially before exposing an instance to the internet.

## Disclaimer
- The software is provided **"as is", without warranty of any kind**, as stated in the [MIT License](LICENSE).
  The authors and contributors are **not liable** for any damage, data loss, security incident or other
  consequence arising from its use or misuse.
- eaTrack is a personal note-taking tool. It is **not a medical device** and does not give medical advice:
  feeding decisions, allergies and reactions must always be discussed with a pediatrician or other
  qualified professional.
- Whoever installs and runs an instance is solely responsible for it: hosting, security, backups,
  and compliance with privacy law (e.g. the GDPR, since the diary may contain health data about minors),
  including completing the privacy notice in `frontend/src/lib/privacy/index.js`.
- The contributors of this repository do not operate any service based on this code: any instance you
  find online is run by whoever deployed it, under their own responsibility.

## License
[MIT](LICENSE). No warranty and no liability: see [DISCLAIMER.md](DISCLAIMER.md).

## weHub (one sign-in and one family for all the family apps)
Optional. With `EATRACK_HUB_URL` and `EATRACK_HUB_KEY` set (see `.env.example` and weHub's README), eaTrack signs people in
only through the OIDC provider (the same Pocket ID as weHub), and takes the family from weHub: members, roles,
people and who may use eaTrack. The family, members and people become read-only here, with a link to weHub; the copy is
refreshed every 2 minutes and keeps working if weHub is down. Existing data is adopted, not recreated: run weHub's
**Import** once (it reads `GET /api/hub/export` with the key). A family someone had made on their own can be merged into the shared one from weHub's import (`POST /api/hub/merge`: a database backup first, then everything moves; children and foods with the same name become one, meals included). Without these settings eaTrack works on its own as before.
