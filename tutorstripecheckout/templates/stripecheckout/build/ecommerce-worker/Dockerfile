FROM {{ STRIPE_CHECKOUT_WORKER_BASE_IMAGE }}

USER root
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get upgrade --yes \
    && rm -rf /var/lib/apt/lists/*
USER 1000

COPY --chown=app:app openedx_stripe_checkout-0.1.0-py3-none-any.whl.b64 /tmp/openedx_stripe_checkout.whl.b64
RUN base64 --decode /tmp/openedx_stripe_checkout.whl.b64 > /tmp/openedx_stripe_checkout-0.1.0-py3-none-any.whl \
    && pip install --no-cache-dir /tmp/openedx_stripe_checkout-0.1.0-py3-none-any.whl \
    && rm /tmp/openedx_stripe_checkout.whl.b64 /tmp/openedx_stripe_checkout-0.1.0-py3-none-any.whl

USER root
RUN DEBIAN_FRONTEND=noninteractive apt-get purge --yes \
        binutils \
        cpp-9 \
        g++ \
        g++-9 \
        gcc \
        gcc-9 \
        libcurl3-gnutls \
        git \
        git-man \
        libc-dev-bin \
        libc6-dev \
        libexpat1-dev \
        libpython3.8-dev \
        linux-libc-dev \
        openssh-client \
        python3.8-dev
USER 1000
