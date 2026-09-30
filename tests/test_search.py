from carecost.search import ProcedureSearch


def test_plain_language_and_code(repo):
    search = ProcedureSearch(repo.catalog())
    assert search.search("knee MRI")[0]["code"] == "73721"
    assert search.search("baby delivery")[0]["code"] == "59409"
    assert search.search("93000")[0]["code"] == "93000"
    assert search.search("") == []
    assert search.search("zzzyyxx") == []


def test_absent_exact_codes_and_known_aliases_do_not_return_unrelated_procedures():
    search = ProcedureSearch([{"code": "46255", "code_type": "CPT", "description": "Unrelated surgery"}])
    assert search.search("29881") == []
    assert search.search("meniscus surgery") == []
    assert search.search("torn meniscus procedure") == []


def test_numeric_hcpcs_label_enrichment_preserves_source_namespace():
    search = ProcedureSearch(
        [{"code": "77067", "code_type": "HCPCS", "description": "Mammogram Screen Bilat Digital"}]
    )
    result = search.search("mammogram")[0]
    assert result["code"] == "77067" and result["code_type"] == "HCPCS"
    assert result["name"] == "Screening mammogram, both breasts"
