"""Reviewed Dark Gift option identities for prototype observation/action features."""

DARK_GIFT_OPTION_IDS = (
    "EDR_100t", "EDR_100t1", "EDR_100t13", "EDR_100t2", "EDR_100t3",
    "EDR_100t5", "EDR_100t6", "EDR_100t7", "EDR_100t8", "EDR_100t9",
)
DARK_GIFT_POLICY_INDEX = {
    "EDR_100t": 1, "EDR_100t1": 2, "EDR_100t2": 3, "EDR_100t6": 4,
    "EDR_100t5": 5, "EDR_100t7": 6, "EDR_100t3": 7, "EDR_100t9": 8,
    "EDR_100t8": 9, "EDR_100t13": 10,
}

def dark_gift_counts(gifts: tuple[str, ...] | list[str]) -> list[int]:
    unknown = set(gifts) - set(DARK_GIFT_OPTION_IDS)
    if unknown:
        raise ValueError(f"Unreviewed Dark Gift identity: {sorted(unknown)}")
    return [sum(gift == option for gift in gifts) for option in DARK_GIFT_OPTION_IDS]
