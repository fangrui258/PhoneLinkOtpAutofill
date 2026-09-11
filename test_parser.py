from PhoneLinkOtpAutofill import extract_otp

CASES = [
    ("【Moka招聘】您的验证码为504659，有效期15分钟，如非本人操作，请忽略本短信。", "504659"),
    ("【北森】验证码:794141（10分钟内有效）", "794141"),
    ("Your verification code is 123456. Do not share it.", "123456"),
    ("OTP 8821 is valid for 5 minutes", "8821"),
    ("订单号123456已发货", None),
]

for text, expected in CASES:
    got = extract_otp(text)
    assert got == expected, (text, expected, got)

print("parser tests passed")
