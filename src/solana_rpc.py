import os
import time
import requests
import json
from typing import Dict, Any, List, Optional

DEFAULT_RPCS = [
    os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"),
    "https://solana-rpc.publicnode.com",
    "https://rpc.ankr.com/solana"
]

class SolanaRpcClient:
    def __init__(self, rpc_urls: Optional[List[str]] = None):
        self.rpc_urls = rpc_urls or DEFAULT_RPCS
        self.current_idx = 0
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def get_url(self) -> str:
        return self.rpc_urls[self.current_idx % len(self.rpc_urls)]

    def rotate_rpc(self):
        self.current_idx = (self.current_idx + 1) % len(self.rpc_urls)
        print(f"[RPC] Rotating to fallback RPC: {self.get_url()}")

    def call(self, method: str, params: Optional[List[Any]] = None, retries: int = 4) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or []
        }
        for attempt in range(retries):
            url = self.get_url()
            try:
                resp = self.session.post(url, json=payload, timeout=25)
                if resp.status_code == 429:
                    time.sleep(1.5 * (attempt + 1))
                    self.rotate_rpc()
                    continue
                data = resp.json()
                if "error" in data:
                    err = data["error"]
                    # If block cleaned or slot skipped
                    if "Slot was skipped" in str(err) or "not available" in str(err):
                        return None
                    time.sleep(1)
                    continue
                return data.get("result")
            except Exception as e:
                time.sleep(1 * (attempt + 1))
                self.rotate_rpc()
        return None

    def get_version(self) -> Optional[Dict[str, Any]]:
        return self.call("getVersion")

    def get_slot(self) -> Optional[int]:
        return self.call("getSlot", [{"commitment": "confirmed"}])

    def get_cluster_nodes(self) -> List[Dict[str, Any]]:
        nodes = self.call("getClusterNodes")
        return nodes or []

    def get_blocks(self, start_slot: int, end_slot: int) -> List[int]:
        res = self.call("getBlocks", [start_slot, end_slot])
        return res or []

    def get_block(self, slot: int, detail: str = "full") -> Optional[Dict[str, Any]]:
        return self.call("getBlock", [
            slot,
            {
                "encoding": "json",
                "transactionDetails": detail,
                "rewards": True,
                "maxSupportedTransactionVersion": 1
            }
        ])

    def get_leader_schedule(self, slot: Optional[int] = None) -> Optional[Dict[str, List[int]]]:
        params = [slot] if slot else []
        return self.call("getLeaderSchedule", params)
