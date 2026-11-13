# 题录库：标签与重复合并

本文约定 C2 的数据层和 HTTP/UI 契约。范围仅限**本地题录库**：不做跨语言模糊匹配、不自动合并、不凭空补元数据。路由和页面由队长按本文实现；数据层在 `src/citeguard/local_library.py`，sidecar 在 `src/citeguard/library_db.py`。

## 1. 数据模型

`LibraryEntry` 新增字段（位于字段列表末尾，旧 JSON 反序列化自动取默认值）：

```python
tags: list[str] = field(default_factory=list)
```

约束：

| 规则 | 取值 |
|---|---|
| 每条最多标签数 | 8（`MAX_TAGS`） |
| 单个标签最大长度 | 24 个字符（`MAX_TAG_LENGTH`） |
| 空标签 | 丢弃（不报错） |
| 首尾/内部连续空白 | 折叠为单个空格 |
| 重复标签 | 按 `casefold()` 去重，保留第一次出现的写法 |
| 类型 | 只能是字符串列表；字符串标量会被拒绝 |

标签是题录的**本地整理信息**，不参与核验结论，也不会被导出到 BibTeX/RIS 之外的元数据里。

JSON 文件版本从 1 升到 2：

```json
{
  "version": 2,
  "count": 1,
  "entries": [
    {
      "title": "累积生态风险与青少年的学业和社交能力",
      "authors": ["鲍振宙", "李董平"],
      "year": 2014,
      "doi": "",
      "tags": ["方法", "综述"]
    }
  ]
}
```

**旧数据兼容**：`version: 1` 或没有 `tags` 字段的条目一律按 `tags: []` 读取；旧数据里类型错误/超限的标签不会让加载失败（非法值丢弃，超过 8 个截断）。写回后文件变为 version 2。

## 2. Python API

所有方法都是**内存操作**，不写磁盘、不联网。`Library` 的 id 为 `entries` 列表的 **0 基下标**，与现有 `/api/library/{index}` 一致；它只在本次列表快照内稳定，下一次增删/合并后会变化。

```python
from citeguard.local_library import Library, LibraryError, LibraryEntry

lib = Library([LibraryEntry(title="A study", year=2020)])
lib.set_tags(0, ["方法", "方法", "综述"])   # -> ["方法", "综述"]
lib.add_tags("A study", ["REVIEW"])         # -> ["方法", "综述", "REVIEW"]
lib.remove_tags("10.1000/abc", ["review"])  # 大小写不敏感，未命中静默忽略
```

| API | 返回 | 说明 |
|---|---|---|
| `set_tags(key_or_doi_or_id, tags)` | `LibraryEntry` | 整体替换；`tags=None` 等价于清空 |
| `add_tags(key_or_doi_or_id, tags)` | `LibraryEntry` | 并集；超限/超长抛 `LibraryError` |
| `remove_tags(key_or_doi_or_id, tags)` | `LibraryEntry` | 按 `casefold()` 删除；未知标签忽略 |
| `find_duplicates()` | `list[dict]` | 只分组，**不删除、不写盘** |
| `merge_duplicates(keep_id, drop_ids)` | `int` | 合并并删除 drop，返回删除条数 |

`key_or_doi_or_id` 支持：

1. `int`：0 基下标（`bool` 被拒绝）；
2. DOI 字符串：忽略 `https://doi.org/`、`doi:` 前缀和大小写；
3. 题名：`norm_title` 归一化后精确匹配（忽略大小写、空格、标点）；
4. 数字字符串按 id 处理。

找不到、重名/同 DOI 多解、越界、类型错误统一抛 `LibraryError`（继承 `ValueError`）。典型消息：

- `条目 id 必须是非负整数`
- `条目 id 越界：9（共 2 条）`
- `找不到题录：…`
- `题名「…」对应 2 条记录，请改用 id`
- `标签最多 8 个，当前 9 个`
- `标签「…」超过 24 个字符`
- `tags 必须是字符串列表`

### 2.1 标签接口要求

`set_tags`/`add_tags`/`remove_tags` **不会自动保存**；HTTP 路由在成功修改后必须调用 `library.save(config.LIBRARY_FILE)`，否则只改了请求内的临时对象。

### 2.2 重复分组

```python
groups = lib.find_duplicates()
# [
#   {
#     "ids": [3, 7],
#     "reason": "doi",              # doi | title_year | doi+title_year
#     "entries": [{...}, {...}],    # 每条为 LibraryEntry.to_dict()
#   }
# ]
```

- DOI 分组键：非空 DOI，经 `_doi_key` 去前缀/小写；
- 题名分组键：`norm_title(title)` + 相同 `year`（两者都必须存在）；
- 关系可传递（A 与 B 同 DOI、B 与 C 同题名年份 → 同一组）；
- `ids` 升序，组按第一个 id 排序；
- `reason` 只有 `doi`、`title_year`、`doi+title_year` 三种；组内没有共享键的组合不会出现。

### 2.3 合并语义

```python
merged = lib.merge_duplicates(keep_id=3, drop_ids=[7, 9])
```

- `keep` 的非空字段优先；空字段按 `drop_ids` 顺序从被删条目补齐（venue/volume/issue/pages/doi/url/abstract/doc_type/source/raw/authors/year/title）；
- 标签取并集（`casefold` 去重），合并后超过 8 个直接拒绝，**不做静默截断**；
- `keep` 出现在 `drop_ids`、drop 为空、id 不存在、drop 重复时去重后处理；
- 所有校验在修改前完成，失败不会留下半合并状态；
- 删除 `drop_ids` 后，若 `Library` 由 `load`/`save` 得到过路径（`_path` 已知），自动 `save` 一次；否则由调用方保存；
- 返回实际删除条数。

## 3. 持久化：JSON 为主，sidecar 为回退

| 数据 | 位置 | 版本 | 角色 |
|---|---|---|---|
| 题录库 JSON | `data/library/library.json` | `LIBRARY_VERSION=2` | 权威、可读、可手工改 |
| SQLite sidecar | 同路径 + `.sqlite3` | `SCHEMA_VERSION=2` | 查询索引/灾难回退 |

- `Library.save(path)` 先写 JSON，再尽力写 sidecar；sidecar 写失败不影响 JSON（与旧行为一致）。
- `Library.load(path)` 优先 JSON；JSON 缺失/损坏时回退 sidecar，此时 **tags 也会从 sidecar 恢复**。
- sidecar 打开时自动迁移：version 1 数据库执行

  ```sql
  ALTER TABLE entries ADD COLUMN tags TEXT NOT NULL DEFAULT '[]';
  ```

  旧行的 tags 变为 `[]`，之后 `write_library` 写入的 tags 保留；`meta.schema` 更新为 `2`。
- sidecar 是索引不是第二真相：两边不一致时 JSON 优先，下次保存刷新索引。

## 4. HTTP 契约（建议实现）

统一约定：

- 路径参数 `index` 为 0 基下标，含义同 `GET /api/library` 返回的 `entries[].index`；
- 错误响应沿用 FastAPI 形状 `{"detail": "人类可读中文"}`；
- 每次请求重新 `Library.load`，修改后 `library.save`（合并方法在 `_path` 已知时会自动保存，路由再保存一次无害）；
- id 来自上一次列表/重复分组的快照，库一变就可能失效，前端应刷新后重试。

### 4.1 `GET /api/library`（扩展，无需新路由）

现有响应天然带 `tags`（`entry.to_dict()`）；前端表格新增“标签”列即可。

### 4.2 `GET /api/library/duplicates`

```json
{
  "count": 1,
  "groups": [
    {
      "ids": [3, 7],
      "reason": "doi",
      "entries": [
        {"index": 3, "title": "…", "tags": ["方法"], "doi": "10.1/abc"},
        {"index": 7, "title": "…", "tags": [], "doi": "10.1/abc"}
      ]
    }
  ]
}
```

- `entries` 在 `to_dict()` 基础上补 `index`，方便前端直接展示/选择；
- `reason` 原样返回；前端映射 `doi`→“DOI 相同”、`title_year`→“题名与年份相同”、`doi+title_year`→“DOI 与题名年份都相同”；
- 无重复时 `{"count": 0, "groups": []}`，HTTP 200。

### 4.3 `POST /api/library/duplicates/merge`

请求：

```json
{"keep_id": 3, "drop_ids": [7, 9]}
```

响应 200：

```json
{
  "merged": 2,
  "count": 18,
  "kept": {"index": 3, "title": "…", "tags": ["方法", "综述"], "...": "…"}
}
```

- `kept.index` 为合并后的新下标；
- `count` 为合并后总条数。

状态码：

| 码 | 场景 | detail 来源/示例 |
|---|---|---|
| 400 | 标签合并后超限、drop 为空、keep 在 drop 中、payload 结构错误 | `LibraryError` 消息，如 `标签最多 8 个，当前 9 个` |
| 404 | keep/drop id 越界 | `条目 id 越界：9（共 2 条）` |
| 409 | 重新计算重复分组后，keep 与任一 drop 不在同一组 | `重复条目已变化，请刷新后重试` |

409 的实现建议：加载库后先 `find_duplicates()`，要求 `{keep_id, *drop_ids}` 的每个 id 都出现在**同一个**当前分组里；不满足就拒绝，避免前端拿旧下标误删正常条目。

### 4.4 `POST /api/library/{index}/tags`

请求：

```json
{"mode": "replace", "tags": ["方法", "综述"]}
```

`mode` 取值：

- `replace` → `set_tags`；
- `add` → `add_tags`；
- `remove` → `remove_tags`。

响应 200：

```json
{"index": 0, "tags": ["方法", "综述"], "count": 42}
```

状态码：

| 码 | 场景 | detail 示例 |
|---|---|---|
| 400 | tags 非列表/含非字符串/超长/超 8 个，或 `mode` 非法 | `标签最多 8 个，当前 9 个` |
| 404 | 下标越界 | `条目 id 越界：9（共 2 条）` |

路由伪代码：

```python
@app.post("/api/library/{index}/tags")
def library_tags(index: int, body: dict = Body(...)):
    library = Library.load(config.LIBRARY_FILE)
    if index < 0 or index >= len(library):
        raise HTTPException(status_code=404, detail=f"条目 id 越界：{index}（共 {len(library)} 条）")
    mode = str(body.get("mode") or "replace")
    tags = body.get("tags")
    try:
        if mode == "add":
            entry = library.add_tags(index, tags)
        elif mode == "remove":
            entry = library.remove_tags(index, tags)
        elif mode == "replace":
            entry = library.set_tags(index, tags)
        else:
            raise HTTPException(status_code=400, detail="mode 必须是 replace/add/remove")
    except LibraryError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    library.save(config.LIBRARY_FILE)
    return {"index": index, "tags": entry.tags, "count": len(library)}
```

> 实现注意：`_resolve_entry` 的越界消息不是机器码；路由若想区分 404/400，可先检查 `index < 0 or index >= len(library)` 再调用，或按 `LibraryError` 文案判断。推荐前者。

## 5. UI 交互

页面：`/library`（`web/templates/library.html` + `web/static/js/library.js`）。

### 5.1 标签

- 表格在 DOI/摘要之间新增“标签”列，展示前 2–3 个 chip（`.tag`），其余显示 `+N`；无标签显示 `—`。
- 行操作区“删除”旁加“编辑标签”；点击后行内展开输入框（或小 popover），逗号/回车确认，Esc 取消。
- 输入框提示：`最多 8 个，每个 ≤24 字`；前端也可先做同样校验，但**以服务端 400 为准**并展示 `detail`。
- 保存走 `POST /api/library/{index}/tags` `mode=replace`；成功后只更新该行 DOM，不整页刷新。
- 标签编辑不应触发重复检测/合并；刷新页面后标签仍在（已写入 JSON/sidecar）。

### 5.2 重复检测与合并

- 入口：`库内题录` 工具栏（搜索框右侧）新增按钮 `查找重复`，带计数徽标；空库隐藏。
- 点击调用 `GET /api/library/duplicates`，按钮 loading；结果为 0 时 toast“没有发现重复题录”。
- 有结果时打开 modal（复用现有 `.modal` 样式）：
  - 每组一行/一卡：左侧 radio 选“保留”，其余条目显示为“将合并删除”；
  - 展示 `reason` 中文标签、题名/年份/DOI/标签，帮助人工判断；
  - 默认选中第一条（或字段最全的一条——建议按摘要/DOI/标签数量排序后默认第一条，但**不自动提交**）；
  - 底部主按钮 `合并所选`，危险色；点击前二次确认“将删除 N 条，且不可撤销”；
  - 一次只处理一组，或允许逐组确认后批量提交；MVP 建议一次一组，降低误删风险。
- 合并不允许“全自动”：没有用户点确认绝不调用 merge。
- 合并成功：关闭 modal、toast `已合并 N 条`，重新拉取 `/api/library?limit=2000` 和重复列表（下标会变，不能复用旧快照）。
- 失败：400 展示 `detail`（如标签超限，提示先精简标签）；404/409 提示“题录已变化，正在刷新”，自动重新拉取列表。
- 标签超限时不要静默丢标签；提示用户先删标签再合并。

### 5.3 可访问性/细节

- 按钮有 `aria-label`；modal 打开后焦点进入，Esc 关闭；合并结果用 `aria-live="polite"` 播报。
- 移动端表格横向滚动，标签 chip 不换行溢出。
- 不新增全局快捷键，避免与现有搜索冲突。

## 6. 验证

```bash
python -m pytest tests/test_local_library.py tests/test_library_db.py -q
# 49 passed
```

覆盖：

- 标签写入/读取/去重/大小写与空白归一化；
- 超长、超 8 个、非字符串、非列表拒绝；
- 未知条目/越界/非法类型抛 `LibraryError`；
- 通过 id、DOI（含 `https://doi.org/` 前缀）、题名寻址；
- JSON 与 sidecar 均保留标签，JSON 删除后 sidecar 回退仍保留；
- 旧 JSON（version 1、无 tags、tags 类型错误）可加载；
- DOI 重复、题名+年份重复（大小写/空格差异）分组且不自动删除；
- 合并保留非空字段/标签并删除 drop、拒绝非法合并、合并后自动保存；
- sidecar v1 无 tags 列可读、自动迁移后标签保留、`meta.schema == 2`。

## 7. 非目标

- 不做跨语言/翻译题名匹配，不做标题相似度阈值分组（避免误合并）；
- 不自动合并、不自动删除；
- 不从网络补写标签或元数据；
- 不改报告核验结论、不改 `web/app.py`（由队长接路由）。
