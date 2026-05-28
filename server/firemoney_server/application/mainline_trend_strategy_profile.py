"""Strategy profile rules for whole-market mainline trend research."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from server.firemoney_server.domain.one_to_two_types import (
    FundamentalSnapshot,
    MarketTrendRow,
)


class TrendProfileLike(Protocol):
    close: float
    ma10: float
    ma20: float
    high_60: float
    low_20: float
    gain_5_pct: float
    distance_to_ma10_pct: float
    distance_to_ma20_pct: float
    position_percentile_120: float
    base_tightness_pct: float


class ScoreBreakdownLike(Protocol):
    logic: float
    capital: float
    sustainability: float


class ThemeSignalLike(Protocol):
    theme: str
    strength: float


@dataclass(frozen=True)
class MainlineTrendStrategyProfile:
    strategy_type: str
    fit: str
    industry_chain_case: str
    profit_driver_case: str
    pre_breakout_case: str
    t_plan: str
    risk_control_case: str
    why_watch_case: str
    main_wave_stage: str
    confirmation_case: str
    holding_plan: str
    failure_signal: str
    position_plan: str


def build_mainline_trend_strategy_profile(
    *,
    row: MarketTrendRow,
    profile: TrendProfileLike,
    fundamental: FundamentalSnapshot | None,
    theme: ThemeSignalLike,
    scores: ScoreBreakdownLike,
) -> MainlineTrendStrategyProfile:
    if (
        scores.logic >= 84
        and scores.capital >= 74
        and scores.sustainability >= 72
        and row.turnover_amount >= 600_000_000
        and 0.42 <= profile.position_percentile_120 <= 0.86
    ):
        strategy_type = "龙头主升候选"
        fit = (
            "产业逻辑强、成交容量够、趋势还没有过度远离均线；"
            "可以按主线核心票观察，但只在回踩承接或放量突破确认后上车。"
        )
    elif (
        scores.sustainability >= 76
        and scores.logic >= 68
        and profile.base_tightness_pct <= 0.22
        and profile.distance_to_ma20_pct <= 0.16
    ):
        strategy_type = "趋势主升候选"
        fit = (
            "趋势结构比故事更强，产业逻辑需要继续扩散验证；适合等缩量回踩后的再转强；"
            "不是追涨模型，重点看20日线和成交额是否继续承接。"
        )
    elif (
        scores.logic >= 72
        and row.turnover_amount >= 200_000_000
        and 0.22 <= profile.position_percentile_120 <= 0.62
        and profile.gain_5_pct <= 0.32
    ):
        strategy_type = "低位主升预备"
        fit = (
            "位置还不高，但必须证明产业逻辑能扩散、资金愿意持续进来；"
            "低位只是安全垫，不是买入理由。"
        )
    elif profile.base_tightness_pct <= 0.18 and row.turnover_amount >= 150_000_000:
        strategy_type = "做T观察"
        fit = (
            "结构有箱体和均线可依托，更适合小仓位围绕支撑阻力做T；"
            "只有放量越过压力并守住，才升级为主升观察。"
        )
    else:
        strategy_type = "研究排除"
        fit = (
            "主升所需的产业、资金、趋势或买点证据不完整；"
            "先当研究样本，不因为短线涨幅就追。"
        )
    return MainlineTrendStrategyProfile(
        strategy_type=strategy_type,
        fit=fit,
        industry_chain_case=_industry_chain_case(theme),
        profit_driver_case=_profit_driver_case(theme, fundamental),
        pre_breakout_case=_pre_breakout_case(row, profile, scores),
        t_plan=_t_plan(profile),
        risk_control_case=_risk_control_case(profile),
        why_watch_case=_why_watch_case(row, profile, theme, scores, fundamental),
        main_wave_stage=_main_wave_stage(row, profile, scores),
        confirmation_case=_confirmation_case(profile),
        holding_plan=_holding_plan(profile),
        failure_signal=_failure_signal(theme, profile),
        position_plan=_position_plan(strategy_type, profile, scores),
    )


def _industry_chain_case(theme: ThemeSignalLike) -> str:
    if theme.theme == "AI服务器PCB上游":
        return (
            "AI服务器产业链：服务器/交换机升级 -> 高速PCB -> 覆铜板/电子布/低介电材料；"
            "能否成为大牛股，核心看订单、涨价、产能利用率和头部客户验证是否连续出现。"
        )
    if theme.theme == "AI算力基础设施":
        return (
            "算力产业链：云厂商资本开支 -> 光模块/互联/CPO -> 高速器件；"
            "持续主升来自800G到1.6T迭代、海外订单和毛利率稳定，而不是一天的题材热度。"
        )
    if theme.theme == "半导体国产替代":
        return (
            "半导体产业链：国产设备/材料/封测 -> 晶圆厂扩产与替代验证；"
            "主力愿意持续定价，通常需要国产份额提升、订单落地和周期拐点共振。"
        )
    if theme.theme == "机器人产业链":
        return (
            "机器人产业链：整机放量 -> 减速器/伺服/传感器/控制器；"
            "主升根源要看真实订单和单机价值量提升，单靠概念难以持续。"
        )
    return (
        f"{theme.theme} 还缺更细的产业链上下游拆解；"
        "后续要补公告、客户、订单、价格和行业景气证据，避免把泛题材当主线。"
    )


def _profit_driver_case(
    theme: ThemeSignalLike,
    fundamental: FundamentalSnapshot | None,
) -> str:
    if fundamental and (
        fundamental.revenue_growth_pct >= 15
        or fundamental.net_profit_growth_pct >= 20
    ):
        return (
            f"经济利益来自财报承接，营收增速 {fundamental.revenue_growth_pct:.1f}%、"
            f"净利增速 {fundamental.net_profit_growth_pct:.1f}%；"
            "这类票能吸引主力，是因为题材可能转化为利润弹性，而不只是消息刺激。"
        )
    if theme.strength >= 84:
        return (
            f"经济利益来自 {theme.theme} 高景气资金池，但当前财务承接待确认；"
            "必须继续跟踪订单、价格、毛利率和产能利用率，确认谁真正受益。"
        )
    return (
        "经济利益暂未看到足够强的利润兑现线索；"
        "只能作为产业研究样本，不能直接按价值投资或主升浪处理。"
    )


def _pre_breakout_case(
    row: MarketTrendRow,
    profile: TrendProfileLike,
    scores: ScoreBreakdownLike,
) -> str:
    if (
        scores.logic >= 72
        and 0.24 <= profile.position_percentile_120 <= 0.66
        and profile.base_tightness_pct <= 0.22
        and row.turnover_amount >= 200_000_000
    ):
        return (
            "低位启动前迹象是位置未过热、箱体收敛且成交额开始够用；"
            "下一步看缩量不破10/20日线，或放量突破60日高点后能否守住。"
        )
    if profile.position_percentile_120 > 0.86 or profile.gain_5_pct > 0.22:
        return (
            "启动前低点窗口大概率已经过去，当前更偏加速；"
            "只能等第一次强势回踩，不把冲高当上车点。"
        )
    return (
        "启动前主升雏形还不充分；"
        "先等产业逻辑扩散、成交额连续放大、均线重新收敛后再评估。"
    )


def _t_plan(profile: TrendProfileLike) -> str:
    support = min(profile.ma10, profile.ma20)
    pressure = profile.high_60
    return (
        f"有底仓才做T，围绕 {support:.2f} 附近缩量承接试错，"
        f"靠近 {pressure:.2f} 或放量冲高回落先降仓；"
        "没有底仓时不为了做T硬追，先等计划买点。"
    )


def _risk_control_case(profile: TrendProfileLike) -> str:
    stop_loss = min(profile.ma20 * 0.97, profile.low_20 * 0.985)
    return (
        f"回撤控制线设在 {stop_loss:.2f}；"
        "跌破后先退出观察，不用补仓摊薄；单票先小仓试错，等趋势兑现再加。"
    )


def _why_watch_case(
    row: MarketTrendRow,
    profile: TrendProfileLike,
    theme: ThemeSignalLike,
    scores: ScoreBreakdownLike,
    fundamental: FundamentalSnapshot | None,
) -> str:
    capacity = f"{row.turnover_amount / 100_000_000:.1f}亿"
    position = f"{profile.position_percentile_120:.0%}"
    if fundamental and (
        fundamental.revenue_growth_pct >= 15
        or fundamental.net_profit_growth_pct >= 20
    ):
        proof = (
            f"财报已有利润线索，营收 {fundamental.revenue_growth_pct:.1f}%、"
            f"净利 {fundamental.net_profit_growth_pct:.1f}%"
        )
    elif theme.strength >= 84:
        proof = "产业景气强但财务证据待补，必须继续盯订单、价格和毛利率"
    else:
        proof = "题材证据还浅，先当产业研究样本"
    return (
        f"{theme.theme} 的逻辑分 {scores.logic:.0f}，成交额 {capacity}，"
        f"120日位置 {position}，20日结构宽度 {profile.base_tightness_pct:.1%}；"
        f"{proof}。真正值得盯的是产业逻辑、资金容量和结构位置同时出现，而不是单日涨幅。"
    )


def _main_wave_stage(
    row: MarketTrendRow,
    profile: TrendProfileLike,
    scores: ScoreBreakdownLike,
) -> str:
    if profile.position_percentile_120 > 0.86 or profile.gain_5_pct > 0.22:
        return (
            "加速/高位风险段，低点窗口大概率已经过去；"
            "只等强势回踩，不把冲高当启动前机会。"
        )
    if (
        scores.logic >= 72
        and row.turnover_amount >= 200_000_000
        and profile.position_percentile_120 <= 0.45
        and profile.base_tightness_pct <= 0.22
    ):
        return (
            "低位蓄势段，开始出现产业逻辑和资金容量；"
            "重点盯第一次放量突破后是否还能缩量守住。"
        )
    if (
        scores.logic >= 72
        and scores.capital >= 70
        and profile.position_percentile_120 <= 0.70
        and profile.distance_to_ma20_pct <= 0.18
    ):
        return (
            "主升确认前段，已经有资金和逻辑共振，尚未到过热区；"
            "这是最适合找回踩确认和突破确认的窗口。"
        )
    if scores.sustainability >= 78 and profile.close >= profile.ma10:
        return (
            "趋势持有段，核心不是重新找低点，而是看10日/20日线能否托住整段。"
        )
    return (
        "研究观察段，证据还不够闭环；"
        "等逻辑扩散、成交额持续和均线收敛后再升级。"
    )


def _confirmation_case(profile: TrendProfileLike) -> str:
    pullback_low = min(profile.ma10, profile.ma20) * 0.99
    pullback_high = profile.ma10 * 1.025
    breakout = profile.high_60 * 1.01
    return (
        f"优先等 {pullback_low:.2f}-{pullback_high:.2f} 缩量回踩不破后再转强；"
        f"或放量突破 {breakout:.2f} 后次日不回落到压力位下方。"
        "确认必须叠加板块同向和成交额承接，不能只看一根阳线。"
    )


def _holding_plan(profile: TrendProfileLike) -> str:
    return (
        f"站稳10日线 {profile.ma10:.2f} 且20日线 {profile.ma20:.2f} 上行时保留核心仓；"
        "第一次跌破10日线先降仓观察，跌破20日线或放量长阴不硬扛。"
        "想吃完整主升浪，纪律是让盈利单沿均线走，而不是每天猜顶。"
    )


def _failure_signal(theme: ThemeSignalLike, profile: TrendProfileLike) -> str:
    stop_loss = min(profile.ma20 * 0.97, profile.low_20 * 0.985)
    return (
        f"跌破 {stop_loss:.2f}、放量跌破20日线、突破后两日内收回平台、"
        f"{theme.theme} 板块不再扩散或核心股轮流掉队；出现任一项，先撤出主升假设。"
    )


def _position_plan(
    strategy_type: str,
    profile: TrendProfileLike,
    scores: ScoreBreakdownLike,
) -> str:
    if strategy_type == "龙头主升候选":
        return (
            "启动前只允许观察或小仓试错，回踩/突破确认后再加到计划仓；"
            "单票不因逻辑强一次打满，回撤受控后才让利润扩大。"
        )
    if strategy_type == "趋势主升候选":
        return (
            "以回踩承接为买点，靠10日/20日线分批；"
            "趋势没坏就持有，偏离均线过远时只减不追。"
        )
    if strategy_type == "低位主升预备":
        return (
            "低位预备只能先建观察仓，等成交连续和板块扩散确认再提高仓位；"
            "低位买错也要快止损，不能把低位当安全保证。"
        )
    if strategy_type == "做T观察":
        return (
            f"只用底仓围绕 {min(profile.ma10, profile.ma20):.2f} 和 "
            f"{profile.high_60:.2f} 做T，突破前不升级为主升仓。"
        )
    return (
        f"综合逻辑/资金/持续 {scores.logic:.0f}/{scores.capital:.0f}/{scores.sustainability:.0f} 未闭环，"
        "只研究不建仓。"
    )


__all__ = [
    "MainlineTrendStrategyProfile",
    "build_mainline_trend_strategy_profile",
]
