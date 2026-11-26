"""Runs last (zz): proves the suite did not modify production lead files."""


def test_production_lead_files_untouched(prod_fingerprint_before, current_prod_fingerprint):
    assert current_prod_fingerprint() == prod_fingerprint_before
