from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, register


@register("daily_message", "xdy", "每日在 QQ 群推送孕期早安消息", "1.3.0")
class DailyPregnancyMorningPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._stop_event = asyncio.Event()
        self._schedule_task: Optional[asyncio.Task] = None

        base_dir = Path(__file__).resolve().parent
        self._storage_path = base_dir / "data" / "subscriptions.json"

        configured_file = str(self.config.get("content_file", "data/pregnancy_content.json") or "data/pregnancy_content.json")
        self._content_path = Path(configured_file)
        if not self._content_path.is_absolute():
            self._content_path = base_dir / configured_file

        self._subscriptions: dict[str, str] = {}
        self._content_library: dict[str, Any] = {}

        self._load_subscriptions()
        self._load_content_library()

    async def initialize(self):
        if not self.config.get("enabled", True):
            logger.info("[daily_message] 插件已禁用，跳过定时任务启动")
            return
        self._schedule_task = asyncio.create_task(self._schedule_loop())
        logger.info("[daily_message] 定时任务已启动")

    async def terminate(self):
        self._stop_event.set()
        if self._schedule_task and not self._schedule_task.done():
            self._schedule_task.cancel()
            try:
                await self._schedule_task
            except asyncio.CancelledError:
                pass
        logger.info("[daily_message] 插件已停止")

    @filter.command("孕早安绑定")
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def bind_group(self, event: AstrMessageEvent):
        """在当前群绑定每日孕期早安推送"""
        group_id = str(getattr(event.message_obj, "group_id", ""))
        if not group_id:
            yield event.plain_result("绑定失败：未识别到群号。")
            return

        self._subscriptions[group_id] = event.unified_msg_origin
        self._save_subscriptions()
        yield event.plain_result(
            f"已绑定群 {group_id}。\n将按 {self.config.get('send_time', '08:00')} 自动推送孕期早安消息。"
        )

    @filter.command("孕早安解绑")
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def unbind_group(self, event: AstrMessageEvent):
        """在当前群解绑每日孕期早安推送"""
        group_id = str(getattr(event.message_obj, "group_id", ""))
        if not group_id:
            yield event.plain_result("解绑失败：未识别到群号。")
            return

        if group_id in self._subscriptions:
            self._subscriptions.pop(group_id, None)
            self._save_subscriptions()
            yield event.plain_result(f"已解绑群 {group_id}。")
            return

        yield event.plain_result("当前群未绑定，无需解绑。")

    @filter.command("孕早安状态")
    async def plugin_status(self, event: AstrMessageEvent):
        """查看插件配置与已绑定群数量"""
        due_date = self.config.get("due_date", "") or "未设置"
        lmp_date = self.config.get("lmp_date", "") or "未设置"
        timezone = self.config.get("timezone", "Asia/Shanghai")
        send_time = self.config.get("send_time", "08:00")
        enabled = self.config.get("enabled", True)
        day_count = len(self._content_library.get("daily_entries", []))

        yield event.plain_result(
            "\n".join(
                [
                    "【孕早安插件状态】",
                    f"启用状态：{'开启' if enabled else '关闭'}",
                    f"发送时间：{send_time} ({timezone})",
                    f"预产期：{due_date}",
                    f"孕期第一天：{lmp_date}",
                    f"内容文件：{self._content_path}",
                    f"本地日内容数量：{day_count}",
                    f"已绑定群数：{len(self._subscriptions)}",
                ]
            )
        )

    @filter.command("孕早安测试")
    async def preview_message(self, event: AstrMessageEvent):
        """预览今日将发送的孕期早安消息"""
        yield event.plain_result(self._build_message())

    @filter.command("孕早安立即推送")
    async def send_now(self, event: AstrMessageEvent):
        """立即向所有已绑定群推送一次消息"""
        sent = await self._broadcast_once()
        yield event.plain_result(f"本次推送完成，成功发送到 {sent} 个群。")

    @filter.command("孕早安重载知识库")
    async def reload_content(self, event: AstrMessageEvent):
        """重载本地孕期知识库 JSON"""
        self._load_content_library()
        day_count = len(self._content_library.get("daily_entries", []))
        yield event.plain_result(f"知识库已重载，当前可用逐天内容 {day_count} 条。")

    async def _schedule_loop(self):
        while not self._stop_event.is_set():
            wait_seconds = self._seconds_until_next_run()
            logger.info(f"[daily_message] 距离下一次推送还有 {int(wait_seconds)} 秒")

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=wait_seconds)
                break
            except asyncio.TimeoutError:
                pass

            try:
                sent = await self._broadcast_once()
                logger.info(f"[daily_message] 定时推送完成，发送到 {sent} 个群")
            except Exception as exc:
                logger.error(f"[daily_message] 定时推送失败: {exc}")

    async def _broadcast_once(self) -> int:
        if not self._subscriptions:
            logger.info("[daily_message] 当前没有已绑定群，跳过推送")
            return 0

        message = self._build_message()
        sent = 0

        for group_id, umo in list(self._subscriptions.items()):
            try:
                chain = MessageChain().message(message)
                await self.context.send_message(umo, chain)
                sent += 1
            except Exception as exc:
                logger.error(f"[daily_message] 向群 {group_id} 推送失败: {exc}")
            await asyncio.sleep(0.2)

        return sent

    def _build_message(self) -> str:
        today = datetime.now(self._get_timezone()).date()
        date_text = f"{today.year}年{today.month}月{today.day}日"
        custom_greeting = str(self.config.get("greeting", "") or "").strip()
        gestational_days, due_date = self._resolve_gestational_days(today)

        if gestational_days is None:
            day_no = 1
            week = 0
            day_in_week = 1
            status_line = "💝【温馨提示】尚未设置预产期，先按第1天生成示例内容"
        else:
            day_no = max(1, gestational_days)
            week = day_no // 7
            day_in_week = day_no % 7
            status_line = f"💝【温馨提示】今日是怀孕第{day_no}天（约第{week}周+{day_in_week}天）"

        # 内容库按 1~40 周组织，这里把“显示周数”映射为内容周数（+1）
        content_week = min(max(week + 1, 1), 40)
        week_profile = self._find_week_profile(content_week)
        daily_entry = self._get_daily_entry(day_no)
        custom_tip = self._get_custom_tip(day_no)

        baby_points = daily_entry.get("baby_day_points", [])[:3]
        if not baby_points:
            baby_points = week_profile.get("baby_development", [])[:3]

        mom_points = daily_entry.get("mom_day_points", [])[:3]
        if not mom_points:
            mom_points = week_profile.get("mom_changes", [])[:3]

        size_text = week_profile.get("size", "发育中")

        topic_title = str(daily_entry.get("title", "均衡饮食与规律作息"))
        topic_summary = custom_tip or str(daily_entry.get("summary", "保持产检与均衡营养。"))
        foods = daily_entry.get("foods", [])[:4]
        boosts = daily_entry.get("boost", [])[:3]
        notes = daily_entry.get("notes", [])[:3]
        comfort = str(daily_entry.get("comfort", self._fallback_comfort(day_no)))
        book_tip_raw = str(daily_entry.get("book_tip", "")).strip()
        book_source = str(daily_entry.get("book_source", "")).strip()
        book_tip = self._format_book_tip(book_tip_raw, book_source, day_no, week, day_in_week)

        lines = [custom_greeting or f"🌅 早安！{date_text}", status_line]

        if due_date is not None:
            remaining = (due_date - today).days
            if remaining >= 0:
                lines.append(f"🗓 预产期：{due_date.isoformat()}（还有 {remaining} 天）")
            else:
                lines.append(f"🗓 预产期：{due_date.isoformat()}（已过 {abs(remaining)} 天）")

        lines.extend(
            [
                "",
                "👶 宝宝发育",
                f"1. 📏 大小约{size_text}",
                f"2. 🌱 {baby_points[0] if len(baby_points) > 0 else '宝宝持续成长中'}",
                f"3. 🧠 {baby_points[1] if len(baby_points) > 1 else '各系统发育逐步完善'}",
                f"4. ✨ {baby_points[2] if len(baby_points) > 2 else '请按时产检关注发育进展'}",
                "",
                "🤰 孕妈妈变化",
                f"1. 💗 {mom_points[0] if len(mom_points) > 0 else '身体在适应孕期激素变化'}",
                f"2. 🌿 {mom_points[1] if len(mom_points) > 1 else '注意休息和睡眠节律'}",
                f"3. 🛌 {mom_points[2] if len(mom_points) > 2 else '保持均衡饮食和适度活动'}",
                "",
                f"📚 今日主题：{topic_title}",
                topic_summary,
                "🥗 富含营养的建议食物：",
            ]
        )

        for i, food in enumerate(foods, start=1):
            lines.append(f"{i}. 🍽️ {food}")

        lines.append("🧪 促进吸收与利用：")
        for item in boosts:
            lines.append(f"- ✅ {item}")

        lines.append("⚠️ 注意事项")
        for i, note in enumerate(notes, start=1):
            lines.append(f"{i}. 🔔 {note}")

        if book_tip:
            lines.extend(["", "📖 每日阅读点", f"📝 {book_tip}"])

        lines.extend(["", f"🌸 {comfort}"])
        return "\n".join(lines)

    def _resolve_gestational_days(self, today: date) -> tuple[Optional[int], Optional[date]]:
        due_date_str = (self.config.get("due_date", "") or "").strip()
        if due_date_str:
            try:
                due_date = date.fromisoformat(due_date_str)
                days = 280 - (due_date - today).days
                return days, due_date
            except ValueError:
                logger.error("[daily_message] due_date 配置格式错误，需为 YYYY-MM-DD")

        lmp_date_str = (self.config.get("lmp_date", "") or "").strip()
        if lmp_date_str:
            try:
                lmp_date = date.fromisoformat(lmp_date_str)
                days = (today - lmp_date).days + 1
                due_date = lmp_date + timedelta(days=280)
                return days, due_date
            except ValueError:
                logger.error("[daily_message] lmp_date 配置格式错误，需为 YYYY-MM-DD")

        gestational_days_raw = self.config.get("gestational_days", 0)
        try:
            gestational_days = int(gestational_days_raw)
            if gestational_days > 0:
                return gestational_days, None
        except Exception:
            logger.error(f"[daily_message] gestational_days 配置非法: {gestational_days_raw}")

        return None, None

    def _seconds_until_next_run(self) -> float:
        timezone = self._get_timezone()
        now = datetime.now(timezone)

        send_time = str(self.config.get("send_time", "08:00") or "08:00")
        hour, minute = self._parse_send_time(send_time)

        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return max((target - now).total_seconds(), 1.0)

    def _parse_send_time(self, raw: str) -> tuple[int, int]:
        try:
            hour_str, minute_str = raw.split(":", 1)
            hour = int(hour_str)
            minute = int(minute_str)
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
            return hour, minute
        except Exception:
            logger.error(f"[daily_message] send_time 配置非法: {raw}，回退到 08:00")
            return 8, 0

    def _get_timezone(self) -> ZoneInfo:
        zone = str(self.config.get("timezone", "Asia/Shanghai") or "Asia/Shanghai")
        try:
            return ZoneInfo(zone)
        except Exception:
            logger.error(f"[daily_message] timezone 配置非法: {zone}，回退到 Asia/Shanghai")
            return ZoneInfo("Asia/Shanghai")

    def _load_content_library(self):
        if not self._content_path.exists():
            logger.error(f"[daily_message] 内容文件不存在: {self._content_path}")
            self._content_library = {}
            return

        try:
            data = json.loads(self._content_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("内容文件必须是 JSON 对象")
            self._content_library = data
            logger.info(
                "[daily_message] 内容库加载成功，周资料 %s 条，每日资料 %s 条",
                len(data.get("week_profiles", {})),
                len(data.get("daily_entries", [])),
            )
        except Exception as exc:
            logger.error(f"[daily_message] 读取内容文件失败: {exc}")
            self._content_library = {}

    def _find_week_profile(self, week: int) -> dict[str, Any]:
        profiles = self._content_library.get("week_profiles", {})
        if not isinstance(profiles, dict) or not profiles:
            return {}

        safe_week = min(max(week, 1), 40)
        profile = profiles.get(str(safe_week), {})
        return profile if isinstance(profile, dict) else {}

    def _get_daily_entry(self, day_no: int) -> dict[str, Any]:
        entries = self._content_library.get("daily_entries", [])
        if not isinstance(entries, list) or not entries:
            return {}

        index = (max(day_no, 1) - 1) % len(entries)
        entry = entries[index]
        return entry if isinstance(entry, dict) else {}

    def _get_custom_tip(self, day_no: int) -> str:
        raw = str(self.config.get("custom_knowledge", "") or "").strip()
        if not raw:
            return ""
        tips = [line.strip() for line in raw.splitlines() if line.strip()]
        if not tips:
            return ""
        return tips[(max(day_no, 1) - 1) % len(tips)]

    def _fallback_comfort(self, day_no: int) -> str:
        pool = self._content_library.get("fallback_comfort", [])
        if not isinstance(pool, list) or not pool:
            return "今天也要开开心心的，宝宝正在努力成长，妈妈辛苦了。"
        return str(pool[(max(day_no, 1) - 1) % len(pool)])

    def _format_book_tip(
        self, raw_tip: str, source: str, day_no: int, week: int, day_in_week: int
    ) -> str:
        if not raw_tip:
            return ""

        # 统一重写阅读点头部，避免 JSON 内预写的孕周口径与当前展示口径不一致。
        if "；" in raw_tip:
            _, body = raw_tip.split("；", 1)
        else:
            body = raw_tip

        safe_source = source
        if not safe_source:
            if "：" in raw_tip:
                safe_source = raw_tip.split("：", 1)[0].strip()
            else:
                safe_source = "每日阅读"

        return f"{safe_source}：第{day_no}天（孕{week}周+{day_in_week}天）；{body.strip()}"

    def _load_subscriptions(self):
        if not self._storage_path.exists():
            return
        try:
            data = json.loads(self._storage_path.read_text(encoding="utf-8"))
            groups = data.get("groups", {}) if isinstance(data, dict) else {}
            if isinstance(groups, dict):
                self._subscriptions = {str(k): str(v) for k, v in groups.items() if v}
        except Exception as exc:
            logger.error(f"[daily_message] 读取订阅数据失败: {exc}")

    def _save_subscriptions(self):
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"groups": self._subscriptions}
        self._storage_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
