[![Task Status](https://firefox-ci-tc.services.mozilla.com/api/github/v1/repository/mozilla-releng/simple-github-client/main/badge.svg)](https://firefox-ci-tc.services.mozilla.com/api/github/v1/repository/mozilla-releng/simple-github-client/main/latest)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/mozilla-releng/simple-github-client/main.svg)](https://results.pre-commit.ci/latest/github/mozilla-releng/simple-github-client/main)
[![Code Coverage](https://codecov.io/gh/mozilla-releng/simple-github-client/branch/main/graph/badge.svg?token=GJIV52ZQNP)](https://codecov.io/gh/mozilla-releng/simple-github-client)
[![License](https://img.shields.io/badge/license-MPL%202.0-orange.svg)](http://mozilla.org/MPL/2.0)

# simple-github

A simple Python Github client that handles auth and provides easy access to the
REST and GraphQL APIs.

## Why use simple-github?

You might consider simple-github if..

1. You don't want to write your own auth (especially app auth) but also don't
   want to be stuck with an object oriented wrapper.
2. You want to use both the REST and GraphQL endpoints.

## Features

- Authenticate with a personal access token, as a Github App or a Github App
  installation.
- Automatic refreshing of app tokens on expiry.
- Query both the REST and GraphQL endpoints.
- Shared `aiohttp` session across both endpoints.

## Installation

Install with `pip`:

```bash
pip install simple-github
```

## Example Usage

### Authenticate with an access token

In the simplest case, you can provide an access token to use:

```python
from simple_github import TokenClient
token = "<access token>"
async with TokenClient(token) as session:
    await session.get("/octocat")
```

### Authenticate as a Github App installation

To authenticate as an app installation you'll need:

1. The Github app id for your app.
2. A private key associated with your app. This can be generated from your
   app's settings page.
3. The organization or user where the app is installed.
4. Optionally a list of repositories to limit access to.

```python
from simple_github import AppClient
app_id = 123
privkey = "<private key>"
owner = "mozilla-releng"

async with AppClient(app_id, privkey, owner=owner) as session:
    await session.get("/octocat")
```

You can also specify repositories if you want to restrict access.

```python
async with AppClient(app_id, privkey, owner=owner, repositories=["simple-github"]) as session:
    await session.get("/octocat")
```

### Authenticate as a Github App

You can also authenticate as the app itself. This is mainly only useful for
administering the app. To do this, simply omit the `owner` argument.

```python
async with AppClient(app_id, privkey) as session:
    await session.get("/octocat")
```

### Query the REST API

simple-github provides only a very basic wrapper around Github's REST API. You can
query it by passing in the path fragment to `session.get` or `session.post`.

For example, you can list pull requests with a `GET` request:

```python
pulls = await session.get("/repos/mozilla-releng/simple-github/pulls")
open_pulls = [p for p in pulls if p["state"] == "open"]
```

Or you can create a pull request with a `POST` request:

```python
data = {
    "title": "Add feature X",
    "body": "This adds new feature X",
    "head": "simple-github:featureX",
    "base": "main",
}
await session.post("/repos/mozilla-releng/simple-github/pulls", data=data)
```

### Query the GraphQL API

simple-github also supports the GraphQL API. In this example we get the contents
of a file:

```python

query = """
  query getFileContents { 
    repository(owner: "mozilla-releng", name: "simple-github") {
      object(expression: "HEAD:README.md") {
        ... on Blob {
          text
        }
      }
    }
  }
"""
contents = await session.execute(query)
```

You can use GraphQL variables via the `variables` argument to `session.execute`.
