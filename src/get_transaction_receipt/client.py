from __future__ import annotations

import httpx
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Callable

from .exceptions import ReceiptNotFoundError, AllProvidersFailedError, UnsupportedNetworkError
from .normalizer import normalize_receipt, NormalizedReceipt

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    supported_networks: set[str]


PROVIDER_CONFIGS = [
    ProviderConfig("GETBLOCK", {
        "ethereum", "bsc", "polygon", "base", "optimism", "arbitrum", "avalanche",
        "tron", "bitcoin",
    }),
    ProviderConfig("ANKR", {
        "ethereum", "bsc", "polygon", "base", "optimism", "arbitrum", "avalanche",
        "tron","bitcoin",
    }),
    ProviderConfig("HELIUS", {"solana"}),
]


@dataclass(frozen=True)
class RpcMethodConfig:
    method: str
    params_factory: Callable[[str], list[Any] | dict[str, Any]]
    is_receipt_like: bool = True
    is_jsonrpc: bool = True  # new: some chains use REST


RPC_METHODS: Dict[str, RpcMethodConfig] = {
    "ethereum":   RpcMethodConfig("eth_getTransactionReceipt", lambda h: [h]),
    "bsc":        RpcMethodConfig("eth_getTransactionReceipt", lambda h: [h]),
    "polygon":    RpcMethodConfig("eth_getTransactionReceipt", lambda h: [h]),
    "base":       RpcMethodConfig("eth_getTransactionReceipt", lambda h: [h]),
    "optimism":   RpcMethodConfig("eth_getTransactionReceipt", lambda h: [h]),
    "arbitrum":   RpcMethodConfig("eth_getTransactionReceipt", lambda h: [h]),
    "avalanche":  RpcMethodConfig("eth_getTransactionReceipt", lambda h: [h]),

    "tron": RpcMethodConfig("eth_getTransactionReceipt", lambda h: [h]),

    "bitcoin":  RpcMethodConfig("getrawtransaction", lambda h: [h, True], is_receipt_like=False),

    "solana": RpcMethodConfig(
        "getTransaction",
        lambda h: [h, {"encoding": "jsonParsed", "commitment": "finalized", "maxSupportedTransactionVersion": 0}]
    ),
}

SUPPORTED_NETWORKS = set(RPC_METHODS.keys())


class TransactionReceiptClient:
    def __init__(
        self,
        provider_urls: Dict[str, Dict[str, str]],
        default_fallback_order: Optional[List[str]] = None,
        httpx_client: Optional[httpx.Client] = None,
    ):
        self.network_to_providers: Dict[str, List[Tuple[str, str]]] = {}

        fallback_order = default_fallback_order or [cfg.name for cfg in PROVIDER_CONFIGS]

        for net in SUPPORTED_NETWORKS:
            candidates: List[Tuple[int, str, str]] = []

            for provider_name in fallback_order:
                if provider_name not in provider_urls:
                    continue
                urls = provider_urls[provider_name]
                if net in urls:
                    url = urls[net].rstrip("/")
                    priority = fallback_order.index(provider_name)
                    candidates.append((priority, provider_name, url))

            if candidates:
                candidates.sort(key=lambda x: x[0])
                self.network_to_providers[net] = [(prov, url) for _, prov, url in candidates]

        if not self.network_to_providers:
            raise ValueError("No valid provider URLs configured")

        self.http = httpx_client or httpx.Client(timeout=15.0)
        logger.info("Initialized with providers: %s",
                    {net: [p for p, _ in provs] for net, provs in self.network_to_providers.items()})

    def get_receipt(
        self,
        tx_hash: str,
        network: str,
        preferred_order: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        net_key = network.lower().strip()
        tx_hash = tx_hash.strip()

        if net_key not in SUPPORTED_NETWORKS:
            raise UnsupportedNetworkError(f"Unsupported: {network}\nSupported: {sorted(SUPPORTED_NETWORKS)}")

        providers = preferred_order or [p for p, _ in self.network_to_providers.get(net_key, [])]

        if not providers:
            raise ValueError(f"No providers for {network}")

        method_cfg = RPC_METHODS[net_key]

        # Special case for TON — warn or fail early
        if net_key == "ton":
            logger.warning("TON tx lookup by hash only is unreliable — most providers need address")

        payload = None
        if method_cfg.is_jsonrpc:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": method_cfg.method,
                "params": method_cfg.params_factory(tx_hash),
            }

        tried: List[Tuple[str, str]] = []
        successes = []

        for provider_name in providers:
            url = next((u for p, u in self.network_to_providers[net_key] if p == provider_name), None)
            if not url:
                tried.append((provider_name, "no_url"))
                continue

            tried.append((provider_name, "attempted"))

            try:
                if payload is not None:
                    resp = self.http.post(url, json=payload, timeout=12.0)
                else:
                    # future: REST handling
                    resp = self.http.get(f"{url}?hash={tx_hash}", timeout=12.0)

                resp.raise_for_status()
                data = resp.json()

                if "error" in data:
                    err = data["error"]
                    err_msg = str(err).lower()
                    if any(kw in err_msg for kw in ["not found", "unknown", "does not exist", "invalid transaction", "invalid param"]):
                        tried[-1] = (provider_name, "not_found_or_invalid")
                        continue
                    tried[-1] = (provider_name, f"rpc_error: {err}")
                    continue

                result = data.get("result")
                if result in (None, "", []):
                    tried[-1] = (provider_name, "null_or_empty_result")
                    continue

                extra = {}
                if net_key in {"bitcoin", "dogecoin"} and isinstance(result, dict) and result.get("blockhash"):
                    extra = self._fetch_block_height(net_key, result["blockhash"], provider_name, url)

                normalized = normalize_receipt(result, net_key, extra_data=extra)
                result_dict = normalized.as_dict()
                result_dict["tried_providers"] = [p for p, _ in tried]
                result_dict["used_provider"] = provider_name

                successes.append((provider_name, result_dict))
                break

            except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as e:
                tried[-1] = (provider_name, f"network_error: {str(e)}")
            except httpx.HTTPStatusError as e:
                tried[-1] = (provider_name, f"http_{e.response.status_code}: {str(e)}")
            except json.JSONDecodeError:
                tried[-1] = (provider_name, "invalid_json")
            except Exception as e:
                tried[-1] = (provider_name, f"unexpected: {type(e).__name__} - {str(e)}")

        if successes:
            return successes[0][1]

        not_found_only = all(any(k in o for k in ["not_found", "null", "invalid"]) for _, o in tried)
        tried_str = ", ".join(f"{p} ({o})" for p, o in tried)

        if not_found_only:
            raise ReceiptNotFoundError(
                f"Transaction {tx_hash} not found on {network}\nTried: {tried_str}"
            )

        raise AllProvidersFailedError(
            f"All providers failed for {network}/{tx_hash}\nTried:\n" + "\n".join(f"  • {p}: {o}" for p, o in tried)
        )

    def _fetch_block_height(self, network: str, block_hash: str, provider: str, url: str) -> Dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getblockheader",
            "params": [block_hash, True]
        }
        try:
            r = self.http.post(url, json=payload, timeout=8.0)
            r.raise_for_status()
            data = r.json()
            height = data.get("result", {}).get("height")
            if height is not None:
                return {"height": height}
        except Exception as e:
            logger.warning("Block height fetch failed %s %s: %s", provider, network, e)
        return {}