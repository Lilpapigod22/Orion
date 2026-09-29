"""
Калкулатори за пари и здраве: кредит, сложна лихва, ДДС, отстъпки, спестявания, гориво, ИТМ.
Сметките са точни — моделът само ги обяснява.
"""
from jarvis import jarvis_tool


def _money(value: float) -> str:
    return f"{value:,.2f}".replace(",", " ")


@jarvis_tool
def loan_payment(amount: float, annual_rate: float, years: float) -> str:
    """Месечна вноска по кредит (анюитет), общо платено и лихва. За ипотека, заем, лизинг.

    Args:
        amount: Размерът на кредита, напр. 100000.
        annual_rate: Годишна лихва в проценти, напр. 3.5.
        years: За колко години.
    """
    months = max(1, round(years * 12))
    rate = annual_rate / 100 / 12
    payment = amount / months if rate == 0 else amount * rate / (1 - (1 + rate) ** -months)
    total = payment * months
    return (f"Вноска {_money(payment)} на месец за {months} месеца; общо ще платите {_money(total)}, "
            f"от които {_money(total - amount)} лихва.")


@jarvis_tool
def compound_interest(principal: float, annual_rate: float, years: float, monthly_deposit: float = 0) -> str:
    """Колко ще станат спестяванията със сложна лихва (и месечни вноски по желание).

    Args:
        principal: Началната сума.
        annual_rate: Годишна доходност в проценти, напр. 5.
        years: За колко години.
        monthly_deposit: Колко добавяте всеки месец (0 — нищо).
    """
    rate, months = annual_rate / 100 / 12, round(years * 12)
    balance = principal
    for _ in range(months):
        balance = balance * (1 + rate) + monthly_deposit
    invested = principal + monthly_deposit * months
    return (f"След {years:g} години: {_money(balance)} (вложени {_money(invested)}, "
            f"печалба {_money(balance - invested)}).")


@jarvis_tool
def vat_calculator(amount: float, includes_vat: bool = False, rate: float = 20) -> str:
    """ДДС: добавя или изважда данъка от сума. Стандартната ставка в България е 20%.

    Args:
        amount: Сумата.
        includes_vat: true — сумата е С ДДС (изчисли без), false — БЕЗ ДДС (изчисли с).
        rate: Ставката в проценти (по подразбиране 20).
    """
    if includes_vat:
        net = amount / (1 + rate / 100)
        return f"{_money(amount)} с ДДС = {_money(net)} без ДДС + {_money(amount - net)} ДДС ({rate:g}%)."
    return f"{_money(amount)} без ДДС = {_money(amount * (1 + rate / 100))} с ДДС ({_money(amount * rate / 100)} данък)."


@jarvis_tool
def discount_price(price: float, discount_percent: float) -> str:
    """Цена след отстъпка и колко спестявате.

    Args:
        price: Началната цена.
        discount_percent: Отстъпката в проценти.
    """
    saved = price * discount_percent / 100
    return f"С {discount_percent:g}% отстъпка: {_money(price - saved)} (спестявате {_money(saved)})."


@jarvis_tool
def savings_goal(goal: float, months: int, already_saved: float = 0) -> str:
    """Колко да спестявате на месец, за да съберете сума до срок.

    Args:
        goal: Целта, напр. 5000.
        months: За колко месеца.
        already_saved: Колко вече имате.
    """
    left = max(0.0, goal - already_saved)
    return f"Трябват Ви още {_money(left)} — по {_money(left / max(1, months))} на месец за {months} месеца."


@jarvis_tool
def fuel_cost(distance_km: float, consumption_per_100km: float, price_per_liter: float, people: int = 1) -> str:
    """Колко струва горивото за пътуване (и на човек, ако сте няколко).

    Args:
        distance_km: Разстоянието в километри.
        consumption_per_100km: Разход в литри на 100 км, напр. 6.5.
        price_per_liter: Цена на литър.
        people: Между колко души се дели.
    """
    liters = distance_km * consumption_per_100km / 100
    cost = liters * price_per_liter
    share = f", по {_money(cost / people)} на човек" if people > 1 else ""
    return f"{liters:.1f} литра гориво за {distance_km:g} км — {_money(cost)}{share}."


@jarvis_tool
def bmi_calculator(weight_kg: float, height_cm: float) -> str:
    """Индекс на телесната маса (ИТМ) и какво значи.

    Args:
        weight_kg: Тегло в килограми.
        height_cm: Ръст в сантиметри.
    """
    bmi = weight_kg / (height_cm / 100) ** 2
    label = ("поднормено тегло" if bmi < 18.5 else "нормално тегло" if bmi < 25
             else "наднормено тегло" if bmi < 30 else "затлъстяване")
    low, high = 18.5 * (height_cm / 100) ** 2, 24.9 * (height_cm / 100) ** 2
    return f"ИТМ {bmi:.1f} — {label}. Нормалното тегло за този ръст е {low:.0f}–{high:.0f} кг."
