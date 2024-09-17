Contributing to Simple Github
=============================

Thanks for your interest in simple-github! To participate in this community, please
review our [code of conduct][0].

[0]: https://github.com/mozilla-releng/simple-github/blob/main/CODE_OF_CONDUCT.md

Clone the Repo
--------------

To contribute to simple-github, you'll need to clone the repository:

```
# first fork simple-github
git clone https://github.com/<user>/simple-github
cd simple-github
git remote add upstream https://github.com/mozilla-releng/simple-github
```

Setting Up the Environment
--------------------------

We use a tool called [uv][1] to manage simple-github and its dependencies. First,
follow the [installation instructions][2].

Then run:

```
uv sync
```

This does several things:

1. Creates a virtualenv for the project in a ``.venv`` directory (if necessary).
2. Syncs the project's dependencies as pinned in ``uv.lock`` (if necessary).
3. Installs ``simple-github`` as an editable package (if necessary).

Now you can prefix commands with `uv run` and they'll have access to this
environment.

[1]: https://docs.astral.sh/uv/
[2]: https://docs.astral.sh/uv/getting-started/installation/

Running Tests
-------------

Tests are run with the [pytest][3] framework:

```
uv run pytest
```

[3]: https://docs.pytest.org

Running Checks
--------------

Linters and formatters are run via [pre-commit][4]. To install the hooks, run:

```
pre-commit install -t pre-commit -t commit-msg
```

Now checks will automatically run on every commit. If you prefer to run checks
manually, you can use:

```
pre-commit run
```

Most of the checks we enforce are done with [ruff][5]. See
[pre-commit-config.yaml][6] for a full list of linters and formatters.

[4]: https://pre-commit.com/
[5]: https://docs.astral.sh/ruff/
[6]: https://github.com/mozilla-releng/simple-github/blob/main/.pre-commit-config.yaml

Releasing
---------

A tool called [commitizen][7] can optionally be used to assist with releasing
the package. First install it with:

```
uv tool install commitizen
```

Then create the version bump commit:

```
cz bump
git show
```

Verify the commit is what you expect, then create a pull request and get the
commit merged into `main`. Once merged, push your tag upstream:

```
git push upstream --tags
```

Finally, create a release in Github, choosing the tag that you just pushed.
This will trigger the `pypi-publish` workflow and upload the package to pypi.

[7]: https://commitizen-tools.github.io/commitizen/
