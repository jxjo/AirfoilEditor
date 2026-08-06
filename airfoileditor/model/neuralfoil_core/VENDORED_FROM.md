# Vendored Source

This directory contains a vendored snapshot of NeuralFoil-Core runtime code.

- Source repository: https://github.com/jxjo/NeuralFoil-Core.git
- Source commit: a9d34bcb53a57927af6cdf3fe501765ad90f5283
- Vendored into AirfoilEditor: 2026-08-06

## Scope

Only runtime files under `neuralfoil/` are vendored here.

## Sync Procedure

1. Update `NeuralFoil-Core` to the desired commit.
2. Copy `neuralfoil/` into `airfoileditor/model/neuralfoil_core/`.
3. Copy upstream `LICENSE.txt` to `LICENSE-NEURALFOIL.txt`.
4. Update this file's source commit and date.
5. Run AirfoilEditor tests that cover neuralfoil integration.
