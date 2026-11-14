# 软件物料清单（SBOM）

`docs/sbom.json` 是 CiteGuard-CN 核心运行时的 CycloneDX 1.5 物料清单，由
`scripts/make_sbom.py` 从 `requirements.txt` 与当前安装的 Python 发行版生成。
它只列服务端**核心依赖**，不列开发工具、可选评测依赖或传递依赖的全部 wheel；
完整第三方清单见《开源及第三方资源使用清单》与 `THIRD_PARTY_NOTICES.md`。

## 重新生成

```bash
python scripts/make_sbom.py
python scripts/make_sbom.py --check   # CI 用：缺依赖或版本过期时返回非零
```

`tests/test_sbom.py` 会校验：这是 CycloneDX 1.5 文档、每个核心依赖都有版本和
许可证条目、应用版本与 `web/app.py` 一致。

## 边界

- 许可证字段来自已安装包的元数据或 PyPI classifier；`pypdfium2` 的元数据是
  组合声明，原文保留，不擅自改写成单一 SPDX id。
- SBOM 不包含模型权重、数据集或 Docker 基础镜像；这些分别在
  `docs/model_card_support_lora*.md`、数据集卡与 `docker/` 中说明。
- 不包含运行时生成的 `data/` 私有状态（历史库、题录库、反馈），那些也不进交付包。
