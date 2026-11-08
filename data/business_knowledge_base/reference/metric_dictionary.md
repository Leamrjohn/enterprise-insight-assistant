# 经营指标口径与使用限制

## 可确认的数值事实

| 指标 | 数据来源 | 计算方式 |
|---|---|---|
| 销售额 | `sales_orders` | 指定期间 `total_amount` 求和，且只统计已交付订单。 |
| 毛利 | `sales_order_items` | `line_amount - unit_cost × quantity` 求和。 |
| 应收余额 | `invoices`、`payments` | 发票金额减截至观察日的已收款。 |
| 逾期 | `invoices.due_date` | 到期日早于观察日且仍有未收余额。 |
| 客诉与退货 | `service_tickets`、`returns` | 按发生日期、类别、严重程度及退款金额汇总。 |
| 采购成本 | `purchase_orders`、`purchase_order_items` | 按采购下单日期及订单行成本汇总。 |

## 禁止的推断

- 订单下降本身不能证明唯一原因。
- 未回款只能证明回款风险或逾期，不能直接认定坏账。
- 同期发生的工单、退货和采购变化只能作为待核验信号，必须结合对应的授权文档形成假设。
