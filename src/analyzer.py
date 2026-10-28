import os
import sys
import json
from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd

from solana_rpc import SolanaRpcClient

# Pure Python Base58 Alphabet & Decoder
B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
B58_MAP = {c: i for i, c in enumerate(B58_ALPHABET)}

def b58decode(s: str) -> bytes:
    """Decodificador Base58 puro em Python sem dependências externas."""
    num = 0
    for char in s:
        if char not in B58_MAP:
            return b""
        num = num * 58 + B58_MAP[char]
    
    # Convert integer to bytes
    res = []
    while num > 0:
        res.append(num & 0xFF)
        num >>= 8
    res = bytes(reversed(res))
    
    # Count leading 1s
    pad = 0
    for char in s:
        if char == '1':
            pad += 1
        else:
            break
    return (b'\x00' * pad) + res

# Canonical Jito Tip Payment Accounts on Solana Mainnet
JITO_TIP_ACCOUNTS = {
    "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5",
    "HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe",
    "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY",
    "ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49",
    "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh",
    "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
    "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL",
    "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT"
}

COMPUTE_BUDGET_PROGRAM_ID = "ComputeBudget111111111111111111111111111111"

def parse_compute_budget(instructions: List[Dict[str, Any]], account_keys: List[str]) -> Dict[str, Any]:
    """Extrai compute unit limit e compute unit price (prioritization fee) da transacao."""
    cu_limit = 200_000 # default
    cu_price = 0       # default (micro-lamports / CU)
    has_jito_tip = False
    tip_amount_lamports = 0

    for ix in instructions:
        # Check program ID
        prog_id = ix.get("programId")
        if not prog_id and "programIdIndex" in ix and ix["programIdIndex"] < len(account_keys):
            prog_id = account_keys[ix["programIdIndex"]]

        if prog_id == COMPUTE_BUDGET_PROGRAM_ID:
            data = ix.get("data")
            if data:
                try:
                    raw_bytes = b58decode(data)
                    if len(raw_bytes) >= 1:
                        discriminator = raw_bytes[0]
                        # 0x02 = SetComputeUnitLimit (u32 little endian)
                        if discriminator == 2 and len(raw_bytes) >= 5:
                            cu_limit = int.from_bytes(raw_bytes[1:5], "little")
                        # 0x03 = SetComputeUnitPrice (u64 little endian, micro-lamports per CU)
                        elif discriminator == 3 and len(raw_bytes) >= 9:
                            cu_price = int.from_bytes(raw_bytes[1:9], "little")
                except Exception:
                    pass

    # Detect Jito tip transfers
    for key in account_keys:
        if key in JITO_TIP_ACCOUNTS:
            has_jito_tip = True
            break

    return {
        "cu_limit": cu_limit,
        "cu_price": cu_price,
        "has_jito_tip": has_jito_tip
    }

def analyze_block(block_data: Dict[str, Any], slot: int, leader_pubkey: str, client_version: str) -> Dict[str, Any]:
    """Analisa as transacoes dentro do bloco e determina as regras de ordenacao aplicadas."""
    transactions = block_data.get("transactions", [])
    blockhash = block_data.get("blockhash", "")
    parent_slot = block_data.get("parentSlot", 0)
    block_time = block_data.get("blockTime")

    tx_records = []
    for idx, tx in enumerate(transactions):
        tx_obj = tx.get("transaction", {})
        meta = tx.get("meta", {})
        
        # Signatures
        sig = "unknown"
        sigs = tx_obj.get("signatures", [])
        if sigs:
            sig = sigs[0]

        message = tx_obj.get("message", {})
        account_keys = message.get("accountKeys", [])
        # If accountKeys are objects or strings
        keys_list = [k if isinstance(k, str) else k.get("pubkey", "") for k in account_keys]

        instructions = message.get("instructions", [])
        budget = parse_compute_budget(instructions, keys_list)

        fee = meta.get("fee", 5000)
        err = meta.get("err")
        compute_units_consumed = meta.get("computeUnitsConsumed", 0)

        tx_records.append({
            "index": idx,
            "signature": sig,
            "cu_price": budget["cu_price"],
            "cu_limit": budget["cu_limit"],
            "fee": fee,
            "has_jito_tip": budget["has_jito_tip"],
            "compute_consumed": compute_units_consumed,
            "success": err is None
        })

    df = pd.DataFrame(tx_records)
    if df.empty:
        return {
            "slot": slot,
            "leader": leader_pubkey,
            "client_version": client_version,
            "tx_count": 0,
            "analysis": "Empty block"
        }

    # Ordering Analysis
    # 1. Jito bundle position: are Jito tips concentrated at the top (lowest indices)?
    jito_txs = df[df["has_jito_tip"]]
    avg_jito_index = float(jito_txs["index"].mean()) if not jito_txs.empty else None
    pct_jito_in_top_10pct = None
    if not jito_txs.empty:
        top_10pct_cutoff = max(1, len(df) * 0.1)
        pct_jito_in_top_10pct = float((jito_txs["index"] <= top_10pct_cutoff).mean())

    # 2. Priority Fee Correlation with Index
    # A negative correlation means higher priority fees appear earlier (smaller index).
    corr = None
    if len(df) > 5 and df["cu_price"].nunique() > 1:
        corr = float(df["cu_price"].corr(df["index"], method="spearman"))

    # 3. Strictness check: among non-zero priority fee transactions, what % respects monotonic order?
    nz_priority = df[df["cu_price"] > 0]
    inversions = 0
    total_pairs = 0
    if len(nz_priority) > 1:
        prices = nz_priority["cu_price"].values
        # Sample pairs to measure inversion rate
        sample_size = min(len(prices), 200)
        sub_sample = prices[:sample_size]
        for i in range(len(sub_sample)):
            for j in range(i + 1, len(sub_sample)):
                total_pairs += 1
                if sub_sample[i] < sub_sample[j]: # lower fee placed before higher fee is an inversion
                    inversions += 1

    inversion_rate = (inversions / total_pairs) if total_pairs > 0 else 0.0
    monotonic_adherence = 1.0 - inversion_rate

    return {
        "slot": slot,
        "leader": leader_pubkey,
        "client_version": client_version,
        "block_time": block_time,
        "tx_count": len(df),
        "jito_bundle_count": len(jito_txs),
        "avg_jito_index": avg_jito_index,
        "pct_jito_in_top_10pct": pct_jito_in_top_10pct,
        "spearman_corr_price_index": corr,
        "monotonic_priority_adherence": monotonic_adherence,
        "transactions_sample": tx_records[:20]
    }
