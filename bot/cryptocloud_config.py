# Синхронизировать с валютами, включёнными в проекте CryptoCloud (ЛК).
# code — значение add_fields.cryptocurrency / available_currencies.

CRYPTOCLOUD_CURRENCIES_METADATA = [
    ("USDT_TRC20", "USDT (TRC-20)"),
    ("USDT_ERC20", "USDT (ERC-20)"),
    ("USDC_ERC20", "USDC (ERC-20)"),
    ("USDT_BSC", "USDT (BSC)"),
    ("BTC", "Bitcoin"),
    ("LTC", "Litecoin"),
    ("ETH", "Ethereum"),
    ("TRX", "Tron"),
    ("SOL", "Solana"),
    ("TON", "TON"),
    ("BNB", "BNB"),
    ("ETH_ARB", "ETH (Arbitrum)"),
    ("ETH_OPT", "ETH (Optimism)"),
    ("ETH_BASE", "ETH (Base)"),
    ("USDT_TON", "USDT (TON)"),
    ("USDT_SOL", "USDT (Solana)"),
    ("USDC_SOL", "USDC (Solana)"),
    ("USDC_BASE", "USDC (Base)"),
    ("USDC_BSC", "USDC (BSC)"),
    ("USDT_ARB", "USDT (Arbitrum)"),
    ("USDC_ARB", "USDC (Arbitrum)"),
    ("USDT_OPT", "USDT (Optimism)"),
    ("USDC_OPT", "USDC (Optimism)"),
    ("USDD_TRC20", "USDD (TRC-20)"),
    ("SHIB_ERC20", "SHIB (ERC-20)"),
]

CRYPTOCLOUD_AVAILABLE_CURRENCIES = tuple(c[0] for c in CRYPTOCLOUD_CURRENCIES_METADATA)

CRYPTOCLOUD_DEFAULT_CURRENCY = "USDT_TRC20"
