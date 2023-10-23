import pytest
import pytest_asyncio
from aiohttp import ClientResponseError
from gql import Client as GqlClient
from gql.client import ReconnectingAsyncClientSession

from simple_github.auth import TokenAuth
from simple_github.client import GITHUB_API_ENDPOINT, GITHUB_GRAPHQL_ENDPOINT, Client


@pytest_asyncio.fixture
async def client():
    client = Client(auth=TokenAuth("abc"))
    yield client
    await client.close()


@pytest.mark.asyncio
async def test_client_get_session(client):
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
async def test_client_rest(aioresponses, client):
    aioresponses.get(
        f"{GITHUB_API_ENDPOINT}/octocat", status=200, payload={"answer": 42}
    )
    result = await client.get("/octocat")
    assert result == {"answer": 42}

    aioresponses.post(
        f"{GITHUB_API_ENDPOINT}/octocat", status=200, payload={"answer": 42}
    )
    result = await client.post("/octocat", data={"foo": "bar"})
    assert result == {"answer": 42}

    aioresponses.get(f"{GITHUB_API_ENDPOINT}/octocat", status=401)
    with pytest.raises(ClientResponseError):
        await client.get("/octocat")


@pytest.mark.asyncio
async def test_client_rest_with_text(aioresponses, client):
    text = "Favour focus over features"
    aioresponses.get(
        f"{GITHUB_API_ENDPOINT}/octocat",
        content_type="application/octocat-stream",
        status=200,
        payload=text,
    )
    result = await client.get("/octocat")
    assert result == text


@pytest.mark.asyncio
async def test_client_graphql(aioresponses, client):
    aioresponses.post(
        GITHUB_GRAPHQL_ENDPOINT, status=200, payload={"data": {"foo": "bar"}}
    )
    query = "query { viewer { login }}"
    result = await client.execute(query)
    assert result == {"foo": "bar"}
