# 维护手册

## 数据刷新

1. 运行 `python scripts/download_data.py` 或 `scripts/download_bits.ps1`，脚本会校验文件大小并写入 `data/raw/manifest.json`。
2. 运行 `python -m src.etl.build_warehouse` 重建仓库。
3. 运行 `python -m src.etl.profile_data` 复核日期范围和月度分布。
4. 重新生成看板、Excel、报告和评测。

## Prompt / 模型版本

- Prompt 放在 `prompts/`，每次修改新增版本号，不覆盖旧版本。
- 修改后用同一套 `eval/questions.jsonl` 重跑评测，记录准确率、拒答率、延迟和 token。
- 模型切换（如 DeepSeek 版本变化）必须重跑评测，不能只看单次演示。

## 发布检查清单

- `pytest -q` 全部通过。
- `python scripts/check_secrets.py` 无密钥。
- `python scripts/check_privacy.py` 无手机号/邮箱。
- 看板离线可打开，Excel 无损坏。
- 报告数字与 SQL 对平。
- README 的快速开始命令可复现。

## 常见问题

**日期跑到未来**：Home Credit 的 `DAYS_*` 是负数，映射时应使用加法。
**金额大得离谱**：金额字段需除以 10,000 做万元归一化。
**比率不可加总**：比率必须回到分子/分母重新汇总。
**Vintage 为空**：确认 `installments_payments` 已完整下载并重建仓库。

