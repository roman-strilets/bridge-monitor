# Bridge Monitor

A utility to check that all Beam-Ethereum bridge transactions are completed successfully. Supports multiple tokens (BEAM, USDT, USDC, DAI, etc.) and both directions (ETH→Beam and Beam→ETH).

## Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) package manager
- Ethereum RPC endpoint ([Infura](https://infura.io))
- Beam wallet with API enabled

## Installation

**Windows:**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**macOS/Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then install the package:
```bash
cd bridge-monitor
uv pip install -e .
```

## Configuration

**Windows:**
```powershell
copy config.example.json config.json
```

**macOS/Linux:**
```bash
cp config.example.json config.json
```

Edit `config.json`:

```json
{
  "common": {
    "ethereum": {
      "rpc_url": "https://eth-mainnet.g.alchemy.com/v2/YOUR-API-KEY"
    },
    "beam": {
      "wallet_api_url": "http://127.0.0.1:12000/api/wallet"
    }
  },
  "tokens": {
    "BEAM": {
      "name": "Beam Native Token",
      "ethereum": {
        "pipe_contract_address": "0x...",
        "start_block": 0
      },
      "beam": {
        "pipe_contract_id": "your-contract-id",
        "pipe_wasm_path": "pipe_app.wasm"
      }
    },
    "USDT": {
      "name": "Tether USD",
      "ethereum": {
        "pipe_contract_address": "0x...",
        "token_contract_address": "0xdac17f958d2ee523a2206206994597c13d831ec7",
        "start_block": 0
      },
      "beam": {
        "pipe_contract_id": "your-usdt-contract-id",
        "pipe_wasm_path": "pipe_app.wasm"
      }
    }
  }
}
```

**Key parameters:**
- `ethereum.rpc_url` — Ethereum JSON-RPC endpoint
- `beam.wallet_api_url` — Beam wallet API endpoint (must match `--port` used when starting the wallet)
- `pipe_contract_address` — Ethereum Pipe contract address per token
- `token_contract_address` — (Optional) ERC20 token contract address
- `start_block` — Starting Ethereum block to scan from
- `pipe_contract_id` — Beam Pipe contract ID
- `pipe_wasm_path` — Path to `pipe_app.wasm` for this token

## Step 1: Start Beam Wallet API

Before running the monitor, start the Beam wallet API:

**Windows:**
```powershell
wallet-api.exe -n eu-nodes.mainnet.beam.mw:8100 --pass 123 --port 12000 --use_http 1 --enable_assets
```

**macOS/Linux:**
```bash
./wallet-api -n eu-nodes.mainnet.beam.mw:8100 --pass 123 --port 12000 --use_http 1 --enable_assets
```

Make sure `beam.wallet_api_url` in `config.json` points to the correct port (e.g. `http://127.0.0.1:12000/api/wallet`).

## Step 2: Run the Monitor

```bash
# Scan blockchains and update transaction statuses
uv run bridge-monitor check

# Check a specific token only
uv run bridge-monitor check --token BEAM

# Show status report (no scanning)
uv run bridge-monitor report

# List all transactions
uv run bridge-monitor list

# Filter by direction or token
uv run bridge-monitor list --direction eth2beam
uv run bridge-monitor list --token USDT --direction beam2eth

# JSON output for automation/alerting
uv run bridge-monitor check --json

# Verbose logging
uv run bridge-monitor -v check

# Custom config or database
uv run bridge-monitor -c custom-config.json -d custom.db check
```

