# 匿名与提交终检（自查记录）

比赛要求作品材料匿名（正文、PPT、压缩包内不出现姓名、学校、院系、导师、基金号等可识别信息）。本文件记录 2026-10 的终检结果与可复现的检查方法。

## 1. 已做的处理

| 位置 | 问题 | 处理 |
| --- | --- | --- |
| 提交 zip | `docs/HANDOFF.md` 是内部交接记录（含个人路径、远端主机、测试账号线索） | 打包时排除，不进提交包 |
| 提交 zip | 文档/脚本中的内网主机 `222.20.126.148`、`222.20.96.215` | 打包时统一替换为 `127.0.0.1` |
| 提交 zip | 文档中的本机路径 `D:\ai+ky\citeguard`、`C:\Users\hejiaxuan` | 打包时替换为 `<project>` / `<user>` |
| 评测脚本 | `eval_chartcheck.py`、`eval_figure_prompt.py` 默认端点写死内网 GPU | 默认改为 `http://127.0.0.1:8099/v1`，仍可用 `CITEGUARD_VL_ENDPOINT` 覆盖 |
| 答辩 PPT | 第 8 页原写「远端：222.20.96.215:8000」 | 改为「现场演示：本地模式（离线可用）/ 在线增强」 |
| 技术报告 | 正文无姓名、学校、致谢、基金号 | 保持；只在「开放成果」页保留公开仓库地址 |

## 2. 保留项及理由

- **GitHub 仓库地址 `github.com/kkk431/citeguard-cn`**：比赛要求开放成果可获取，仓库本身是作品的一部分；`kkk431` 是项目账号，不含真实姓名。若赛区要求彻底匿名，可在提交材料里改为「开源仓库（见资源清单附件）」并附二维码/短链，由组织方按需获取。
- **第三方数据集与模型名称**（SciFact、ChartCheck、OpenAlex、Qwen 等）：属于公开成果引用，不是身份信息。
- **示例文献的作者名**（如 BERT/Mamba 论文作者）：公开文献元数据，不是参赛者信息。

## 3. 提交前复跑检查

```powershell
cd D:\ai+ky\citeguard
python scripts/package_deliverable.py --quiet
python - <<'PY'
import re, zipfile
from pathlib import Path
z = sorted(Path("dist").glob("citeguard-cn-*.zip"))[-1]
bad = re.compile(r"222\.20\.|D:\\\\ai\+ky|C:\\\\Users|sk-[a-f0-9]{20}|HANDOFF\.md")
hits = []
with zipfile.ZipFile(z) as f:
    for name in f.namelist():
        if bad.search(name):
            hits.append(name)
        elif name.lower().endswith((".md", ".py", ".html", ".js", ".json", ".txt", ".yml")):
            text = f.read(name).decode("utf-8", "ignore")
            for m in bad.finditer(text):
                hits.append(f"{name}: {m.group(0)}")
print(z.name, "hits:", hits[:10], "count:", len(hits))
PY
```

`count: 0` 才算通过。另人工过一遍：

- [ ] 技术报告 PDF：封面、页眉页脚、致谢、图表来源、附录
- [ ] 答辩 PPT：封面、成员页、截图里的浏览器地址栏/用户名
- [ ] 演示视频：不做（本次不提交）
- [ ] 资源清单附件：文件大小、格式、能否打开
- [ ] 压缩包解压后直接 `pip install -r requirements.txt` 能起服务（离线模式）

## 4. 本次结论（2026-10-27）

- 源码包、报告 PDF、PPT 三份材料均已过一遍上述检查；提交包里不含姓名/学校/内网地址/密钥。
- 报告与 PPT 中的数字与 `data/experiments/*.json` 一致（详见 `docs/ppt_numbers.md` 的「不能这么说」一节）。
- 尚未做：真人用户测试（需要用户自己找 3–5 位同学）；演示视频（按要求不做）。
