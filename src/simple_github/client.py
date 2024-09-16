import asyncio
import json
from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Coroutine, Dict, Optional, Union

from aiohttp import ClientResponse, ClientSession
from gql import Client as GqlClient
from gql import gql
from gql.client import ReconnectingAsyncClientSession, SyncClientSession
from gql.transport.aiohttp import AIOHTTPTransport
from gql.transport.requests import RequestsHTTPTransport
from requests import Response as RequestsResponse
from requests import Session

if TYPE_CHECKING:
    from simple_github.auth import Auth

GITHUB_API_ENDPOINT = "https://api.github.com"
GITHUB_GRAPHQL_ENDPOINT = "https://api.github.com/graphql"

Response = Union[RequestsResponse, ClientResponse]
RequestData = Optional[Dict[str, Any]]

# Implementations of the base class can be either sync or async.
BaseDict = Union[Dict[str, Any], Coroutine[None, None, Dict[str, Any]]]
BaseNone = Union[None, Coroutine[None, None, None]]
BaseResponse = Union[Response, Coroutine[None, None, Response]]


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
        self._gql_client: Optional[GqlClient] = None
        self._gql_session: Optional[
            Any[ReconnectingAsyncClientSession, SyncClientSession]
        ] = None

    @abstractmethod
    def close(self) -> BaseNone: ...

    @abstractmethod
    def request(self, method: str, query: str, **kwargs: Any) -> BaseResponse: ...

    @abstractmethod
    def get(self, query: str) -> BaseResponse: ...

    @abstractmethod
    def post(self, query: str, data: RequestData = None) -> BaseResponse: ...

    @abstractmethod
    def put(self, query: str, data: RequestData = None) -> BaseResponse: ...

    @abstractmethod
    def patch(self, query: str, data: RequestData = None) -> BaseResponse: ...

    @abstractmethod
    def delete(self, query: str, data: RequestData = None) -> BaseNone: ...

    @abstractmethod
    def execute(self, query: str, variables: RequestData = None) -> BaseDict: ...


class SyncClient(Client):
    def __enter__(self):
        return self

    def __exit__(self, *excinfo: Any):
        self.close()

    def close(self) -> None:
        asyncio.run(self.auth.close())
        if self._gql_client:
            self._gql_client.close_sync()

    def _get_gql_session(self) -> SyncClientSession:
        """Return an AIOHTTP session.

        The session will be automatically re-created anytime the auth's
        token changes.

        Returns:
            aiohttp.ClientSession: An AIOHTTP session object.
        """
        token = asyncio.run(self.auth.get_token())

        if token == self._prev_token:
            assert isinstance(self._gql_session, SyncClientSession)
            return self._gql_session

        # Create a new session with updated token.
        self._prev_token = token
        if self._gql_client:
            self._gql_client.close_sync()

        headers = {
            "Accept": "application/vnd.github+json",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"

        transport = RequestsHTTPTransport(url=GITHUB_GRAPHQL_ENDPOINT, headers=headers)
        self._gql_client = GqlClient(
            transport=transport, fetch_schema_from_transport=False
        )
        self._gql_session = self._gql_client.connect_sync()
        assert isinstance(self._gql_session, SyncClientSession)
        return self._gql_session

    def _get_requests_session(self) -> Session:
        session = self._get_gql_session()
        assert isinstance(session.transport, RequestsHTTPTransport)
        assert session.transport.session
        return session.transport.session

    def request(self, method: str, query: str, **kwargs) -> RequestsResponse:
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
        session = self._get_requests_session()

        with session.request(method, url, **kwargs) as resp:
            return resp

    def get(self, query: str) -> RequestsResponse:
        """Make a GET request to Github's REST API.

        Args:
            query (str): The path segment of the request, e.g `/octocat`.

        Returns:
            Dict: The JSON result of the request.
        """
        return self.request("GET", query)

    def post(self, query: str, data: RequestData = None) -> RequestsResponse:
        """Make a POST request to Github's REST API.

        Args:
            query (str): The path segment of the request, e.g `/octocat`.
            data (Dict): The data to send in the request (optional).

        Returns:
            Dict: The JSON result of the request.
        """
        return self.request("POST", query, data=json.dumps(data))

    def put(self, query: str, data: RequestData = None) -> RequestsResponse:
        """Make a PUT request to Github's REST API.

        Args:
            query (str): The path segment of the request, e.g `/octocat`.
            data (Dict): The data to send in the request (optional).

        Returns:
            Dict: The JSON result of the request.
        """
        return self.request("PUT", query, data=json.dumps(data))

    def patch(self, query: str, data: RequestData = None) -> RequestsResponse:
        """Make a PATCH request to Github's REST API.

        Args:
            query (str): The path segment of the request, e.g `/octocat`.
            data (Dict): The data to send in the request (optional).

        Returns:
            Dict: The JSON result of the request.
        """
        return self.request("PATCH", query, data=json.dumps(data))

    def delete(self, query: str, data: RequestData = None) -> None:
        """Make a DELETE request to Github's REST API.

        Args:
            query (str): The path segment of the request, e.g `/octocat`.
            data (Dict): The data to send in the request (optional).
        """
        self.request("DELETE", query, data=json.dumps(data))

    def execute(self, query: str, variables: RequestData = None) -> Dict[str, Any]:
        """Execute a query against Github's GraphQL endpoint.

        Args:
            query (str): The GraphQL query to execute.
            variables (Dict): The GraphQL variables associated with the query
                (optional).

        Returns:
            Dict: The result of the executed query.
        """
        session = self._get_gql_session()
        return session.execute(gql(query), variable_values=variables)


class AsyncClient(Client):
    async def __aenter__(self):
        return self

    async def __aexit__(self, *excinfo: Any):
        await self.close()

    async def close(self) -> None:
        await self.auth.close()
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
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"

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

    async def request(self, method: str, query: str, **kwargs: Any) -> ClientResponse:
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
        return await session.request(method, url, **kwargs)

    async def get(self, query: str) -> ClientResponse:
        """Make a GET request to Github's REST API.

        Args:
            query (str): The path segment of the request, e.g `/octocat`.

        Returns:
            Dict: The JSON result of the request.
        """
        return await self.request("GET", query)

    async def post(self, query: str, data: RequestData = None) -> ClientResponse:
        """Make a POST request to Github's REST API.

        Args:
            query (str): The path segment of the request, e.g `/octocat`.
            data (Dict): The data to send in the request (optional).

        Returns:
            Dict: The JSON result of the request.
        """
        return await self.request("POST", query, data=json.dumps(data))

    async def put(self, query: str, data: RequestData = None) -> ClientResponse:
        """Make a PUT request to Github's REST API.

        Args:
            query (str): The path segment of the request, e.g `/octocat`.
            data (Dict): The data to send in the request (optional).

        Returns:
            Dict: The JSON result of the request.
        """
        return await self.request("PUT", query, data=json.dumps(data))

    async def patch(self, query: str, data: RequestData = None) -> ClientResponse:
        """Make a PATCH request to Github's REST API.

        Args:
            query (str): The path segment of the request, e.g `/octocat`.
            data (Dict): The data to send in the request (optional).

        Returns:
            Dict: The JSON result of the request.
        """
        return await self.request("PATCH", query, data=json.dumps(data))

    async def delete(self, query: str, data: RequestData = None) -> None:
        """Make a DELETE request to Github's REST API.

        Args:
            query (str): The path segment of the request, e.g `/octocat`.
            data (Dict): The data to send in the request (optional).
        """
        await self.request("DELETE", query, data=json.dumps(data))

    async def execute(
        self, query: str, variables: RequestData = None
    ) -> Dict[str, Any]:
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
