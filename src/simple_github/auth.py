import asyncio
import os
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, AsyncIterator
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from simple_github.client import AsyncClient


# For compatibility with Python <3.10.
async def anext(ait: AsyncIterator[Any]):
    return await ait.__anext__()


class Auth(ABC):
    @abstractmethod
    async def get_token(self) -> str:
        """Returns"""
        ...

    async def close(self) -> None:
        """Close the authentication if necessary."""
        pass


class PublicAuth(Auth):
    """Shim for unauthenticated API access."""

    async def get_token(self) -> str:
        return ""


class TokenAuth(Auth):
    def __init__(self, token: str):
        """Authentication for an access token.

        Args:
            token (str): The access token to authenticate with.
        """
        self._token = token

    async def get_token(self) -> str:
        """Get the access token.

        Returns:
            str: The access token.
        """
        return self._token


class AppAuth(Auth):
    def __init__(self, app_id: str | int, privkey: str):
        """Authentication for a Github app.

        Args:
            app_id (str or int): The Github Client (str) or App (int) ID. GitHub
                recommends using the Client ID.
            privkey (str): A base64 encoded private key associated with the
                app.
        """
        self.id = app_id
        self._privkey = privkey
        self._generator = self._gen_jwt()

    async def _gen_jwt(self) -> AsyncGenerator[str, None]:
        """Generates a JSON Web Token (JWT).

        The token will expire in 9 minutes but subsequent calls to this function
        will yield the same token as long as there is more than a minute remaining
        before its expiry. After which point, a new token will be generated.

        Yields:
            str: JSON Web Token
        """
        issued_at = int(time.time())
        payload = {
            "iat": issued_at,
            "exp": issued_at + 540,
            "iss": str(self.id),
        }

        token = jwt.encode(payload, self._privkey, algorithm="RS256")

        while True:
            current = int(time.time())
            # Refresh the token a minute before expiry.
            if payload["exp"] - current < 60:
                payload["iat"] = current
                payload["exp"] = current + 540
                token = jwt.encode(payload, self._privkey, algorithm="RS256")
            yield token

    async def get_token(self) -> str:
        """Get the JSON web token (JWT) signed by `privkey`.

        If the token is about to expire, it will automatically be re-generated.

        Returns:
            str: The signed JSON web token.
        """
        return await anext(self._generator)


class AppInstallationAuth(Auth):
    def __init__(
        self,
        app: AppAuth,
        owner: str,
        repositories: list[str] | str | None = None,
    ):
        """Authentication for a Github App installation.

        Args:
            app (AppAuth): Authentication for a Github app, used to generate an
                installation access token.
            owner (str): The organization or user which owns the installation.
            repositories (List[str]): Repositories to limit the scope to. If not
                specified, authentication will be granted for all repositories
                owned by `owner`.
        """
        if isinstance(repositories, str):
            repositories = [repositories]

        self.app = app
        self.owner = owner
        self.repositories = repositories
        self._client = AsyncClient(auth=self.app)
        self._installation_id: str | None = None
        self._token: str | None = None
        self._expires = 0
        # Serializes refreshes so concurrent callers don't mint duplicate tokens.
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        """Close the Client used to fetch the installation token."""
        await self._client.close()

    async def _get_installation_id(self) -> str:
        """Return the app's installation id for owner.

        Returns:
            str: The app's installation id.
        """
        async with await self._client.get("/app/installations") as response:
            response.raise_for_status()
            installations = await response.json()
        assert isinstance(installations, list)

        for installation in installations:
            if installation["account"].get("login") == self.owner:
                return installation["id"]

        raise Exception(
            f"Github App '{self.app.id}' is not installed with owner '{self.owner}'!"
        )

    async def _create_token(self) -> str:
        """Create a Github App installation access token for the owner and
        repositories.

        Returns:
            str: An app installation access token scoped to the repositories.
        """
        if self._installation_id is None:
            self._installation_id = await self._get_installation_id()

        query = f"/app/installations/{self._installation_id}/access_tokens"
        data = {}
        if self.repositories:
            # Ensures the token is only valid for the current repo.
            data["repositories"] = self.repositories

        response = await self._client.post(query, data=data)
        response.raise_for_status()
        result = await response.json()
        assert isinstance(result, dict)
        return result["token"]

    async def get_token(self) -> str:
        """Get the installation access token.

        If the token is about to expire, it will automatically be re-generated.
        If creating a token fails, the next call tries again.

        Returns:
            str: The installation access token."""
        async with self._lock:
            # Refresh the token a minute before it expires.
            if self._token is None or self._expires - int(time.time()) < 60:
                self._token = await self._create_token()
                self._expires = int(time.time()) + 3600  # valid for one hour
            return self._token


class TaskclusterAuth(Auth):
    # Tokens are refreshed this long before they expire.
    _REFRESH_MARGIN = timedelta(minutes=5)

    def __init__(
        self,
        app: str,
        owner: str,
        repositories: list[str] | str,
        permissions: dict[str, str],
        taskcluster_options: dict[str, Any] | None = None,
    ):
        """Authentication for a Github App installation, with tokens provided by
        Taskcluster.

        Args:
            app (str): The name of the Github App, as registered in Taskcluster.
            owner (str): The organization or user which owns the installation.
            repositories (list[str] or str): Repository, or list of
                repositories, to scope the token to. Must not be empty.
            permissions (dict[str, str]): Github permissions to request, e.g.
                `{"contents": "write"}`. Must not be empty.
            taskcluster_options (dict): Options for the Taskcluster client, in
                the format taskcluster clients accept (`rootUrl`, `credentials`,
                etc). If not specified, they are read from the environment.
                Inside a task with taskcluster-proxy enabled, requests go
                through the proxy.

        Raises:
            ValueError: If `repositories` or `permissions` is empty.
            ImportError: If `taskcluster` is not installed.
        """
        if isinstance(repositories, str):
            repositories = [repositories]
        if not repositories:
            raise ValueError("'repositories' must not be empty")
        if not permissions:
            raise ValueError("'permissions' must not be empty")

        # Imported lazily so the `taskcluster` extra stays optional.
        try:
            import taskcluster.aio  # noqa: PLC0415
        except ImportError as e:
            raise ImportError(
                "TaskclusterAuth requires the taskcluster package. Install it "
                "with `pip install simple-github[taskcluster]`."
            ) from e

        if taskcluster_options is None:
            taskcluster_options = taskcluster.optionsFromEnvironment()
            # Inside a task, credentials normally come from taskcluster-proxy,
            # which `optionsFromEnvironment()` doesn't know about.
            proxy_url = os.environ.get("TASKCLUSTER_PROXY_URL")
            if proxy_url and "credentials" not in taskcluster_options:
                taskcluster_options["rootUrl"] = proxy_url

        self.app = app
        self.owner = owner.lower()
        self._taskcluster = taskcluster.aio.Auth(taskcluster_options)
        self._payload = {
            "repositories": [repo.lower() for repo in repositories],
            "permissions": dict(permissions),
        }
        self._token: str | None = None
        self._expires: datetime | None = None
        # Serializes refresh so concurrent callers don't create duplicate tokens.
        self._lock = asyncio.Lock()

    async def get_token(self) -> str:
        """Get the installation access token.

        If the token is about to expire, it will automatically be re-generated.

        Returns:
            str: The installation access token.

        Raises:
            ValueError: If Taskcluster returns a malformed response.
        """
        async with self._lock:
            if (
                self._token is None
                or self._expires is None
                or datetime.now(timezone.utc) >= self._expires - self._REFRESH_MARGIN
            ):
                response: Any = await self._taskcluster.githubRepoToken(
                    self.app, self.owner, self._payload
                )

                if (
                    not isinstance(response, dict)
                    or not isinstance(response.get("token"), str)
                    or not isinstance(response.get("expires"), str)
                ):
                    raise ValueError(
                        "Unexpected response from Taskcluster's githubRepoToken "
                        "endpoint: expected 'token' and 'expires' strings"
                    )
                self._token = response["token"]
                # Taskcluster returns a "Z" suffix, which Python 3.10's
                # fromisoformat() doesn't accept.
                self._expires = datetime.fromisoformat(
                    response["expires"].replace("Z", "+00:00")
                )
            assert self._token is not None
            return self._token
