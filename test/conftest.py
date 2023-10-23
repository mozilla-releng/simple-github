from pathlib import Path

import pytest
from responses import RequestsMock

here = Path(__file__).parent


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
