import importlib.util
from pathlib import Path


def load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "build_support_matrix.py"
    spec = importlib.util.spec_from_file_location("build_support_matrix", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_macro_f1_and_accuracy():
    mod = load_module()
    gold = ["support", "partial", "contradict", "no_evidence"]
    assert mod.accuracy(gold, gold) == 1.0
    assert round(mod.macro_f1(gold, gold), 4) == 1.0
    pred = ["support", "support", "contradict", "no_evidence"]
    assert 0.0 < mod.macro_f1(gold, pred) < 1.0


def test_bootstrap_is_deterministic_and_brackets_point():
    mod = load_module()
    gold = ["support", "partial", "contradict", "no_evidence", "support", "partial"]
    pred = ["support", "support", "contradict", "no_evidence", "partial", "partial"]
    a = mod.bootstrap(gold, pred, n_boot=200, seed=7)
    b = mod.bootstrap(gold, pred, n_boot=200, seed=7)
    assert a == b
    point = mod.macro_f1(gold, pred)
    lo, hi = a["macro_f1"]
    assert lo <= point <= hi


def test_matrix_markdown_keeps_constructed_boundary():
    mod = load_module()
    matrix = mod.build()
    md = mod.to_markdown(matrix)
    assert "构造标签" in md
    assert "不能这么说" in md
    assert "4B LoRA" in md
