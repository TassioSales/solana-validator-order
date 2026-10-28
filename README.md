# Solana Validator Transaction Ordering Engine

Empirical measurement framework and analysis suite for transaction ordering across Solana validators.

> **Superteam Ukraine Bounty Submission:** *Inside the Block: How Solana Validators Order Transactions ($2,500 USDC)*  
> **Author:** Tassio Sales  
> **Platform:** Superteam Earn  

---

## Overview

This tool connects to the Solana `mainnet-beta` cluster, identifies active validator nodes spanning multiple software client families (**Agave**, **Jito-Solana**, **Solana Labs**), ingests full block transaction details, and measures the ordering mechanics of transactions within each slot.

It addresses the three core research questions:
1. **By what rule does each chosen validator order transactions in its block?**
2. **How strictly does that rule hold?**
3. **Is there a discernible rule present at all?**

---

## Single-Command Execution (Docker)

To run the complete experiment and generate data with a single command:

```bash
docker compose up --build
```

The experiment will:
1. Connect to Solana mainnet RPC.
2. Discover active validators and partition them across client software families.
3. Download blocks produced by the selected validator nodes.
4. Decode compute unit limits, priority fees, and Jito tip bundle transfers.
5. Save raw JSON data to `data/raw_experiment_data.json`.
6. Compile the final empirical analysis into `REPORT.md`.

---

## Local Python Execution

Alternatively, to run natively:

```bash
pip install -r requirements.txt
python src/main.py
```

---

## Deliverables Included

- `src/solana_rpc.py`: Multi-endpoint RPC client with automatic fallback and rate-limit rotation.
- `src/analyzer.py`: Transaction instruction decoder and statistical ordering analyzer.
- `src/main.py`: Experiment orchestrator and automated report generator.
- `REPORT.md`: Comprehensive technical paper answering the bounty questions.
- `data/raw_experiment_data.json`: Fully preserved raw empirical dataset.
