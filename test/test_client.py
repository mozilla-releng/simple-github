import asyncio
from unittest import mock

import pytest
import pytest_asyncio
import requests
from aiohttp import ClientResponseError
from gql import Client as GqlClient
from gql.client import ReconnectingAsyncClientSession, SyncClientSession
from requests.exceptions import HTTPError

from simple_github.auth import TokenAuth
from simple_github.client import (
    GITHUB_API_ENDPOINT,
    GITHUB_GRAPHQL_ENDPOINT,
    AsyncClient,
    SyncClient,
)


@pytest_asyncio.fixture
async def async_client():
    client = AsyncClient(auth=TokenAuth("abc"))
    yield client
    await client.close()


@pytest.fixture
def sync_client():
    client = SyncClient(auth=TokenAuth("abc"))
    yield client
    client.close()


@pytest.mark.asyncio
async def test_async_client_get_session(async_client):
    client = async_client
    assert client._gql_client is None
    assert client._gql_session is None

    session = await client._get_aiohttp_session()
    assert isinstance(client._gql_client, GqlClient)
    assert isinstance(client._gql_session, ReconnectingAsyncClientSession)

    assert client._gql_session.transport.session == session
    assert dict(session._default_headers) == {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {client.auth._token}",
    }

    # Calling get_session again returns the same session
    assert await client._get_aiohttp_session() == session

    # Unless the token has changed
    client.auth._token = "def"
    new_session = await client._get_aiohttp_session()
    assert new_session != session
    assert session.closed
    assert dict(new_session._default_headers) == {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {client.auth._token}",
    }


@pytest.mark.asyncio
async def test_async_client_get_session_concurrent(async_client):
    """Concurrent callers all get a session, none observe a partial setup."""
    client = async_client

    sessions = await asyncio.gather(*(client._get_aiohttp_session() for _ in range(25)))

    assert isinstance(client._gql_session, ReconnectingAsyncClientSession)
    assert all(s == sessions[0] for s in sessions)


@pytest.mark.asyncio
async def test_async_client_get_session_no_token(async_client):
    client = async_client
    client.auth._token = ""
    session = await client._get_aiohttp_session()
    assert dict(session._default_headers) == {
        "Accept": "application/vnd.github+json",
    }


@pytest.mark.asyncio
async def test_async_client_recovers_from_connection_failure(async_client):
    """A failed connect leaves nothing cached, so the next call retries."""
    client = async_client

    with mock.patch.object(
        GqlClient, "connect_async", side_effect=OSError("no route to host")
    ):
        with pytest.raises(OSError):
            await client._get_gql_session()

    assert client._prev_token is None

    session = await client._get_aiohttp_session()
    assert dict(session._default_headers) == {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {client.auth._token}",
    }


def test_sync_client_get_session(sync_client):
    client = sync_client
    assert client._gql_client is None
    assert client._gql_session is None

    session = client._get_requests_session()
    assert isinstance(client._gql_client, GqlClient)
    print(client._gql_session)
    assert isinstance(client._gql_session, SyncClientSession)

    assert client._gql_session.transport.session == session
    assert dict(client._gql_session.transport.headers) == {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {client.auth._token}",
    }

    # Calling get_session again returns the same session
    assert client._get_requests_session() == session

    # Unless the token has changed
    client.auth._token = "def"
    new_session = client._get_requests_session()
    assert new_session != session
    assert dict(client._gql_session.transport.headers) == {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {client.auth._token}",
    }


def test_sync_client_get_session_no_token(sync_client):
    client = sync_client
    client.auth._token = ""
    client._get_requests_session()
    assert dict(client._gql_session.transport.headers) == {
        "Accept": "application/vnd.github+json",
    }


def test_sync_client_recovers_from_connection_failure(sync_client):
    """A failed connect leaves nothing cached, so the next call retries."""
    client = sync_client

    with mock.patch.object(
        GqlClient, "connect_sync", side_effect=OSError("no route to host")
    ):
        with pytest.raises(OSError):
            client._get_gql_session()

    assert client._prev_token is None

    client._get_requests_session()
    assert dict(client._gql_session.transport.headers) == {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {client.auth._token}",
    }


@pytest.mark.asyncio
async def test_async_client_rest(aioresponses, async_client):
    client = async_client
    url = f"{GITHUB_API_ENDPOINT}/octocat"

    aioresponses.get(url, status=200, payload={"answer": 42})
    resp = await client.get("/octocat")
    result = await resp.json()
    assert result == {"answer": 42}
    assert_correct_aiorequest_headers(aioresponses, url, "GET")

    aioresponses.post(url, status=200, payload={"answer": 42})
    resp = await client.post("/octocat", data={"foo": "bar"})
    result = await resp.json()
    assert result == {"answer": 42}
    assert_correct_aiorequest_headers(aioresponses, url, "POST")

    aioresponses.put(url, status=200, payload={"answer": 42})
    resp = await client.put("/octocat", data={"foo": "bar"})
    result = await resp.json()
    assert result == {"answer": 42}
    assert_correct_aiorequest_headers(aioresponses, url, "PUT")

    aioresponses.patch(url, status=200, payload={"answer": 42})
    resp = await client.patch("/octocat", data={"foo": "bar"})
    result = await resp.json()
    assert result == {"answer": 42}
    assert_correct_aiorequest_headers(aioresponses, url, "PATCH")

    aioresponses.delete(url, status=200)
    await client.delete("/octocat")
    aioresponses.assert_called_with(
        url,
        "DELETE",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer abc",
        },
        data="null",
        allow_redirects=True,
        # internal aiohttp-retry tracking data
        trace_request_ctx=mock.ANY,
    )
    assert_correct_aiorequest_headers(aioresponses, url, "DELETE")

    aioresponses.get(url, status=401)
    with pytest.raises(ClientResponseError):
        resp = await client.get("/octocat")
        resp.raise_for_status()


def assert_correct_aiorequest_headers(aioresponses, url: str, method: str = "GET"):
    aioresponses.assert_called_with(
        url,
        method=method,
        args_to_match=["headers"],
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer abc",
        },
    )


@pytest.mark.asyncio
async def test_async_client_retries_on_5xx(aioresponses, async_client):
    client = async_client
    url = f"{GITHUB_API_ENDPOINT}/octocat"

    aioresponses.get(url, status=502)
    aioresponses.get(url, status=200, payload={"answer": 42})

    resp = await client.get("/octocat")
    result = await resp.json()
    assert result == {"answer": 42}


def test_sync_client_rest(responses, sync_client):
    client = sync_client
    url = f"{GITHUB_API_ENDPOINT}/octocat"

    get_mock = responses.get(url, status=200, json={"answer": 42})
    resp = client.get("/octocat")
    result = resp.json()
    assert result == {"answer": 42}
    assert_correct_request_headers(get_mock.calls[0].request)

    post_mock = responses.post(url, status=200, json={"answer": 42})
    resp = client.post("/octocat", data={"foo": "bar"})
    result = resp.json()
    assert result == {"answer": 42}
    assert_correct_request_headers(post_mock.calls[0].request)

    put_mock = responses.put(url, status=200, json={"answer": 42})
    resp = client.put("/octocat", data={"foo": "bar"})
    result = resp.json()
    assert result == {"answer": 42}
    assert_correct_request_headers(put_mock.calls[0].request)

    patch_mock = responses.patch(url, status=200, json={"answer": 42})
    resp = client.patch("/octocat", data={"foo": "bar"})
    result = resp.json()
    assert result == {"answer": 42}
    assert_correct_request_headers(patch_mock.calls[0].request)

    delete_mock = responses.delete(url, status=200)
    client.delete("/octocat")
    resp = responses.calls[-1].response
    assert resp.url == url
    assert resp.request.method == "DELETE"
    assert resp.status_code == 200
    assert_correct_request_headers(delete_mock.calls[0].request)

    responses.get(url, status=401)
    with pytest.raises(HTTPError):
        resp = client.get("/octocat")
        resp.raise_for_status()


def assert_correct_request_headers(request: requests.Request):
    # We want to retain the original request headers.
    default_request_headers = requests.Session().headers
    for hdr, val in default_request_headers.items():
        if hdr.lower() in ["accept", "authorization"]:
            continue
        assert (
            request.headers[hdr] == val
        ), "Incorrectly inherited header from the original requests session"

    assert (
        request.headers["accept"] == "application/vnd.github+json"
    ), "Incorrect Accept in request to GitHub REST API"
    assert (
        request.headers["authorization"] == "Bearer abc"
    ), "Incorrect Authorization in request to GitHub REST API"


def test_sync_client_retries_on_5xx(responses, sync_client):
    client = sync_client
    url = f"{GITHUB_API_ENDPOINT}/octocat"

    responses.get(url, status=502)
    responses.get(url, status=200, json={"answer": 42})

    resp = client.get("/octocat")
    result = resp.json()
    assert result == {"answer": 42}


@pytest.mark.asyncio
async def test_async_client_rest_with_text(aioresponses, async_client):
    client = async_client
    text = "Favour focus over features"
    aioresponses.get(
        f"{GITHUB_API_ENDPOINT}/octocat",
        content_type="application/octocat-stream",
        status=200,
        payload=text,
    )
    resp = await client.get("/octocat")
    result = (await resp.text()).strip('"')
    assert result == text


def test_sync_client_rest_with_text(responses, sync_client):
    client = sync_client
    text = "Favour focus over features"
    responses.get(
        f"{GITHUB_API_ENDPOINT}/octocat",
        content_type="application/octocat-stream",
        status=200,
        json=text,
    )
    resp = client.get("/octocat")
    result = resp.json()
    assert result == text


@pytest.mark.asyncio
async def test_async_client_graphql(aioresponses, async_client):
    client = async_client

    aioresponses.post(
        GITHUB_GRAPHQL_ENDPOINT,
        status=200,
        payload={"data": {"foo": "bar"}},
    )
    query = "query { viewer { login }}"
    result = await client.execute(query)
    assert result == {"foo": "bar"}

    aioresponses.post(
        GITHUB_GRAPHQL_ENDPOINT,
        status=200,
        payload={"data": {"user": {"email": "octocat@github.com"}}},
    )
    query = "query($user:String!) { user(login: $user) { email }}"
    variables = {"user": "octocat"}
    result = await client.execute(query, variables)
    assert result == {"user": {"email": "octocat@github.com"}}


def test_sync_client_graphql(responses, sync_client):
    client = sync_client

    responses.post(GITHUB_GRAPHQL_ENDPOINT, status=200, json={"data": {"foo": "bar"}})
    query = "query { viewer { login }}"
    result = client.execute(query)
    assert result == {"foo": "bar"}

    responses.post(
        GITHUB_GRAPHQL_ENDPOINT,
        status=200,
        json={"data": {"user": {"email": "octocat@github.com"}}},
    )
    query = "query($user:String!) { user(login: $user) { email }}"
    variables = {"user": "octocat"}
    result = client.execute(query, variables)
    assert result == {"user": {"email": "octocat@github.com"}}
