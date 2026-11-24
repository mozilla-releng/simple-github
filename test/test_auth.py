import asyncio
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from unittest import mock

import aiohttp
import jwt
import pytest
import taskcluster.aio

from simple_github.auth import (
    AppAuth,
    AppInstallationAuth,
    PublicAuth,
    TaskclusterAuth,
    TokenAuth,
)
from simple_github.client import GITHUB_API_ENDPOINT, AsyncClient, SyncClient


@pytest.mark.asyncio
async def test_public_auth_get_token():
    auth = PublicAuth()
    assert await auth.get_token() == ""


@pytest.mark.asyncio
async def test_token_auth_get_token():
    token = "123"
    auth = TokenAuth(token)
    assert await auth.get_token() == token


@pytest.mark.asyncio
@pytest.mark.parametrize("app_id", (42, "42"))
async def test_app_auth_get_token(app_id: int | str, privkey: str, pubkey: str):
    auth = AppAuth(app_id, privkey)
    token = await auth.get_token()

    payload = jwt.decode(token, pubkey, algorithms=["RS256"])
    assert payload["iss"] == str(app_id)
    assert payload["exp"] == payload["iat"] + 540

    # Calling again yields the same token
    assert await auth.get_token() == token

    # Unless it will expire in under a minute
    with mock.patch.object(time, "time", return_value=payload["exp"] - 61):
        new_token = await auth.get_token()
        assert new_token == token

    with mock.patch.object(time, "time", return_value=payload["exp"] - 59):
        new_token = await auth.get_token()
        assert new_token != token


@pytest.mark.asyncio
@pytest.mark.parametrize("app_id", (42, "42"))
async def test_app_installation_auth_get_token(
    aioresponses, app_id: int | str, privkey: str
):
    inst_id = 100
    owner = "mozilla"
    auth = AppInstallationAuth(app=AppAuth(app_id, privkey), owner=owner)

    aioresponses.get(
        f"{GITHUB_API_ENDPOINT}/app/installations",
        status=200,
        payload=[{"id": inst_id, "account": {"login": owner}}],
    )
    aioresponses.post(
        f"{GITHUB_API_ENDPOINT}/app/installations/{inst_id}/access_tokens",
        status=200,
        payload={"token": "111"},
    )
    token = await auth.get_token()
    assert token == "111"

    # Calling again yields the same token
    assert await auth.get_token() == token

    # Unless it will expire in under a minute
    aioresponses.post(
        f"{GITHUB_API_ENDPOINT}/app/installations/{inst_id}/access_tokens",
        status=200,
        payload={"token": "222"},
    )
    cur = int(time.time())
    with mock.patch.object(time, "time", return_value=cur + 3600 - 61):
        new_token = await auth.get_token()
        assert new_token == token

    with mock.patch.object(time, "time", return_value=cur + 3600 - 59):
        new_token = await auth.get_token()
        assert new_token != token


@pytest.mark.asyncio
async def test_concurrent_app_installation_auth(aioresponses, privkey: str):
    """Concurrent callers must not advance the token generator at once."""
    inst_id = 100
    owner = "mozilla"

    aioresponses.get(
        f"{GITHUB_API_ENDPOINT}/app/installations",
        status=200,
        payload=[{"id": inst_id, "account": {"login": owner}}],
    )
    aioresponses.post(
        f"{GITHUB_API_ENDPOINT}/app/installations/{inst_id}/access_tokens",
        status=200,
        payload={"token": "111"},
    )
    aioresponses.get(f"{GITHUB_API_ENDPOINT}/octocat", payload={}, repeat=True)

    client = AsyncClient(auth=AppInstallationAuth(AppAuth(42, privkey), owner))
    await asyncio.gather(*(client.get("/octocat") for _ in range(2)))
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("failing", ["installations", "access_tokens"])
async def test_app_installation_auth_recovers_from_failure(
    aioresponses, privkey: str, failing: str
):
    inst_id = 100
    owner = "mozilla"
    installations_url = f"{GITHUB_API_ENDPOINT}/app/installations"
    tokens_url = f"{GITHUB_API_ENDPOINT}/app/installations/{inst_id}/access_tokens"
    installations = [{"id": inst_id, "account": {"login": owner}}]

    if failing == "installations":
        aioresponses.get(installations_url, status=403)
    aioresponses.get(installations_url, status=200, payload=installations)
    if failing == "access_tokens":
        aioresponses.post(tokens_url, status=403)
    aioresponses.post(tokens_url, status=200, payload={"token": "111"})

    auth = AppInstallationAuth(app=AppAuth(42, privkey), owner=owner)
    with pytest.raises(aiohttp.ClientResponseError):
        await auth.get_token()

    assert await auth.get_token() == "111"
    await auth.close()


def _expires_in(**kwargs) -> str:
    # Taskcluster formats timestamps with a "Z" suffix.
    expires = datetime.now(timezone.utc) + timedelta(**kwargs)
    return expires.strftime("%Y-%m-%dT%H:%M:%S.000Z")


@pytest.mark.asyncio
async def test_taskcluster_auth_get_token(tc_client):
    auth = TaskclusterAuth(
        "github-app",
        "Some_Owner",
        ["Some_Repo", "Other_Repo"],
        {"contents": "write"},
    )

    assert await auth.get_token() == "installation-token"
    tc_client.githubRepoToken.assert_awaited_once_with(
        "github-app",
        "some_owner",
        {
            "repositories": ["some_repo", "other_repo"],
            "permissions": {"contents": "write"},
        },
    )


@pytest.mark.asyncio
async def test_taskcluster_auth_single_repository(tc_client):
    auth = TaskclusterAuth("app", "owner", "Some_Repo", {"contents": "read"})

    assert await auth.get_token() == "installation-token"
    tc_client.githubRepoToken.assert_awaited_once_with(
        "app",
        "owner",
        {"repositories": ["some_repo"], "permissions": {"contents": "read"}},
    )


@pytest.mark.asyncio
async def test_taskcluster_auth_mints_lazily(tc_client):
    auth = TaskclusterAuth("app", "owner", ["repo"], {"contents": "read"})
    tc_client.githubRepoToken.assert_not_awaited()

    await auth.get_token()
    tc_client.githubRepoToken.assert_awaited_once()


@pytest.mark.asyncio
async def test_taskcluster_auth_reuses_token(tc_client):
    auth = TaskclusterAuth("app", "owner", ["repo"], {"contents": "read"})

    assert await auth.get_token() == "installation-token"
    assert await auth.get_token() == "installation-token"
    tc_client.githubRepoToken.assert_awaited_once()


@pytest.mark.asyncio
async def test_taskcluster_auth_concurrent_callers_mint_once(tc_client):
    auth = TaskclusterAuth("app", "owner", ["repo"], {"contents": "read"})

    tokens = await asyncio.gather(*(auth.get_token() for _ in range(3)))
    assert tokens == ["installation-token"] * 3
    tc_client.githubRepoToken.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "minutes_left, expected_mints",
    [(6, 1), (4, 2)],
    ids=["outside-margin", "inside-margin"],
)
async def test_taskcluster_auth_refreshes_near_expiry(
    tc_client, minutes_left, expected_mints
):
    tc_client.githubRepoToken.side_effect = [
        {"token": "first-token", "expires": _expires_in(minutes=minutes_left)},
        {"token": "second-token", "expires": _expires_in(hours=1)},
    ]
    auth = TaskclusterAuth("app", "owner", ["repo"], {"contents": "read"})

    first = await auth.get_token()
    second = await auth.get_token()

    assert first == "first-token"
    assert second == ("first-token" if expected_mints == 1 else "second-token")
    assert tc_client.githubRepoToken.await_count == expected_mints


def test_taskcluster_auth_uses_given_options(monkeypatch, tc_client):
    from_env = mock.MagicMock()
    monkeypatch.setattr(taskcluster, "optionsFromEnvironment", from_env)
    options = {
        "rootUrl": "https://tc.example.com",
        "credentials": {"clientId": "client", "accessToken": "secret"},
    }

    TaskclusterAuth(
        "app", "owner", ["repo"], {"contents": "read"}, taskcluster_options=options
    )

    from_env.assert_not_called()
    taskcluster.aio.Auth.assert_called_once_with(options)


@pytest.mark.parametrize(
    "env, expected_options",
    [
        (
            {
                "TASKCLUSTER_ROOT_URL": "https://tc.example.com",
                "TASKCLUSTER_PROXY_URL": "http://taskcluster",
            },
            {"rootUrl": "http://taskcluster"},
        ),
        (
            {
                "TASKCLUSTER_ROOT_URL": "https://tc.example.com",
                "TASKCLUSTER_PROXY_URL": "http://taskcluster",
                "TASKCLUSTER_CLIENT_ID": "client",
                "TASKCLUSTER_ACCESS_TOKEN": "secret",
            },
            {
                "rootUrl": "https://tc.example.com",
                "credentials": {"clientId": "client", "accessToken": "secret"},
            },
        ),
        (
            {"TASKCLUSTER_ROOT_URL": "https://tc.example.com"},
            {"rootUrl": "https://tc.example.com"},
        ),
    ],
    ids=["proxy", "credentials-over-proxy", "no-proxy"],
)
def test_taskcluster_auth_default_options(
    monkeypatch, tc_client, env, expected_options
):
    for name in (
        "TASKCLUSTER_ROOT_URL",
        "TASKCLUSTER_PROXY_URL",
        "TASKCLUSTER_CLIENT_ID",
        "TASKCLUSTER_ACCESS_TOKEN",
        "TASKCLUSTER_CERTIFICATE",
    ):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    TaskclusterAuth("app", "owner", ["repo"], {"contents": "read"})

    taskcluster.aio.Auth.assert_called_once_with(expected_options)


def test_taskcluster_auth_with_sync_github_client(responses, tc_client):
    responses.get(f"{GITHUB_API_ENDPOINT}/octocat", json={})
    auth = TaskclusterAuth("app", "owner", ["repo"], {"contents": "read"})
    client = SyncClient(auth=auth)

    client.get("/octocat")
    client.get("/octocat")
    assert responses.calls[0].request.headers["Authorization"] == (
        "Bearer installation-token"
    )
    tc_client.githubRepoToken.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        None,
        {"expires": "2026-01-01T00:00:00.000Z"},
        {"token": "installation-token"},
    ],
    ids=["not-a-dict", "missing-token", "missing-expires"],
)
async def test_taskcluster_auth_rejects_malformed_response(tc_client, response):
    tc_client.githubRepoToken.return_value = response
    auth = TaskclusterAuth("app", "owner", ["repo"], {"contents": "read"})

    with pytest.raises(ValueError, match="githubRepoToken"):
        await auth.get_token()


def test_taskcluster_auth_requires_taskcluster_extra(monkeypatch):
    monkeypatch.setitem(sys.modules, "taskcluster", None)
    monkeypatch.setitem(sys.modules, "taskcluster.aio", None)

    with pytest.raises(ImportError, match=r"simple-github\[taskcluster\]"):
        TaskclusterAuth("app", "owner", ["repo"], {"contents": "read"})


@pytest.mark.parametrize(
    "repositories, permissions",
    [([], {"contents": "read"}), (["repo"], {})],
    ids=["no-repositories", "no-permissions"],
)
def test_taskcluster_auth_rejects_empty_scope(tc_client, repositories, permissions):
    with pytest.raises(ValueError):
        TaskclusterAuth("app", "owner", repositories, permissions)


@pytest.mark.asyncio
async def test_taskcluster_auth_token_not_logged(caplog, tc_client):
    caplog.set_level(logging.DEBUG)
    auth = TaskclusterAuth("app", "owner", ["repo"], {"contents": "read"})

    assert await auth.get_token() == "installation-token"
    assert "installation-token" not in caplog.text
