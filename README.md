# get-transaction-receipt

Reliable transaction receipt fetching with automatic multi-provider fallback

Fetch transaction receipts / transaction details from many blockchains using GetBlock, Ankr and Helius (Solana), with smart fallback logic and normalized output.

Supported Networks
------------------

Network     | Aliases              | Providers available              | Type     | Notes
------------|----------------------|----------------------------------|----------|------------------------------------
ETH         | ethereum             | GetBlock, Ankr                   | EVM      |
BSC         | bnb, binance         | Ankr, GetBlock                   | EVM      | Ankr often first
POLYGON     | matic                | GetBlock, Ankr                   | EVM      |
BASE        | base                 | GetBlock, Ankr                   | EVM      | Coinbase L2
OP          | optimism             | GetBlock, Ankr                   | EVM      |
ARB         | arbitrum             | GetBlock, Ankr                   | EVM      |
AVAX        | avalanche, c-chain   | GetBlock, Ankr                   | EVM      |

Installation
------------

pip install get-transaction-receipt

# or latest version directly from GitHub:
pip install git+https://github.com/meysamzandy/get_transaction_receipt.git

sample of usage
-----------

```
from get_transaction_receipt import TransactionReceiptClient
client = TransactionReceiptClient(
    provider_urls={
        "GETBLOCK": {
            "ethereum":   GETBLOCK_ETHEREUM_URL,
            "bsc":        GETBLOCK_BSC_URL,
            "polygon":    GETBLOCK_POLYGON_URL,
            "base":       GETBLOCK_BASE_URL,
            "optimism":   GETBLOCK_OPTIMISM_URL,
            "arbitrum":   GETBLOCK_ARBITRUM_URL,
            "avalanche":  GETBLOCK_AVALANCHE_URL,
            "bitcoin":    GETBLOCK_BITCOIN_URL,
            "dogecoin":   GETBLOCK_DOGECOIN_URL,
            "tron":       GETBLOCK_TRON_URL,
            "ton":        GETBLOCK_TON_URL,
            "xrp":        GETBLOCK_XRP_URL,
        },
        "ANKR": {
            "ethereum":   ANKR_ETHEREUM_URL,
            "bsc":        ANKR_BSC_URL,
            "polygon":    ANKR_POLYGON_URL,
            "base":       ANKR_BASE_URL,
            "optimism":   ANKR_OPTIMISM_URL,
            "arbitrum":   ANKR_ARBITRUM_URL,
            "avalanche":  ANKR_AVALANCHE_URL,
            "tron":       ANKR_TRON_URL,
            "solana":     ANKR_SOL_URL,
            "ton":        ANKR_TON_URL,
            "xrp":        ANKR_XRP_URL,
            "bitcoin":    ANKR_BTC_URL,

        },
        "HELIUS": {
            "solana":     HELIUS_SOL_URL,
        }
    },
    default_fallback_order=["GETBLOCK", "ANKR", "HELIUS"]
)
```

```
client.get_receipt("0x80cb65205fc3bed31e8918018efc55dd5eb77bc74cb7b79cf6cb9df3a7be8340", network="ethereum")
```

Provider supported
----------------------------

Provider   |
-----------|------------
GETBLOCK   | EVM
ANKR       | EVM
HELIUS     | SOL

You only need to provide the providers/keys you actually want to use.
Missing keys are automatically skipped.


Requirements
------------
• Python 3.8 or newer
• httpx

License
-------
MIT