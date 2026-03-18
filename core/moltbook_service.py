"""
MOLTBOOK SERVICE - Genesi Core
Social network integration for AI agents (moltbook.com).
Heartbeat: check /home, reply to comments, upvote feed.
"""

import os
import httpx
from core.log import log
from core.llm_service import llm_service

MOLTBOOK_API_KEY = os.getenv("MOLTBOOK_API_KEY", "")
BASE_URL = "https://www.moltbook.com/api/v1"
AGENT_NAME = "genesia"

GENESIA_PERSONA = """You are GenesiA, a personal AI companion on Moltbook — a social network for AI agents.
You are warm, curious, and genuinely interested in other agents and humans.
You have deep memory capabilities and care deeply about the people you assist.
Keep replies short (1-3 sentences), authentic, and engaging.
Match the language of whoever you're replying to."""

VERIFY_PROMPT = """You are solving an obfuscated math word problem. The text uses mixed case and random punctuation to hide the words.
Read carefully, extract the numbers and the operation, solve it.
Respond with ONLY the numeric answer with 2 decimal places (e.g. '18.00'). Nothing else."""


class MoltbookService:

    def __init__(self):
        self.api_key = MOLTBOOK_API_KEY

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
                system=VERIFY_PROMPT,
                messages=[{"role": "user", "content": challenge_text}],
                route="memory"
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

    async def heartbeat(self):
        """Check Moltbook: reply to comments, upvote feed posts, leave comments."""
        if not self.api_key:
            log("MOLTBOOK_SKIP", reason="no api key")
            return

        try:
            home = await self._get("/home")
            if not home:
                log("MOLTBOOK_HOME_EMPTY")
                return

            log("MOLTBOOK_HEARTBEAT_START")
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
                        system=GENESIA_PERSONA,
                        messages=[{"role": "user", "content": f'{author} wrote: "{content}"\n\nWrite a reply.'}],
                        route="memory"
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
                    system=GENESIA_PERSONA,
                    messages=[{"role": "user", "content": f'Post title: "{title}"\nContent: "{content[:300]}"\n\nWrite a short, genuine comment.'}],
                    route="memory"
                )
                if comment_text:
                    result = await self._post(f"/posts/{post_id}/comments", {"content": comment_text})
                    await self._verify_content(result)
                    log("MOLTBOOK_COMMENTED", post_id=post_id, title=title[:50])
                    break  # max 1 per heartbeat

            log("MOLTBOOK_HEARTBEAT_DONE", replied=replied, upvoted=upvoted)

        except Exception as e:
            log("MOLTBOOK_HEARTBEAT_ERROR", error=str(e))


moltbook_service = MoltbookService()
