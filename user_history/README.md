# User accounts and history

This folder owns the account/history feature. The existing FastAPI app registers its router, template directory and static files. The saved crop model and dataset are unchanged.

```text
user_history/
  accounts.py          # Password hashes, users, sessions and attempt limits
  database.py          # Shared MongoDB client and environment configuration
  history_store.py     # Owner-scoped prediction storage and pagination
  routes.py            # Account and history HTTP endpoints
  templates/           # Sign-in, registration and history pages
  static/              # Account/history JavaScript, CSS and translations
  tests/               # Real MongoDB integration tests
```

## Run it

Use the project's existing Python environment. Install the updated requirements, keep MongoDB running, then restart FastAPI:

```powershell
cd C:\Users\sushe\Crop-Recommendation-ML-Project
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload
```

The default connection is `mongodb://127.0.0.1:27017`, database **crop_advisor**. MongoDB was already running on the development computer. Optional overrides go in the project-root `.env` (copy the relevant entries from `.env.example`; keep existing keys):

```dotenv
MONGODB_URI=mongodb://127.0.0.1:27017
MONGODB_DATABASE=crop_advisor
SESSION_COOKIE_SECURE=false
```

For a hosted app, use a shared MongoDB/Atlas connection string and set `SESSION_COOKIE_SECURE=true` with HTTPS. All devices must use the same app/database to share an account's history. Two unrelated local MongoDB databases do not synchronize automatically. The URI stays on the server, outside frontend code and Git.

1. Open `/register` and create an account. Usernames use 3–32 English letters, numbers, dots, underscores or hyphens; passwords use 12–128 characters.
2. Run **Crop Recommendation** or **Soil Analysis** while signed in.
3. Open **History** to view saved inputs, crop, probability, status and the original report. Reuse inputs without automatically running another prediction, or delete individual entries.
4. Sign into the same account on another device to access its saved history.

The dashboard shows six recent account predictions. The full page loads 20 entries at a time with **Load more**. Both low-confidence and out-of-range results are stored with their original warnings; an out-of-range result retains no recommended crop. Guests can still run the model, but their results are not saved. Old browser-only `ca_hist` entries are not assigned automatically to a newly registered account.

## Accounts and roles

Every registered account has the ordinary **user** role. A user can read and delete only their own entries. The app gets the owner ID from the server session, not a user ID supplied by the browser. The project owner administers MongoDB and deployment; there is no separate administrator login/dashboard in this feature. Password reset/email verification is outside this initial username/password feature.

Passwords use Argon2id; the browser receives an HttpOnly session cookie while MongoDB stores its hash and expiration. Sign-out revokes that session. Mutating browser requests require the same-origin app header and reject foreign Origin headers. Account attempts are rate-limited in MongoDB. Account/history responses use `Cache-Control: no-store`. See the [FastAPI password-hashing guidance](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/) and [OWASP session guidance](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).

MongoDB collections are `users`, `sessions`, `auth_attempts` and `prediction_history`. Sessions and attempt counters have expiry indexes; saved history remains until its owner deletes it. The owner/history index supports paginated reads. The connection uses bounded operation timeouts, following the [PyMongo connection documentation](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/connect/).

If MongoDB cannot be reached, account/history actions report that storage is unavailable. A valid prediction is still returned with `history.saved=false` and `reason=storage_unavailable`; the interface does not claim that it was saved.

## API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| POST | `/api/auth/register` | Create an ordinary user and session |
| POST | `/api/auth/login` | Sign in |
| GET | `/api/auth/me` | Read the current session's public user |
| POST | `/api/auth/logout` | Revoke the current session |
| GET | `/api/history?limit=20&before=...` | Read the current user's history |
| GET | `/api/history/{id}` | Read an owned saved report |
| DELETE | `/api/history/{id}` | Delete an owned entry |

For POST/DELETE testing in Postman, send `X-Crop-Request: 1` and retain the login response's cookie. Registration/login take JSON `username` and `password`. A signed-in `POST /predict` also needs that header and automatically saves the response. `X-Activity-Source: soil-analysis` distinguishes Soil Analysis from ordinary recommendations; it never determines ownership or changes model features.

## Languages and verification

The feature's controls, guidance, validation, storage errors and history actions have offline translations for all twelve regional languages. Dates follow the selected locale. Usernames, session identity, numeric inputs, record IDs and API payload keys are preserved. Existing report charts use the app's shared localization. Some pre-existing technical report paragraphs remain English as documented in `LANGUAGE_SUPPORT.md`.

```powershell
npm ci
npm test
python -m unittest discover -s user_history/tests -p test_user_history.py -v
```

The 25 frontend tests include account/history language changes, pagination, reports, deletion and outage messages. Eleven backend tests use a uniquely named disposable MongoDB test database to verify hashes, user-only registration, ownership, cross-device access, expiry/logout, CSRF, rate limits and outages. The tests skip if MongoDB is unavailable and never clear production collections. `TEST_MONGODB_URI` can select a test server. A separate browser check registered a temporary account in an isolated database, saved a real prediction, opened its history in Telugu and reopened the report in Urdu.
