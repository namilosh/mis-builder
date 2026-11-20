# Copyright 2026 Namilosh
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo.exceptions import AccessError
from odoo.tests import common, new_test_user


class TestAccessRights(common.TransactionCase):
    """Reports are for accounting users only: invoicing-only users get no
    access, accounting readers can run and export reports, accountants
    manage report instances and accounting managers manage templates."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.report = cls.env["mis.report"].create(
            {
                "name": "access test report",
                "kpi_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "inc",
                            "description": "Income",
                            "expression": "-balp[('account_type', '=', 'income')]",
                        },
                    )
                ],
            }
        )
        cls.instance = cls.env["mis.report.instance"].create(
            {
                "name": "access test instance",
                "report_id": cls.report.id,
                "company_id": cls.company.id,
                "period_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "p1",
                            "mode": "fix",
                            "manual_date_from": "2026-01-01",
                            "manual_date_to": "2026-12-31",
                        },
                    )
                ],
            }
        )

        def user(login, groups):
            return new_test_user(
                cls.env,
                login=login,
                groups=groups,
                company_id=cls.company.id,
                company_ids=[(6, 0, cls.company.ids)],
            )

        cls.invoice_user = user("mis_invoice_only", "account.group_account_invoice")
        cls.readonly_user = user("mis_readonly", "account.group_account_readonly")
        cls.accountant = user("mis_accountant", "account.group_account_user")
        cls.manager = user("mis_manager", "account.group_account_manager")

    def _template_vals(self):
        return {
            "name": "new template",
            "kpi_ids": [(0, 0, {"name": "k", "description": "K", "expression": "1"})],
        }

    def test_invoice_only_user_has_no_access(self):
        self.assertFalse(self.invoice_user.has_group("account.group_account_readonly"))
        instance = self.instance.with_user(self.invoice_user)
        with self.assertRaises(AccessError):
            instance.read(["name"])
        with self.assertRaises(AccessError):
            instance.compute()
        with self.assertRaises(AccessError):
            self.report.with_user(self.invoice_user).read(["name"])

    def test_readonly_user_runs_and_exports(self):
        instance = self.instance.with_user(self.readonly_user)
        data = instance.compute()
        self.assertEqual(data["body"][0]["label"], "Income")
        drilldown_arg = data["body"][0]["cells"][0]["drilldown_arg"]
        action = instance.drilldown(drilldown_arg)
        self.assertEqual(action["res_model"], "account.move.line")
        self.assertTrue(instance.print_pdf())
        self.assertTrue(instance.export_xls())
        report_model = self.env["ir.actions.report"].with_user(self.readonly_user)
        html, __ = report_model._render_qweb_html(
            "mis_builder.report_mis_report_instance", instance.ids, data={"dummy": 1}
        )
        self.assertIn(b"Income", html)
        xlsx, fmt = report_model._render(
            "mis_builder.mis_report_instance_xlsx", instance.ids, data={"dummy": 1}
        )
        self.assertEqual(fmt, "xlsx")
        self.assertTrue(xlsx)
        self.env["add.mis.report.instance.dashboard.wizard"].with_user(
            self.readonly_user
        ).create(
            {
                "name": "dash",
                "dashboard_id": self.env.ref("board.open_board_my_dash_action").id,
            }
        )
        with self.assertRaises(AccessError):
            instance.write({"name": "changed"})
        with self.assertRaises(AccessError):
            self.env["mis.report.instance"].with_user(self.readonly_user).create(
                {"name": "ro", "report_id": self.report.id}
            )

    def test_accountant_manages_instances_not_templates(self):
        Instance = self.env["mis.report.instance"].with_user(self.accountant)
        instance = Instance.create(
            {
                "name": "accountant instance",
                "report_id": self.report.id,
                "company_id": self.company.id,
                "period_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "p",
                            "mode": "fix",
                            "manual_date_from": "2026-01-01",
                            "manual_date_to": "2026-06-30",
                        },
                    )
                ],
            }
        )
        instance.compute()
        instance.period_ids.write({"name": "renamed"})
        instance.unlink()
        with self.assertRaises(AccessError):
            self.env["mis.report"].with_user(self.accountant).create(
                self._template_vals()
            )
        with self.assertRaises(AccessError):
            self.report.with_user(self.accountant).write({"name": "changed"})

    def test_manager_manages_templates(self):
        report = (
            self.env["mis.report"].with_user(self.manager).create(self._template_vals())
        )
        report.kpi_ids.write({"description": "K2"})
        self.env["mis.report.style"].with_user(self.manager).create({"name": "st"})
        self.env["mis.report.instance"].with_user(self.manager).create(
            {"name": "manager instance", "report_id": report.id}
        )
