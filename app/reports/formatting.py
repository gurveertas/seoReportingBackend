from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def report_number(value: int | float, *, signed: bool = False) -> str:
    """Format a numeric report value without altering its source precision."""
    if isinstance(value, int):
        result = f"{value:,}"
    else:
        result = f"{value:,.1f}".rstrip("0").rstrip(".")
    if result == "-0":
        result = "0"
    if signed and value > 0 and result != "0":
        return "+" + result
    return result


def report_position(value) -> str:
    """Display average search rank to one decimal place in PDFs."""
    if value is None:
        return "No data"
    try:
        position = Decimal(str(value).strip())
    except InvalidOperation:
        return str(value)
    if not position.is_finite():
        return "No data"
    return format(position.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP), "f")
