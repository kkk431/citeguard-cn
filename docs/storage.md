# 存储：JSON 与 SQLite 的分工

CiteGuard 把**报告**和**任务记录**分开存：

| 数据 | 位置 | 格式 | 是否可删 |
|---|---|---|---|
| 报告正文 / 报告页 | `data/jobs/<id>/report.*` | JSON/HTML/MD/RIS… | 可，历史页会显示“报告已清理” |
| 任务记录 | `data/jobs/<id>.json` | JSON | 可删，SQLite 索引会随之收缩 |
| 任务索引 | `data/history.db` | SQLite | 可删，下次启动自动重建 |
| 本地题录库 | `data/library/library.json` | JSON（权威） | 不可删（用户资产） |
| 题录库索引 | `data/library/library.json.sqlite3` | SQLite sidecar | 可删，下次保存自动重建 |

## 为什么加 SQLite

历史页原来每次加载都 glob `data/jobs/*.json` 再逐个 parse；任务上千后这是 O(n) 次磁盘读。0.9.96 起：

- 任务 JSON **仍写入**（保持可读、可备份、可手工修）；
- 同时写 `data/history.db` 的 `jobs` 表；
- `JobManager.recent()` 先查索引，索引落后于 JSON mtime 时自动增量同步；
- 索引文件丢失/损坏时自动回退到 JSON glob，不影响主流程。

## 导出与迁移

```bash
# 从 SQLite 导出回 JSON（每个任务一个文件）
python - <<'PY'
from citeguard.history_db import HistoryDB
print(HistoryDB().export_json("backup/jobs"))
PY
```

- 换目录测试/多实例：设置 `CITEGUARD_HISTORY_DB=/path/to/history.db`；
- 索引指向不同 jobs 目录时会自动清空重建，避免两份历史混在一起；
- 题录库仍是 JSON 权威：用户可直接看、改、备份；保存时同步写 `library.json.sqlite3` 索引（1.3.2）。
- JSON 丢失/损坏时，`Library.load` 会回退到 sidecar；两边不一致时 JSON 优先，下次保存刷新索引。
- 回滚是显式的，且拒绝用空索引覆盖 JSON：

```bash
PYTHONPATH=src python scripts/migrate_library_sqlite.py --check
PYTHONPATH=src python scripts/migrate_library_sqlite.py --rollback
```


## 已验证

- `tests/test_history_db.py`：同步、按更新时间排序、`has_report` 标记、导出、删除、目录切换重建；
- `tests/test_jobs.py`：`recent()` 返回字段与 JSON 版本一致（含 `filename`）；
- 全套 658 passed。
