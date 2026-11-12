from ipaddress import IPv4Address, IPv6Address

from pydantic import TypeAdapter

from schemas.audit_log import AuditLogRead


def test_audit_log_ip_address_accepts_ipv4():
    field = AuditLogRead.model_fields["ip_address"]
    adapter = TypeAdapter(field.annotation)
    address = IPv4Address("192.0.2.10")

    assert adapter.validate_python(address) == address


def test_audit_log_ip_address_accepts_ipv6():
    field = AuditLogRead.model_fields["ip_address"]
    adapter = TypeAdapter(field.annotation)
    address = IPv6Address("2001:db8::1")

    assert adapter.validate_python(address) == address


def test_audit_log_ip_address_accepts_none():
    field = AuditLogRead.model_fields["ip_address"]
    adapter = TypeAdapter(field.annotation)

    assert adapter.validate_python(None) is None
