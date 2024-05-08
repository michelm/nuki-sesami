
class SesamiArgError(Exception):
    def __init__(self, arg: list[str]) -> None:
        super().__init__(f"Argument not specified: [{' | '.join(arg)}]")
