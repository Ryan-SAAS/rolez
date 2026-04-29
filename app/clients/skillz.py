from __future__ import annotations

import httpx


class SkillzError(Exception):
    pass


class SkillzNotFound(SkillzError):
    pass


class SkillzClient:
    def __init__(self, base_url: str, token: str, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "User-Agent": "rolez/0.1 (+skillz-client)",
        }

    async def get_skill(self, name: str) -> dict:
        url = f"{self.base_url}/api/v1/skills/{name}"
        async with httpx.AsyncClient(timeout=self.timeout) as http:
            resp = await http.get(url, headers=self._headers())
        if resp.status_code == 404:
            raise SkillzNotFound(f"skill {name!r} not found upstream")
        if resp.status_code >= 400:
            raise SkillzError(f"skillz returned {resp.status_code}: {resp.text}")
        return resp.json()
