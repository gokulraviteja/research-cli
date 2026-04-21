# research-cli

Read-only Twitter/X research CLI. Wraps [`twikit`](https://github.com/d60/twikit) with cookie-based auth and applies monkey-patches for Twitter API drift (missing `legacy` fields, rotated GraphQL query IDs, changed webpack chunk format).

No API key required — just cookies from a logged-in x.com session.

## Setup

```bash
cd research-cli
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

cp env_example.txt .env
# edit .env and paste your ct0 and auth_token cookies
```

**Get the cookies:** x.com → log in → DevTools (F12) → Application → Cookies → copy `ct0` and `auth_token`. `ct0` is the long one (~160 chars), `auth_token` is the short one (~40 chars). Don't swap them.

## Usage

```bash
./venv/bin/python cli.py auth                          # verify cookies
./venv/bin/python cli.py timeline --count 10           # "For You" feed
./venv/bin/python cli.py latest --count 10             # "Following" feed
./venv/bin/python cli.py search "claude code" --count 5 --product Latest
./venv/bin/python cli.py tweet 1234567890
./venv/bin/python cli.py replies 1234567890 --count 10
```

All output is JSON (pretty-printed by default). Pass `--compact` **before** the subcommand for single-line JSON, e.g.:

```bash
./venv/bin/python cli.py --compact latest --count 20 | jq '.[] | {author, text}'
```

To override cookies from the CLI (e.g. to test a different account): `--ct0 XXX --auth-token YYY`.

## Commands

| Command | Description |
|---|---|
| `auth` | Verify cookies; prints `{authenticated, user}`. |
| `timeline [--count N]` | Home timeline ("For You"). |
| `latest [--count N]` | Latest timeline ("Following", chronological). |
| `search <query> [--count N] [--product Top\|Latest]` | Full-text tweet search. |
| `tweet <id>` | Fetch a tweet by ID. |
| `replies <id> [--count N]` | Fetch replies to a tweet. |

## Tweet output shape

```json
{
  "id": "...",
  "text": "...",
  "author": "screen_name",
  "author_name": "Display Name",
  "author_id": "...",
  "created_at": "Sun Apr 19 18:44:43 +0000 2026",
  "like_count": 4,
  "retweet_count": 0,
  "reply_count": 0
}
```

## Caveats

Twitter rotates the GraphQL persisted-query IDs for `search` / `tweet` / `replies` every few weeks. If those 404, update the three IDs at the top of `sources/twitter.py` (check the currently-maintained list at [trevorhobenshield/twitter-api-client](https://github.com/trevorhobenshield/twitter-api-client/blob/main/twitter/constants.py)). `auth`, `timeline`, and `latest` are the most stable.

401 on `auth` means your cookies have expired — refresh from a logged-in browser session.
