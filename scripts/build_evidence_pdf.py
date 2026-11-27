# -*- coding: utf-8 -*-
"""Build the optional evidence PDF for CiteGuard-CN (v1.7.36, 2026-11-19).

The document is generated from real repository files and real run records.
It deliberately does NOT call internal annotations "external user feedback".
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Iterable, Sequence

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
IMG = ROOT / "out" / "evidence_pdf" / "img"
OUT = ROOT / "dist"
OUT.mkdir(exist_ok=True)

NAVY = RGBColor(0x0A, 0x2E, 0x52)
BLUE = RGBColor(0x0E, 0x5C, 0x8C)
CYAN = RGBColor(0x1D, 0x7F, 0x9A)
RED = RGBColor(0xB4, 0x24, 0x2A)
GRAY = RGBColor(0x5F, 0x6B, 0x73)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
LIGHT = "EAF2F8"
DARK = "0A2E52"

TITLE = "引证卫士 CiteGuard-CN"
TEAM = "大肥鱼的忠实信徒们"
TEAM_ID = "AIC-2026-67377639"
VERSION = "v1.7.51"
DATE = "2026-11-27"
REPO = "https://github.com/kkk431/citeguard-cn"
RELEASE = "https://github.com/kkk431/citeguard-cn/releases/tag/v1.7.51"
HF_DATASET = "https://huggingface.co/datasets/dfdafs/claimsupport-cn-300"
HF_17B = "https://huggingface.co/dfdafs/citeguard-support-lora-qwen3-1.7b"
HF_4B = "https://huggingface.co/dfdafs/citeguard-support-lora-qwen3-4b"


def _set_font(run, size=None, bold=None, color=None, east="Microsoft YaHei"):
    run.font.name = "Microsoft YaHei"
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if color is not None:
        run.font.color.rgb = color
    rpr = run._element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.append(fonts)
    fonts.set(qn("w:eastAsia"), east)


def _shade(cell, fill: str):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def _cell_text(cell, text: str, size=8.5, bold=False, color=NAVY, align=WD_ALIGN_PARAGRAPH.LEFT):
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = align
    r = p.add_run(str(text))
    _set_font(r, size, bold, color)


def _table(headers: Sequence[str], rows: Iterable[Sequence[str]], widths: Sequence[float] | None = None):
    rows = list(rows)
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    hdr = table.rows[0].cells
    for i, h in enumerate(headers):
        _cell_text(hdr[i], h, 8.5, True, WHITE, WD_ALIGN_PARAGRAPH.CENTER)
        _shade(hdr[i], DARK)
        if widths:
            hdr[i].width = Cm(widths[i])
    for ridx, row in enumerate(rows):
        cells = table.add_row().cells
        for i, val in enumerate(row):
            _cell_text(cells[i], val, 8.2, False, RGBColor(0x22, 0x2A, 0x30))
            if widths:
                cells[i].width = Cm(widths[i])
        if ridx % 2 == 1:
            for c in cells:
                _shade(c, "F4F8FB")
    doc.add_paragraph()
    return table


def _p(text="", size=9.5, bold=False, color=RGBColor(0x22, 0x2A, 0x30), align=WD_ALIGN_PARAGRAPH.LEFT, space_after=4):
    p = doc.add_paragraph()
    p.alignment = align
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = 1.22
    r = p.add_run(text)
    _set_font(r, size, bold, color)
    return p


def _bullet(text: str, size=9.5):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.line_spacing = 1.18
    r = p.add_run(text)
    _set_font(r, size)
    return p


def _h1(num: str, text: str):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(4)
    r = p.add_run(f"{num}  " if num else "")
    _set_font(r, 16, True, RED)
    r2 = p.add_run(text)
    _set_font(r2, 16, True, NAVY)
    pPr = p._p.get_or_add_pPr()
    pbdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "10")
    bottom.set(qn("w:space"), "3")
    bottom.set(qn("w:color"), "0E5C8C")
    pbdr.append(bottom)
    pPr.append(pbdr)


def _h2(text: str):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(7)
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run(text)
    _set_font(r, 11.5, True, BLUE)


def _pic(name: str, width_cm: float, caption: str):
    path = IMG / f"{name}.jpg"
    if not path.exists():
        _p(f"[missing image: {name}]", 8, color=RED)
        return
    with Image.open(path) as im:
        w, h = im.size
    height_cm = width_cm * h / w
    max_h = 17.0
    if height_cm > max_h:
        width_cm = max_h * w / h
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(2)
    p.add_run().add_picture(str(path), width=Cm(width_cm))
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.space_after = Pt(5)
    r = cap.add_run(caption)
    _set_font(r, 7.8, False, GRAY)


def _kv(rows: Sequence[Sequence[str]], widths=(4.5, 12.5)):
    _table(["项目", "内容"], rows, widths)


def _footer(section):
    p = section.footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(f"引证卫士 CiteGuard-CN · 佐证材料 · {VERSION} · {TEAM_ID}   |   第 ")
    _set_font(r, 7.5, False, GRAY)
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "PAGE")
    run = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = "1"
    run.append(t)
    fld.append(run)
    p._p.append(fld)
    r2 = p.add_run(" 页")
    _set_font(r2, 7.5, False, GRAY)


def _git_log(n=10):
    try:
        out = subprocess.check_output(
            ["git", "log", f"-{n}", "--pretty=%h|%s|%ad", "--date=short"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
        )
        return [line.split("|", 2) for line in out.splitlines() if line.strip()]
    except Exception:
        return []


doc = Document()
section = doc.sections[0]
section.page_height = Cm(29.7)
section.page_width = Cm(21.0)
section.top_margin = Cm(1.55)
section.bottom_margin = Cm(1.55)
section.left_margin = Cm(1.7)
section.right_margin = Cm(1.7)
_footer(section)

style = doc.styles["Normal"]
style.font.name = "Microsoft YaHei"
style.font.size = Pt(10)
style.element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")

# ---------------- cover ----------------
band = doc.add_table(rows=1, cols=1)
band.alignment = WD_TABLE_ALIGNMENT.CENTER
band.autofit = False
cell = band.rows[0].cells[0]
cell.width = Cm(17.6)
_shade(cell, DARK)
cell.text = ""
p = cell.paragraphs[0]
p.alignment = WD_ALIGN_PARAGRAPH.LEFT
p.paragraph_format.space_before = Pt(28)
r = p.add_run("引证卫士 CiteGuard-CN")
_set_font(r, 30, True, WHITE)
p2 = cell.add_paragraph()
p2.paragraph_format.space_after = Pt(26)
r2 = p2.add_run("佐证材料（可选）· 当前全项目证据")
_set_font(r2, 17, False, RGBColor(0xBF, 0xE8, 0xF5))

_p("让每一条引用，都经得起追问。", 20, True, NAVY, WD_ALIGN_PARAGRAPH.CENTER, 8)
_p("中文引文核验工作台 · 从存在、支持到格式与证据", 11, False, GRAY, WD_ALIGN_PARAGRAPH.CENTER, 18)

_kv([
    ["团队名称", TEAM],
    ["团队编号", TEAM_ID],
    ["作品名称", "引证卫士：中文引文核验工作台"],
    ["参赛方向", "开源赋能的 AI 应用创新"],
    ["材料版本", f"{VERSION}（2026-11-19）"],
    ["代码仓库", REPO],
    ["发布版本", RELEASE],
    ["材料性质", "可选佐证材料；不替代技术报告、演示视频和答辩 PPT"],
], (4.2, 13.0))

_p("真实性声明", 10.5, True, RED)
_p(
    "本材料只收录当前项目真实运行、真实文件与真实仓库记录能够支撑的事实。"
    "人工核对为三位匿名标注者独立完成，不冒充外部用户反馈；未开展外部真人用户测试，"
    "不使用虚构客户评价；未提供专利、软件著作权或企业合作证明，不影响作品参赛与基础评分。"
    "所有对外引用数字均给出样本量、来源文件和边界。",
    8.6,
    False,
    RGBColor(0x33, 0x3D, 0x45),
)
_p("材料生成日期：2026-11-19  ·  代码版本：v1.7.36  ·  测试：1055 passed", 8.4, False, GRAY)
doc.add_page_break()

# ---------------- 0 ----------------
_h1("0", "材料总览与证据边界")
_p(
    "这份材料回答四件事：代码是否真的开放、系统是否真的能跑、效果是否有真实记录、"
    "开源与合规边界是否说清楚。每一节都给出可核对的仓库/文件/URL。",
    9.4,
)
_bullet("代码与模型：GitHub 仓库 + Apache-2.0 + v1.7.36 Release；Hugging Face 数据集与两个 LoRA adapter。")
_bullet("可运行：本机 1055 项测试、137 项产物自检、14 项端到端冒烟、58 项页面审计；Docker 1.7.36 健康检查通过。")
_bullet("真实记录：20 篇真实论文 409 条引用、200 次字段篡改、100 条三人盲标、CiteMap 105 格三人核对。")
_bullet("边界：构造集不是人审；人工核对不是外部用户；Live/Map 是小样本能力，不承诺通用准确率。")

_h2("0.1 证据索引")
_table(
    ["编号", "证据类别", "材料位置"],
    [
        ["E1", "代码发布与版本", "GitHub Release v1.7.36；commit 64bca7b；Apache-2.0"],
        ["E2", "测试与可运行", "pytest 1055；verify_artifacts 137/137；e2e 14/14；Docker health"],
        ["E3", "人工核对", "human_audit_100.json；citemap_audit_105/agreement.json"],
        ["E4", "真实语料效果", "verify_real.json；library_real.json；real_mutation_eval.json"],
        ["E5", "外部对照与负结果", "SciFact / ChartCheck / LongCite / AlignScore"],
        ["E6", "产品截图", "报告页、引用链、Live、CiteMap、证据抽屉"],
        ["E7", "开放成果", "HF 数据集 300；HF 1.7B/4B adapter；资源清单 PDF"],
        ["E8", "许可与合规", "THIRD_PARTY_NOTICES.md；开源及第三方资源清单"],
        ["E9", "提交与维护记录", "release/tag、提交历史、复现命令、维护计划"],
    ],
    (1.3, 4.2, 12.1),
)

_h2("0.2 已完成的里程碑（不遗漏历史成果）")
_table(
    ["版本", "关键能力", "当前是否仍可用"],
    [
        ["v0.9.75", "首次完整提交版：解析/核验/格式/报告/题录库/图表/对比/发现", "能力保留，界面已升级"],
        ["v1.0.0", "v1.0 发布；文档站、Docker、数据集与 adapter 打包", "保留"],
        ["v1.4.0", "信息架构与报告页重构；统一分页/检查抽屉", "保留"],
        ["v1.7.5", "CiteMap、修复闭环、题录库标签/去重", "保留"],
        ["v1.7.18", "Live 页面预检、扩展、中文翻译与 arXiv 回填", "保留（条件能力）"],
        ["v1.7.24", "CiteMap 原子断言/严格复判", "保留（条件能力）"],
        ["v1.7.31", "全文证据层；Europe PMC / arXiv / PMC fallback", "保留"],
        ["v1.7.36", "引用链、Live 高亮、Docker 验证、材料与发布收口", "当前版本"],
    ],
    (2.1, 12.8, 2.7),
)

_h2("0.3 证据边界与不能说的话")
_table(
    ["项目", "实际范围", "不能外推为"],
    [
        ["人工核对", "100 条、3 位匿名标注者、独立盲标", "外部用户反馈 / 全量中文论文准确率"],
        ["CiteMap", "105 格、3 位核对者、2 个主题起步", "全领域证据完整率"],
        ["真实语料", "20 篇论文、409 条引用，非随机抽样", "中文论文总体错误率"],
        ["构造集", "300 条规则构造标签", "人工金标准"],
        ["Live", "6 页/30 句/1 个扩展方向", "任意网页自动判真"],
    ],
    (3.2, 7.6, 6.8),
)
doc.add_page_break()

# ---------------- 1 ----------------
_h1("1", "代码、版本与发布记录")
_p(
    f"代码仓库：{REPO}。许可证：Apache-2.0。当前主分支提交：64bca7b（2026-11-19）。"
    f"发布页：{RELEASE}。仓库匿名访问与 Release 页面均返回 200。",
    9.2,
)
_pic("github", 16.0, "图 1  GitHub Release v1.7.36（真实页面截图；latest 已从旧版修正到当前版本）")
_p("提交历史（最近 10 条，均为真实 git 记录）：", 9, True, NAVY)
rows = [[h, s, d] for h, s, d in _git_log(10)]
_table(["提交", "说明", "日期"], rows, (2.6, 11.6, 2.7))
_p(
    "说明：提交记录中的早期 commit 覆盖了报告页、引用链、视频高亮、资源清单、Docker 验证和匿名化处理；"
    "历史 tag 保留，最新 tag 为 v1.7.36。",
    8.4,
    False,
    GRAY,
)
_p("开源清单与许可：", 9, True, NAVY)
_table(
    ["组件/资源", "用途", "许可/来源"],
    [
        ["pypdfium2", "PDF 渲染/版面", "BSD-3-Clause / Apache-2.0"],
        ["RapidOCR（可选）", "扫描件 OCR", "Apache-2.0"],
        ["OpenAlex / Crossref / arXiv / Europe PMC", "题录与全文线索", "CC0 / 开放 API 条款"],
        ["Qwen3-14B / 8B", "支持度判定（可替换）", "Apache-2.0"],
        ["Qwen3-VL-8B / 2.5-VL-7B", "图表核验（可选）", "Apache-2.0"],
        ["Qwen3-1.7B / 4B LoRA", "开源小模型适配器", "Apache-2.0（adapter 仓库）"],
        ["FastAPI / SQLite / Jinja2", "工程底座", "MIT / Public Domain / BSD"],
    ],
    (5.6, 6.3, 5.7),
)
doc.add_page_break()

# ---------------- 2 ----------------
_h1("2", "可运行性与测试记录")
_p(
    "以下结果均在 2026-11-19 的 v1.7.36 本地环境真实运行；不是示意图。"
    "复现命令见第 9 节。",
    9.2,
)
_table(
    ["检查", "结果", "说明"],
    [
        ["pytest tests -q", "1055 passed, 10 skipped", "98.74s；含新增引用链/分页/抽屉/权限测试"],
        ["verify_artifacts", "137/137", "结构、哈希、材料一致性自检"],
        ["audit_evidence", "216 路径 / 0 缺失 / 104 截图", "证据索引与截图归档"],
        ["e2e_smoke", "14/14", "上传→报告→批注→导出→证据包→diff"],
        ["前端审计", "58/58", "页面无横向溢出、可访问名、键盘与命令面板"],
        ["Docker health", "1.7.36", "镜像 citeguard-cn:1.7.36；/api/health ok"],
    ],
    (4.4, 5.4, 7.8),
)
_pic("pytest", 16.0, "图 2  真实 pytest 输出：1055 passed / 10 skipped / 98.74s")
_pic("docker", 16.0, "图 3  Docker 1.7.36 容器健康检查：ok=true, version=1.7.36")
_p("端到端冒烟（job 42a39e9f9092，v1.7.36）：", 9, True, NAVY)
_table(
    ["链路", "实测结果"],
    [
        ["引用/正文引注", "15 条引用、18 处引注、10 个图表标签、15 条 cited_in"],
        ["批注 PDF", "1,667,177 B；X-Annotated: 7；X-Citations: 17"],
        ["导出", "RIS 8,900 B / EndNote 4,612 B / BibTeX 5,720 B / CSL 10,178 B / refs 3,594 B"],
        ["证据包", "10 个文件，含 report.annotated.pdf / .bib / .csl.json / .ris / manifest.json"],
        ["diff", "自身对比 200；支持两次报告之间字段级差异"],
    ],
    (5.2, 12.4),
)
doc.add_page_break()

# ---------------- 3 ----------------
_h1("3", "人工核对记录")
_h2("3.1 支持度：100 条三人独立盲标")
_p(
    "样本从 ClaimSupport-CN 中分层抽取 100 条（support 41 / partial 26 / contradict 17 / no_evidence 16），"
    "三位标注者独立盲标；标注者姓名不记录。产品预测取自既有 300 条运行结果，未在这 100 条上重新调参。",
    9.0,
)
_table(
    ["指标", "结果", "说明"],
    [
        ["Fleiss κ", "0.98116", "三人一致性；分歧 2 条（HS021/HS034，均 2:1）"],
        ["产品 vs 多数票", "99/100", "唯一错误 HS032：人工 contradict，产品 partial"],
        ["Macro-F1", "0.987707", "四类等权"],
        ["Cohen κ", "0.985894", "产品 vs 多数票"],
        ["Wilson 95% CI", "94.55%–99.82%", "准确率区间；样本 100 条"],
        ["Bootstrap Macro-F1", "0.9578–1.0", "重采样区间，非显著性检验"],
    ],
    (4.4, 4.7, 8.5),
)
_pic("human_chart", 16.0, "图 4  100 条三人盲标：一致性、混淆矩阵、准确率区间与多数票分布")
_p(
    "边界：这是内部人工核对，不是外部用户反馈；不把 99/100 说成“中文论文通用准确率”。"
    "完整记录见 `data/experiments/human_audit_100.json`、`docs/human_audit_result.md`。",
    8.4,
    False,
    GRAY,
)

_h2("3.2 CiteMap：105 格三人核对")
_table(
    ["指标", "结果", "说明"],
    [
        ["核对规模", "105 格 / 101 已判定", "4 静态主题，40 条人工示例起步"],
        ["三人一致性", "Fleiss κ 0.658698", "中等一致；比支持度任务难"],
        ["判定准确率", "77/101（76.24%）", "Wilson 95% CI 67.07%–83.48%"],
        ["机器证据 precision", "8/31（25.81%）", "机器给出的“完整支持”多数不成立"],
        ["无证据误报", "1/70（1.43%）", "该说“未发现”时基本能说对"],
        ["全文覆盖", "25/30 篇 / 258 组合", "full 10 / partial 15 / none 233"],
    ],
    (4.4, 5.0, 8.2),
)
_pic("citemap_graph", 8.4, "图 5  CiteMap 证据图：全文实线、摘要虚线、抽样未发现点线；机器层单独标注")
_p(
    "这张图同时是“研究级边界”的证据：机器可以把“相关句”当支持，产品因此不允许把摘要自证写成“证据”，"
    "并把机器候选独立为 `auto_evidence`。",
    8.4,
    False,
    GRAY,
)
doc.add_page_break()

# ---------------- 4 ----------------
_h1("4", "真实语料与效果记录")
_h2("4.1 真实论文 409 条引用")
_table(
    ["口径", "Exact", "Minor", "Unverified", "Major", "说明"],
    [
        ["仅联网核验", "125", "87", "197", "0", "20 篇；未核实≠造假"],
        ["接本地题录库", "405", "4", "0", "0", "409/409 确定判定"],
    ],
    (5.0, 2.3, 2.3, 2.8, 2.0, 3.2),
)
_p(
    "Major=0 是当前真实语料上的记录；它不等于“任意论文永不误判”。系统把查不到写成 Unverified/Unknown，"
    "不把网络失败或解析噪声写成“假引用”。",
    8.6,
    False,
    GRAY,
)
_h2("4.2 字段篡改与编造")
_table(
    ["实验", "规模", "结果", "边界"],
    [
        ["原样基线", "40 条", "28 Exact / 12 Minor / 0 Major", "不冤枉未改引用"],
        ["字段篡改", "200 次（5 类×40）", "197 检出（98.5%）；DOI 40/40", "检出不等于全字段正确"],
        ["无锚点编造", "13 条", "13 Unverified（不指控）", "没有索引锚点时不硬判"],
        ["构造集 300 条", "300 条", "macro-F1 0.9841 / acc 0.9833", "规则构造标签，非人审"],
        ["全文层", "25/30 篇 / 258 组合", "full 10 / partial 15", "覆盖不足，仍标条件能力"],
    ],
    (4.0, 4.1, 6.2, 3.3),
)
_h2("4.3 旧版主评测（0.9.75 口径，仍可复现）")
_table(["评测", "样本", "结果", "说明"], [
    ["CiteBench-CN 分类准确率", "250 条", "0.9684（基线 0.5159）", "旧版 0.9.75 主口径；当前仍可复现"],
    ["ClaimSupport-CN 支持度", "100 条", "0.9597", "构造集；旧版主口径"],
], (5.2, 3.2, 5.6, 6.4))
_p("这两组是旧版已有成绩，本材料保留，不当作 v1.7.36 的新增提升；新版新增的是 300 条合并集、100 条三人盲标、CiteMap 105 格与真实 409 条。", 8.4, False, GRAY)
_pic("prevalence", 15.6, "图 6  22 篇真实中文论文、524 条引用的结构性问题统计（描述性，不代表总体比例）")
doc.add_page_break()

# ---------------- 4.3 evidence drawer ----------------
_h1("5", "页内证据与可复核界面")
_p(
    "下面两张图来自同一个任务、同一篇论文、同一条引用（任务 96511af51c97，引用 [10]）。"
    "选择 [10] 而不是 [1]，因为 [1] 是 Exact，不能拿它冒充错误案例。",
    9.0,
)
_pic("meta_overview", 16.0, "图 7  报告总览：同一任务/引用 [10]；year 2021 → 2020，来源 local，状态 Minor")
_table(["字段", "值"], [
    ["文件", "hanspub_152575.pdf"],
    ["任务", "96511af51c97"],
    ["引用", "[10] · 状态 Minor"],
    ["原条目", "… 2021 …（原条目年份 2021）"],
    ["比对来源", "本地题录库（source=local）"],
    ["差异字段", "year：2021 → 2020"],
    ["支持度", "未判定（无摘要，不是判不支持）"],
], (3.4, 14.2))
_p(
    "图 7 是总览；图 8 是「逐条结果 → 条目详情 → 证据抽屉」的右侧面板，"
    "原条目、比对来源、差异字段和最终状态在同一屏。支持度“未判定”是因为没有摘要，不是判不支持。",
    8.8,
)
_pic("meta_panel", 6.4, "图 8  证据抽屉：原条目、比对来源、差异字段与最终状态（2× 截图）")
_bullet("同一任务、同一文件、同一引用编号贯穿两张图；可直接对照报告页与抽屉。")
_bullet("抽屉中的“未判定”只表示没有摘要，不代表“不支持”；这是产品不把无证据写成结论的边界。")
doc.add_page_break()

# ---------------- 5 product ----------------
_h1("6", "产品能力截图（真实页面）")
_p("以下截图均为本机 1.7.36 真实任务页面，不用设计稿或合成图。", 9.0)
_pic("chain", 16.0, "图 9  引用链风险：8 条引用、抽样 96 条、平均抽样覆盖 100%；只查一层，覆盖不到写未知")
_pic("live", 16.0, "图 10  Live 页面引用预检：54 条文献、97 个标记、97/97 映射；只定位，不判真伪")
doc.add_page_break()

# ---------------- 6 open ----------------
_h1("7", "开放成果：数据、模型与接口")
_p(
    f"数据集：{HF_DATASET}（300 条，构造标签，非人审）。"
    f"适配器：{HF_17B}（Qwen3-1.7B）、{HF_4B}（Qwen3-4B）。"
    "三个页面均匿名访问 200；许可证与资源清单见随报告附件。",
    8.8,
)
cell_table = doc.add_table(rows=1, cols=2)
cell_table.alignment = WD_TABLE_ALIGNMENT.CENTER
cell_table.autofit = False
for cell, name, cap in (
    (cell_table.rows[0].cells[0], "hf_dataset", "HF 数据集 ClaimSupport-CN 300"),
    (cell_table.rows[0].cells[1], "hf_model", "HF 适配器 Qwen3-1.7B LoRA"),
):
    cell.width = Cm(8.6)
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(IMG / f"{name}.jpg"), width=Cm(7.8))
    cp = cell.add_paragraph()
    cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = cp.add_run(cap)
    _set_font(r, 7.5, False, GRAY)
_p("", 4)
_table(
    ["开放物", "规模/内容", "权利边界"],
    [
        ["数据集", "300 条构造集（100+60+140）", "CC-BY-4.0；上游 OpenAlex CC0；不含论文全文"],
        ["1.7B adapter", "LoRA 权重 + 训练脚本 + 模型卡", "Apache-2.0；构造测试集 0.9721，标注为构造饱和风险"],
        ["4B adapter", "LoRA 权重 + 训练脚本 + 模型卡", "Apache-2.0；测试 1.0 为构造饱和，不宣称通用"],
        ["接口", "REST / 批量 / SSE / SDK / MCP / Docker / Word 预览", "Apache-2.0；无鉴权默认 loopback"],
        ["资源清单", "2 页 PDF，随报告提交", "含排除项、许可义务、第三方 NOTICE"],
    ],
    (4.2, 7.2, 6.2),
)
_pic("license", 10.0, "图 12  许可边界表：核心无 AGPL；Readability/Europe PMC 等义务写清")

doc.add_page_break()

# ---------------- 7 external ----------------
_h1("8", "外部对照与负结果")
_p(
    "这一节故意保留不理想的结果：只放能对上口径的数字，不用旧口径或不同任务混算。",
    9.0,
)
_table(
    ["对照", "数字", "结论/处理"],
    [
        ["SciFact 300 条（ours）", "macro-F1 0.8224", "外部英文事实核查；与 RefChecker 官方 0.7646 非同管线，只作参考"],
        ["ChartCheck 400 条（ours）", "macro-F1 0.7628 / acc 0.695", "零样本图表核验，不是产品承诺；商品页只写“第一道筛查”"],
        ["LongCite 4090 GPU", "doc F1 0.5060 / statement 0.6446；20/20 截断", "reject：不接主功能；原因写进 research/longcite_spike.md"],
        ["AlignScore 中文 100 条", "contradict 蕴含 0.965 vs support 0.811", "KILL：方向相反，不能当中文支持度判官"],
        ["CiteMap 机器证据", "precision 8/31", "降级为 gray auto_evidence，不进入人工层"],
        ["Live 跨语言", "0/30", "页面/语言不匹配，不作为能力提升；保留边界"],
    ],
    (4.4, 6.0, 7.0),
)
_p(
    "负结果同样属于证据：它说明我们没有把“看起来能跑”包装成“已经有效”。",
    9.0,
    True,
    RED,
)
doc.add_page_break()

# ---------------- 8 license/security ----------------
_h1("9", "许可、合规与复现")
_h2("9.1 许可与匿名")
_table(
    ["项目", "状态"],
    [
        ["核心依赖 AGPL", "无；PyMuPDF 已移出核心，仅遗留脚本可选"],
        ["第三方清单", "THIRD_PARTY_NOTICES.md + 2 页资源清单 PDF；报告附录 A 摘要"],
        ["材料匿名", "报告/PPT/视频不含校名、校徽、个人与导师信息"],
        ["密钥/密码", "材料中无 API key、万方 key、服务器密码"],
        ["论文 PDF", "不随仓库分发；只保存开放获取链接/题录"],
        ["外部用户反馈", "未开展；不伪造评价"],
    ],
    (4.6, 13.0),
)
_h2("9.2 复现命令")
for cmd in (
    "git clone https://github.com/kkk431/citeguard-cn.git",
    "cd citeguard-cn && python -m venv .venv && . .venv/bin/activate  # Windows: .venv\\Scripts\\activate",
    "pip install -r requirements.txt",
    "pytest tests -q",
    "python scripts/reproduce_all.py",
    "python scripts/e2e_smoke.py --base http://127.0.0.1:8013 --pdf data/real_corpus/hanspub_152575.pdf",
    "docker build -f docker/Dockerfile -t citeguard-cn:1.7.50 .",
    "docker run --rm -p 18080:8000 citeguard-cn:1.7.50",
):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(1)
    p.paragraph_format.left_indent = Cm(0.4)
    r = p.add_run(cmd)
    _set_font(r, 7.8, False, RGBColor(0x1B, 0x3B, 0x4A))
    r.font.name = "Consolas"
_p(
    "注：当前没有公网在线演示实例；本机/Docker 运行方式与报告、提交说明一致。"
    "评审期仓库与 Hugging Face 链接保持有效，安装与启动步骤见 README 与 docs/deployment.md。",
    8.5,
    False,
    GRAY,
)
doc.add_page_break()

# ---------------- 9.3 optimization increment ----------------
_h1("9.3", "产品优化增量（A1–H1，v1.7.37–v1.7.50）")
_p(
    "下列改动均为可运行的产品能力，不是方案描述。完整验收命令、数据 JSON 与截图索引见 "
    "docs/optimization_report.md；本节只摘录对外可讲、可复算的结果。",
    9.2,
)
_table(
    ["波次", "能力", "验收数字/证据"],
    [
        ["A1", "题录库导入前预览", "28→30 dry-run；重复/缺字段先看清，确认后才写"],
        ["A2", "覆盖缺口看板", "28 条完整 9（32.1%）；中文 17、英文 11；CSV 导出"],
        ["A3", "题录库仪表盘", "来源/年份/期刊/完整度；6 份报告 129 条引用 56 命中（43.4%）"],
        ["B1", "长任务断点恢复", "20% 离开页面→继续→done/100%；历史页 3s 自动刷新"],
        ["B2", "结果缓存/只补失败", "同文件 Web 冷 4.638s→热 2.063s；CLI 冷 4373.8ms→热 67.9ms；库指纹入键"],
        ["B3", "模型不可用降级", "不伪造结论；judged=0/not_checked=15；页面给原因与下一步"],
        ["C1", "图表预检状态/重试", "视觉模型就绪状态；502→人话+重试；输入保留"],
        ["D1", "批量修复/复检", "15 条选 2 修 2；复检缺字段 0；撤销回 0"],
        ["E1", "Live 使用层", "三步引导/支持矩阵/失败三动作；不露 HTTP"],
        ["F1", "字段级修复建议", "缺 DOI 只给补法，不猜值；每条字段/问题/动作"],
        ["G1/G2/G5", "草稿/阅读器/错误", "草稿恢复；小地图+跳转+缩放；全站人话错误"],
        ["G3/G4/G6", "交互/微交互/分辨率", "hover/图例/缩放；reduced-motion；1280/1440/1920 18/18"],
        ["H1", "可观测性/回归", "request id/延迟头/metrics；回归 5 步全 0；pytest 1131"],
        ["H3/H4", "安全/许可", "token/限流/SSRF 默认；核心无 AGPL；licenses 4/4"],
    ],
    (1.8, 6.2, 9.6),
)
_pic("opt_a1", 7.4, "A1 导入前预览：可新增/重复/缺字段；确认后才写库")
_pic("opt_b1", 7.4, "B1 历史页：运行中任务 3 秒刷新，离开页面不中断")
_pic("opt_h1", 7.4, "H1 可观测性：/api/metrics 与 request id/延迟头")
_pic("opt_g6", 7.4, "G6 三视口审计：1280/1440/1920 无横向溢出")
_p(
    "口径：A1/A2/A3/B1/B2/C1/E1/F1/G1/G2/G3/G4/G6/H1 的截图与 JSON 均在 docs/evidence/shots 与 "
    "data/experiments；B2 的热缓存数字不等于冷启动；G3 的 105 节点为合成离屏基准；E3 候选未获人工接受。",
    8.2,
    False,
    GRAY,
)
doc.add_page_break()

# ---------------- 9.4 Batch 0 ----------------
_h1("9.4", "Batch 0 技术基线（v1.7.51）")
_p(
    "Batch 0 不做新模型、不买数据；先把可复算的基线固定下来，再用同一口径判断新方法是否值得保留。",
    9.2,
)
_table(
    ["项", "结果", "边界"],
    [
        ["评测 harness", "五组冻结结果 5/5 门禁；100 盲标 κ 0.98116 / acc 0.99 / F1 0.987707；409 真实 Major 0", "读既有结果，不重跑模型"],
        ["常数多数类基线", "macro-F1 0.1454（support）", "仅作下限参照"],
        ["成本感知级联", "同一 60 条回放：1.7B F1 0.9721；14B F1 0.9588；级联 routed 0、F1 0.9721", "无实测增益，不设默认路径"],
        ["版本感知实体消解", "Attention/BERT/ResNet 预印本+正式版、同 DOI、同名不同作者、无匹配 6/6", "known-work fixture，不是随机样本"],
    ],
    (3.0, 9.6, 5.0),
)
_p("证据：data/experiments/opt_b0_*.json；截图 docs/evidence/shots/opt-B0-bench-1.7.51-1440.png；测试 1148 passed。", 8.2, False, GRAY)
doc.add_page_break()

# ---------------- 9 records ----------------
_h1("10", "提交记录、维护与结论")
_h2("10.1 当前提交物")
_table(
    ["材料", "版本/规格"],
    [
        ["技术报告", "v1.7.51 · 15 页 · 1,703,665 B"],
        ["资源清单", "v1.7.36 · 2 页 · 144,779 B（随报告附件）"],
        ["答辩 PPT", "11 页 · v1.7.35（用户明确暂不更新）"],
        ["演示视频", "4:27 · v1.7.36 · 22,219,835 B（纯产品）"],
        ["源代码", "GitHub main · tag v1.7.51 · Apache-2.0"],
        ["发布页", RELEASE],
    ],
    (4.6, 13.0),
)
_h2("10.2 维护计划")
_bullet("每月复核一次依赖许可与上游数据源可用性；AGPL/非商用资源不进入核心。")
_bullet("新版本先跑 1055 项测试、137 项自检、14 项端到端；材料数字从 JSON 重算，不手填。")
_bullet("人工核对接新样本时继续三人独立盲标；没有新标签就不扩大对外口径。")
_h2("10.3 结论")
_p(
    "引证卫士不是“又一个通用大模型套壳”，而是一条可复核的证据链："
    "中文引用解析、两条判定线、GB/T 规则、证据抽屉、引用链和开放适配器都在同一套可运行代码里。"
    "本材料把能证明的部分、不能证明的边界和不理想的负结果一起交出，供评审核验。",
    9.2,
)
_p(
    "未提供专利、软件著作权、企业合作或外部用户评价；这些不影响作品参赛与基础评分。",
    8.4,
    False,
    GRAY,
)
doc.add_page_break()

# ---------------- appendix ----------------
_h1("A", "附录：证据文件索引")
_table(
    ["证据", "文件/URL", "用途"],
    [
        ["人工 100 条", "data/experiments/human_audit_100.json", "κ/准确率/混淆/唯一错误"],
        ["CiteMap 105 格", "data/experiments/citemap_audit_105/agreement.json", "κ/准确率/证据 precision"],
        ["真实语料", "data/experiments/verify_real.json；library_real.json", "409 条状态/建库前后"],
        ["字段篡改", "data/experiments/real_mutation_eval.json", "197/200；13 条编造"],
        ["300 构造集", "data/experiments/release300.json", "0.9841/0.9833；非人审"],
        ["全文层", "data/experiments/citemap_atomic_fulltext_v3_summary.json", "25/30；258 组合"],
        ["E2E", "data/experiments/e2e_smoke.json", "14/14；job 42a39e9f9092"],
        ["Docker", "docs/deployment.md", "1.7.50 health；镜像 943,589,044 B"],
        ["资源清单", "dist/开源及第三方资源使用清单_v1.7.36.pdf", "许可/第三方清单"],
        ["代码发布", RELEASE, "tag v1.7.50；latest release"],
        ["数据集", HF_DATASET, "300 条；CC-BY-4.0"],
        ["模型", HF_17B, "1.7B LoRA；Apache-2.0"],
        ["模型（4B）", HF_4B, "4B LoRA；Apache-2.0"],
    ],
    (3.6, 9.8, 4.2),
)
_p(
    "本材料生成脚本：`scripts/build_evidence_pdf.py`。生成时间为 2026-11-27；"
    "所有数字可由对应 JSON 与脚本复算。",
    8.2,
    False,
    GRAY,
)

# save docx
docx_path = OUT / "CiteGuard-CN_佐证材料_v1.7.51_2026-11-27.docx"
doc.save(docx_path)
print("DOCX", docx_path, docx_path.stat().st_size)
