from typing import List, Optional, Union

from .client import Client
from .auth import AppAuth, AppInstallationAuth, TokenAuth


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
    auth = AppAuth(id, privkey)
    if owner:
        auth = AppInstallationAuth(auth, owner, repositories=repositories)
    return Client(auth=auth)


def TokenClient(token: str) -> Client:
    """Convenience function to create a `Client` instance authenticated
    with an access token.

    Args:
        token (str): The access token to use.

    Returns:
        Client: A client authenticated with the token."""
    return Client(auth=TokenAuth(token))
