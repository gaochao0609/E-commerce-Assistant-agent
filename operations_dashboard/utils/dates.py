"""封装日期计算的常用辅助函数。"""

from datetime import date, timedelta


def recent_period(days: int) -> tuple[date, date]:
    """
    功能说明:
        根据给定天数返回最近的起止日期（包含当天）。
    参数:
        days (int): 包含的天数，至少为 1。
    返回:
        tuple[date, date]: (start, end) 日期元组。
    """
    end = date.today()
    start = end - timedelta(days=max(days, 1) - 1)
    return start, end
