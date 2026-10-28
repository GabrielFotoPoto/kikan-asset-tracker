# Kikan - suivi des actifs et remise de materiel signee
# Copyright (C) 2026 Gabriel Chollet
# Developpe avec l'assistance d'une IA (Claude, Anthropic).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Tests de la retention : 30 jours, plus la premiere sauvegarde de chaque mois pendant 12 mois.

  docker run --rm --entrypoint python kikan-backup -m unittest /app/test_retention.py -v
"""
import datetime as dt
import unittest

from kikan_backup import parse_name, select_deletions


def name(d: dt.datetime) -> str:
    return d.strftime("kikan-%Y%m%d-%H%M%S.tar.gz.age")


NOW = dt.datetime(2026, 10, 29, 2, 0, 0)


def nightly(days: int, hour: int = 2) -> list[str]:
    return [name(NOW.replace(hour=hour) - dt.timedelta(days=i)) for i in range(days)]


class Retention(unittest.TestCase):
    def test_nothing_to_delete_within_30_days(self):
        self.assertEqual(select_deletions(nightly(30), NOW), [])

    def test_unparsable_names_are_never_deleted(self):
        names = nightly(5) + ["notes.txt", "kikan-bad.tar.gz.age", "kikan-20260101-000000.tar.gz.age.sha256"]
        self.assertEqual(select_deletions(names, NOW), [])

    def test_empty(self):
        self.assertEqual(select_deletions([], NOW), [])

    def test_old_nightlies_deleted_but_first_of_month_kept(self):
        names = nightly(120)                      # 120 nuits d'affilee
        deleted = set(select_deletions(names, NOW))
        kept = set(names) - deleted
        for n in nightly(30):                      # tout ce qui a moins de 30 jours est garde
            self.assertIn(n, kept)
        firsts = {name(dt.datetime(2026, 7, 2, 2)), name(dt.datetime(2026, 8, 1, 2)), name(dt.datetime(2026, 9, 1, 2))}   # premiere de chaque mois (la serie commence le 2 juillet)
        self.assertTrue(firsts <= kept, firsts - kept)
        # une sauvegarde ordinaire de plus de 30 jours (hors premiere du mois) est supprimee
        self.assertIn(name(dt.datetime(2026, 8, 15, 2)), deleted)
        self.assertIn(name(dt.datetime(2026, 9, 10, 2)), deleted)

    def test_monthly_kept_for_a_year_only(self):
        # une sauvegarde par mois depuis 20 mois
        names = []
        y, m = 2025, 3
        for _ in range(20):
            names.append(name(dt.datetime(y, m, 1, 2)))
            m += 1
            if m > 12:
                y, m = y + 1, 1
        deleted = set(select_deletions(names + nightly(3), NOW))
        self.assertIn(name(dt.datetime(2025, 3, 1, 2)), deleted)          # plus d'un an : supprimee
        self.assertNotIn(name(dt.datetime(2026, 4, 1, 2)), deleted)       # 6 mois : gardee
        self.assertNotIn(name(dt.datetime(2025, 10, 1, 2)), deleted)      # 12 mois : gardee
        self.assertIn(name(dt.datetime(2025, 9, 1, 2)), deleted)          # 13 mois : supprimee

    def test_newest_is_never_deleted_even_if_very_old(self):
        names = [name(dt.datetime(2020, 5, 7, 2)), name(dt.datetime(2020, 5, 8, 2))]
        deleted = select_deletions(names, NOW)
        self.assertNotIn(names[1], deleted)       # la plus recente est toujours conservee
        self.assertIn(names[0], deleted)

    def test_first_of_month_is_the_earliest_of_that_month(self):
        names = [name(dt.datetime(2026, 7, 3, 2)), name(dt.datetime(2026, 7, 20, 2)), name(dt.datetime(2026, 7, 28, 2))] + nightly(2)
        deleted = set(select_deletions(names, NOW))
        self.assertNotIn(name(dt.datetime(2026, 7, 3, 2)), deleted)
        self.assertIn(name(dt.datetime(2026, 7, 20, 2)), deleted)
        self.assertIn(name(dt.datetime(2026, 7, 28, 2)), deleted)

    def test_custom_settings(self):
        names = nightly(10)
        deleted = select_deletions(names, NOW, keep_days=3, keep_months=0)
        # gardes : les 4 plus recentes (jusqu'a 3 jours) et la premiere du mois (20 octobre) ; supprimees : les 5 autres
        self.assertEqual(len(deleted), 5)
        self.assertNotIn(name(dt.datetime(2026, 10, 20, 2)), deleted)

    def test_parse_name(self):
        self.assertEqual(parse_name("kikan-20261029-020000.tar.gz.age"), dt.datetime(2026, 10, 29, 2, 0, 0))
        self.assertIsNone(parse_name("kikan-20261340-020000.tar.gz.age"))
        self.assertIsNone(parse_name("autre.age"))


if __name__ == "__main__":
    unittest.main()
