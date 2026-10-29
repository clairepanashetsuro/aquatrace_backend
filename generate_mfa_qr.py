import qrcode

uri = input("Paste the complete provisioning URI: ").strip()

if not uri.startswith("otpauth://totp/"):
    raise ValueError("Expected an otpauth://totp/ provisioning URI")

image = qrcode.make(uri)
image.save("aquatrace_mfa_qr.png")

print("QR code saved to ~/cytech-backend/aquatrace_mfa_qr.png")
