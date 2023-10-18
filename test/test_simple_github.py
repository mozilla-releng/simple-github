import pytest

from simple_github import AppClient, TokenClient


@pytest.mark.asyncio
async def test_token_client(aioresponses):
    aioresponses.get("/octocat", status=200, payload={"foo": "bar"})

    async with TokenClient("abc") as client:
        result = await client.get("/octocat")
        assert result == {"foo": "bar"}


@pytest.mark.asyncio
async def test_app_client(aioresponses, privkey):
    aioresponses.get("/octocat", status=200, payload={"foo": "bar"})

    async with AppClient(id=123, privkey=privkey) as client:
        result = await client.get("/octocat")
        assert result == {"foo": "bar"}


@pytest.mark.asyncio
async def test_app_installation_client(aioresponses, privkey):
    owner = "owner"
    inst_id = 1

    aioresponses.get(
        "/app/installations",
        status=200,
        payload=[{"id": inst_id, "account": {"login": owner}}],
    )
    aioresponses.post(
        f"/app/installations/{inst_id}/access_tokens",
        status=200,
        payload={"token": "789"},
    )
    aioresponses.get("/octocat", status=200, payload={"foo": "bar"})

    async with AppClient(id=123, privkey=privkey, owner=owner) as client:
        result = await client.get("/octocat")
        assert result == {"foo": "bar"}
