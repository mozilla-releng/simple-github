import time
from abc import ABC, abstractmethod
from typing import AsyncGenerator, List, Optional, Union

import jwt

from simple_github.client import Client


# For compatibility with Python <3.10.
async def anext(ait):
    return await ait.__anext__()


class Auth(ABC):
    @abstractmethod
    async def get_token(self) -> str:
        """Returns"""
        ...


class TokenAuth(Auth):
    def __init__(self, token):
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
    def __init__(self, app_id, privkey):
        """Authentication for a Github app.

        Args:
            id (str): The Github app id.
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
            "iss": self.id,
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
        repositories: Optional[Union[List[str], str]] = None,
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
        self._client = Client(auth=self.app)
        self._generator = self._gen_installation_token()

    async def _get_installation_id(self) -> str:
        """Return the app's installation id for owner.

        Returns:
            str: The app's installation id.
        """
        installations = await self._client.get("/app/installations")

        for installation in installations:
            if installation["account"]["login"] == self.owner:
                return installation["id"]

        raise Exception(
            f"Github App '{self.app.id}' is not installed with owner '{self.owner}'!"
        )

    async def _gen_installation_token(self) -> AsyncGenerator[str, None]:
        """Generates a Github App installation access token for the given owner
        and repositories.

        Subsequent iterations of this generator return the same token until it
        expires, or is about to expire. After which, a new token is generated.

        Args:
            owner (str): The Github org or user where the app is installed.
            repos (List[str]): A list of repositories under <owner> to restrict
                access to. If not provided, the token will have access to all
                repositories.

        Yields:
            str: An app installation access token scoped to the given repositories.
        """
        installation_id = await self._get_installation_id()
        query = f"/app/installations/{installation_id}/access_tokens"
        data = {}
        if self.repositories:
            # Ensures the token is only valid for the current repo.
            data["repositories"] = self.repositories

        async def _gentoken():
            return (await self._client.post(query, data=data))["token"]

        token = await _gentoken()
        exp = int(time.time()) + 3600  # tokens are valid for one hour
        while True:
            cur = int(time.time())
            if exp - cur < 60:
                # token is about to expire, refresh it
                token = await _gentoken()
                exp = int(time.time()) + 3600
            yield token

    async def get_token(self) -> str:
        """Get the installation access token.

        If the token is about to expire, it will automatically be re-generated.

        Returns:
            str: The installation access token."""
        return await anext(self._generator)
