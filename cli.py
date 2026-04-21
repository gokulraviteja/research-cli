#!/usr/bin/env python3
"""
Research CLI — read-only Twitter/X commands backed by twikit with cookie auth.

Examples:
    ./cli.py auth
    ./cli.py timeline --count 10
    ./cli.py latest --count 10
    ./cli.py search "claude code" --count 5 --product Latest
    ./cli.py tweet 1234567890
    ./cli.py replies 1234567890 --count 10

Credentials are loaded from .env (TWITTER_CT0, TWITTER_AUTH_TOKEN) or
passed via --ct0 / --auth-token.
"""

import argparse
import asyncio
import json
import os
import sys

from dotenv import load_dotenv

from sources.twitter import TwitterSource


def load_credentials(args) -> tuple[str, str]:
    load_dotenv()
    ct0 = args.ct0 or os.getenv("TWITTER_CT0")
    auth_token = args.auth_token or os.getenv("TWITTER_AUTH_TOKEN")
    if not ct0 or not auth_token:
        print(
            "Error: TWITTER_CT0 and TWITTER_AUTH_TOKEN must be set in .env "
            "or passed via --ct0/--auth-token",
            file=sys.stderr,
        )
        sys.exit(2)
    return ct0, auth_token


def emit(data, compact: bool) -> None:
    if compact:
        print(json.dumps(data, ensure_ascii=False, default=str))
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


async def run(args) -> None:
    ct0, auth_token = load_credentials(args)
    twitter = TwitterSource()

    if args.command == "auth":
        result = await twitter.authenticate(ct0, auth_token)
    elif args.command == "timeline":
        result = await twitter.get_timeline(ct0, auth_token, args.count)
    elif args.command == "latest":
        result = await twitter.get_latest_timeline(ct0, auth_token, args.count)
    elif args.command == "search":
        result = await twitter.search_tweets(
            ct0, auth_token, args.query, args.count, args.product
        )
    elif args.command == "tweet":
        result = await twitter.get_tweet(ct0, auth_token, args.tweet_id)
    elif args.command == "replies":
        result = await twitter.get_tweet_replies(
            ct0, auth_token, args.tweet_id, args.count
        )
    else:
        raise SystemExit(f"Unknown command: {args.command}")

    emit(result, args.compact)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research",
        description="Twitter research CLI (cookie-based auth via twikit)",
    )
    parser.add_argument("--ct0", help="Override TWITTER_CT0 from .env")
    parser.add_argument("--auth-token", help="Override TWITTER_AUTH_TOKEN from .env")
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Emit single-line JSON instead of pretty-printed",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("auth", help="Verify cookies and print authenticated user info")

    p_timeline = sub.add_parser("timeline", help="Your home timeline (For You)")
    p_timeline.add_argument("--count", type=int, default=20)

    p_latest = sub.add_parser("latest", help="Your latest timeline (Following)")
    p_latest.add_argument("--count", type=int, default=20)

    p_search = sub.add_parser("search", help="Search tweets")
    p_search.add_argument("query")
    p_search.add_argument("--count", type=int, default=20)
    p_search.add_argument("--product", choices=["Top", "Latest"], default="Latest")

    p_tweet = sub.add_parser("tweet", help="Fetch a tweet by ID")
    p_tweet.add_argument("tweet_id")

    p_replies = sub.add_parser("replies", help="Fetch replies to a tweet")
    p_replies.add_argument("tweet_id")
    p_replies.add_argument("--count", type=int, default=20)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        asyncio.run(run(args))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
