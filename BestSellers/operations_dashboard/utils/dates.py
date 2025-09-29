from datetime import date, timedelta


def recent_period(days: int) -> tuple[date, date]:
    """返回滚动窗口的起止日期。

    参数:
        days: 需要统计的天数，最小值会限制为 1。

    返回:
        (start, end) 元组，均为包含在统计窗口内的日期。
    """

    end = date.today()
    start = end - timedelta(days=max(days, 1) - 1)
    return start, end
