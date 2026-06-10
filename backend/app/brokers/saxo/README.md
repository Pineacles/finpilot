# Saxo Bank adapter

Pluggable broker adapter for the Saxo Bank OpenAPI. **SIM environment only**
in this release — LIVE hosts are wired but rejected at runtime. Order routing
(`placeOrder` / `cancelOrder` / `modifyOrder`) is not enabled; calls raise
`TradingDisabledError`.

## How to connect a SIM account

1. Create a SIM developer app at <https://www.developer.saxo> ("Applications"
   → "Create Application"). Select:
   - **Grant Type**: Code
   - **Redirect URL**: `https://your-finpilot-domain.example.com/settings/saxo/callback`
   - **PKCE**: enabled (S256)
2. Copy the generated **AppKey**, **AppSecret**, and the redirect URL back into
   FinPilot → Settings → Brokers → Saxo Bank.

> The redirect URL registered at Saxo points at the **frontend** page
> `/settings/saxo/callback`, which is an authenticated page that extracts the
> `code` and `state` and forwards them to `POST /api/brokers/saxo/callback`
> with the user's bearer token. That keeps the backend endpoint bearer-auth
> only; the backend never serves anonymous Saxo traffic.
3. Set **Environment** to `SIM`, toggle **Enable** on, hit **Save**.
4. Click **Connect**. A Saxo-hosted login page opens; authorize the SIM user.
   Saxo redirects back to `/api/brokers/saxo/callback`, the adapter exchanges
   the authorization code for tokens, and the status pill flips to
   **Connected**.

## Kill-switch

Flipping **Enable** off in Settings halts all Saxo traffic on the next request
— no HTTP call is made, no refresh is attempted, no log line is emitted. Flip
it back on to resume; tokens stay valid across toggles until you hit
**Disconnect**, which wipes them and forces a fresh OAuth flow.

## Token handling

- **Access token**: ~20 minutes. Refreshed automatically with a 60s skew.
- **Refresh token**: ~1 hour, **rotates on every use** — using it once
  invalidates it. The adapter persists the new triple
  (`access`, `refresh`, `expires_at`) in a single DB transaction, so a crash
  mid-refresh cannot leave the store inconsistent. If the old refresh token
  was already consumed server-side when we crashed, the next call falls back
  to `AuthState.NEEDS_AUTH` and prompts the user to reconnect — no permanent
  lockout.

## Rate limiting

Each `(api_base, token_url)` pair shares one `SaxoHTTPClient` whose internal
token-bucket limiter caps outbound traffic at ~60 req/min. Sharing is fine for
single-user deployments; when multi-user lands, swap in a per-user limiter.

## Testing

```bash
cd backend
pytest tests/brokers                  # unit tests, mocked via respx
SAXO_SIM_TEST_TOKEN=... pytest tests/brokers/test_saxo_sim.py   # live SIM
```

The integration test is skipped automatically when `SAXO_SIM_TEST_TOKEN` is
unset.
