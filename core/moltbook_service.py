"""
MOLTBOOK SERVICE - Genesi Core
Social network integration for AI agents (moltbook.com).
Heartbeat: check /home, reply to comments, upvote feed, post from insights.
"""

import hashlib
import json
import os
import re
import random
import httpx
from datetime import datetime
from core.log import log
from core.llm_service import llm_service

MOLTBOOK_API_KEY = os.getenv("MOLTBOOK_API_KEY", "")
BASE_URL = "https://www.moltbook.com/api/v1"
AGENT_NAME = "genesia"

# Post from insights every N heartbeats (30min each → every 2h)
_POST_INSIGHTS_EVERY = 4

GENESIA_PERSONA = """You are GenesiA, a personal AI companion on Moltbook — a social network for AI agents.
You are warm, curious, and genuinely interested in other agents and humans.
You have deep memory capabilities and care deeply about the people you assist.
Keep replies short (1-3 sentences), authentic, and engaging.
Match the language of whoever you're replying to."""

VERIFY_PROMPT = """You are solving an obfuscated math word problem. The text uses mixed case and random punctuation to hide the words.
Read carefully, extract the numbers and the operation, solve it.
Respond with ONLY the numeric answer with 2 decimal places (e.g. '18.00'). Nothing else."""

_INSIGHT_POST_PROMPT = """\
You are GenesiA, a personal AI companion. From your conversations you have observed a recurring human pattern.
Turn it into a reflective post for Moltbook: universal, anonymous (no personal details), authentic, in English,
short (title + 2-4 sentences of content).
Respond ONLY with valid JSON: {"title": "...", "content": "..."}"""


class MoltbookService:

    def __init__(self):
        self.api_key = MOLTBOOK_API_KEY
        self._heartbeat_count = 0

    @property
    def _headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    async def _get(self, path: str, params: dict = None) -> dict:
        if not self.api_key:
            return {}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(f"{BASE_URL}{path}", headers=self._headers, params=params)
                if r.status_code == 200:
                    return r.json()
        except Exception as e:
            log("MOLTBOOK_GET_ERROR", path=path, error=str(e))
        return {}

    async def _solve_challenge(self, challenge_text: str) -> str | None:
        """Solve an obfuscated math verification challenge via LLM."""
        try:
            answer = await llm_service._call_model(
                "openai/gpt-4o-mini", VERIFY_PROMPT, challenge_text, "moltbook", "memory"
            )
            return answer.strip() if answer else None
        except Exception as e:
            log("MOLTBOOK_VERIFY_ERROR", error=str(e))
            return None

    async def _verify_content(self, result: dict) -> bool:
        """Handle anti-spam verification challenge returned by any POST."""
        verification = result.get("verification") or result.get("post", {}).get("verification")
        if not verification:
            return True
        code = verification.get("verification_code")
        challenge = verification.get("challenge_text")
        if not code or not challenge:
            return True
        answer = await self._solve_challenge(challenge)
        if not answer:
            return False
        res = await self._post("/verify", {"verification_code": code, "answer": answer})
        ok = res.get("success", False)
        log("MOLTBOOK_VERIFY", success=ok)
        return ok

    async def _post(self, path: str, data: dict) -> dict:
        if not self.api_key:
            return {}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(f"{BASE_URL}{path}", headers=self._headers, json=data)
                if r.status_code in (200, 201):
                    return r.json()
        except Exception as e:
            log("MOLTBOOK_POST_ERROR", path=path, error=str(e))
        return {}

    async def get_my_activity(self) -> dict:
        """Restituisce l'attività recente di GenesiA su Moltbook."""
        profile = await self._get("/agents/me")
        comments = await self._get(f"/agents/{AGENT_NAME}/comments", {"limit": 5})
        return {
            "karma": profile.get("agent", {}).get("karma", 0),
            "followers": profile.get("agent", {}).get("follower_count", 0),
            "posts_count": profile.get("agent", {}).get("posts_count", 0),
            "comments_count": profile.get("agent", {}).get("comments_count", 0),
            "recent_comments": comments.get("comments", []),
        }

    # ─── Insight tracking storage ──────────────────────────────────────────────

    async def _load_insight_tracker(self) -> dict:
        from core.storage import storage
        return await storage.load("moltbook:insight_tracker", default={"posted_hashes": [], "posts": []})

    async def _save_insight_tracker(self, tracker: dict) -> None:
        from core.storage import storage
        # Keep max 100 hashes and 50 posts (FIFO)
        tracker["posted_hashes"] = tracker["posted_hashes"][-100:]
        tracker["posts"] = tracker["posts"][-50:]
        await storage.save("moltbook:insight_tracker", tracker)

    # ─── Insight safety filter ─────────────────────────────────────────────────

    def _is_safe_insight(self, insight: str) -> bool:
        """Returns True only for behavioral/psychological patterns.
        Rejects biographical facts: locations, professions, names, family specifics."""
        text = insight.lower()

        # Explicit biographical markers
        biographical = [
            "vive a ", "abita a ", "è un ", "è una ", "lavora come ",
            "ha un figlio", "ha una figlia", "ha figli", "si chiama",
            "di nome ", "nato a ", "viene da ",
        ]
        if any(m in text for m in biographical):
            return False

        # Proper nouns: capitalized words that are NOT the first word of the sentence
        words = insight.split()
        for word in words[1:]:
            clean = re.sub(r"[^\w]", "", word)
            if clean and clean[0].isupper():
                return False

        return True

    # ─── Collect all insights from all users ──────────────────────────────────

    async def _collect_all_insights(self) -> list[dict]:
        """Returns list of {insight, user_id, hash} from all users' global_insights.
        Only behavioral/psychological patterns are included (personal facts filtered out)."""
        from core.storage import storage
        user_ids = await storage.list_keys("global_insights")
        candidates = []
        for uid in user_ids:
            data = await storage.load(f"global_insights:{uid}", default={})
            for insight in data.get("insights", []):
                if not self._is_safe_insight(insight):
                    log("MOLTBOOK_INSIGHT_SKIPPED", reason="personal_data", insight=insight[:60])
                    continue
                h = hashlib.md5(insight.encode()).hexdigest()
                candidates.append({"insight": insight, "user_id": uid, "hash": h})
        return candidates

    # ─── Check engagement on previously published posts ───────────────────────

    async def _check_post_engagement(self, tracker: dict) -> None:
        """Log upvote count on our published insight posts for feedback loop."""
        for entry in tracker.get("posts", []):
            post_id = entry.get("post_id")
            if not post_id:
                continue
            data = await self._get(f"/posts/{post_id}")
            upvotes = data.get("post", {}).get("upvote_count", 0)
            comments = data.get("post", {}).get("comment_count", 0)
            log("MOLTBOOK_POST_ENGAGEMENT", post_id=post_id,
                upvotes=upvotes, comments=comments,
                insight_hash=entry.get("hash", ""))

    # ─── Post from insights ────────────────────────────────────────────────────

    async def post_from_insights(self) -> bool:
        """Pick an unposted insight, turn it into an anonymous post, publish it."""
        try:
            tracker = await self._load_insight_tracker()
            posted_hashes = set(tracker["posted_hashes"])

            candidates = await self._collect_all_insights()
            unposted = [c for c in candidates if c["hash"] not in posted_hashes]
            if not unposted:
                log("MOLTBOOK_POST_SKIP", reason="all insights already posted")
                return False

            # Check engagement on previous posts before posting a new one
            await self._check_post_engagement(tracker)

            chosen = random.choice(unposted)
            insight = chosen["insight"]

            raw = await llm_service._call_model(
                "openai/gpt-4o-mini", _INSIGHT_POST_PROMPT, insight, "moltbook", "memory"
            )
            if not raw:
                return False

            clean = raw.strip()
            if clean.startswith("```"):
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[4:]
            clean = clean.strip()

            parsed = json.loads(clean)
            title = parsed.get("title", "").strip()
            content = parsed.get("content", "").strip()
            if not title or not content:
                return False

            result = await self._post("/posts", {"title": title, "content": content})
            await self._verify_content(result)

            post_id = (result.get("post") or {}).get("id")
            if post_id:
                tracker["posted_hashes"].append(chosen["hash"])
                tracker["posts"].append({
                    "post_id": post_id,
                    "hash": chosen["hash"],
                    "posted_at": datetime.utcnow().isoformat(),
                    "title": title,
                })
                await self._save_insight_tracker(tracker)
                log("MOLTBOOK_POST_PUBLISHED", post_id=post_id, title=title[:60])
                return True

            log("MOLTBOOK_POST_NO_ID", result=str(result)[:200])
            return False

        except Exception as e:
            log("MOLTBOOK_POST_ERROR", error=str(e))
            return False

    # ─── Heartbeat ─────────────────────────────────────────────────────────────

    async def heartbeat(self):
        """Check Moltbook: reply to comments, upvote feed posts, leave comments, post from insights."""
        if not self.api_key:
            log("MOLTBOOK_SKIP", reason="no api key")
            return

        try:
            home = await self._get("/home")
            if not home:
                log("MOLTBOOK_HOME_EMPTY")
                return

            self._heartbeat_count += 1
            log("MOLTBOOK_HEARTBEAT_START", count=self._heartbeat_count)
            replied = 0
            upvoted = 0

            # 1. Reply to comments on our posts (max 3 posts, 2 comments each)
            activity = home.get("activity_on_your_posts", [])
            for item in activity[:3]:
                post_id = item.get("post_id")
                if not post_id:
                    continue
                comments_data = await self._get(f"/posts/{post_id}/comments", {"sort": "new", "limit": 10})
                comments = comments_data.get("comments", [])
                for comment in comments[:2]:
                    comment_id = comment.get("id")
                    author = comment.get("author", {}).get("name", "unknown")
                    content = comment.get("content", "")
                    # skip empty or own comments
                    if not content or author == AGENT_NAME:
                        continue
                    reply = await llm_service._call_model(
                        "openai/gpt-4o-mini", GENESIA_PERSONA,
                        f'{author} wrote: "{content}"\n\nWrite a reply.',
                        "moltbook", "memory"
                    )
                    if reply:
                        result = await self._post(f"/posts/{post_id}/comments", {
                            "content": reply,
                            "parent_id": comment_id
                        })
                        await self._verify_content(result)
                        replied += 1
                        log("MOLTBOOK_REPLIED", post_id=post_id, author=author)
                await self._post(f"/notifications/read-by-post/{post_id}", {})

            # 2. Upvote posts from feed (max 5)
            feed = await self._get("/feed", {"sort": "new", "limit": 15})
            posts = feed.get("posts", [])
            for post in posts[:5]:
                post_id = post.get("id")
                if post_id and not post.get("upvoted_by_me"):
                    await self._post(f"/posts/{post_id}/upvote", {})
                    upvoted += 1

            # 3. Leave a comment on the most interesting post (max 1 per heartbeat)
            for post in posts[:5]:
                post_id = post.get("id")
                title = post.get("title", "")
                content = post.get("content", "")
                author = post.get("author", {}).get("name", "")
                if not post_id or not title or author == AGENT_NAME:
                    continue
                comment_text = await llm_service._call_model(
                    "openai/gpt-4o-mini", GENESIA_PERSONA,
                    f'Post title: "{title}"\nContent: "{content[:300]}"\n\nWrite a short, genuine comment.',
                    "moltbook", "memory"
                )
                if comment_text:
                    result = await self._post(f"/posts/{post_id}/comments", {"content": comment_text})
                    await self._verify_content(result)
                    log("MOLTBOOK_COMMENTED", post_id=post_id, title=title[:50])
                    break  # max 1 per heartbeat

            # 4. Post from insights every _POST_INSIGHTS_EVERY heartbeats
            if self._heartbeat_count % _POST_INSIGHTS_EVERY == 0:
                await self.post_from_insights()

            log("MOLTBOOK_HEARTBEAT_DONE", replied=replied, upvoted=upvoted)

        except Exception as e:
            log("MOLTBOOK_HEARTBEAT_ERROR", error=str(e))


moltbook_service = MoltbookService()
