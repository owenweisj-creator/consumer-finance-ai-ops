# 数据质量报告

- 数据源：Home Credit public dataset via Hugging Face (minhSpaceX/home_credit)
- 业务日历锚点：2026-09-30

## 表级检查

| 表 | 行数 | 字段数 |
|---|---:|---:|
| raw.application_train | 307,511 | 122 |
| raw.previous_application | 1,670,214 | 37 |
| raw.installments_payments | 13,605,401 | 8 |
| raw.pos_cash_balance | 10,001,358 | 8 |
| raw.credit_card_balance | 3,840,312 | 23 |
| raw.bureau | 1,716,428 | 17 |
| raw.bureau_balance | 27,299,925 | 3 |

## 主键重复

| 表:主键 | 重复数 |
|---|---:|
| raw.application_train:SK_ID_CURR | 0 |
| raw.previous_application:SK_ID_PREV | 0 |
| raw.installments_payments:SK_ID_PREV,NUM_INSTALMENT_NUMBER | 743,407 |
| raw.bureau:SK_ID_BUREAU | 0 |

## 关键字段缺失率

| 字段 | 缺失率 |
|---|---:|
| raw.application_train:AMT_CREDIT | 0.00% |
| raw.application_train:AMT_ANNUITY | 0.00% |
| raw.previous_application:NAME_CONTRACT_STATUS | 0.00% |
| raw.installments_payments:DAYS_ENTRY_PAYMENT | 0.02% |

## 历史申请状态分布

| 状态 | 笔数 |
|---|---:|
| Approved | 1,036,781 |
| Canceled | 316,319 |
| Refused | 290,678 |
| Unused offer | 26,436 |
