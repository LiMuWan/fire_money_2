"""HTML renderer for the FireMoney desktop preview."""

from __future__ import annotations

from pathlib import Path

from shared.contracts import (
    CommercialReadinessReport,
    NotificationRecord,
    OneToTwoBacktestAuditReport,
    OneToTwoDoctorReport,
    OneToTwoEndOfDayReview,
    OneToTwoMorningReport,
    OneToTwoScheduleHealthReport,
    OneToTwoScheduleRun,
    OneToTwoStabilityReport,
    PaperBacktestReport,
    PaperTradeDatabaseReport,
    PaperTradingDecisionReport,
    StrategyDecisionReport,
)

from .render_sections import (
    render_after_hours_radar,
    render_backtest_audit_panel,
    render_backtest_snapshot,
    render_board_shadow_system_panel,
    render_candidate_carousel,
    render_commercial_readiness_panel,
    render_decision_cockpit,
    render_doctor_panel,
    render_eod_review_panel,
    render_home_execution_panel,
    render_mainline_candidates,
    render_mainline_continuity,
    render_notification_message,
    render_notification_records,
    render_one_to_two_position,
    render_paper_backtest_panel,
    render_paper_database_panel,
    render_paper_decision_panel,
    render_schedule_panel,
    render_stability_panel,
    render_strategy_decision_panel,
)


_STATIC_DIR = Path(__file__).with_name("static")


def _clean_document(document: str) -> str:
    return "\n".join(line.rstrip() for line in document.splitlines()) + "\n"


def _runtime_status_bar() -> str:
    return """
    <section class="runtime-live-status" id="runtime-live-status" data-tone="neutral">
      <div>
        <span class="runtime-preview-label">预览 · 真实优先</span>
        <span class="runtime-label">实时值守</span>
        <strong id="runtime-live-headline">等待值守写入实时状态</strong>
      </div>
      <div class="runtime-live-detail" id="runtime-live-detail">
        <span class="runtime-chip" data-tone="neutral">真实值守读取中</span>
        <span class="runtime-next">真实值守、飞书 sent 记录和真实账本优先于静态样例。</span>
      </div>
    </section>
    <script>
      (() => {
        const root = document.getElementById("runtime-live-status");
        const headline = document.getElementById("runtime-live-headline");
        const detail = document.getElementById("runtime-live-detail");
        if (!root || !headline || !detail) {
          return;
        }
        const statusName = {
          ready: "运行正常",
          repaired: "已自动修复",
          warning: "需要留意",
          blocked: "存在阻断"
        };
        const scheduleName = {
          ready: "早评/晚评覆盖正常",
          warning: "早评/晚评需要留意",
          blocked: "早评/晚评存在阻断",
          closed: "非交易日静默"
        };
        const itemName = {
          morning: "早评",
          eod: "晚评"
        };
        const renderSchedule = (report) => {
          if (!report || !Array.isArray(report.items) || report.items.length === 0) {
            return "早评/晚评：暂无实时健康检查";
          }
          const items = report.items.map((item) => {
            const name = itemName[item.workflow] || item.workflow;
            return `${name}${item.scheduled_time || ""} ${item.status || "-"} / ${item.notification_status || "-"}`;
          });
          return `${scheduleName[report.status] || report.status || "早评/晚评状态未知"}：${items.join("；")}`;
        };
        const plainScheduleLine = (line) => {
          if (!line) {
            return "";
          }
          const text = String(line);
          const isMorning = text.includes("morning 08:50");
          const isEod = text.includes("eod 15:10");
          const name = isMorning ? "早评" : isEod ? "晚评" : "通知";
          if (text.includes("notification failed") || text.includes("通知 failed")) {
            return `${name}发送失败，需要检查飞书；服务本身不等于挂了`;
          }
          if (text.includes("notification sent") || text.includes("通知 sent")) {
            return `${name}已发送`;
          }
          if (text.includes("pending")) {
            return `${name}等待到点触发`;
          }
          if (text.includes("closed")) {
            return `${name}休市日不发送`;
          }
          return text;
        };
        const renderRawSchedule = (raw) => {
          if (!raw) {
            return "早评/晚评：暂无实时健康检查";
          }
          const text = String(raw).replace(/\\s+/g, " ").trim();
          const morning = text.match(/morning 08:50:[^。]+。?/);
          const eod = text.match(/eod 15:10:[^。]+。?/);
          const lines = [morning && morning[0], eod && eod[0]]
            .filter(Boolean)
            .map(plainScheduleLine);
          return lines.length ? lines.join("；") : text.slice(0, 220);
        };
        const chipTone = (text) => {
          const value = String(text || "");
          if (value.includes("失败") || value.includes("failed") || value.includes("阻断") || value.includes("blocked") || value.includes("未达标")) {
            return "danger";
          }
          if (value.includes("留意") || value.includes("warning") || value.includes("等待") || value.includes("pending") || value.includes("小仓")) {
            return "warning";
          }
          if (value.includes("已发送") || value.includes("sent") || value.includes("正常") || value.includes("达标") || value.includes("ready")) {
            return "success";
          }
          return "neutral";
        };
        const makeChip = (label, value, tone) => {
          const chip = document.createElement("span");
          chip.className = "runtime-chip";
          chip.dataset.tone = tone || chipTone(value);
          chip.textContent = `${label}：${value}`;
          return chip;
        };
        const findScheduleItem = (report, workflow) => {
          if (!report || !Array.isArray(report.items)) {
            return null;
          }
          return report.items.find((item) => item.workflow === workflow) || null;
        };
        const itemStatus = (item, fallback) => {
          if (!item) {
            return fallback || "暂无";
          }
          const status = item.notification_status || item.status || "未知";
          if (status === "sent") {
            return "已发送";
          }
          if (status === "failed") {
            return "失败";
          }
          if (status === "pending") {
            return "等待";
          }
          if (status === "ready") {
            return "正常";
          }
          return status;
        };
        const compactStatus = (value) => {
          const text = String(value || "");
          if (text.includes("失败") || text.includes("failed")) {
            return "失败";
          }
          if (text.includes("已发送") || text.includes("sent")) {
            return "已发送";
          }
          if (text.includes("等待") || text.includes("pending")) {
            return "等待";
          }
          if (text.includes("休市")) {
            return "休市";
          }
          if (text.includes("正常") || text.includes("ready")) {
            return "正常";
          }
          return text.slice(0, 12) || "暂无";
        };
        const rawStatus = (raw, workflow) => {
          const text = String(raw || "");
          const marker = workflow === "morning" ? "morning 08:50" : "eod 15:10";
          const line = text.match(new RegExp(`${marker}:[^\\n\\r]+`));
          return compactStatus(plainScheduleLine(line && line[0])) || "暂无";
        };
        const betaLabel = (value) => {
          const status = String(value || "").replace("Beta值守：", "").trim().toLowerCase();
          if (!status || status === "未知") {
            return "未知";
          }
          if (status === "check_only") {
            return "体检模式";
          }
          if (status.includes("running")) {
            return "运行中";
          }
          if (status === "stopped" || status === "stop") {
            return "未运行";
          }
          if (status === "missing") {
            return "未发现";
          }
          return status.slice(0, 12);
        };
        const betaTone = (label) => {
          if (label === "运行中") {
            return "success";
          }
          if (label === "体检模式") {
            return "warning";
          }
          if (label === "未运行" || label === "未发现") {
            return "danger";
          }
          return "neutral";
        };
        const checkedDate = (data) => {
          const value = String(data.checked_at || "").slice(0, 10);
          return /^\\d{4}-\\d{2}-\\d{2}$/.test(value) ? value : "";
        };
        const todayKey = () => {
          const now = new Date();
          const yyyy = now.getFullYear();
          const mm = String(now.getMonth() + 1).padStart(2, "0");
          const dd = String(now.getDate()).padStart(2, "0");
          return `${yyyy}-${mm}-${dd}`;
        };
        const isRuntimeStale = (data) => {
          const date = checkedDate(data);
          return !date || date !== todayKey();
        };
        const normalizeRuntimeData = (data) => {
          if (!isRuntimeStale(data)) {
            return data;
          }
          return {
            ...data,
            status: "blocked",
            stale_runtime: true,
            findings: [
              ...Array.from(new Set([...(Array.isArray(data.findings) ? data.findings : []), "runtime_status_stale"]))
            ]
          };
        };
        const nextRuntimeAction = (data, morning, eod, paper, paperText) => {
          const action = cleanSentence(paper.action);
          if (data.stale_runtime) {
            return "下一步：先运行运行守护检查，刷新今天的 runtime_status 后再看买点。";
          }
          if (data.status === "blocked") {
            if (morning === "失败") {
              return "下一步：先跑 beta-check / feishu-test，确认早评已发送后再看买点。";
            }
            if (eod === "失败") {
              return "下一步：先修晚评通知链路，确认飞书 sent 记录恢复。";
            }
            return "下一步：先修复通知和值守链路，再看买点。";
          }
          return action || cleanSentence(paperText) || "下一步：按真实状态执行。";
        };
        const renderRuntimeChips = (data, paperText, beta) => {
          detail.textContent = "";
          const report = data.schedule_health;
          const morning = report
            ? itemStatus(findScheduleItem(report, "morning"), "暂无")
            : rawStatus(data.schedule_health_raw, "morning");
          const eod = report
            ? itemStatus(findScheduleItem(report, "eod"), "暂无")
            : rawStatus(data.schedule_health_raw, "eod");
          const paper = data.paper_db || {};
          const paperValue = paper.tone === "success"
            ? "收益达标"
            : paper.tone === "warning" || paper.tone === "danger"
              ? "收益未达标"
              : (paper.headline ? cleanSentence(paper.headline).slice(0, 12) : "暂无账本");
          const betaValue = betaLabel(beta);
          const tradeValue = data.status === "blocked"
            ? "暂停"
            : paper.tone === "warning" || paper.tone === "danger"
              ? "小仓验证"
              : "按指挥单";
          const tradeTone = tradeValue === "暂停"
            ? "danger"
            : tradeValue === "小仓验证"
              ? "warning"
              : "success";
          const chips = [
            makeChip("交易", tradeValue, tradeTone),
            data.stale_runtime ? makeChip("状态", "已过期", "danger") : null,
            makeChip("早评", morning),
            makeChip("晚评", eod),
            makeChip("真实账本", paperValue, paper.tone),
            makeChip("Beta", betaValue, betaTone(betaValue))
          ].filter(Boolean);
          detail.append(...chips);
          const next = document.createElement("span");
          next.className = "runtime-next";
          next.textContent = nextRuntimeAction(data, morning, eod, paper, paperText);
          detail.appendChild(next);
        };
        const scheduleTone = (data, morning, eod, betaValue) => {
          if (data.status === "blocked" || morning === "失败" || eod === "失败") {
            return "danger";
          }
          if (data.status === "warning" || morning === "等待" || eod === "等待" || betaValue === "体检模式") {
            return "warning";
          }
          return "success";
        };
        const pct = (value) => {
          const number = Number(value);
          if (!Number.isFinite(number)) {
            return "--";
          }
          return `${(number * 100).toFixed(2)}%`;
        };
        const metricMeter = (label, value) => {
          const raw = String(value || "").replace(/[^\\d.-]/g, "");
          const number = Number(raw);
          if (!Number.isFinite(number)) {
            return "0%";
          }
          if (label === "闭环样本") {
            return `${Math.max(0, Math.min(100, number / 30 * 100)).toFixed(0)}%`;
          }
          if (label === "赚撤比") {
            return `${Math.max(0, Math.min(100, number / 3 * 100)).toFixed(0)}%`;
          }
          return `${Math.max(0, Math.min(100, number)).toFixed(0)}%`;
        };
        const cleanSentence = (value) => String(value || "").trim().replace(/[。；;]+$/g, "");
        const renderPaperDb = (paper) => {
          if (!paper) {
            return "真实模拟盘：暂无账本摘要";
          }
          const sample = Number(paper.closed_trade_count || 0);
          const winRate = pct(paper.win_rate);
          const ret = pct(paper.total_realized_return_pct);
          const ratio = Number(paper.average_profit_drawdown_ratio || 0).toFixed(2);
          const headlineText = cleanSentence(paper.headline || "等待收益质量判断");
          const actionText = cleanSentence(paper.action);
          return `真实模拟盘：${headlineText}；闭环 ${sample}，胜率 ${winRate}，收益 ${ret}，赚撤比 ${ratio}R${actionText ? `。${actionText}` : ""}`;
        };
        const applyPaperDbToTrustCard = (paper) => {
          if (!paper) {
            return;
          }
          const card = document.querySelector(".trust-overview .trust-card:nth-child(2)");
          if (!card) {
            return;
          }
          card.dataset.tone = paper.tone || "neutral";
          const title = card.querySelector(":scope > span");
          const headlineNode = card.querySelector(":scope > strong");
          const permission = card.querySelector(".permission-line");
          const metricValues = card.querySelectorAll(".trust-metrics b");
          const nextAction = card.querySelector(":scope > p");
          const latest = paper.latest_trade;
          if (title) {
            title.textContent = "真实收益守门";
          }
          if (headlineNode) {
            headlineNode.textContent = paper.tone === "warning" || paper.tone === "danger"
              ? "收益质量未达标，暂不放大仓位。"
              : (paper.headline || "等待真实模拟盘收益质量判断。");
          }
          if (permission) {
            permission.textContent = paper.tone === "warning" || paper.tone === "danger"
              ? "只允许小仓验证，不因样例加仓。"
              : (paper.action || "先按真实账本结论执行。");
          }
          const values = [
            String(Number(paper.closed_trade_count || 0)),
            pct(paper.win_rate),
            pct(paper.total_realized_return_pct),
            `${Number(paper.average_profit_drawdown_ratio || 0).toFixed(2)}R`
          ];
          metricValues.forEach((node, index) => {
            node.textContent = values[index] || "--";
            const wrapper = node.closest(".guard-meter");
            const label = wrapper && wrapper.querySelector("small")
              ? wrapper.querySelector("small").textContent
              : "";
            if (wrapper) {
              wrapper.style.setProperty("--meter", metricMeter(label, node.textContent));
            }
          });
          if (nextAction) {
            const latestLine = latest
              ? `最近闭环：${latest.name}（${latest.symbol}）${pct(latest.realized_pnl_pct)}。`
              : "";
            nextAction.textContent = latestLine || "下一步：继续记录真实买卖闭环。";
          }
        };
        const applyScheduleToTrustCard = (data, scheduleText, beta) => {
          const card = document.querySelector(".trust-overview .trust-card:first-child");
          if (!card) {
            return;
          }
          const report = data.schedule_health;
          const morning = report
            ? itemStatus(findScheduleItem(report, "morning"), "暂无")
            : rawStatus(data.schedule_health_raw, "morning");
          const eod = report
            ? itemStatus(findScheduleItem(report, "eod"), "暂无")
            : rawStatus(data.schedule_health_raw, "eod");
          const betaValue = betaLabel(beta);
          card.dataset.tone = scheduleTone(data, morning, eod, betaValue);
          const title = card.querySelector(":scope > span");
          const headlineNode = card.querySelector(":scope > strong");
          const shortLine = card.querySelector(".trust-short-lines b");
          const noteLine = card.querySelector(".trust-short-lines small");
          const nextAction = card.querySelector(":scope > p");
          if (title) {
            title.textContent = "运行信任";
          }
          if (headlineNode) {
            headlineNode.textContent = data.stale_runtime
              ? "运行状态不是今天的，先刷新值守。"
              : data.status === "blocked"
              ? "早评/飞书链路存在阻断，先暂停交易。"
              : "早评/晚评和值守链路已接入真实检查。";
          }
          if (shortLine) {
            shortLine.textContent = data.stale_runtime
              ? `状态日期：${checkedDate(data) || "未知"} / 今日：${todayKey()}`
              : `早评：${morning} / 晚评：${eod} / Beta：${betaValue}`;
          }
          if (noteLine) {
            noteLine.textContent = data.stale_runtime
              ? "旧状态不可作为今天交易依据。"
              : data.status === "blocked"
              ? "真实 sent 记录未恢复前，不执行买入。"
              : "真实 sent 记录优先于静态预览。";
          }
          if (nextAction) {
            nextAction.textContent = data.stale_runtime
              ? "下一步：刷新 runtime_status。"
              : data.status === "blocked"
              ? "下一步：修复早评/飞书/值守。"
              : morning === "等待" || eod === "等待"
                ? "下一步：保持值守常驻，到 08:50/15:10 后复核 sent。"
                : "下一步：按真实 sent 记录和值守结果执行。";
          }
          const stepValues = card.querySelectorAll(".trust-step-value");
          if (stepValues.length >= 4) {
            stepValues[0].textContent = morning;
            stepValues[1].textContent = data.status === "blocked" ? "暂停" : "可值守";
            stepValues[2].textContent = eod;
            stepValues[3].textContent = betaValue;
          }
          const steps = card.querySelectorAll(".trust-step");
          const tones = [
            chipTone(morning),
            data.status === "blocked" ? "danger" : data.status === "warning" ? "warning" : "success",
            chipTone(eod),
            betaTone(betaValue)
          ];
          steps.forEach((step, index) => {
            step.dataset.tone = tones[index] || "neutral";
          });
        };
        const applyRuntimeGateToCockpit = (data) => {
          const cockpit = document.querySelector(".decision-cockpit");
          if (!cockpit) {
            return;
          }
          const paper = data.paper_db || {};
          const paperTone = paper.tone || "neutral";
          const runtimeBlocked = data.status === "blocked";
          const paperWeak = paperTone === "warning" || paperTone === "danger";
          if (!runtimeBlocked && !paperWeak) {
            return;
          }
          const title = cockpit.querySelector(".cockpit-primary h2");
          const summary = cockpit.querySelector(".cockpit-summary");
          const dataMode = cockpit.querySelector(".cockpit-data-mode");
          const nextCommand = cockpit.querySelector(".command-strip strong");
          cockpit.dataset.action = "standby";
          cockpit.dataset.realGate = runtimeBlocked ? "runtime_blocked" : "paper_db_weak";
          if (title) {
            title.textContent = data.stale_runtime
              ? "先刷新值守，再谈买入"
              : runtimeBlocked ? "先修值守，再谈买入" : "真实收益未达标，先小仓验证";
          }
          if (summary) {
            summary.textContent = data.stale_runtime
              ? "当前运行状态不是今天生成的，旧指挥单不可作为今天交易依据。"
              : runtimeBlocked
              ? "当前真实值守有阻断：先处理早评、飞书和调度，样例买点不可直接执行。"
              : "真实模拟盘收益质量未达标：只允许小仓验证，不因样例好看而加仓。";
          }
          if (dataMode) {
            dataMode.textContent = "真实运行优先：上方实时值守和真实账本覆盖静态预览。";
          }
          if (nextCommand) {
            nextCommand.textContent = data.stale_runtime
              ? "先运行 FireMoneyRuntimeWatchdog / schedule-health，刷新今天状态后再看买点。"
              : runtimeBlocked
              ? "先运行 schedule-health / beta-check，修复通知和值守链路后再看买点。"
              : (paper.action || "先复盘真实账本，仓位保持小样本验证。");
          }
          const commandPanel = document.querySelector(".workbench-side .evidence-details.is-primary");
          if (commandPanel) {
            commandPanel.open = true;
            commandPanel.dataset.realGate = runtimeBlocked ? "runtime_blocked" : "paper_db_weak";
            const summaryTitle = commandPanel.querySelector("summary span");
            const summarySubtitle = commandPanel.querySelector("summary strong");
            if (summaryTitle) {
              summaryTitle.textContent = "真实运行闸门";
            }
            if (summarySubtitle) {
              summarySubtitle.textContent = data.stale_runtime
                ? "指挥单暂停：运行状态已过期"
                : runtimeBlocked
                ? "指挥单暂停：先修值守，再看买点"
                : "指挥单降级：真实收益未达标，只能小仓验证";
            }
            Array.from(commandPanel.children).forEach((child) => {
              if (child.tagName !== "SUMMARY") {
                child.remove();
              }
            });
            const section = document.createElement("section");
            section.className = "panel one-to-two-panel runtime-gate-panel";
            const h2 = document.createElement("h2");
            h2.textContent = runtimeBlocked ? "指挥单暂停" : "指挥单降级";
            const p = document.createElement("p");
            p.className = "next-action";
            p.textContent = data.stale_runtime
              ? "runtime_status.json 不是今天生成的，当前页面只可查看，不可作为交易依据。"
              : runtimeBlocked
              ? "真实值守存在阻断，当前页面里的样例买点不可直接执行。"
              : "真实模拟盘收益质量未达标，当前只允许小仓验证，不因为样例好看加仓。";
            const ul = document.createElement("ul");
            ul.className = "detail-list compact";
            const lines = data.stale_runtime
              ? [
                  "先运行 FireMoneyRuntimeWatchdog 或 schedule-health，刷新今天的运行状态。",
                  "状态刷新前，不执行买入、不参考静态样例指挥单。",
                  "如果今天是非交易日，只保持服务器和值守自检，不发送早评/晚评。"
                ]
              : runtimeBlocked
              ? [
                  "先修复早评、飞书和调度链路，确认 sent 记录后再看买点。",
                  "未恢复前，右侧静态指挥单只作为页面样例，不作为当天交易依据。",
                  "建议命令：schedule-health / beta-check / feishu-test。"
                ]
              : [
                  cleanSentence(paper.action || "先复盘真实账本，仓位保持小样本验证"),
                  "收益质量没有达标前，不放大仓位，不把样例收益当真实收益。",
                  "下一步：继续记录真实买卖闭环，等胜率、收益和赚撤比一起改善。"
                ];
            lines.forEach((line) => {
              const li = document.createElement("li");
              li.textContent = line;
              ul.appendChild(li);
            });
            section.append(h2, p, ul);
            commandPanel.appendChild(section);
          }
        };
        const runtimeHeadline = (data) => {
          const findings = Array.isArray(data.findings) ? data.findings : [];
          const httpOk = findings.includes("preview_http_200");
          if (data.stale_runtime) {
            return `运行状态已过期 · ${data.checked_at || "未记录时间"}`;
          }
          if (data.status === "blocked" && httpOk) {
            return `服务正常，但有通知阻断 · ${data.checked_at || "未记录时间"}`;
          }
          return `${statusName[data.status] || data.status || "状态未知"} · ${data.checked_at || "未记录时间"}`;
        };
        fetch("runtime_status.json", { cache: "no-store" })
          .then((response) => {
            if (!response.ok) {
              throw new Error(`HTTP ${response.status}`);
            }
            return response.json();
          })
          .then((data) => {
            data = normalizeRuntimeData(data || {});
            const tone = data.status === "blocked" ? "danger" : data.status === "warning" ? "warning" : "success";
            root.dataset.tone = tone;
            headline.textContent = runtimeHeadline(data);
            const beta = data.beta_watch ? `Beta值守：${data.beta_watch}` : "Beta值守：未知";
            const scheduleText = data.schedule_health
              ? renderSchedule(data.schedule_health)
              : renderRawSchedule(data.schedule_health_raw);
            const paperText = renderPaperDb(data.paper_db);
            renderRuntimeChips(data, paperText, beta);
            applyScheduleToTrustCard(data, scheduleText, beta);
            applyPaperDbToTrustCard(data.paper_db);
            applyRuntimeGateToCockpit(data);
          })
          .catch(() => {
            root.dataset.tone = "warning";
            headline.textContent = "等待值守写入实时状态";
            detail.textContent = "";
            detail.append(
              makeChip("值守", "等待写入", "warning"),
              makeChip("账本", "等待检查", "neutral")
            );
            const next = document.createElement("span");
            next.className = "runtime-next";
            next.textContent = "下一步：保持 FireMoneyRuntimeWatchdog 开机自启，等待下一次健康检查。";
            detail.appendChild(next);
          });
      })();
    </script>
    """


def _evidence_details(
    title: str,
    subtitle: str,
    body: str,
    *,
    open_by_default: bool = False,
    class_name: str = "",
    anchor_id: str = "",
) -> str:
    if not body.strip():
        return ""
    open_attr = " open" if open_by_default else ""
    class_attr = f"evidence-details {class_name}".strip()
    id_attr = f' id="{anchor_id}"' if anchor_id else ""
    return f"""
        <details class="{class_attr}"{id_attr}{open_attr}>
          <summary>
            <span>{title}</span>
            <strong>{subtitle}</strong>
          </summary>
          {body}
        </details>
    """


def _evidence_hub_nav(items) -> str:
    return f"""
      <nav class="evidence-hub-nav" aria-label="证据中心目录">
        {"".join(
            f'''
            <button class="evidence-hub-tab" type="button" data-evidence-target="{anchor}" aria-selected="{"true" if index == 0 else "false"}">
              <strong>{title}</strong>
              <span>{subtitle}</span>
              <b aria-hidden="true">+</b>
            </button>
            '''
            for index, (title, subtitle, anchor, _body) in enumerate(items)
        )}
      </nav>
    """


def _evidence_page(title: str, subtitle: str, anchor: str, body: str, *, active: bool) -> str:
    if not body.strip():
        return ""
    return f"""
      <section class="evidence-page{" is-active" if active else ""}" id="{anchor}" data-evidence-page="{anchor}" aria-hidden="{"false" if active else "true"}">
        <header class="evidence-page__head">
          <div>
            <span>{title}</span>
            <strong>{subtitle}</strong>
          </div>
        </header>
        <div class="evidence-page__body">
          {body}
        </div>
      </section>
    """


def render_one_to_two_workflow_html(
    report: OneToTwoMorningReport,
    watch_report: OneToTwoMorningReport,
    eod_review: OneToTwoEndOfDayReview,
    stability_report: OneToTwoStabilityReport,
    board_shadow_system_report=None,
    paper_backtest_report: PaperBacktestReport | None = None,
    strategy_decision_report: StrategyDecisionReport | None = None,
    paper_decision_report: PaperTradingDecisionReport | None = None,
    paper_database_report: PaperTradeDatabaseReport | None = None,
    doctor_report: OneToTwoDoctorReport | None = None,
    schedule_run: OneToTwoScheduleRun | None = None,
    schedule_health_report: OneToTwoScheduleHealthReport | None = None,
    notification_records: tuple[NotificationRecord, ...] = (),
    backtest_audit: OneToTwoBacktestAuditReport | None = None,
    commercial_readiness_report: CommercialReadinessReport | None = None,
) -> str:
    css = (_STATIC_DIR / "core.css").read_text(encoding="utf-8")
    account = watch_report.account
    latest_event = account.events[0].message if account.events else "暂无新的模拟盘事件。"
    notification = watch_report.notification
    webhook_state = "已配置" if notification.webhook_configured else "未配置"
    evidence_items = (
        (
            "上线验收",
            "合规、稳定、真实收益和回撤门槛",
            "evidence-commercial",
            render_commercial_readiness_panel(
                commercial_readiness_report
            ),
        ),
        (
            "重点候选",
            "股票卡片翻页，先看股票名、状态、买点和风险",
            "evidence-candidates",
            f"""
        <section class="evidence-hero">
          <div class="evidence-hero__head">
            <div>
              <span>重点候选</span>
              <strong>卡片左右滑动，先看股票名、状态、买点和风险</strong>
            </div>
            <div class="candidate-carousel__controls">
              <button type="button" data-candidate-scroll="-1">上一组</button>
              <button type="button" data-candidate-scroll="1">下一组</button>
            </div>
          </div>
          {render_candidate_carousel(report)}
        </section>
            """,
        ),
        (
            "持仓风险",
            "当前持仓、T+1、止盈止损纪律",
            "evidence-risk",
            f'<section class="panel one-to-two-panel"><h2>模拟盘与风险</h2>{render_one_to_two_position(watch_report)}</section>',
        ),
        (
            "龙虎榜雷达",
            "50-800 亿市值带、通测分组、硬剔除",
            "evidence-radar",
            render_after_hours_radar(report),
        ),
        (
            "飞书通知",
            "只看早评、买入、卖出、晚评",
            "evidence-notification",
            f'''
          <section class="panel one-to-two-panel">
            <h2>飞书通知</h2>
            <ul class="detail-list compact">
              <li>请求日期：{report.trade_context.requested_date} / {report.trade_context.note.replace("requested date is an A-share trading day", "当前日期为 A 股交易日")}</li>
              <li>状态：{notification.status.value.replace("prepared", "已生成").replace("sent", "已发送").replace("failed", "发送失败")} / 飞书 {webhook_state}</li>
              <li>最新事件：{latest_event}</li>
            </ul>
            <div class="notification-stack">
              {render_notification_message("08:50 早盘判断", report.notification.message)}
              {render_notification_message("盘中事件", watch_report.notification.message)}
              {render_notification_message("15:10 尾盘测评", eod_review.notification.message)}
            </div>
            <h3 class="panel-subtitle">通知记录</h3>
            <ul class="notification-records">
              {render_notification_records(notification_records)}
            </ul>
          </section>
          ''',
        ),
        (
            "主线持续性",
            "主线强度、新闻、同题材候选",
            "evidence-continuity",
            f'<section class="panel one-to-two-panel"><h2>主线持续性</h2>{render_mainline_continuity(watch_report)}</section>',
        ),
        ("策略证据", "主线或空仓选择依据", "evidence-strategy", render_strategy_decision_panel(strategy_decision_report)),
        ("交易指挥单", "买入价、仓位、止损、取消条件", "evidence-command", render_paper_decision_panel(paper_decision_report)),
        ("模拟盘账本", "胜率、收益、最近闭环", "evidence-ledger", render_paper_database_panel(paper_database_report)),
        ("历史回测", "年度/月度收益和回撤证据", "evidence-backtest", render_paper_backtest_panel(paper_backtest_report)),
        ("运行预检", "行情源、飞书、账本、调度", "evidence-doctor", render_doctor_panel(doctor_report)),
        (
            "本地调度",
            "漏发定位、早评、盘中、晚评执行窗口",
            "evidence-schedule",
            render_schedule_panel(schedule_run, schedule_health_report),
        ),
        ("晚评复盘", "尾盘总结和下一步", "evidence-eod", render_eod_review_panel(eod_review)),
        ("稳定性", "样本质量和系统阶段", "evidence-stability", render_stability_panel(stability_report)),
    )
    evidence_items = tuple(item for item in evidence_items if item[3].strip())
    evidence_pages = "".join(
        _evidence_page(title, subtitle, anchor, body, active=index == 0)
        for index, (title, subtitle, anchor, body) in enumerate(evidence_items)
    )
    evidence_center = f"""
        {_evidence_hub_nav(evidence_items)}
        <div class="evidence-stage" aria-live="polite">
          {evidence_pages}
        </div>
    """
    return _clean_document(
        f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FireMoney 主线首板</title>
  <style>
{css}
  </style>
</head>
<body>
  <main class="app-shell one-to-two-app">
    <header class="topbar">
      <div class="brand">
        <div class="brand-row">
          <h1 class="app-name">FireMoney 主线首板</h1>
          <span class="subtitle">主线首板专项台 · 只做能验证的赚钱闭环</span>
        </div>
        <div class="core-path">沪深主板 10cm -> 50-800 亿市值带 -> 主线首板筛选 -> 模拟盘买卖点 -> 收益与回撤复盘</div>
      </div>
      <div class="nav" aria-label="产品定位">
        <div class="nav-item is-active">主线交易播报</div>
        <button class="nav-item nav-button" type="button" data-open-evidence>证据中心</button>
      </div>
    </header>
    {_runtime_status_bar()}
    <div class="one-to-two-dashboard one-to-two-workbench">
      <section class="workbench-main" aria-label="核心决策">
        {render_decision_cockpit(strategy_decision_report, paper_decision_report, watch_report)}
        {render_backtest_snapshot(paper_backtest_report)}
      </section>
      <aside class="workbench-side" aria-label="证据与明细">
        {render_home_execution_panel(
          report=report,
          watch_report=watch_report,
          paper_report=paper_decision_report,
          paper_database_report=paper_database_report,
          doctor_report=doctor_report,
          schedule_run=schedule_run,
          schedule_health_report=schedule_health_report,
          notification_records=notification_records,
        )}
      </aside>
    </div>
    <section class="evidence-modal" id="evidence-center-modal" aria-hidden="true" aria-label="证据中心全屏">
      <div class="evidence-modal__backdrop" data-close-evidence></div>
      <div class="evidence-modal__panel" role="dialog" aria-modal="true" aria-labelledby="evidence-center-title">
        <header class="evidence-modal__header">
          <div>
            <span>全屏证据中心</span>
            <h2 id="evidence-center-title">候选、雷达、账本、回测和运行预检</h2>
          </div>
          <button type="button" class="evidence-modal__close" data-close-evidence>关闭</button>
        </header>
        <div class="evidence-modal__body">
          <div class="evidence-stack">{evidence_center}</div>
        </div>
      </div>
    </section>
    <script>
      (() => {{
        const modal = document.getElementById("evidence-center-modal");
        const openButtons = document.querySelectorAll("[data-open-evidence]");
        if (!modal || openButtons.length === 0) {{
          return;
        }}
        const closeButtons = modal.querySelectorAll("[data-close-evidence]");
        const setOpen = (open) => {{
          modal.classList.toggle("is-open", open);
          modal.setAttribute("aria-hidden", open ? "false" : "true");
          document.body.classList.toggle("has-modal-open", open);
        }};
        const showEvidencePage = (target) => {{
          const page = modal.querySelector(`[data-evidence-page="${{target}}"]`);
          if (!page) {{
            return false;
          }}
          modal.querySelectorAll("[data-evidence-page]").forEach((item) => {{
            const active = item === page;
            item.classList.toggle("is-active", active);
            item.setAttribute("aria-hidden", active ? "false" : "true");
          }});
          modal.querySelectorAll("[data-evidence-target]").forEach((button) => {{
            button.setAttribute(
              "aria-selected",
              button.getAttribute("data-evidence-target") === target ? "true" : "false"
            );
          }});
          return true;
        }};
        const openCurrentEvidence = (preferredTarget = "") => {{
          const target = preferredTarget || (window.location.hash ? window.location.hash.slice(1) : "");
          if (target) {{
            showEvidencePage(target);
            window.history.replaceState(null, "", `#${{target}}`);
          }}
          setOpen(true);
        }};
        openButtons.forEach((button) => {{
          button.addEventListener("click", () => {{
            openCurrentEvidence(button.getAttribute("data-evidence-open-target") || "");
          }});
        }});
        closeButtons.forEach((button) => {{
          button.addEventListener("click", () => setOpen(false));
        }});
        document.addEventListener("keydown", (event) => {{
          if (event.key === "Escape" && modal.classList.contains("is-open")) {{
            setOpen(false);
          }}
        }});
        const setCandidatePage = (direction) => {{
          const track = modal.querySelector(".candidate-carousel__track");
          const slides = Array.from(modal.querySelectorAll(".candidate-slide"));
          if (!track || slides.length === 0) {{
            return;
          }}
          const current = Number(track.dataset.page || "0");
          const next = Math.max(0, Math.min(slides.length - 1, current + direction));
          track.dataset.page = String(next);
          slides.forEach((slide, index) => {{
            slide.classList.toggle("is-current", index === next);
          }});
          track.style.setProperty("--candidate-page", String(next));
        }};
        setCandidatePage(0);
        modal.addEventListener("click", (event) => {{
          const tab = event.target.closest("[data-evidence-target]");
          if (tab) {{
            const target = tab.getAttribute("data-evidence-target") || "";
            if (showEvidencePage(target)) {{
              window.history.replaceState(null, "", `#${{target}}`);
            }}
            return;
          }}
          const button = event.target.closest("[data-candidate-scroll]");
          if (!button) {{
            return;
          }}
          const direction = Number(button.getAttribute("data-candidate-scroll") || "1");
          setCandidatePage(direction);
        }});
        window.addEventListener("hashchange", () => {{
          const target = window.location.hash ? window.location.hash.slice(1) : "";
          if (target && showEvidencePage(target)) {{
            setOpen(true);
          }}
        }});
        const initialTarget = window.location.hash ? window.location.hash.slice(1) : "";
        if (initialTarget && showEvidencePage(initialTarget)) {{
          setOpen(true);
        }}
      }})();
    </script>
  </main>
</body>
</html>
"""
    )


__all__ = ["render_one_to_two_workflow_html"]
