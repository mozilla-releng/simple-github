import asyncio
from typing import List, Optional, Union

from .auth import AppAuth, AppInstallationAuth, PublicAuth, TokenAuth
from .client import AsyncClient, Client, SyncClient


def AppClient(
    id: int,
    privkey: str,
    owner: Optional[str] = None,
    repositories: Optional[Union[List[str], str]] = None,
) -> Client:
    """Convenience function to create a `Client` instance authenticated
    as a Github App.

    Authenticates directly as the app when only `id` and `privkey` are passed
    in. Authenticates as an app installation when `owner` is additionally
    passed in.

    Args:
        id (int): The id of the Github app.
        privkey (str): A base64 encoded private key configured for the app.
        owner (str): The org or user where the app is installed. If not
            specified, the returned client will be authenticated as the app
            itself rather than as an app installation.
        repositories (List[str]): A list of repositories to limit the app's
            scope to. If not specified, the client will have access to all
            repositories owned by `owner`.

    Returns:
        Client: A client authenticated as the app.
    """
    try:
        asyncio.get_running_loop()
        is_async = True
    except RuntimeError:
        is_async = False

    auth = AppAuth(id, privkey)
    if owner:
        auth = AppInstallationAuth(auth, owner, repositories=repositories)
    return AsyncClient(auth=auth) if is_async else SyncClient(auth=auth)


def TokenClient(token: str) -> Client:
    """Convenience function to create a `Client` instance authenticated
    with an access token.

    Args:
        token (str): The access token to use.

    Returns:
        Client: A client authenticated with the token."""
    try:
        asyncio.get_running_loop()
        is_async = True
    except RuntimeError:
        is_async = False

    auth = TokenAuth(token)
    return AsyncClient(auth=auth) if is_async else SyncClient(auth=auth)


def PublicClient() -> Client:
    """Convenience function to create an unauthenticated `Client` instance.

    Returns:
        Client: A client without any authentication."""
    try:
        asyncio.get_running_loop()
        is_async = True
    except RuntimeError:
        is_async = False

    auth = PublicAuth()
    return AsyncClient(auth=auth) if is_async else SyncClient(auth=auth)
