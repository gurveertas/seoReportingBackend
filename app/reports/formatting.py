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
