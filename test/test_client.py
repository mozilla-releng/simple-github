import pytest
import pytest_asyncio
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
async def test_async_client_get_session_no_token(async_client):
    client = async_client
    client.auth._token = ""
    session = await client._get_aiohttp_session()
    assert dict(session._default_headers) == {
        "Accept": "application/vnd.github+json",
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


@pytest.mark.asyncio
async def test_async_client_rest(aioresponses, async_client):
    client = async_client
    url = f"{GITHUB_API_ENDPOINT}/octocat"

    aioresponses.get(url, status=200, payload={"answer": 42})
    resp = await client.get("/octocat")
    result = await resp.json()
    assert result == {"answer": 42}

    aioresponses.post(url, status=200, payload={"answer": 42})
    resp = await client.post("/octocat", data={"foo": "bar"})
    result = await resp.json()
    assert result == {"answer": 42}

    aioresponses.put(url, status=200, payload={"answer": 42})
    resp = await client.put("/octocat", data={"foo": "bar"})
    result = await resp.json()
    assert result == {"answer": 42}

    aioresponses.patch(url, status=200, payload={"answer": 42})
    resp = await client.patch("/octocat", data={"foo": "bar"})
    result = await resp.json()
    assert result == {"answer": 42}

    aioresponses.delete(url, status=200)
    await client.delete("/octocat")
    aioresponses.assert_called_with(url, "DELETE", data="null")

    aioresponses.get(url, status=401)
    with pytest.raises(ClientResponseError):
        resp = await client.get("/octocat")
        resp.raise_for_status()


def test_sync_client_rest(responses, sync_client):
    client = sync_client
    url = f"{GITHUB_API_ENDPOINT}/octocat"

    responses.get(url, status=200, json={"answer": 42})
    resp = client.get("/octocat")
    result = resp.json()
    assert result == {"answer": 42}

    responses.post(url, status=200, json={"answer": 42})
    resp = client.post("/octocat", data={"foo": "bar"})
    result = resp.json()
    assert result == {"answer": 42}

    responses.put(url, status=200, json={"answer": 42})
    resp = client.put("/octocat", data={"foo": "bar"})
    result = resp.json()
    assert result == {"answer": 42}

    responses.patch(url, status=200, json={"answer": 42})
    resp = client.patch("/octocat", data={"foo": "bar"})
    result = resp.json()
    assert result == {"answer": 42}

    responses.delete(url, status=200)
    client.delete("/octocat")
    resp = responses.calls[-1].response
    assert resp.url == url
    assert resp.request.method == "DELETE"
    assert resp.status_code == 200

    responses.get(url, status=401)
    with pytest.raises(HTTPError):
        resp = client.get("/octocat")
        resp.raise_for_status()


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
        GITHUB_GRAPHQL_ENDPOINT, status=200, payload={"data": {"foo": "bar"}}
    )
    query = "query { viewer { login }}"
    result = await client.execute(query)
    assert result == {"foo": "bar"}


def test_sync_client_graphql(responses, sync_client):
    client = sync_client
    responses.post(GITHUB_GRAPHQL_ENDPOINT, status=200, json={"data": {"foo": "bar"}})
    query = "query { viewer { login }}"
    result = client.execute(query)
    assert result == {"foo": "bar"}
