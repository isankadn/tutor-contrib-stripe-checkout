FROM {{ STRIPE_CHECKOUT_ECOMMERCE_BASE_IMAGE }}

COPY --chown=app:app openedx_stripe_checkout-0.1.0-py3-none-any.whl.b64 /tmp/openedx_stripe_checkout.whl.b64
RUN base64 --decode /tmp/openedx_stripe_checkout.whl.b64 > /tmp/openedx_stripe_checkout-0.1.0-py3-none-any.whl \
    && pip install --no-cache-dir /tmp/openedx_stripe_checkout-0.1.0-py3-none-any.whl \
    && rm /tmp/openedx_stripe_checkout.whl.b64 /tmp/openedx_stripe_checkout-0.1.0-py3-none-any.whl
