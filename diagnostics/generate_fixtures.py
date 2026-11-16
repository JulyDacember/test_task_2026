import random
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FakeEntity:
    """
    Имитация сущности amoCRM для локального тестирования.

    Не обращается к API и не требует подключения к amoCRM.
    """

    id: int
    name: str
    custom_fields_values: dict = field(default_factory=dict)
    status_id: Optional[int] = None
    contacts: list = field(default_factory=list)
    companies: list = field(default_factory=list)

    def get_field(self, field_name):
        return self.custom_fields_values.get(
            field_name, {}
        ).get("value")

    def as_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "custom_fields_values": self.custom_fields_values,
        }


def make_entity(entity_id, name, login=None):
    fields = {}

    if login is not None:
        fields["Логин"] = {"value": login}

    return FakeEntity(
        id=entity_id,
        name=name,
        custom_fields_values=fields,
    )


def generate_fixtures(
    customers_count=1000,
    leads_count=2500,
    seed=42,
):
    """
    Генерирует покупателей и сделки с воспроизводимым результатом.

    seed позволяет получать одинаковые данные при каждом запуске.
    """

    random.seed(seed)

    customers = []
    leads = []

    # 1. Генерируем покупателей
    for i in range(1, customers_count + 1):

        # Каждый двадцатый покупатель без логина
        if i % 20 == 0:
            login = None
        else:
            login = f"user_{i}"

        customer = make_entity(
            entity_id=i,
            name=f"Покупатель {i}",
            login=login,
        )

        customers.append(customer)

    # 2. Генерируем сделки
    for i in range(1, leads_count + 1):

        lead_id = 100000 + i

        scenario = i % 10

        if scenario in (0, 1, 2, 3, 4, 5):
            # 60% сделок имеют логин существующего покупателя
            customer_id = random.randint(1, customers_count)
            login = f"user_{customer_id}"

        elif scenario == 6:
            # 10% сделок без логина
            login = None

        elif scenario == 7:
            # 10% сделок с неизвестным логином
            login = f"unknown_{i}"

        elif scenario == 8:
            # 10% сделок с потенциально неоднозначным логином
            login = "duplicate_login"

        else:
            # 10% сделок с отдельными логинами
            login = f"lead_user_{i}"

        lead = make_entity(
            entity_id=lead_id,
            name=f"Сделка {i}",
            login=login,
        )

        leads.append(lead)

    return customers, leads


if __name__ == "__main__":
    customers, leads = generate_fixtures()

    print("Тестовые данные созданы")
    print(f"Покупателей: {len(customers)}")
    print(f"Сделок: {len(leads)}")

    customers_without_login = sum(
        1 for customer in customers
        if not customer.get_field("Логин")
    )

    leads_without_login = sum(
        1 for lead in leads
        if not lead.get_field("Логин")
    )

    print(f"Покупателей без логина: {customers_without_login}")
    print(f"Сделок без логина: {leads_without_login}")