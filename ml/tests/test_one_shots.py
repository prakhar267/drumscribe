import json

from drumscribe_ml.one_shots import audit_one_shot_catalog


def test_one_shot_audit_requires_license_and_reports_class_coverage(tmp_path):
    library = tmp_path / "library"
    samples = library / "source/samples/tambourine"
    samples.mkdir(parents=True)
    (samples / "one.wav").write_bytes(b"sample")
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "requiredClasses": ["TAMBOURINE"],
                "sources": [
                    {
                        "id": "rights-cleared",
                        "license": {
                            "identifier": "CC0-1.0",
                            "url": "https://creativecommons.org/publicdomain/zero/1.0/",
                            "commercialUseAllowed": True,
                            "attribution": "Test fixture",
                        },
                        "mappings": [
                            {
                                "instrument": "TAMBOURINE",
                                "directory": "source/samples/tambourine",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    audit = audit_one_shot_catalog(catalog, library)
    assert audit["trainingReady"] is True
    assert audit["coverage"]["TAMBOURINE"]["sampleCount"] == 1
    assert len(audit["corpusSha256"]) == 64
