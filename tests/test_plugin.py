import importlib
from pathlib import Path

from tutor import hooks


def plugin_module():
    return importlib.import_module("tutorstripecheckout.plugin")


def test_gate_c_defaults_are_safe_and_version_pinned():
    plugin = plugin_module()
    defaults = dict(hooks.Filters.CONFIG_DEFAULTS.apply([]))
    overrides = dict(hooks.Filters.CONFIG_OVERRIDES.apply([]))

    assert defaults["STRIPE_CHECKOUT_ENABLED"] is False
    assert defaults["STRIPE_CHECKOUT_MODE"] == "test"
    assert defaults["STRIPE_CHECKOUT_API_VERSION"] == "2026-02-25.clover"
    assert defaults["STRIPE_CHECKOUT_CURRENCY"] == "USD"
    assert defaults["STRIPE_CHECKOUT_SECRET_KEY_HOST_PATH"].endswith("/secret_key")
    assert defaults["STRIPE_CHECKOUT_WEBHOOK_SECRET_HOST_PATH"].endswith("/webhook_secret")
    assert overrides["ECOMMERCE_DOCKER_IMAGE"] == "openedx-ecommerce-stripe-checkout:0.1.3"
    assert overrides["ECOMMERCE_WORKER_DOCKER_IMAGE"] == (
        "openedx-ecommerce-worker-stripe-checkout:0.1.3"
    )
    assert "STRIPE_CHECKOUT_PAYMENT_MFE_REPOSITORY" not in defaults
    assert "STRIPE_CHECKOUT_PAYMENT_MFE_VERSION" not in defaults
    assert overrides["ECOMMERCE_PAYMENT_MFE_APP"] == {
        "name": "payment",
        "repository": "https://github.com/isankadn/frontend-app-payment",
        "version": "stripe-checkout-tutor15-v0.1.0",
        "port": 1998,
    }
    assert "{{" not in repr(overrides["ECOMMERCE_PAYMENT_MFE_APP"])
    assert "sk_" not in repr(defaults)
    assert "whsec_" not in repr(defaults)
    assert plugin._SECRET_KEY_CONTAINER_PATH.startswith("/run/secrets/")


def test_ecommerce_image_builds_are_replaced_without_touching_other_images():
    plugin = plugin_module()
    tasks = [
        ("openedx", ("build", "openedx"), "openedx:test", ()),
        ("ecommerce", ("plugins", "ecommerce", "build", "ecommerce"), "old-web", ()),
        (
            "ecommerce-worker",
            ("plugins", "ecommerce", "build", "ecommerce-worker"),
            "old-worker",
            (),
        ),
    ]

    replaced = plugin._replace_ecommerce_image_builds(tasks, {})

    assert replaced[0] == tasks[0]
    assert replaced[1] == (
        "ecommerce",
        ("plugins", "stripecheckout", "build", "ecommerce"),
        "{{ ECOMMERCE_DOCKER_IMAGE }}",
        (),
    )
    assert replaced[2] == (
        "ecommerce-worker",
        ("plugins", "stripecheckout", "build", "ecommerce-worker"),
        "{{ ECOMMERCE_WORKER_DOCKER_IMAGE }}",
        (),
    )


def test_secret_mount_callbacks_are_registered_for_dev_and_local():
    plugin = plugin_module()

    dev_callbacks = [callback.func for callback in hooks.Filters.COMPOSE_DEV_TMP.callbacks]
    local_callbacks = [callback.func for callback in hooks.Filters.COMPOSE_LOCAL_TMP.callbacks]

    assert plugin._mount_secret_files_if_present in dev_callbacks
    assert plugin._mount_secret_files_if_present in local_callbacks


def test_secret_mounts_are_read_only_web_only_and_idempotent():
    plugin = plugin_module()
    compose = {"services": {"ecommerce-worker": {"volumes": []}}}
    key_path = Path("/secure/secret_key")
    webhook_path = Path("/secure/webhook_secret")

    once = plugin._mount_secret_files(compose, key_path, webhook_path)
    twice = plugin._mount_secret_files(once, key_path, webhook_path)

    assert twice == once
    volumes = once["services"]["ecommerce"]["volumes"]
    assert volumes == [
        {
            "type": "bind",
            "source": str(key_path),
            "target": "/run/secrets/stripe-checkout/secret_key",
            "read_only": True,
        },
        {
            "type": "bind",
            "source": str(webhook_path),
            "target": "/run/secrets/stripe-checkout/webhook_secret",
            "read_only": True,
        },
    ]
    assert once["services"]["ecommerce-worker"]["volumes"] == []

def test_secret_mounts_are_skipped_until_both_files_exist(tmp_path, monkeypatch):
    plugin = plugin_module()
    key_path = tmp_path / "secret_key"
    webhook_path = tmp_path / "webhook_secret"
    config = {
        "STRIPE_CHECKOUT_SECRET_KEY_HOST_PATH": str(key_path),
        "STRIPE_CHECKOUT_WEBHOOK_SECRET_HOST_PATH": str(webhook_path),
    }
    monkeypatch.setenv("TUTOR_ROOT", str(tmp_path))
    monkeypatch.setattr(plugin.tutor_config, "load_full", lambda root: config)

    compose = {"services": {}}
    assert plugin._mount_secret_files_if_present(compose) == compose
    key_path.touch()
    assert plugin._mount_secret_files_if_present(compose) == compose
    webhook_path.touch()

    mounted = plugin._mount_secret_files_if_present(compose)
    assert mounted["services"]["ecommerce"]["volumes"] == [
        {
            "type": "bind",
            "source": str(key_path),
            "target": "/run/secrets/stripe-checkout/secret_key",
            "read_only": True,
        },
        {
            "type": "bind",
            "source": str(webhook_path),
            "target": "/run/secrets/stripe-checkout/webhook_secret",
            "read_only": True,
        },
    ]


def test_secret_mounts_use_tutor_default_root_without_environment(
    tmp_path, monkeypatch
):
    plugin = plugin_module()
    key_path = tmp_path / "secret_key"
    webhook_path = tmp_path / "webhook_secret"
    key_path.touch()
    webhook_path.touch()
    config = {
        "STRIPE_CHECKOUT_SECRET_KEY_HOST_PATH": str(key_path),
        "STRIPE_CHECKOUT_WEBHOOK_SECRET_HOST_PATH": str(webhook_path),
    }
    loaded_roots = []
    monkeypatch.delenv("TUTOR_ROOT", raising=False)
    monkeypatch.setattr(
        plugin.appdirs,
        "user_data_dir",
        lambda *, appname: str(tmp_path),
    )
    monkeypatch.setattr(
        plugin.tutor_config,
        "load_full",
        lambda root: loaded_roots.append(root) or config,
    )

    mounted = plugin._mount_secret_files_if_present({"services": {}})

    assert loaded_roots == [str(tmp_path)]
    assert [
        volume["target"]
        for volume in mounted["services"]["ecommerce"]["volumes"]
    ] == [
        "/run/secrets/stripe-checkout/secret_key",
        "/run/secrets/stripe-checkout/webhook_secret",
    ]


def test_gate_c_init_migrates_and_updates_processor_switch_idempotently():
    plugin = plugin_module()
    task = plugin._GATE_C_INIT_TASK
    registered = hooks.Filters.CLI_DO_INIT_TASKS.apply([])
    ecommerce_registered = list(
        hooks.Filters.CLI_DO_INIT_TASKS.iterate_from_context(
            hooks.Contexts.APP("ecommerce").name
        )
    )

    assert ("ecommerce", task) in registered
    assert ("ecommerce", task) in ecommerce_registered
    assert task.splitlines()[0] == "./manage.py migrate openedx_stripe_checkout --noinput"
    assert "dict.fromkeys(processors + ['stripe-checkout'])" in task
    assert "site__domain='{{ ECOMMERCE_HOST }}'" in task
    assert "site_id=1" not in task
    assert "Switch.objects.update_or_create" in task
    assert "payment_processor_active_" not in task
    assert "PAYMENT_PROCESSOR_SWITCH_PREFIX" in task
    assert "STRIPE_CHECKOUT_ENABLED" in task


def test_settings_and_mfe_patches_share_one_enablement_source():
    plugin = plugin_module()
    settings_patch = (plugin._PACKAGE_ROOT / "patches" / "ecommerce-settings-common").read_text()
    mfe_patch = (plugin._PACKAGE_ROOT / "patches" / "openedx-lms-production-settings").read_text()
    registered = dict(hooks.Filters.ENV_PATCHES.apply([]))

    assert registered["ecommerce-settings-common"] == settings_patch
    assert registered["openedx-lms-production-settings"] == mfe_patch
    assert registered["openedx-lms-development-settings"] == mfe_patch
    assert 'ROOT_URLCONF = "openedx_stripe_checkout.urls"' in settings_patch
    assert '"openedx_stripe_checkout.processor.StripeCheckout"' in settings_patch
    assert '"stripe-checkout"' in settings_patch
    assert '"secret_key_file": "/run/secrets/stripe-checkout/secret_key"' in settings_patch
    assert '"webhook_secret_file": "/run/secrets/stripe-checkout/webhook_secret"' in settings_patch
    assert "STRIPE_CHECKOUT_ENABLED" in mfe_patch
    assert "sk_test_" not in settings_patch
    assert "whsec_" not in settings_patch


def test_derived_dockerfiles_install_same_versioned_wheel():
    plugin = plugin_module()
    files = [
        plugin._PACKAGE_ROOT / "templates" / "stripecheckout" / "build" / "ecommerce" / "Dockerfile",
        plugin._PACKAGE_ROOT / "templates" / "stripecheckout" / "build" / "ecommerce-worker" / "Dockerfile",
    ]

    contents = [path.read_text() for path in files]
    for content in contents:
        assert "openedx_stripe_checkout-0.1.0-py3-none-any.whl" in content
        assert "pip install --no-cache-dir" in content
        assert "apt-get upgrade --yes" in content
        assert "linux-libc-dev" in content
        assert "apt-get purge --yes" in content
        assert content.rstrip().endswith("USER 1000")
        assert ".patch" not in content
    assert Path(files[0]).name == Path(files[1]).name == "Dockerfile"


def test_remote_development_port_rewrite_remains_narrow():
    plugin = plugin_module()
    patches = [
        (
            "local-docker-compose-dev-services",
            'ports:\n  - "127.0.0.1:8130:8130"\n',
        ),
        ("unrelated", 'ports:\n  - "127.0.0.1:9999:9999"\n'),
    ]

    rewritten = plugin._expose_ecommerce_development_port(patches)

    assert rewritten[0][1] == 'ports:\n  - "0.0.0.0:8130:8130"\n'
    assert rewritten[1] == patches[1]
