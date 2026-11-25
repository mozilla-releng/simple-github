import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock

import aiohttp
import pytest
import taskcluster.aio
from responses import RequestsMock

here = Path(__file__).parent


# Cribbed from https://github.com/j7an/dep-rank/pull/123
# aiohttp 3.14 added a required keyword-only ``stream_writer`` argument to
# ``ClientResponse.__init__``. aioresponses (<=0.7.8) builds mocked responses
# without it, so every mocked request raises ``TypeError: ... missing 1
# required keyword-only argument: 'stream_writer'``. aiohttp only reads
# ``stream_writer.output_size``, so a ``Mock(output_size=0)`` suffices.
#
# This mirrors the upstream fix (aioresponses#288, tracking aioresponses#289).
# The signature guard makes it a no-op on aiohttp < 3.14 and once aioresponses
# ships a release that supplies the argument itself; remove this shim then.
_response_init = aiohttp.ClientResponse.__init__
if "stream_writer" in inspect.signature(_response_init).parameters:

    def _patched_response_init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        kwargs.setdefault("stream_writer", Mock(output_size=0))
        _response_init(self, *args, **kwargs)

    aiohttp.ClientResponse.__init__ = _patched_response_init


@pytest.fixture
def responses():
    with RequestsMock() as rsps:
        yield rsps


@pytest.fixture(scope="session")
def datadir():
    return here / "data"


@pytest.fixture(scope="session")
def project_root():
    return here.parent


@pytest.fixture(scope="session")
def privkey(datadir):
    with open(datadir / "test_private_key.pem", "rb") as fh:
        return fh.read()


@pytest.fixture(scope="session")
def pubkey(datadir):
    with open(datadir / "test_key.pub", "rb") as fh:
        return fh.read()


@pytest.fixture
def tc_client(monkeypatch):
    """Replace the Taskcluster client that `TaskclusterAuth` builds with a mock.

    By default `githubRepoToken` returns a token valid for an hour. The patched
    constructor is available as `taskcluster.aio.Auth`.
    """
    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    client = MagicMock(
        githubRepoToken=AsyncMock(
            return_value={
                "token": "installation-token",
                "expires": expires.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            }
        )
    )
    monkeypatch.setattr(taskcluster.aio, "Auth", MagicMock(return_value=client))
    return client
