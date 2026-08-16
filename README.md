# Tutor Stripe Checkout

Tutor 15 integration for the Open edX `stripe-checkout` processor. This guide configures a **development or Stripe sandbox environment**. It does not authorize a production deployment.

## Values required from Stripe

The integration needs three Stripe values:

| Value | Format | Where it is used |
|---|---|---|
| Test secret API key | `sk_test_...` | Server-to-server Stripe API calls |
| Stripe account ID | `acct_...` | Prevents using credentials from the wrong account |
| Webhook signing secret | `whsec_...` | Verifies webhook requests |

A publishable key (`pk_test_...`) is not needed because card data is collected on Stripe's hosted Checkout page.

### Test secret API key

1. Sign in to the [Stripe Dashboard test API keys page](https://dashboard.stripe.com/test/apikeys).
2. Make sure a sandbox/test environment is selected, not live mode.
3. Create or reveal a **secret key** beginning with `sk_test_`.
4. Copy it directly into the protected file described below. Do not put it in Git, Tutor YAML, source code, command arguments, email, or chat.

This plugin version accepts `sk_test_...` in test mode. It does not currently accept `pk_test_...` or `rk_test_...` keys.

### Account ID

In the Stripe Dashboard, open **Settings > Business > Account details** and copy the identifier beginning with `acct_`.

The account ID is not the secret API key. The backend verifies that the API key belongs to this exact account before creating a Checkout Session.

### Webhook signing secret

Webhook secrets are specific to one endpoint and are separate from API keys.

For local development, install and authenticate the [Stripe CLI](https://docs.stripe.com/stripe-cli), then keep this listener running:

```bash
stripe listen \
  --events checkout.session.completed,checkout.session.async_payment_succeeded,checkout.session.async_payment_failed,checkout.session.expired \
  --forward-to http://127.0.0.1:8130/payment/stripe-checkout/webhook/
```

The command prints a signing secret beginning with `whsec_`. Store that value in the protected webhook file below. If a later listener reports a different secret, update the file and recreate the Ecommerce service before testing again.

For a public deployment, create an HTTPS webhook endpoint in Stripe Workbench/Dashboard instead. Use this path on the public Ecommerce origin:

```text
/payment/stripe-checkout/webhook/
```

Subscribe it to the same four event types and copy that endpoint's signing secret. Do not reuse a Stripe CLI signing secret for a Dashboard endpoint.

## Store secrets on the Tutor host

The default development paths are:

```text
/home/dev/.config/stripe-checkout/secret_key
/home/dev/.config/stripe-checkout/webhook_secret
```

Run the following as the `dev` user, **without `sudo`**. You can paste the whole
block into Bash, or save it as `stripe_config.sh` and run
`bash ./stripe_config.sh`. The `#!/usr/bin/env bash` line is required when the
file is executed directly: `/bin/sh` does not support Bash's `read -s` option.

```bash
#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" -ne 1000 ]]; then
  echo "Run this script as the UID 1000 Tutor application user; do not use sudo." >&2
  exit 1
fi

secret_dir=/home/dev/.config/stripe-checkout
secret_key_file="$secret_dir/secret_key"
webhook_secret_file="$secret_dir/webhook_secret"

install -d -m 700 "$secret_dir"

# Permit an intentional rerun after previously creating mode-0400 files.
for secret_file in "$secret_key_file" "$webhook_secret_file"; do
  if [[ -e "$secret_file" ]]; then
    [[ -f "$secret_file" && ! -L "$secret_file" ]] || {
      echo "Refusing unsafe secret path: $secret_file" >&2
      exit 1
    }
    chmod 600 "$secret_file"
  fi
done

umask 077
read -rsp "Stripe test secret key: " STRIPE_SECRET_KEY
echo
printf '%s' "$STRIPE_SECRET_KEY" > "$secret_key_file"
unset STRIPE_SECRET_KEY

read -rsp "Stripe webhook signing secret: " STRIPE_WEBHOOK_SECRET
echo
printf '%s' "$STRIPE_WEBHOOK_SECRET" > "$webhook_secret_file"
unset STRIPE_WEBHOOK_SECRET

chmod 400 "$secret_key_file" "$webhook_secret_file"
```

If this was previously run with `sudo`, repair ownership once, then rerun it
without `sudo`:

```bash
sudo chown dev:dev \
  /home/dev/.config/stripe-checkout \
  /home/dev/.config/stripe-checkout/secret_key \
  /home/dev/.config/stripe-checkout/webhook_secret
sudo chmod 700 /home/dev/.config/stripe-checkout
sudo chmod 600 \
  /home/dev/.config/stripe-checkout/secret_key \
  /home/dev/.config/stripe-checkout/webhook_secret
bash ./stripe_config.sh
```

The default configuration requires:

- directory mode `0700`;
- file mode exactly `0400`;
- file owner UID `1000`;
- file group GID `1000`;
- regular files, not symlinks;
- an `sk_test_...` key when `STRIPE_CHECKOUT_MODE=test`;
- a `whsec_...` webhook secret.

Verify metadata without printing either secret:

```bash
stat -c '%U %G %a %F %n' \
  /home/dev/.config/stripe-checkout \
  /home/dev/.config/stripe-checkout/secret_key \
  /home/dev/.config/stripe-checkout/webhook_secret
```

If Tutor runs Ecommerce as a UID/GID other than `1000:1000`, set `STRIPE_CHECKOUT_SECRET_UID` and `STRIPE_CHECKOUT_SECRET_GID` to the actual container user and make the host files match.

## Configure Tutor

Run from the Tutor project root. Replace `acct_REPLACE_ME` with the Stripe account ID:

```bash
tutor config save \
  --set STRIPE_CHECKOUT_MODE=test \
  --set STRIPE_CHECKOUT_EXPECTED_ACCOUNT_ID=acct_REPLACE_ME \
  --set STRIPE_CHECKOUT_PUBLIC_BASE_URL=http://ecommerce.local.overhang.io:8130 \
  --set STRIPE_CHECKOUT_ENABLED=true
```

Do not put the API key or webhook secret in `tutor config save`; the plugin reads only the mounted files.

Keep these reviewed defaults unless the integration code and tests are deliberately updated:

```text
STRIPE_CHECKOUT_API_VERSION=2026-02-25.clover
STRIPE_CHECKOUT_CURRENCY=USD
```

The plugin pins the Payment MFE to the reviewed repository and immutable source
tag. These build inputs are intentionally fixed by this plugin release:

```text
Repository: https://github.com/isankadn/frontend-app-payment
Version: stripe-checkout-tutor15-v0.1.0
```

The derived Ecommerce image names default to local build tags. A deployment that
promotes prebuilt artifacts must replace them with immutable digest references:

```bash
tutor config save \
  --set ECOMMERCE_DOCKER_IMAGE=REGISTRY/ecommerce@sha256:DIGEST \
  --set ECOMMERCE_WORKER_DOCKER_IMAGE=REGISTRY/ecommerce-worker@sha256:DIGEST \
  --set MFE_DOCKER_IMAGE=REGISTRY/mfe@sha256:DIGEST \
  --set STRIPE_CHECKOUT_ENABLED=false
```

The first two settings are Tutor Ecommerce's standard web and worker image
values. Keep the processor disabled until the
digest-pinned web, worker, and MFE artifacts, migrations, mounts, PayPal flow,
and rollback path have been verified on the target.

Build the production MFE image from that immutable tag:

```bash
tutor images build mfe
```

Apply migrations and activate the Ecommerce processor switch:

```bash
tutor dev do init --limit ecommerce
```

Recreate Ecommerce so Docker applies the secret-file mounts:

```bash
tutor dev stop ecommerce
tutor dev start -d ecommerce
```

The development Payment MFE must run the modified source tree for the Stripe button to exist. Replace the path if the repository is elsewhere:

```bash
tutor dev stop payment
tutor dev start -d --skip-build \
  --mount /home/dev/workbench/targets/frontend-app-payment \
  payment
```

Restart the LMS if `/api/mfe_config/v1?mfe=payment` still reports an old value for `STRIPE_CHECKOUT_ENABLED`.

## Verify the development flow

1. Keep `stripe listen` running.
2. Start a purchase from the real LMS course page so Ecommerce creates the learner-owned basket.
3. Open the Payment MFE, normally `http://apps.local.overhang.io:1998/payment`.
4. Select **Pay securely with Stripe**.
5. Confirm the browser navigates to `https://checkout.stripe.com/c/pay/...`.
6. Use a [Stripe test card](https://docs.stripe.com/testing#cards), never a real card. Common test numbers include:
   - success: `4242 4242 4242 4242`;
   - 3D Secure authentication: `4000 0025 0000 3155`;
   - declined payment: `4000 0000 0000 9995`.
7. Confirm the callback, signed webhook, Ecommerce order, receipt, and enrollment converge exactly once.

Random or invented `sk_test_...`, `whsec_...`, and `acct_...` values can make the button visible, but they cannot create a Stripe Checkout Session. Stripe will reject a random API key.

## Disable Stripe Checkout

```bash
tutor config save --set STRIPE_CHECKOUT_ENABLED=false
tutor dev do init --limit ecommerce
```

Then restart the LMS, Ecommerce, and Payment MFE processes so the backend switch and learner-facing configuration are refreshed. Disabling Stripe Checkout does not disable PayPal.

## Security rules

- Use test credentials and Stripe test cards in development.
- Never commit or build secrets into an image.
- Never send `sk_...` or `whsec_...` values through chat or ordinary logs.
- Do not expose either secret to the Payment MFE or browser.
- Use distinct credentials and webhook endpoints for development and production.
- Rotate a key immediately if it is exposed.
- A production rollout requires HTTPS, live-mode configuration, an immutable frontend artifact, reviewed secret management, and separate deployment approval.

## Stripe references

- [API keys](https://docs.stripe.com/keys)
- [Stripe CLI](https://docs.stripe.com/stripe-cli)
- [Receive and test webhooks](https://docs.stripe.com/webhooks)
- [Test cards](https://docs.stripe.com/testing#cards)
