from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

MODULE_SPEC = spec_from_file_location(
    "activate_dodo_live_env", Path(__file__).with_name("activate_dodo_live_env.py")
)
assert MODULE_SPEC is not None and MODULE_SPEC.loader is not None
activation = module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(activation)


def test_activate_promotes_staged_values_and_keeps_secrets_out_of_output(tmp_path: Path) -> None:
    environment = tmp_path / "drumscribe.env"
    environment.write_text(
        """UNRELATED=value
DRUMSCRIBE_BILLING_PROVIDER=dodo
DRUMSCRIBE_DODO_PAYMENTS_ENVIRONMENT=test_mode
DRUMSCRIBE_DODO_PAYMENTS_API_KEY=test-api
DRUMSCRIBE_DODO_PAYMENTS_WEBHOOK_KEY=test-webhook
DRUMSCRIBE_DODO_CREDIT_PACK_PRODUCT_ID=pdt_test
DRUMSCRIBE_DODO_LIVE_API_KEY=live-api-secret
DRUMSCRIBE_DODO_LIVE_WEBHOOK_KEY=live-webhook-secret
DRUMSCRIBE_DODO_LIVE_PRODUCT_ID=pdt_live
DRUMSCRIBE_BILLING_RETURN_URL=https://drumtoscore.com/billing/success
DRUMSCRIBE_BILLING_CANCEL_URL=https://drumtoscore.com/pricing
DRUMSCRIBE_CREDIT_PACK_SIZE=10
""",
        encoding="utf-8",
    )
    environment.chmod(0o600)

    backup = activation.activate(environment)

    active = activation.parse_environment(environment.read_text(encoding="utf-8").splitlines())
    previous = activation.parse_environment(backup.read_text(encoding="utf-8").splitlines())
    assert active["DRUMSCRIBE_DODO_PAYMENTS_ENVIRONMENT"] == "live_mode"
    assert active["DRUMSCRIBE_DODO_PAYMENTS_API_KEY"] == "live-api-secret"
    assert active["DRUMSCRIBE_DODO_PAYMENTS_WEBHOOK_KEY"] == "live-webhook-secret"
    assert active["DRUMSCRIBE_DODO_CREDIT_PACK_PRODUCT_ID"] == "pdt_live"
    assert active["UNRELATED"] == "value"
    assert previous["DRUMSCRIBE_DODO_PAYMENTS_ENVIRONMENT"] == "test_mode"
    assert environment.stat().st_mode & 0o777 == 0o600
    assert backup.stat().st_mode & 0o777 == 0o600
