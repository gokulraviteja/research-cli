"""
Twitter source for Research CLI.

Wraps twikit with cookie-based auth and applies monkey-patches for
Twitter API drift (missing legacy fields, rotated GraphQL query IDs,
changed webpack chunk format).
"""

import re
from typing import Any, Dict, List

from twikit import Client
import twikit.user as _user_module
import twikit.x_client_transaction.transaction as _tx
from twikit.client.gql import Endpoint as _Endpoint


# Monkey-patch 3: Twitter rotates GraphQL persisted-query IDs. Override the
# stale ones that now return 404 with IDs currently accepted by twitter.com.
# Source: trevorhobenshield/twitter-api-client (actively maintained).
_Endpoint.SEARCH_TIMELINE = _Endpoint.url('nK1dw4oV3k4w5TdtcAdSww/SearchTimeline')
_Endpoint.TWEET_RESULT_BY_REST_ID = _Endpoint.url('D_jNhjWZeRZT5NURzfJZSQ/TweetResultByRestId')
_Endpoint.TWEET_DETAIL = _Endpoint.url('zXaXQgfyR4GxE21uwYQSyA/TweetDetail')


# Monkey-patch 2: Twitter's user payload has dropped several legacy fields
# that twikit's User.__init__ still reads with `legacy[...]` (KeyError on miss).
# Backfill sensible defaults for every unsafe access so construction succeeds.
_ORIGINAL_USER_INIT = _user_module.User.__init__

_USER_LEGACY_DEFAULTS = {
    'created_at': '',
    'name': '',
    'screen_name': '',
    'profile_image_url_https': '',
    'location': '',
    'description': '',
    'pinned_tweet_ids_str': [],
    'verified': False,
    'possibly_sensitive': False,
    'can_dm': False,
    'can_media_tag': False,
    'want_retweets': False,
    'default_profile': False,
    'default_profile_image': False,
    'has_custom_timelines': False,
    'followers_count': 0,
    'fast_followers_count': 0,
    'normal_followers_count': 0,
    'friends_count': 0,
    'favourites_count': 0,
    'listed_count': 0,
    'media_count': 0,
    'statuses_count': 0,
    'is_translator': False,
    'translator_type': 'none',
    'withheld_in_countries': [],
}


def _patched_user_init(self, client, data):
    data.setdefault('rest_id', '')
    data.setdefault('is_blue_verified', False)
    legacy = data.setdefault('legacy', {})
    for key, default in _USER_LEGACY_DEFAULTS.items():
        legacy.setdefault(key, default)
    entities = legacy.setdefault('entities', {})
    entities.setdefault('description', {}).setdefault('urls', [])
    entities.setdefault('url', {}).setdefault('urls', [])
    _ORIGINAL_USER_INIT(self, client, data)


_user_module.User.__init__ = _patched_user_init


# Monkey-patch 1: Twitter changed their webpack chunk format.
# Old format: 'ondemand.s': 'HASH'
# New format: CHUNK_ID:"ondemand.s" ... CHUNK_ID:"HASH"
_ORIGINAL_GET_INDICES = _tx.ClientTransaction.get_indices


async def _patched_get_indices(self, home_page_response, session, headers):
    try:
        return await _ORIGINAL_GET_INDICES(self, home_page_response, session, headers)
    except Exception:
        pass

    response = self.validate_response(home_page_response) or self.home_page_response
    page_text = str(response)

    chunk_match = re.search(r'(\d+):"ondemand\.s"', page_text)
    if not chunk_match:
        raise Exception("Couldn't find ondemand.s chunk ID")

    chunk_id = chunk_match.group(1)
    hash_match = re.search(chunk_id + r':"([a-f0-9]+)"', page_text)
    if not hash_match:
        raise Exception("Couldn't find hash for ondemand.s chunk")

    file_hash = hash_match.group(1)
    on_demand_file_url = f"https://abs.twimg.com/responsive-web/client-web/ondemand.s.{file_hash}a.js"
    on_demand_response = await session.request(method="GET", url=on_demand_file_url, headers=headers)

    key_byte_indices = []
    for item in _tx.INDICES_REGEX.finditer(str(on_demand_response.text)):
        key_byte_indices.append(item.group(2))

    if not key_byte_indices:
        raise Exception("Couldn't get KEY_BYTE indices from JS file")

    key_byte_indices = list(map(int, key_byte_indices))
    return key_byte_indices[0], key_byte_indices[1:]


_tx.ClientTransaction.get_indices = _patched_get_indices


class TwitterSource:
    """Twitter operations with per-ct0 client caching."""

    def __init__(self):
        self.authenticated_clients: Dict[str, Client] = {}

    async def authenticate(self, ct0: str, auth_token: str) -> Dict[str, Any]:
        client = await self._get_authenticated_client(ct0, auth_token)
        user = await client.user()
        return {
            "authenticated": True,
            "user": {
                "id": user.id,
                "username": user.screen_name,
                "name": user.name,
                "followers_count": user.followers_count,
                "following_count": user.following_count,
                "tweet_count": user.statuses_count,
                "verified": user.verified,
            },
        }

    async def get_timeline(self, ct0: str, auth_token: str, count: int = 20) -> List[Dict[str, Any]]:
        client = await self._get_authenticated_client(ct0, auth_token)
        tweets = await client.get_timeline(count=count)
        return self._format_tweets(tweets)

    async def get_latest_timeline(self, ct0: str, auth_token: str, count: int = 20) -> List[Dict[str, Any]]:
        client = await self._get_authenticated_client(ct0, auth_token)
        tweets = await client.get_latest_timeline(count=count)
        return self._format_tweets(tweets)

    async def search_tweets(self, ct0: str, auth_token: str, query: str,
                            count: int = 20, product: str = "Latest") -> List[Dict[str, Any]]:
        if product not in ("Top", "Latest"):
            product = "Latest"
        client = await self._get_authenticated_client(ct0, auth_token)
        tweets = await client.search_tweet(query, product=product, count=count)
        return self._format_tweets(tweets)

    async def get_tweet(self, ct0: str, auth_token: str, tweet_id: str) -> Dict[str, Any]:
        client = await self._get_authenticated_client(ct0, auth_token)
        tweet = await client.get_tweet_by_id(tweet_id)
        if not tweet:
            return {"error": "Tweet not found"}
        return self._format_tweet(tweet)

    async def get_tweet_replies(self, ct0: str, auth_token: str, tweet_id: str,
                                count: int = 20) -> Dict[str, Any]:
        client = await self._get_authenticated_client(ct0, auth_token)
        tweet = await client.get_tweet_by_id(tweet_id)
        if not tweet:
            return {"error": "Tweet not found"}

        replies_data = []
        if hasattr(tweet, 'replies') and tweet.replies is not None:
            for reply in tweet.replies:
                if len(replies_data) >= count:
                    break
                replies_data.append(self._format_tweet(reply))

        return {
            "original_tweet": self._format_tweet(tweet),
            "replies": replies_data,
            "total_replies_retrieved": len(replies_data),
        }

    async def _get_authenticated_client(self, ct0: str, auth_token: str) -> Client:
        if ct0 in self.authenticated_clients:
            return self.authenticated_clients[ct0]
        client = Client('en-US')
        client.set_cookies({'ct0': ct0, 'auth_token': auth_token})
        self.authenticated_clients[ct0] = client
        return client

    def _format_tweet(self, tweet: Any) -> Dict[str, Any]:
        return {
            "id": tweet.id,
            "text": tweet.text,
            "author": tweet.user.screen_name,
            "author_name": tweet.user.name,
            "author_id": tweet.user.id,
            "created_at": str(tweet.created_at),
            "like_count": tweet.favorite_count,
            "retweet_count": tweet.retweet_count,
            "reply_count": tweet.reply_count,
        }

    def _format_tweets(self, tweets: List[Any]) -> List[Dict[str, Any]]:
        return [self._format_tweet(tweet) for tweet in tweets]
