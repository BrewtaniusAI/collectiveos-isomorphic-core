# Mining Ops

This directory contains the operational baseline for local-wallet-first crypto mining.

## Objectives
- start mining quickly to a local wallet
- preserve local custody
- avoid exchange dependency in the baseline path
- support weekly offload
- leave room for later AI profit switching and virtual crypto lab simulation

## Recommended baseline
- Coin: Monero (XMR)
- Algorithm: RandomX
- Miner: XMRig
- Wallet: local Monero wallet (GUI or CLI)

## Baseline operating model
1. Create local wallet
2. Configure miner to pay directly to local wallet address
3. Run miner with bounded CPU allocation
4. Track local logs and payouts
5. Offload weekly according to `weekly_offload.md`

## Expansion path
- add profitability monitor
- add AI/rule-based switching
- add virtual crypto lab for simulation and testing
