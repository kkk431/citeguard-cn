from citeguard import numeric_check as nc


def test_extract_units():
    q = nc.extract("提升 2.3%，样本 1.2 万篇，耗时 38 秒")
    assert [x.value for x in q] == [2.3, 1.2, 38]
    assert [x.unit for x in q] == ["%", "万", "秒"]


def test_missing_number_flagged():
    r = nc.check("准确率提升 2.3%。", "该方法在三个数据集上表现更稳定。")
    assert r.checked == 1 and r.missing == ["2.3%"] and not r.ok


def test_matched_number_ok():
    r = nc.check("准确率提升 2.3%。", "实验显示准确率提升 2.3%，且稳定。")
    assert r.ok and r.matched == 1


def test_unit_mismatch_flagged():
    r = nc.check("参数量 7B。", "参数量为 7 亿。")
    assert r.missing == ["7"] or r.missing == ["7B"] or r.missing


def test_direction_conflict():
    r = nc.check("错误率下降 12%。", "实验显示错误率提升 12%。")
    assert r.direction_conflicts == ["12%"] and not r.ok


def test_no_numbers():
    r = nc.check("该方法更好。", "证据表明它更稳。")
    assert r.checked == 0 and r.ok and r.notes
