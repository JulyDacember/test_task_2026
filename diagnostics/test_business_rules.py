"""
Интеграционные тесты бизнес-правил синхронизации.

Запуск:
    export TEST_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@localhost:5432/crm_test'
    python -m unittest discover -s diagnostics -p 'test_*.py' -v

Тесты работают с PostgreSQL, поскольку модель использует JSONB и оператор @>.
Имя тестовой базы должно содержать слово 'test'.
"""

import os
import unittest
from unittest.mock import patch
from urllib.parse import urlparse

from flask import Flask

from models import db, AbstractCustomer
from amocrm import Customer, Lead
from abstract_customer import (
    create_or_update_customer,
    get_abccustomer_by_lead_login,
    get_abccustomer_by_amocustomer_login,
)
import main


# ---------------------------------------------------------
# Вспомогательные функции для создания тестовых сущностей
# ---------------------------------------------------------

def fake_customer(
    entity_id=1,
    name="Покупатель",
    login="user_1",
    contacts=None,
    companies=None,
):
    customer = Customer(
        id=entity_id,
        name=name,
        next_price=None,
        next_date=None,
        responsible_user_id=None,
        status_id=None,
        periodicity=None,
        created_by=None,
        updated_by=None,
        created_at=None,
        updated_at=None,
        closest_task_at=None,
        is_deleted=False,
        ltv=None,
        purchases_count=None,
        average_check=None,
        account_id=None,
        custom_fields_values=(
            {} if login is None else {"Логин": {"value": login}}
        ),
        _embedded={
            "contacts": contacts or [],
            "companies": companies or [],
        },
    )

    # В исходном проекте метод as_dict отсутствует.
    # Добавляем его только для тестовых объектов.
    customer.as_dict = lambda: {
        "id": customer.id,
        "name": customer.name,
        "custom_fields_values": customer.custom_fields_values,
    }

    return customer


def fake_lead(
    entity_id=101,
    name="Сделка",
    login="user_1",
    contacts=None,
):
    lead = Lead(
        id=entity_id,
        name=name,
        custom_fields_values=(
            {} if login is None else {"Логин": {"value": login}}
        ),
        _embedded={"contacts": contacts or []},
    )

    lead.contacts = contacts or []

    # В исходном проекте метод as_dict отсутствует.
    lead.as_dict = lambda: {
        "id": lead.id,
        "name": lead.name,
        "custom_fields_values": lead.custom_fields_values,
    }

    return lead


# ---------------------------------------------------------
# Интеграционные тесты
# ---------------------------------------------------------

class BusinessRulesTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        database_url = (
            os.getenv("TEST_DATABASE_URL")
            or os.getenv("DATABASE_URL")
        )

        if not database_url:
            raise RuntimeError(
                "Укажи TEST_DATABASE_URL для отдельной PostgreSQL-базы"
            )

        database_name = urlparse(database_url).path.lstrip("/")

        if "test" not in database_name.lower():
            raise RuntimeError(
                f"Отказ от запуска: база '{database_name}' "
                "не выглядит тестовой. Используй отдельную БД, "
                "например crm_test."
            )

        cls.app = Flask(__name__)

        cls.app.config.update(
            SQLALCHEMY_DATABASE_URI=database_url,
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            TESTING=True,
        )

        db.init_app(cls.app)

        with cls.app.app_context():
            db.create_all()

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()

        db.session.rollback()
        db.session.query(AbstractCustomer).delete()
        db.session.commit()

    def tearDown(self):
        db.session.rollback()
        db.session.remove()
        self.context.pop()

    # -----------------------------------------------------
    # Вспомогательные методы
    # -----------------------------------------------------

    def add_record(
        self,
        customers=None,
        leads=None,
        contacts=None,
        companies=None,
    ):
        record = AbstractCustomer(
            amo_customers=customers or [],
            amo_leads=leads or [],
            amo_contacts=contacts or [],
            amo_companies=companies or [],
        )

        db.session.add(record)
        db.session.flush()

        return record

    @staticmethod
    def customer_json(entity_id, login, name="Покупатель"):
        return {
            "general": {
                "id": entity_id,
                "login": login,
                "name": name,
            },
            "api_value": {},
        }

    @staticmethod
    def lead_json(entity_id, login, name="Сделка"):
        return {
            "general": {
                "id": entity_id,
                "login": login,
                "name": name,
            },
            "api_value": {},
        }

    # -----------------------------------------------------
    # 1. Покупатель без логина пропускается
    # -----------------------------------------------------

    def test_01_customer_without_login_is_skipped(self):
        customer = fake_customer(1, login=None)

        with patch.object(
            main,
            "amocrm_get",
            side_effect=[[customer], []],
        ):
            main.collect_leads_customers(is_full=False)

        self.assertEqual(
            db.session.query(AbstractCustomer).count(),
            0,
        )

    # -----------------------------------------------------
    # 2. Покупатель находится по CRM ID и обновляется
    # -----------------------------------------------------

    def test_02_customer_is_found_by_crm_id_and_updated(self):
        record = self.add_record(
            customers=[
                self.customer_json(1, "old_login")
            ]
        )

        updated_customer = fake_customer(
            1,
            name="Новое имя",
            login="new_login",
        )

        result = create_or_update_customer(
            record,
            updated_customer,
        )

        db.session.flush()
        db.session.refresh(result)

        self.assertEqual(result.id, record.id)

        self.assertEqual(
            result.amo_customers[0]["general"]["login"],
            "new_login",
        )

    # -----------------------------------------------------
    # 3. Покупатель находится по логину среди сохранённых сделок
    # -----------------------------------------------------

    def test_03_customer_fallback_finds_saved_lead_by_login(self):
        record = self.add_record(
            leads=[
                self.lead_json(101, "shared_login")
            ]
        )

        found = get_abccustomer_by_lead_login("shared_login")

        self.assertIsNotNone(found)
        self.assertEqual(found.id, record.id)

    # -----------------------------------------------------
    # 4. Неоднозначное совпадение логина игнорируется
    # -----------------------------------------------------

    def test_04_ambiguous_login_match_is_ignored(self):
        self.add_record(
            leads=[
                self.lead_json(101, "duplicate")
            ]
        )

        self.add_record(
            leads=[
                self.lead_json(102, "duplicate")
            ]
        )

        found = get_abccustomer_by_lead_login("duplicate")

        self.assertIsNone(found)

    # -----------------------------------------------------
    # 5. Сделка находится по CRM ID и обновляется
    # -----------------------------------------------------

    def test_05_lead_is_found_by_crm_id_and_updated(self):
        record = self.add_record(
            leads=[
                self.lead_json(101, "old_login")
            ]
        )

        lead = fake_lead(
            101,
            name="Обновлённая сделка",
            login=None,
        )

        result = main.lead_action(lead)

        db.session.refresh(record)

        self.assertEqual(result.id, record.id)

        self.assertEqual(
            record.amo_leads[0]["general"]["name"],
            "Обновлённая сделка",
        )

    # -----------------------------------------------------
    # 6. Сделка находится по логину среди покупателей
    # -----------------------------------------------------

    def test_06_lead_fallback_finds_customer_by_login(self):
        record = self.add_record(
            customers=[
                self.customer_json(1, "shared_login")
            ]
        )

        found = get_abccustomer_by_amocustomer_login(
            "shared_login"
        )

        self.assertIsNotNone(found)
        self.assertEqual(found.id, record.id)

        result = main.lead_action(
            fake_lead(101, login="shared_login")
        )

        self.assertEqual(result.id, record.id)
        self.assertEqual(len(record.amo_leads), 1)

    # -----------------------------------------------------
    # 7. Конфликт совпадений: объединение в запись по ID сделки
    # -----------------------------------------------------

    def test_07_conflicting_matches_merge_into_lead_record(self):
        lead_record = self.add_record(
            leads=[
                self.lead_json(101, "lead_login")
            ]
        )

        customer_record = self.add_record(
            customers=[
                self.customer_json(1, "customer_login")
            ]
        )

        result = main.lead_action(
            fake_lead(101, login="customer_login")
        )

        self.assertIsNotNone(result)

        self.assertEqual(
            result.id,
            lead_record.id,
        )

        self.assertIsNone(
            db.session.get(
                AbstractCustomer,
                customer_record.id,
            )
        )

        self.assertEqual(
            len(lead_record.amo_customers),
            1,
        )

    # -----------------------------------------------------
    # 8. Если совпадений нет, создаётся новая запись
    # -----------------------------------------------------

    def test_08_unmatched_lead_creates_new_record(self):
        result = main.lead_action(
            fake_lead(999, login=None)
        )

        self.assertIsNotNone(result)

        self.assertEqual(
            result.amo_leads[0]["general"]["id"],
            999,
        )

    # -----------------------------------------------------
    # 9. При полной синхронизации отсутствующие покупатели удаляются
    # -----------------------------------------------------

    def test_09_full_sync_deletes_customer_absent_from_export(self):
        self.add_record(
            customers=[
                self.customer_json(77, "old")
            ]
        )

        with patch.object(
            main,
            "amocrm_get",
            side_effect=[[], []],
        ):
            main.collect_leads_customers(is_full=True)

        self.assertEqual(
            db.session.query(AbstractCustomer).count(),
            0,
        )

    # -----------------------------------------------------
    # 10. Удаляются отсутствующие вложенные сущности
    #     и сущности с названием "удалить"
    # -----------------------------------------------------

    def test_10_full_sync_removes_missing_and_marked_entities(self):
        record = self.add_record(
            leads=[
                self.lead_json(
                    101,
                    "present",
                    "Обычная сделка",
                ),
                self.lead_json(
                    102,
                    "old",
                    "Сделка удалить",
                ),
            ]
        )

        main.filter_merge_abstract_customer(
            record,
            "amo_leads",
            [101],
        )

        db.session.refresh(record)

        actual_ids = [
            item["general"]["id"]
            for item in record.amo_leads
        ]

        self.assertEqual(actual_ids, [101])

    # -----------------------------------------------------
    # 11. При прерывании синхронизации очистка не запускается
    # -----------------------------------------------------

    def test_11_interrupted_collection_does_not_run_cleanup(self):
        record = self.add_record(
            customers=[
                self.customer_json(77, "old")
            ]
        )

        lead = fake_lead(101, login=None)

        with patch.object(
            main,
            "amocrm_get",
            side_effect=[[], [lead]],
        ), patch.object(
            main,
            "lead_action",
            side_effect=RuntimeError("simulated failure"),
        ):
            main.collect_leads_customers(is_full=True)

        self.assertIsNotNone(
            db.session.get(
                AbstractCustomer,
                record.id,
            )
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)