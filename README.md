# astrbot-pregnancy-daily-care

一个面向孕期场景的 AstrBot 插件：每天定时在 QQ 群推送一条「孕早安」消息，包含：

- 宝宝逐天发育要点
- 孕妈妈逐天变化建议
- 当日孕期主题知识
- 《西尔斯怀孕百科》《怀孕一天一页》《跟老婆一起怀孕：写给准爸爸的孕期指导书》《海蒂怀孕大百科》的主题提炼阅读点
- 注意事项与安慰话语

## 知识来源（本地离线）

默认使用本地预制 JSON：

- [`data/pregnancy_content.json`](./data/pregnancy_content.json)

当前结构：

- `week_profiles`: 1~40 周档案
- `daily_entries`: 1~280 天逐天文案（每一天都有独立字段）
- `fallback_comfort`: 安慰话术池

`daily_entries` 内每条包含：

- `baby_day_points`: 当天宝宝发育要点
- `mom_day_points`: 当天孕妈变化/建议
- `book_tip`: 当天书籍启发知识点（主题提炼）
- `book_source`: 当天知识点来源书籍

当前默认分配策略：

- 280 天 `book_tip` 全部不重复
- 书籍占比约为：`《跟老婆一起怀孕》40%`、`《西尔斯怀孕百科》20%`、`《怀孕一天一页》20%`、`《海蒂怀孕大百科》20%`

> 说明：书籍相关内容为知识提炼和结构化表达，不含原文摘录。

## 功能特性

- 每日定时主动推送（例如每天 `08:00`）
- 群内一键绑定/解绑推送目标
- 预产期自动计算孕天数（优先）
- 支持直接填写“孕期第一天（末次月经第一天）”自动换算
- 本地知识库文件可替换（`content_file`）
- 支持热重载知识库（命令重载）

## 安装

将本插件目录放到 AstrBot 的 `data/plugins/` 下，然后在 WebUI 插件页启用本插件。

## 配置说明

在 WebUI 的插件配置里可看到以下配置项：

- `enabled`: 是否启用定时推送
- `send_time`: 每日发送时间（`HH:MM`）
- `timezone`: 时区（默认 `Asia/Shanghai`）
- `due_date`: 预产期（`YYYY-MM-DD`，优先计算孕周）
- `lmp_date`: 孕期第一天（`YYYY-MM-DD`）
- `gestational_days`: 未填预产期时的备用孕周天数
- `content_file`: 本地内容文件路径（默认 `data/pregnancy_content.json`）
- `custom_knowledge`: 每行一条，自定义覆盖“今日主题总结”

## 用法说明（参考 AstrBot 官方文档）

1. 在 AstrBot WebUI 中启用插件 `孕早安日报`。
2. 在插件配置中至少填写：
   - `enabled=true`
   - `send_time`（如 `08:00`）
   - `timezone`（如 `Asia/Shanghai`）
   - `due_date` 或 `lmp_date`（二选一，推荐填写 `due_date`）
3. 保存配置后，在目标 QQ 群发送绑定命令：
   - `/孕早安绑定`
4. 用测试命令确认消息内容：
   - `/孕早安测试`
5. 到达 `send_time` 后，插件会按已绑定群自动推送；也可手动触发：
   - `/孕早安立即推送`

### 群内命令

- `/孕早安绑定`：绑定当前群到推送列表
- `/孕早安解绑`：解绑当前群
- `/孕早安状态`：查看配置、知识库路径、已绑定群数量
- `/孕早安测试`：预览今日消息
- `/孕早安立即推送`：立即向所有已绑定群发送一次
- `/孕早安重载知识库`：重新加载本地 JSON 内容文件

## 官方文档参考

- [插件开发指南](https://docs.astrbot.app/dev/star/plugin-new.html)
- [发送消息（主动消息）](https://docs.astrbot.app/dev/star/guides/send-message.html)
- [插件配置](https://docs.astrbot.app/dev/star/guides/plugin-config.html)
- [消息事件与命令过滤器](https://docs.astrbot.app/dev/star/plugin-struct.html)

## 关键文件

- [`main.py`](./main.py)
- [`_conf_schema.json`](./_conf_schema.json)
- [`data/pregnancy_content.json`](./data/pregnancy_content.json)
- [`metadata.yaml`](./metadata.yaml)

## License

[GNU AGPLv3](./LICENSE)
