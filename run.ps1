python -m venv .venv
.\venv\Scripts\Activate.ps1
pip install uv
uv pip install numpy pandas matplotlib scikit-learn optuna "psycopg[binary,pool]" python-dotenv

python -m src.dataloader -f 2023-01-01 -t 2024-12-31 -o data/train.csv
python -m src.dataloader -f 2025-01-01 -t 2025-12-31 -o data/test.csv
python -m src.dataloader -f 2023-01-01 -t 2024-12-31 -o data/train_vnindex.csv -vni
python -m src.dataloader -f 2025-01-01 -t 2025-12-31 -o data/test_vnindex.csv -vni

python -m src.backtest -i config/insample.yaml
python -m src.backtest -i config/outsample.yaml
