from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class NormalizedReceipt:
    transaction_hash: str
    fee: Optional[int]               # smallest unit
    status: Optional[bool]           # True=success, False=failed, None=pending/unknown
    chain: str
    contract_address: Optional[str] = None

    def as_dict(self) -> dict:
        d = {
            "tx_id": self.transaction_hash,
            "fee": self.fee,
            "status": self.status,
            "chain": self.chain,
        }
        if self.contract_address is not None:
            d["contractAddress"] = self.contract_address
        return d


def normalize_receipt(raw: Any, network: str, extra_data: Optional[dict] = None) -> NormalizedReceipt:
    network = network.lower().strip()
    data = dict(raw) if isinstance(raw, dict) else {}

    tx_hash = (
        data.get("transactionHash")
        or data.get("hash")
        or data.get("txid")
        or data.get("TransactionID")
        or data.get("id")
        or data.get("signature")  # solana
        or ""
    ).strip()

    evm_like = {"ethereum", "bsc", "polygon", "base", "optimism", "arbitrum", "avalanche", "tron"}
    if tx_hash and not tx_hash.startswith("0x") and network in evm_like:
        tx_hash = f"0x{tx_hash}"

    fee = None
    status: Optional[bool] = None
    contract_address = data.get("contractAddress")

    extra = extra_data or {}

    # EVM
    if network in evm_like:
        gas_used = _to_int(data.get("gasUsed"))
        gas_price = _to_int(data.get("effectiveGasPrice") or data.get("gasPrice"))
        if gas_used is not None and gas_price is not None:
            fee = gas_used * gas_price

        status_raw = data.get("status")
        if status_raw is not None:
            status = _to_int(status_raw) == 1

    # Solana
    elif network == "solana":
        meta = data.get("meta", {})
        fee = _to_int(meta.get("fee"))
        status = meta.get("err") is None

    # Bitcoin / Dogecoin
    elif network in {"bitcoin", "dogecoin"}:
        # fee still None (can improve later with vin/vout if you add prev tx fetch)
        confirmations = _to_int(data.get("confirmations", 0))
        if confirmations is not None and confirmations > 0:
            status = True
        elif "blockhash" in data or "height" in extra:
            status = True
        else:
            status = None  # unconfirmed / in mempool

    # TON — very partial (data structure varies a lot)
    elif network == "ton":
        fee_str = data.get("total_fees") or data.get("fee") or "0"
        fee = _to_int(fee_str)
        # Very conservative — assume present = success unless error field exists
        if "exit_code" in data and _to_int(data["exit_code"]) != 0:
            status = False
        elif data.get("aborted", False):
            status = False
        else:
            status = True if data else None

    # XRP
    elif network == "xrp":
        fee = _to_int(data.get("Fee"))
        meta = data.get("meta", {})
        if isinstance(meta, dict):
            status = meta.get("TransactionResult") == "tesSUCCESS"
        if data.get("validated", False) and status is None:
            status = meta.get("TransactionResult") == "tesSUCCESS"

    # Better general fallback
    if status is None:
        confirmed_keys = {"blockHash", "blockNumber", "slot", "height", "ledger_index", "ledger", "blockhash"}
        if any(k in data for k in confirmed_keys) or "height" in extra:
            status = True
        elif "confirmations" in data:
            conf = _to_int(data["confirmations"])
            status = conf is not None and conf > 0
        else:
            status = None  # pending

    return NormalizedReceipt(
        transaction_hash=tx_hash,
        fee=fee,
        status=status,
        chain=network,
        contract_address=contract_address,
    )


def _to_int(val: Any) -> Optional[int]:
    if val is None:
        return None
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        val = val.strip()
        if val.lower() in {"null", "none", ""}:
            return None
        if val.startswith(("0x", "0X")):
            try:
                return int(val, 16)
            except ValueError:
                pass
        try:
            return int(val)
        except ValueError:
            pass
    if isinstance(val, float):
        try:
            return int(val)
        except:
            pass
    return None