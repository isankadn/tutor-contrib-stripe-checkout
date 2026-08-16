"""Tutor 15 integration for the Stripe Checkout Gate C package."""

import os
from pathlib import Path

from tutor import config as tutor_config
from tutor import hooks

_PACKAGE_ROOT = Path(__file__).resolve().parent
_TEMPLATE_ROOT = _PACKAGE_ROOT / "templates"
_SECRET_KEY_CONTAINER_PATH = "/run/secrets/stripe-checkout/secret_key"
_WEBHOOK_SECRET_CONTAINER_PATH = "/run/secrets/stripe-checkout/webhook_secret"
_ECOMMERCE_LOOPBACK_BIND = '"127.0.0.1:8130:8130"'
_ECOMMERCE_REMOTE_BIND = '"0.0.0.0:8130:8130"'
_PAYMENT_MFE_REPOSITORY = "https://github.com/isankadn/frontend-app-payment"
_PAYMENT_MFE_VERSION = "stripe-checkout-tutor15-v0.1.0"

_CONFIG_DEFAULTS = {
    "STRIPE_CHECKOUT_ENABLED": False,
    "STRIPE_CHECKOUT_MODE": "test",
    "STRIPE_CHECKOUT_EXPECTED_ACCOUNT_ID": "SET-ME",
    "STRIPE_CHECKOUT_API_VERSION": "2026-02-25.clover",
    "STRIPE_CHECKOUT_CURRENCY": "USD",
    "STRIPE_CHECKOUT_PUBLIC_BASE_URL": "http://ecommerce.local.overhang.io:8130",
    "STRIPE_CHECKOUT_SECRET_KEY_HOST_PATH": "/home/dev/.config/stripe-checkout/secret_key",
    "STRIPE_CHECKOUT_WEBHOOK_SECRET_HOST_PATH": "/home/dev/.config/stripe-checkout/webhook_secret",
    "STRIPE_CHECKOUT_SECRET_UID": 1000,
    "STRIPE_CHECKOUT_SECRET_GID": 1000,
    "STRIPE_CHECKOUT_CALLBACK_MAX_AGE": 3600,
    "STRIPE_CHECKOUT_WEBHOOK_TOLERANCE": 300,
    "STRIPE_CHECKOUT_WEBHOOK_MAX_BYTES": 262144,
    "STRIPE_CHECKOUT_REQUEST_TIMEOUT": 10,
    "STRIPE_CHECKOUT_MAX_NETWORK_RETRIES": 2,
    "STRIPE_CHECKOUT_SESSION_TTL": 1800,
    "STRIPE_CHECKOUT_ECOMMERCE_BASE_IMAGE": "docker.io/overhangio/openedx-ecommerce:15.0.2",
    "STRIPE_CHECKOUT_WORKER_BASE_IMAGE": "docker.io/overhangio/openedx-ecommerce-worker:15.0.2",
}

hooks.Filters.CONFIG_DEFAULTS.add_items(list(_CONFIG_DEFAULTS.items()))
hooks.Filters.CONFIG_OVERRIDES.add_items(
    [
        (
            "ECOMMERCE_DOCKER_IMAGE",
            "openedx-ecommerce-stripe-checkout:0.1.3",
        ),
        (
            "ECOMMERCE_WORKER_DOCKER_IMAGE",
            "openedx-ecommerce-worker-stripe-checkout:0.1.3",
        ),
        (
            "ECOMMERCE_PAYMENT_MFE_APP",
            {
                "name": "payment",
                "repository": _PAYMENT_MFE_REPOSITORY,
                "version": _PAYMENT_MFE_VERSION,
                "port": 1998,
            },
        ),
    ]
)

hooks.Filters.ENV_TEMPLATE_ROOTS.add_item(str(_TEMPLATE_ROOT))
hooks.Filters.ENV_TEMPLATE_TARGETS.add_item(("stripecheckout/build", "plugins"))


@hooks.Filters.IMAGES_BUILD.add(priority=100)
def _replace_ecommerce_image_builds(tasks, config):
    """Build versioned derived web and worker images from one pinned wheel."""
    replacements = {
        "ecommerce": (
            "ecommerce",
            ("plugins", "stripecheckout", "build", "ecommerce"),
            "{{ ECOMMERCE_DOCKER_IMAGE }}",
            (),
        ),
        "ecommerce-worker": (
            "ecommerce-worker",
            ("plugins", "stripecheckout", "build", "ecommerce-worker"),
            "{{ ECOMMERCE_WORKER_DOCKER_IMAGE }}",
            (),
        ),
    }
    return [replacements.get(task[0], task) for task in tasks]


@hooks.Filters.ENV_PATCHES.add(priority=100)
def _expose_ecommerce_development_port(patches):
    """Expose Ecommerce for the approved remote development browser."""
    return [
        (
            name,
            content.replace(
                _ECOMMERCE_LOOPBACK_BIND,
                _ECOMMERCE_REMOTE_BIND,
                1,
            )
            if name == "local-docker-compose-dev-services"
            else content,
        )
        for name, content in patches
    ]


def _mount_secret_files(compose, key_host, webhook_host):
    """Mount resolved secret files read-only only into Ecommerce web."""
    service = compose.setdefault("services", {}).setdefault("ecommerce", {})
    volumes = service.setdefault("volumes", [])
    mounts = (
        {
            "type": "bind",
            "source": str(key_host),
            "target": _SECRET_KEY_CONTAINER_PATH,
            "read_only": True,
        },
        {
            "type": "bind",
            "source": str(webhook_host),
            "target": _WEBHOOK_SECRET_CONTAINER_PATH,
            "read_only": True,
        },
    )
    for mount in mounts:
        if mount not in volumes:
            volumes.append(mount)
    return compose


def _mount_secret_files_if_present(compose):
    """Mount configured secrets only when both host files exist."""
    tutor_root = os.environ.get("TUTOR_ROOT")
    if not tutor_root:
        return compose
    config = tutor_config.load_full(tutor_root)
    key_host = Path(
        os.path.expandvars(str(config["STRIPE_CHECKOUT_SECRET_KEY_HOST_PATH"]))
    ).expanduser()
    webhook_host = Path(
        os.path.expandvars(str(config["STRIPE_CHECKOUT_WEBHOOK_SECRET_HOST_PATH"]))
    ).expanduser()
    if not key_host.is_file() or not webhook_host.is_file():
        return compose
    return _mount_secret_files(compose, key_host, webhook_host)


hooks.Filters.COMPOSE_DEV_TMP.add()(_mount_secret_files_if_present)
hooks.Filters.COMPOSE_LOCAL_TMP.add()(_mount_secret_files_if_present)

_GATE_C_INIT_TASK = """\
./manage.py migrate openedx_stripe_checkout --noinput
./manage.py shell -c "
from django.conf import settings
from django.db import transaction
from ecommerce.core.models import SiteConfiguration
from waffle.models import Switch
with transaction.atomic():
    config = SiteConfiguration.objects.get(site_id=1)
    processors = [name.strip() for name in config.payment_processors.split(',') if name.strip()]
    config.payment_processors = ','.join(dict.fromkeys(processors + ['stripe-checkout']))
    config.full_clean()
    config.save(update_fields=['payment_processors'])
    Switch.objects.update_or_create(
        name=settings.PAYMENT_PROCESSOR_SWITCH_PREFIX + 'stripe-checkout',
        defaults={'active': {% if STRIPE_CHECKOUT_ENABLED %}True{% else %}False{% endif %}},
    )
"
"""

with hooks.Contexts.APP("ecommerce").enter():
    hooks.Filters.CLI_DO_INIT_TASKS.add_item(
        ("ecommerce", _GATE_C_INIT_TASK),
        priority=100,
    )

for patch_path in sorted((_PACKAGE_ROOT / "patches").iterdir()):
    if patch_path.is_file():
        hooks.Filters.ENV_PATCHES.add_item(
            (patch_path.name, patch_path.read_text())
        )
