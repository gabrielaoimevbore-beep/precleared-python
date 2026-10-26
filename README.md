# precleared

Python client for [Precleared](https://precleared.dev), a cold-email legality check for AI agents.

One call per recipient, before the first cold email, answers: is it legal to send this person a cold or marketing email? Precleared looks the recipient up live (for the UK: Companies House, the domain and the company website) and applies the local rules (UK PECR and GDPR, US CAN-SPAM, Canadian CASL, German UWG, French CNIL guidance and the rules for Australia, Ireland and the Netherlands). It returns a verdict, the rule that decided it with its source, what the footer must include, the next step and a signed receipt.

Decision support with sources, not legal advice.

## Install

```bash
pip install precleared                     # client only (depends on httpx)
pip install "precleared[langchain]"        # + LangChain / LangGraph tools
pip install "precleared[crewai]"           # + CrewAI tools
pip install "precleared[llamaindex]"       # + LlamaIndex tools
pip install "precleared[openai-agents]"    # + OpenAI Agents SDK tools
pip install "precleared[all]"
```

Python 3.9 or later for the client. The framework extras follow the frameworks' own Python requirements (CrewAI and the current LangChain, LlamaIndex and Agents SDK releases need 3.10 or later).

## Quick start

```python
from precleared import Precleared

client = Precleared()  # keyless: 10 checks a day per network. Or Precleared("pc_live_...")
result = client.check("jane@acme.co.uk", pitch="Bookkeeping software for small firms", address_source="unknown")
if result.ok:
    print("Send, with a footer that meets:", result.footer_text)
else:
    print(result.verdict, result.next_step, result.receipt_url)
```

`check()` takes the same fields as the API: `recipient_email` or `recipient_domain`, `pitch`, `address_source` (`published`, `bought`, `scraped`, `given` or `unknown`), `sender_country` (default `GB`), `existing_customer`, `pitch_relevant`, `company_number`, `recipient_country`, `default_recipient_country` and `suppressed`.

`address_source` defaults to `unknown` and is always sent (the API treats a missing value as `unknown` too). It changes verdicts, so never pass `published` unless the recipient put the address on their website or a public listing for people to contact them.

### Reading a result

| Verdict | Meaning | `result.ok` | `result.must_not_send` |
| --- | --- | --- | --- |
| `ok_to_email` | Send, with a footer that meets `footer_text` | `True` | `False` |
| `consent_needed` | Do not send. Follow `next_step` | `False` | `True` |
| `blocked` | Do not send. Follow `next_step` | `False` | `True` |
| `unknown` | A fact could not be established. Treat as `consent_needed` unless you can supply the missing fact (for example `company_number` or `recipient_country`) and check again | `False` | `False` (see `needs_more_facts`) |

`footer_text` describes a requirement (who you are, a postal address, a way to opt out). It is not wording to paste.

`CheckResult` is a dataclass with typed fields (`verdict`, `confidence`, `reasons`, `rules_applied`, `footer_text`, `next_step`, `facts`, `receipt`, `usage`, `disclaimer`, `rules_version`) plus:

- `.raw`: the full response as a dict
- `.rule`: `rule_key` of the reason that decided the verdict
- `.reason`: that reason, with `text`, `source_title` and `source_url`
- `.notes`: the other reasons entries
- `.receipt_id` and `.receipt_url` (`https://precleared.dev/r/<id>`)
- `.summary()` and `.summary_text()`: the compact forms the framework tools return

### Receipts and health

```python
receipt = client.verify_receipt("cc_rcpt_...")   # also accepts a receipt URL
receipt.verdict, receipt.request_hash, receipt.response_hash, receipt.signature, receipt.public_key

client.health().ok  # GET /api/v1/health: status, checked_at, api_ok, mcp_ok, worker_ok
```

A receipt proves what was asked and answered. The signature is Ed25519 over `request_hash.response_hash`; the receipt endpoint returns the public key alongside it, and `GET /api/v1/public-key` serves it too.

### Async

```python
from precleared import AsyncPrecleared

async with AsyncPrecleared("pc_live_...") as client:
    result = await client.check("jane@acme.co.uk", address_source="bought")
```

## Framework tools

Each adapter exposes the same two tools, `precleared_check` and `precleared_verify_receipt`, with descriptions that tell the model when to call them: before the first cold email to anyone who is not already a customer, in the UK, US, Canada, Germany, France, Australia, Ireland or the Netherlands, and not for transactional email. The tools return compact text (verdict, rule, footer_text, next_step, receipt URL) rather than the whole JSON. Pass `to_dict=True` for a dictionary instead. Every factory takes an optional `api_key`.

Example tool output:

```
verdict: consent_needed (confidence: medium)
rule: gb_individual_consent
reason: The recipient is a sole trader or a partnership in England, Wales or Northern Ireland. PECR treats them as individual subscribers, so unsolicited marketing email needs their prior consent, or the soft opt-in for existing customers. Source: PECR 2003 regulation 22(2) and ICO Guide to PECR, https://www.legislation.gov.uk/uksi/2003/2426/regulation/22
next_step: Do not cold email. Use a route they offer, such as their contact form, or obtain consent first.
receipt: cc_rcpt_E21TTJV8D9JAYTQZ https://precleared.dev/r/cc_rcpt_E21TTJV8D9JAYTQZ
```

API errors come back as text too (`error: daily_limit`, with `get_key_url`, `buy_url` or `retry_after` when the API gives one), so the agent can react instead of crashing.

### LangChain / LangGraph

```python
from langchain.agents import create_agent  # pip install langchain
from precleared.langchain import precleared_tools

agent = create_agent(model, tools=precleared_tools(api_key="pc_live_..."))
```

`precleared_tools()` returns two `StructuredTool`s with pydantic argument schemas, so they also work with `model.bind_tools(...)` and LangGraph's prebuilt agents. `precleared_check_tool()` and `precleared_verify_receipt_tool()` build them one at a time.

### CrewAI

```python
from crewai import Agent
from precleared.crewai import PreclearedCheckTool, PreclearedVerifyReceiptTool

sdr = Agent(role="SDR", goal="...", backstory="...", tools=[PreclearedCheckTool(api_key="pc_live_..."), PreclearedVerifyReceiptTool()])
```

The key is held privately, so it does not appear in the tool's `repr()` or `model_dump()`.

### LlamaIndex

```python
from llama_index.core.agent.workflow import FunctionAgent
from precleared.llamaindex import precleared_tools

agent = FunctionAgent(tools=precleared_tools(), llm=llm)
```

### OpenAI Agents SDK

```python
from agents import Agent
from precleared.openai_agents import precleared_tools

agent = Agent(name="SDR", instructions="Check every address before the first email.", tools=precleared_tools())
```

## Errors

Everything raised after a request is sent is a subclass of `precleared.PreclearedError`, with `.message`, `.status_code`, `.code` and `.body`. Bad arguments raise a plain `ValueError` before anything is sent (for example an `address_source` outside the five allowed values).

| Class | When | Extra attributes |
| --- | --- | --- |
| `InvalidRequest` | 400, the body names the invalid field | |
| `InvalidKey` | 401, `invalid_key` or `revoked_key` | `.code` |
| `PaymentRequired` | 402, free checks used and no pack credits | `.buy_url` |
| `DailyLimit` | 429 `daily_limit`, the free daily allowance is used | `.get_key_url` |
| `RateLimited` | 429 `rate_limited`, more than 60 checks a minute | `.retry_after` (seconds, from the body or the `Retry-After` header) |
| `ReceiptNotFound` | 404 from the receipt endpoint | |
| `ServerError` | 5xx | |
| `NetworkError` | the request did not complete (DNS, connection, timeout) | `__cause__` is the httpx exception |

```python
from precleared import Precleared, DailyLimit, RateLimited

try:
    result = Precleared().check("jane@acme.co.uk")
except RateLimited as exc:
    time.sleep(exc.retry_after or 1)
except DailyLimit as exc:
    print("Get a free key:", exc.get_key_url)
```

The API key is never logged, printed or included in an exception.

## Allowances and limits

- Without a key: 10 checks a day over the REST API, shared by everyone on the same network.
- With a free key (`https://precleared.dev/get-key`, no card): 100 checks a day for the first 14 days, then 25 a day over the REST API and 100 over MCP.
- 60 checks a minute per key. Above that the API returns 429 `rate_limited` with `retry_after`.
- Days run on UK time. For more, £15 a month keeps 100 checks a day, or buy a pack: £9 for 300 checks (a key's first purchase) or £39 for 2,000. Pack checks are used after the day's free checks, never expire and stack on the same key. When no credits are left the API returns 402 with `buy_url`.
- A check can take up to 25 seconds when a register or website is slow; the client's default timeout is 30 seconds.

## Configuration

```python
Precleared(
    api_key=None,                          # or the PRECLEARED_API_KEY environment variable
    base_url="https://precleared.dev",
    timeout=30,                            # seconds, or an httpx.Timeout
    user_agent="precleared-python/0.1.0",  # Precleared's hosting refuses requests without one
)
```

## Disclaimer

Decision support with sources, not legal advice. The receipt proves what was asked and answered, not that an email was sent.

## Support

support@precleared.dev. API reference: https://precleared.dev/docs and https://precleared.dev/openapi.json.

## Development

```bash
pip install -e . pytest anyio
pytest
```

The tests mock all HTTP with `httpx.MockTransport` and never call the live API. The adapter tests run when the matching framework is installed and skip otherwise.
