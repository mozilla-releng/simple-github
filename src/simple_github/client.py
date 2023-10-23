import json
from typing import TYPE_CHECKING, Dict, Optional, TypeAlias, Union

from aiohttp import ClientSession, ContentTypeError
from gql import Client as GqlClient
from gql import gql
from gql.client import ReconnectingAsyncClientSession
from gql.transport.aiohttp import AIOHTTPTransport

if TYPE_CHECKING:
    from simple_github.auth import Auth

GITHUB_API_ENDPOINT = "https://api.github.com"
GITHUB_GRAPHQL_ENDPOINT = "https://api.github.com/graphql"

Response: TypeAlias = Union[Dict, str]


class Client:
    def __init__(self, auth: "Auth"):
        """A Github client.

        It can make GET and POST requests to the Github v3 API, as well
        as execute queries against the GraphQL API.

        Args:
            auth (Auth): An `Auth` instance for creating an authentication
                token.
        """
        self.auth = auth
        self._prev_token = None
        self._gql_client = None
        self._gql_session = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *excinfo):
        await self.close()

    async def close(self) -> None:
        if self._gql_client:
            await self._gql_client.close_async()

    async def _get_gql_session(self) -> ReconnectingAsyncClientSession:
        """Return an AIOHTTP session.

        The session will be automatically re-created anytime the auth's
        token changes.

        Returns:
            aiohttp.ClientSession: An AIOHTTP session object.
        """
        token = await self.auth.get_token()
        if token == self._prev_token:
            assert isinstance(self._gql_session, ReconnectingAsyncClientSession)
            return self._gql_session

        # Create a new session with updated token.
        self._prev_token = token
        if self._gql_client:
            await self._gql_client.close_async()

        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
        }
        transport = AIOHTTPTransport(url=GITHUB_GRAPHQL_ENDPOINT, headers=headers)
        self._gql_client = GqlClient(
            transport=transport, fetch_schema_from_transport=False
        )
        self._gql_session = await self._gql_client.connect_async(reconnecting=True)
        assert isinstance(self._gql_session, ReconnectingAsyncClientSession)
        return self._gql_session

    async def _get_aiohttp_session(self) -> ClientSession:
        session = await self._get_gql_session()
        assert isinstance(session.transport, AIOHTTPTransport)
        assert session.transport.session
        return session.transport.session

    async def _make_request(self, method: str, query: str, **kwargs) -> Response:
        """Make a request to Github's REST API.

        Args:
            method (str): The HTTP method, either 'GET' or 'POST'.
            query (str): The path segment of the request, e.g `/octocat`.
            kwargs (Dict): Extra args to pass to
                `aiohttp.ClientSession.request`.

        Returns:
            Dict: The JSON result of the request.
        """
        url = f"{GITHUB_API_ENDPOINT}/{query.lstrip('/')}"
        session = await self._get_aiohttp_session()

        async with session.request(method, url, **kwargs) as resp:
            if not resp.ok:
                resp.raise_for_status()
            try:
                return await resp.json()
            except ContentTypeError:
                return (await resp.text()).strip('"')

    async def get(self, query: str) -> Response:
        """Make a GET request to Github's REST API.

        Args:
            query (str): The path segment of the request, e.g `/octocat`.

        Returns:
            Dict: The JSON result of the request.
        """
        return await self._make_request("GET", query)

    async def post(self, query: str, data: Optional[Dict] = None) -> Response:
        """Make a POST request to Github's REST API.

        Args:
            query (str): The path segment of the request, e.g `/octocat`.
            data (Dict): The data to send in the request (optional).

        Returns:
            Dict: The JSON result of the request.
        """
        return await self._make_request("POST", query, data=json.dumps(data))

    async def execute(self, query: str, variables: Optional[Dict] = None) -> Dict:
        """Execute a query against Github's GraphQL endpoint.

        Args:
            query (str): The GraphQL query to execute.
            variables (Dict): The GraphQL variables associated with the query
                (optional).

        Returns:
            Dict: The result of the executed query.
        """
        session = await self._get_gql_session()
        return await session.execute(gql(query), variable_values=variables)
