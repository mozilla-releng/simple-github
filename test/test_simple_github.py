import pytest

from simple_github import AppClient, PublicClient, TokenClient, client_from_env
from simple_github.client import GITHUB_API_ENDPOINT


@pytest.mark.asyncio
async def test_public_client(aioresponses):
    aioresponses.get(
        f"{GITHUB_API_ENDPOINT}/octocat", status=200, payload={"foo": "bar"}
    )

    async with PublicClient() as client:
        resp = await client.get("/octocat")
        result = await resp.json()
        assert result == {"foo": "bar"}


@pytest.mark.asyncio
async def test_token_client(aioresponses):
    aioresponses.get(
        f"{GITHUB_API_ENDPOINT}/octocat", status=200, payload={"foo": "bar"}
    )

    async with TokenClient("abc") as client:
        resp = await client.get("/octocat")
        result = await resp.json()
        assert result == {"foo": "bar"}


@pytest.mark.asyncio
async def test_app_client(aioresponses, privkey):
    aioresponses.get(
        f"{GITHUB_API_ENDPOINT}/octocat", status=200, payload={"foo": "bar"}
    )

    async with AppClient(id=123, privkey=privkey) as client:
        resp = await client.get("/octocat")
        result = await resp.json()
        assert result == {"foo": "bar"}


@pytest.mark.asyncio
async def test_app_installation_client(aioresponses, privkey):
    owner = "owner"
    inst_id = 1

    aioresponses.get(
        f"{GITHUB_API_ENDPOINT}/app/installations",
        status=200,
        payload=[{"id": inst_id, "account": {"login": owner}}],
    )
    aioresponses.post(
        f"{GITHUB_API_ENDPOINT}/app/installations/{inst_id}/access_tokens",
        status=200,
        payload={"token": "789"},
    )
    aioresponses.get(
        f"{GITHUB_API_ENDPOINT}/octocat", status=200, payload={"foo": "bar"}
    )

    async with AppClient(id=123, privkey=privkey, owner=owner) as client:
        resp = await client.get("/octocat")
        result = await resp.json()
        assert result == {"foo": "bar"}


@pytest.mark.parametrize(
    "env,expected_client",
    (
        pytest.param(
            {"GITHUB_TOKEN": "fake"},
            TokenClient,
            id="token",
        ),
        pytest.param(
            {"GITHUB_APP_ID": "123", "GITHUB_APP_PRIVKEY": "fake"},
            AppClient,
            id="app",
        ),
        pytest.param(
            {},
            PublicClient,
            id="public",
        ),
    ),
)
def test_client_from_env(monkeypatch, env, expected_client):
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    client_func = client_from_env("owner", ["repo"])
    if hasattr(client_func, "func"):
        client_func = client_func.func
    assert client_func == expected_client
