from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

NAVY = "#173B57"
TEAL = "#0E7C86"
ORANGE = "#D97706"
GRAY = "#6B7280"
LIGHT = "#E5E7EB"


def set_chinese_font() -> None:
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.dpi"] = 160


def _style(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(LIGHT)
    ax.spines["bottom"].set_color(LIGHT)
    ax.tick_params(colors=GRAY, labelsize=8)
    ax.grid(axis="y", color=LIGHT, linewidth=0.8, alpha=0.8)
    ax.set_axisbelow(True)


def kpi_trend_chart(df: pd.DataFrame, path: Path) -> Path:
    set_chinese_font()
    fig, ax1 = plt.subplots(figsize=(9, 4.2))
    ax1.bar(df["year_month"], df["applications"], color=TEAL, alpha=0.85, label="进件量")
    ax1.set_ylabel("进件量", color=GRAY)
    _style(ax1)
    ax2 = ax1.twinx()
    ax2.plot(df["year_month"], df["approval_rate"] * 100, color=ORANGE, marker="o", linewidth=2, label="审批通过率")
    ax2.set_ylabel("审批通过率 (%)", color=GRAY)
    ax2.tick_params(colors=GRAY, labelsize=8)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_color(LIGHT)
    ax1.set_title("月度进件量与审批通过率", loc="left", fontsize=13, color=NAVY, pad=12, fontweight="bold")
    ax1.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def funnel_chart(df: pd.DataFrame, path: Path) -> Path:
    set_chinese_font()
    stages = ["进件", "审批通过", "实际用信"]
    values = [df["applications"].sum(), df["approved"].sum(), df["used"].sum()]
    fig, ax = plt.subplots(figsize=(7, 3.6))
    bars = ax.barh(stages[::-1], values[::-1], color=[TEAL, "#4FA3A9", NAVY][::-1], height=0.55)
    for bar, value in zip(bars, values[::-1]):
        ax.text(value * 1.01, bar.get_y() + bar.get_height() / 2, f"{value:,.0f}", va="center", fontsize=9, color=NAVY)
    _style(ax)
    ax.set_xlabel("笔数", color=GRAY)
    ax.set_title("审批漏斗", loc="left", fontsize=13, color=NAVY, pad=12, fontweight="bold")
    ax.set_xlim(0, max(values) * 1.18 if max(values) else 1)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def vintage_heatmap(df: pd.DataFrame, path: Path) -> Path:
    set_chinese_font()
    if df.empty:
        fig, ax = plt.subplots(figsize=(7, 3))
        ax.text(0.5, 0.5, "还款数据加载后生成 Vintage 热力图", ha="center", va="center", color=GRAY, fontsize=11)
        ax.axis("off")
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        return path
    pivot = df.pivot_table(index="cohort", columns="mob", values="cum_dpd30_rate", aggfunc="mean")
    fig, ax = plt.subplots(figsize=(10, max(3.2, 0.28 * len(pivot))))
    image = ax.imshow(pivot.fillna(0).values * 100, aspect="auto", cmap="YlOrRd", vmin=0)
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns, fontsize=7)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index, fontsize=7)
    ax.set_xlabel("账龄月 (MOB)", color=GRAY)
    ax.set_ylabel("放款 cohort", color=GRAY)
    ax.set_title("Vintage 累计 DPD30 迁徙热力图 (%)", loc="left", fontsize=13, color=NAVY, pad=12, fontweight="bold")
    fig.colorbar(image, ax=ax, fraction=0.025, pad=0.02)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def channel_chart(df: pd.DataFrame, path: Path) -> Path:
    set_chinese_font()
    if df.empty:
        return path
    data = df.sort_values("approved_amount", ascending=True).tail(8)
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    ax.barh(data["channel_type"].astype(str), data["approved_amount"], color=TEAL, height=0.55)
    _style(ax)
    ax.set_xlabel("审批金额（万元，归一化）", color=GRAY)
    ax.set_title("渠道审批金额", loc="left", fontsize=13, color=NAVY, pad=12, fontweight="bold")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path
