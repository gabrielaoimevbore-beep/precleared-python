# Publishing `precleared` to PyPI

Steps for publishing this package under your own PyPI account. Nothing here has been run; the package name `precleared` was free on PyPI on 17 October 2026 (so was `precleared-sdk`, kept in reserve).

## 0. One-off account setup

1. Create an account at https://pypi.org/account/register/ and turn on two-factor authentication (PyPI requires it for uploads).
2. Create an API token at https://pypi.org/manage/account/token/ with scope "Entire account" for the first upload. After the first release, replace it with a token scoped to the `precleared` project.
3. Optional but recommended: do the same at https://test.pypi.org to rehearse.

Keep tokens out of the repository. `twine` reads them from `~/.pypirc` or from the `TWINE_USERNAME` and `TWINE_PASSWORD` environment variables.

## 1. Check the version

The version lives in two places and must match:

- `pyproject.toml`: `version = "0.1.0"`
- `src/precleared/_version.py`: `__version__ = "0.1.0"`

PyPI never lets you re-upload the same version, so bump both before every release.

## 2. Run the tests

```bash
cd sdk-python
python -m venv .venv && source .venv/bin/activate
pip install -e ".[all]" pytest anyio
pytest
```

The framework tests skip when a framework is missing, so `pip install -e . pytest anyio` is enough for the core suite.

## 3. Build

```bash
pip install --upgrade build twine
rm -rf dist
python -m build
twine check dist/*
```

`python -m build` produces `dist/precleared-0.1.0.tar.gz` and `dist/precleared-0.1.0-py3-none-any.whl`. `twine check` must report `PASSED` for both.

## 4. Rehearse on TestPyPI (optional)

```bash
twine upload --repository testpypi dist/*
python -m venv /tmp/try && /tmp/try/bin/pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ precleared
/tmp/try/bin/python -c "import precleared; print(precleared.__version__)"
```

## 5. Upload to PyPI

```bash
twine upload dist/*
```

When prompted, the username is `__token__` and the password is the API token (including the `pypi-` prefix). Then confirm:

```bash
python -m venv /tmp/check && /tmp/check/bin/pip install precleared
/tmp/check/bin/python -c "from precleared import Precleared; print(Precleared())"
```

The project page will be https://pypi.org/project/precleared/.

## 6. Trusted publishing instead of tokens (recommended once the code is on GitHub)

Trusted publishing lets GitHub Actions upload without a long-lived token.

1. On PyPI, open https://pypi.org/manage/account/publishing/ and add a "pending publisher": PyPI project name `precleared`, your GitHub owner and repository name, workflow file name `publish.yml`, environment name `pypi`.
2. In the repository, create a `pypi` environment under Settings, Environments.
3. Add `.github/workflows/publish.yml`:

```yaml
name: Publish to PyPI
on:
  release:
    types: [published]
jobs:
  publish:
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python -m pip install --upgrade build
      - run: python -m build
      - uses: pypa/gh-action-pypi-publish@release/v1
```

4. Publish a GitHub release tagged `v0.1.0`. The workflow builds and uploads; no token is stored anywhere.

The first upload can be done either way. If you upload with a token first, add the trusted publisher afterwards from the project's "Publishing" settings page.

## 7. After publishing: get listed by the frameworks

### LangChain (verified on 17 October 2026)

LangChain no longer accepts integration code or new documentation pages by pull request. The route for a published package is the integration listing form in the `langchain-ai/docs` repository:

- Open https://github.com/langchain-ai/docs/issues/new?template=06-integration-submission.yml and fill it in with the PyPI name `precleared`, the docs URL (`https://precleared.dev/docs` or the README on PyPI) and the component type "tools".
- A maintainer applies the `integration-run` label and automation opens the pull request that adds a row to `scripts/data/integration_external_docs.yaml`. Do not open that PR by hand and do not add an MDX page; automation closes manual ones.
- A hosted guide under `src/oss/python/integrations/tools/` (template `src/oss/python/integrations/tools/TEMPLATE.mdx` in `langchain-ai/docs`) is only for packages with 50,000 or more monthly downloads, or ones the maintainers choose to feature.

Source: https://docs.langchain.com/oss/python/contributing/integrations-langchain

### LlamaIndex (partly verified)

LlamaIndex lists tools on LlamaHub from packages inside its monorepo, `run-llama/llama_index`. Tool packages live under `llama-index-integrations/tools/llama-index-tools-<name>/` (confirmed from the README of the published `llama-index-tools-tavily-research` package, which points at `llama-index-integrations/tools/llama-index-tools-tavily-research/examples/tavily.ipynb`). The contributing guide at https://docs.llamaindex.ai/en/latest/CONTRIBUTING asks for unit tests that mock the remote system and for coverage of at least 50 percent.

So the route is a pull request to `run-llama/llama_index` adding `llama-index-integrations/tools/llama-index-tools-precleared/` (its own `pyproject.toml`, `README.md`, `llama_index/tools/precleared/base.py` wrapping `precleared.llamaindex`, `tests/` and an `examples/` notebook). Not verified: the exact scaffold command (`llamaindex-cli new-package` is the usual one) and whether a docs notebook under `docs/docs/examples/tools/` is still required; check the repository's current `CONTRIBUTING.md` before opening the PR.

### CrewAI and the OpenAI Agents SDK (not verified)

Community CrewAI tools are collected in the `crewAIInc/crewAI-tools` repository; this was not verified from inside this session. The OpenAI Agents SDK has no integration directory; the README example is the integration.

## 8. Next releases

1. Bump the version in both files and note the change in the README if the surface changed.
2. `pytest`, `python -m build`, `twine check dist/*`.
3. `twine upload dist/*`, or publish a GitHub release if trusted publishing is set up.
