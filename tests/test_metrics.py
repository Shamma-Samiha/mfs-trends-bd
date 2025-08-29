import pandas as pd
from src.metrics import add_growth

def test_growth_shapes():
    df = pd.DataFrame({
        "month": pd.date_range("2023-01-01", periods=3, freq="MS"),
        "category": ["P2P"]*3,
        "amount_bdt": [1,2,3]
    })
    out = add_growth(df.copy())
    assert {"mom","yoy"} <= set(out.columns)